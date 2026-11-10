"""Patch generation service managing planning, patch proposals, persistence, and human review."""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.service import bug_detection_service
from app.core.config import settings
from app.core.logging import logger
from app.database.models import FixPlanModel, PatchProposalModel, PatchReviewModel
from app.database.session import AsyncSessionLocal, check_database_connection
from app.patch.graph import execute_patch_workflow
from app.patch.nodes.enrichment import enrich_context_node
from app.patch.nodes.impact import impact_analysis_node
from app.patch.nodes.planning import plan_fix_node
from app.patch.nodes.understanding import understand_issue_node
from app.patch.schemas import FixPlan, PatchProposal, PatchReview, ReviewDecision, ValidationDetail
from app.patch.state import AgentWorkflowState


class PatchService:
    """Manages fix plans, patch proposal lifecycles, and human reviews with dual persistence."""

    def __init__(self, storage_root: Optional[Path] = None):
        self._custom_storage_root = storage_root.resolve() if storage_root is not None else None

    @property
    def storage_root(self) -> Path:
        if self._custom_storage_root is not None:
            return self._custom_storage_root
        from app.repository.service import repository_service
        return repository_service.storage_root

    @storage_root.setter
    def storage_root(self, val: Optional[Path]) -> None:
        self._custom_storage_root = val.resolve() if val is not None else None

    def _get_repo_dir(self, repo_id: str) -> Path:
        return self.storage_root / repo_id

    def _get_plans_dir(self, repo_id: str) -> Path:
        d = self._get_repo_dir(repo_id) / "fix_plans"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _get_patches_dir(self, repo_id: str) -> Path:
        d = self._get_repo_dir(repo_id) / "patch_proposals"
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -------------------------------------------------------------
    # Local JSON Storage Helpers
    # -------------------------------------------------------------
    def _save_local_plan(self, plan: FixPlan) -> None:
        p_dir = self._get_plans_dir(plan.repository_id)
        file_path = p_dir / f"{plan.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(plan.model_dump(), f, indent=2)

    def _load_local_plan(self, repo_id: str, plan_id: str) -> Optional[FixPlan]:
        p_dir = self._get_plans_dir(repo_id)
        file_path = p_dir / f"{plan_id}.json"
        if not file_path.exists():
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return FixPlan.model_validate(json.load(f))
        except Exception:
            return None

    def _load_latest_local_plan_for_issue(self, repo_id: str, issue_id: str) -> Optional[FixPlan]:
        p_dir = self._get_plans_dir(repo_id)
        matching = []
        for p in p_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("issue_id") == issue_id:
                        matching.append(FixPlan.model_validate(data))
            except Exception:
                continue
        matching.sort(key=lambda x: x.created_at, reverse=True)
        return matching[0] if matching else None

    def _save_local_patch(self, proposal: PatchProposal) -> None:
        p_dir = self._get_patches_dir(proposal.repository_id)
        file_path = p_dir / f"{proposal.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(proposal.model_dump(), f, indent=2)

    def _load_local_patch(self, patch_id: str) -> Optional[PatchProposal]:
        # Search all repositories
        for repo_dir in self.storage_root.iterdir():
            if repo_dir.is_dir():
                candidate = repo_dir / "patch_proposals" / f"{patch_id}.json"
                if candidate.exists():
                    try:
                        with open(candidate, "r", encoding="utf-8") as f:
                            return PatchProposal.model_validate(json.load(f))
                    except Exception:
                        return None
        return None

    def _load_all_local_patches(self, repo_id: str) -> List[PatchProposal]:
        p_dir = self._get_patches_dir(repo_id)
        patches = []
        for p in p_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    patches.append(PatchProposal.model_validate(json.load(f)))
            except Exception:
                continue
        patches.sort(key=lambda x: x.created_at, reverse=True)
        return patches

    # -------------------------------------------------------------
    # Database Synchronization
    # -------------------------------------------------------------
    async def _sync_plan_to_db(self, plan: FixPlan) -> None:
        if not await check_database_connection():
            return
        try:
            async with AsyncSessionLocal() as session:
                model = FixPlanModel(
                    id=plan.id,
                    issue_id=plan.issue_id,
                    repository_id=plan.repository_id,
                    summary=plan.summary,
                    root_cause=plan.root_cause,
                    proposed_solution=plan.proposed_solution,
                    implementation_steps=plan.implementation_steps,
                    affected_files=plan.affected_files,
                    impact_report=plan.impact_report,
                    risk_level=plan.risk_level,
                    expected_behavior=plan.expected_behavior,
                    recommended_tests=plan.recommended_tests,
                    created_at=datetime.fromisoformat(plan.created_at),
                )
                await session.merge(model)
                await session.commit()
        except Exception as e:
            logger.warning("Database sync warning for fix plan '%s': %s", plan.id, e)

    async def _sync_patch_to_db(self, proposal: PatchProposal) -> None:
        if not await check_database_connection():
            return
        try:
            async with AsyncSessionLocal() as session:
                model = PatchProposalModel(
                    id=proposal.id,
                    repository_id=proposal.repository_id,
                    issue_id=proposal.issue_id,
                    fix_plan_id=proposal.fix_plan_id,
                    patch_content=proposal.patch_content,
                    affected_files=proposal.affected_files,
                    original_snippets=proposal.original_snippets,
                    modified_snippets=proposal.modified_snippets,
                    lines_added=proposal.lines_added,
                    lines_removed=proposal.lines_removed,
                    confidence_score=proposal.confidence_score,
                    risk_level=proposal.risk_level,
                    validation_status=proposal.validation_status,
                    validation_details=proposal.validation_details,
                    review_status=proposal.review_status,
                    workflow_status=proposal.workflow_status,
                    regeneration_attempt=proposal.regeneration_attempt,
                    created_at=datetime.fromisoformat(proposal.created_at),
                    updated_at=datetime.fromisoformat(proposal.updated_at),
                )
                await session.merge(model)
                await session.commit()
        except Exception as e:
            logger.warning("Database sync warning for patch '%s': %s", proposal.id, e)

    # -------------------------------------------------------------
    # Core Operations
    # -------------------------------------------------------------
    def _find_issue(self, repo_id: str, issue_id: str) -> Optional[Dict[str, Any]]:
        """Finds target issue from BugDetectionService storage."""
        issues_res = bug_detection_service.get_issues(repo_id)
        for iss in issues_res.issues:
            if iss.issue_id == issue_id:
                return iss.model_dump()
        return None

    async def create_fix_plan(self, repository_id: str, issue_id: str) -> FixPlan:
        """Executes issue understanding, context enrichment, and fix planning nodes."""
        logger.info("[PatchService] Generating fix plan for repository '%s', issue '%s'...", repository_id, issue_id)
        start_time = time.time()

        issue_data = self._find_issue(repository_id, issue_id)
        if not issue_data:
            raise ValueError(f"Issue '{issue_id}' not found in repository '{repository_id}'.")

        state: AgentWorkflowState = {
            "repository_id": repository_id,
            "issue_id": issue_id,
            "issue_data": issue_data,
            "target_file_path": issue_data.get("file_path"),
            "workflow_status": "understanding_issue",
        }

        # Step 1: Understand issue
        s1_t0 = time.time()
        logger.info("[PatchService] [Step 1/4] Executing issue understanding for '%s'...", issue_id)
        res1 = await understand_issue_node(state)
        state.update(res1)
        s1_elapsed = time.time() - s1_t0
        logger.info("[PatchService] [Step 1/4] Issue understanding finished in %.2fs (status: %s)", s1_elapsed, state.get("workflow_status"))
        if state.get("workflow_status") in ("issue_outdated", "failed"):
            raise ValueError(state.get("error_details") or "Failed to verify issue against source code.")

        # Step 2: Context enrichment
        s2_t0 = time.time()
        logger.info("[PatchService] [Step 2/4] Executing context enrichment (AST + RAG)...")
        res2 = await enrich_context_node(state)
        state.update(res2)
        s2_elapsed = time.time() - s2_t0
        logger.info("[PatchService] [Step 2/4] Context enrichment finished in %.2fs", s2_elapsed)

        # Step 3: Plan fix
        s3_t0 = time.time()
        logger.info("[PatchService] [Step 3/4] Executing AI fix planning...")
        res3 = await plan_fix_node(state)
        state.update(res3)
        s3_elapsed = time.time() - s3_t0
        logger.info("[PatchService] [Step 3/4] AI fix planning finished in %.2fs", s3_elapsed)
        if state.get("workflow_status") == "failed":
            raise RuntimeError(state.get("error_details") or "AI Fix Planning failed.")

        # Step 4: Impact analysis
        s4_t0 = time.time()
        logger.info("[PatchService] [Step 4/4] Executing impact analysis...")
        res4 = await impact_analysis_node(state)
        state.update(res4)
        s4_elapsed = time.time() - s4_t0
        logger.info("[PatchService] [Step 4/4] Impact analysis finished in %.2fs", s4_elapsed)

        plan_dict = state["fix_plan"]
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        plan = FixPlan(
            id=plan_id,
            issue_id=issue_id,
            repository_id=repository_id,
            summary=plan_dict.get("summary", "Automated Remediation Plan"),
            root_cause=plan_dict.get("root_cause", ""),
            proposed_solution=plan_dict.get("proposed_solution", ""),
            implementation_steps=plan_dict.get("implementation_steps", []),
            affected_files=plan_dict.get("affected_files", []),
            impact_report=plan_dict.get("impact_report", {}),
            risk_level=plan_dict.get("risk_level", "Low"),
            expected_behavior=plan_dict.get("expected_behavior", ""),
            recommended_tests=plan_dict.get("recommended_tests", []),
            created_at=now,
        )

        self._save_local_plan(plan)
        await self._sync_plan_to_db(plan)

        total_elapsed = time.time() - start_time
        logger.info(
            "[PatchService] Fix plan '%s' created for issue '%s' in %.2fs (Risk: %s).",
            plan_id,
            issue_id,
            total_elapsed,
            plan.risk_level,
        )
        return plan

    async def get_fix_plan(self, repository_id: str, issue_id: str) -> Optional[FixPlan]:
        """Retrieves existing fix plan for an issue."""
        local = self._load_latest_local_plan_for_issue(repository_id, issue_id)
        if local:
            return local

        if await check_database_connection():
            try:
                async with AsyncSessionLocal() as session:
                    stmt = (
                        select(FixPlanModel)
                        .where(FixPlanModel.repository_id == repository_id)
                        .where(FixPlanModel.issue_id == issue_id)
                        .order_by(FixPlanModel.created_at.desc())
                        .limit(1)
                    )
                    res = await session.execute(stmt)
                    m = res.scalar_one_or_none()
                    if m:
                        return FixPlan.model_validate(m.to_dict())
            except Exception:
                pass
        return None

    async def generate_patch_proposal(
        self,
        repository_id: str,
        issue_id: str,
        feedback: Optional[str] = None,
    ) -> PatchProposal:
        """Executes full LangGraph patch synthesis workflow and stores the patch proposal."""
        issue_data = self._find_issue(repository_id, issue_id)
        if not issue_data:
            raise ValueError(f"Issue '{issue_id}' not found in repository '{repository_id}'.")

        # Load or create fix plan
        fix_plan = await self.get_fix_plan(repository_id, issue_id)
        if not fix_plan:
            fix_plan = await self.create_fix_plan(repository_id, issue_id)

        initial_state: AgentWorkflowState = {
            "repository_id": repository_id,
            "issue_id": issue_id,
            "issue_data": issue_data,
            "target_file_path": issue_data.get("file_path"),
            "fix_plan": fix_plan.model_dump(),
            "human_feedback": feedback,
            "regeneration_count": 0,
            "max_regenerations": 2,
            "workflow_status": "starting",
        }

        # Run LangGraph Workflow
        logger.info("[PatchService] Executing LangGraph patch generation workflow for '%s'...", issue_id)
        wf_t0 = time.time()
        final_state = await execute_patch_workflow(initial_state)
        wf_elapsed = time.time() - wf_t0
        logger.info("[PatchService] LangGraph workflow finished in %.2fs (status: %s)", wf_elapsed, final_state.get("workflow_status"))

        workflow_status = final_state.get("workflow_status", "failed")
        if workflow_status == "failed" or workflow_status == "issue_outdated":
            err = final_state.get("error_details") or "Patch generation workflow failed."
            raise RuntimeError(err)

        val_results = final_state.get("validation_results") or {}
        val_status = "valid" if val_results.get("is_valid") else "invalid"

        patch_id = f"patch_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        risk = final_state.get("risk_assessment") or {}

        proposal = PatchProposal(
            id=patch_id,
            repository_id=repository_id,
            issue_id=issue_id,
            fix_plan_id=fix_plan.id,
            patch_content=final_state.get("generated_patches") or "",
            affected_files=list((final_state.get("modified_snippets") or {}).keys()) or [issue_data.get("file_path", "")],
            original_snippets=final_state.get("original_snippets") or {},
            modified_snippets=final_state.get("modified_snippets") or {},
            lines_added=final_state.get("lines_added", 0),
            lines_removed=final_state.get("lines_removed", 0),
            confidence_score=final_state.get("confidence_score", 0.8),
            risk_level=risk.get("risk_level", fix_plan.risk_level),
            validation_status=val_status,
            validation_details=val_results,
            review_status="pending_review",
            workflow_status=workflow_status,
            regeneration_attempt=final_state.get("regeneration_count", 0),
            created_at=now,
            updated_at=now,
        )

        self._save_local_patch(proposal)
        await self._sync_patch_to_db(proposal)

        logger.info("Patch proposal '%s' successfully generated (Status: %s, Risk: %s).", patch_id, val_status, proposal.risk_level)
        return proposal

    async def list_patches(self, repository_id: str) -> List[PatchProposal]:
        """Lists all patch proposals for a repository."""
        patches = self._load_all_local_patches(repository_id)
        if patches:
            return patches

        if await check_database_connection():
            try:
                async with AsyncSessionLocal() as session:
                    stmt = (
                        select(PatchProposalModel)
                        .where(PatchProposalModel.repository_id == repository_id)
                        .order_by(PatchProposalModel.created_at.desc())
                    )
                    res = await session.execute(stmt)
                    models = res.scalars().all()
                    return [PatchProposal.model_validate(m.to_dict()) for m in models]
            except Exception:
                pass
        return []

    async def get_patch(self, patch_id: str) -> Optional[PatchProposal]:
        """Retrieves a single patch proposal by ID."""
        local = self._load_local_patch(patch_id)
        if local:
            return local

        if await check_database_connection():
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(PatchProposalModel).where(PatchProposalModel.id == patch_id)
                    res = await session.execute(stmt)
                    m = res.scalar_one_or_none()
                    if m:
                        return PatchProposal.model_validate(m.to_dict())
            except Exception:
                pass
        return None

    async def get_patch_diff(self, patch_id: str) -> Optional[str]:
        """Returns the raw unified-diff string for a patch proposal."""
        patch = await self.get_patch(patch_id)
        return patch.patch_content if patch else None

    async def review_patch(
        self,
        patch_id: str,
        decision: ReviewDecision,
        feedback: Optional[str] = None,
    ) -> PatchProposal:
        """Records a human review decision (approved/rejected/regeneration_requested)."""
        patch = await self.get_patch(patch_id)
        if not patch:
            raise ValueError(f"Patch proposal '{patch_id}' not found.")

        now = datetime.now(timezone.utc).isoformat()
        if decision == "approved":
            patch.review_status = "approved"
            patch.workflow_status = "approved"
        elif decision == "rejected":
            patch.review_status = "rejected"
            patch.workflow_status = "rejected"
        elif decision == "regeneration_requested":
            patch.review_status = "pending_review"
            patch.workflow_status = "regeneration_requested"

        patch.updated_at = now

        # Save review record
        review_id = f"rev_{uuid.uuid4().hex[:12]}"
        review = PatchReview(
            id=review_id,
            patch_id=patch_id,
            decision=decision,
            reviewer_feedback=feedback,
            reviewed_at=now,
        )

        self._save_local_patch(patch)
        await self._sync_patch_to_db(patch)

        # Save review to DB
        if await check_database_connection():
            try:
                async with AsyncSessionLocal() as session:
                    m = PatchReviewModel(
                        id=review.id,
                        patch_id=review.patch_id,
                        decision=review.decision,
                        reviewer_feedback=review.reviewer_feedback,
                        reviewed_at=datetime.fromisoformat(review.reviewed_at),
                    )
                    session.add(m)
                    await session.commit()
            except Exception as e:
                logger.warning("Failed to save patch review to DB: %s", e)

        logger.info("Patch '%s' reviewed: decision=%s", patch_id, decision)
        return patch

    async def regenerate_patch(self, patch_id: str, feedback: Optional[str] = None) -> PatchProposal:
        """Regenerates a patch proposal incorporating human reviewer feedback."""
        existing = await self.get_patch(patch_id)
        if not existing:
            raise ValueError(f"Patch proposal '{patch_id}' not found.")

        # Trigger generation with user feedback
        proposal = await self.generate_patch_proposal(
            repository_id=existing.repository_id,
            issue_id=existing.issue_id,
            feedback=feedback,
        )
        return proposal

    async def get_workflow_status(self, patch_id: str) -> Dict[str, Any]:
        """Returns the current workflow status of a patch proposal."""
        patch = await self.get_patch(patch_id)
        if not patch:
            raise ValueError(f"Patch proposal '{patch_id}' not found.")

        return {
            "patch_id": patch.id,
            "repository_id": patch.repository_id,
            "issue_id": patch.issue_id,
            "status": patch.workflow_status,
            "review_status": patch.review_status,
            "validation_status": patch.validation_status,
            "regeneration_attempt": patch.regeneration_attempt,
            "risk_level": patch.risk_level,
            "lines_added": patch.lines_added,
            "lines_removed": patch.lines_removed,
        }


patch_service = PatchService()
