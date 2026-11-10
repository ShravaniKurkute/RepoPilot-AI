"""Sandbox execution service managing validation runs, dual persistence, and report retrieval."""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import select
from app.core.config import settings
from app.core.logging import logger
from app.database.models import SandboxExecutionModel
from app.database.session import AsyncSessionLocal, check_database_connection
from app.patch.service import patch_service
from app.repository.service import repository_service
from app.sandbox.runner import sandbox_runner
from app.sandbox.schemas import (
    BeforeAfterComparison,
    ExecutionReportResponse,
    ExecutionStatus,
    ExecutionVerdict,
    SandboxExecution,
    SandboxExecutionRequest,
    TestRunResult,
)


class SandboxExecutionService:
    """Manages patch execution runs in Docker sandboxes with local and database persistence."""

    def __init__(self, storage_root: Optional[Path] = None):
        self._custom_storage_root = storage_root

    @property
    def storage_root(self) -> Path:
        if self._custom_storage_root is not None:
            return self._custom_storage_root
        return repository_service.storage_root

    def _get_executions_dir(self, repository_id: str) -> Path:
        p = self.storage_root / repository_id / "sandbox_executions"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _save_local_execution(self, execution: SandboxExecution) -> None:
        exec_dir = self._get_executions_dir(execution.repository_id)
        file_path = exec_dir / f"{execution.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(execution.model_dump(), f, indent=2)

    def _load_local_execution(self, execution_id: str) -> Optional[SandboxExecution]:
        # Search all repositories
        for repo_dir in self.storage_root.iterdir():
            if repo_dir.is_dir():
                candidate = repo_dir / "sandbox_executions" / f"{execution_id}.json"
                if candidate.exists():
                    try:
                        with open(candidate, "r", encoding="utf-8") as f:
                            return SandboxExecution.model_validate(json.load(f))
                    except Exception:
                        return None
        return None

    def _load_all_local_executions(self, repository_id: str) -> List[SandboxExecution]:
        exec_dir = self._get_executions_dir(repository_id)
        executions = []
        for p in exec_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    executions.append(SandboxExecution.model_validate(json.load(f)))
            except Exception:
                continue
        executions.sort(key=lambda x: x.created_at, reverse=True)
        return executions

    # -------------------------------------------------------------
    # Database Synchronization
    # -------------------------------------------------------------
    async def _sync_execution_to_db(self, execution: SandboxExecution) -> None:
        if not await check_database_connection():
            return
        try:
            async with AsyncSessionLocal() as session:
                model = SandboxExecutionModel(
                    id=execution.id,
                    repository_id=execution.repository_id,
                    patch_id=execution.patch_id,
                    status=execution.status.value if hasattr(execution.status, "value") else str(execution.status),
                    language=execution.language,
                    container_id=execution.container_id,
                    patch_applied=1 if execution.patch_applied else 0,
                    modified_files=execution.modified_files,
                    dependencies_installed=1 if execution.dependencies_installed else 0,
                    baseline_result=execution.baseline_result.model_dump() if execution.baseline_result else None,
                    patched_result=execution.patched_result.model_dump() if execution.patched_result else None,
                    comparison=execution.comparison.model_dump() if execution.comparison else None,
                    duration_seconds=execution.duration_seconds,
                    logs=execution.logs,
                    error_message=execution.error_message,
                    created_at=datetime.fromisoformat(execution.created_at),
                    completed_at=datetime.fromisoformat(execution.completed_at) if execution.completed_at else None,
                )
                await session.merge(model)
                await session.commit()
        except Exception as e:
            logger.warning("[SandboxService] Database sync warning for execution '%s': %s", execution.id, e)

    # -------------------------------------------------------------
    # Execution Lifecycle Operations
    # -------------------------------------------------------------
    async def execute_patch(
        self,
        repository_id: str,
        patch_id: str,
        request: Optional[SandboxExecutionRequest] = None,
    ) -> SandboxExecution:
        """Initiates containerized sandbox execution for a patch proposal."""
        req = request or SandboxExecutionRequest()
        logger.info("[SandboxService] Requesting execution for patch '%s' on repository '%s'...", patch_id, repository_id)

        # 1. Retrieve patch proposal
        patch = await patch_service.get_patch(patch_id)
        if not patch:
            raise ValueError(f"Patch proposal '{patch_id}' not found.")

        # Ensure repository IDs match
        if patch.repository_id != repository_id:
            raise ValueError(f"Patch proposal '{patch_id}' belongs to repository '{patch.repository_id}', not '{repository_id}'.")

        # 2. Determine primary repository language
        primary_lang = "python"
        try:
            repo_summary = repository_service.get_repository(repository_id)
            if repo_summary and repo_summary.languages:
                top_lang = repo_summary.languages[0].name.lower()
                if "javascript" in top_lang or "typescript" in top_lang or "node" in top_lang:
                    primary_lang = "javascript"
                else:
                    primary_lang = "python"
        except Exception:
            # Fallback check file extensions in patch
            if any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in patch.affected_files):
                primary_lang = "javascript"

        # 3. Create execution tracking instance
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        execution = SandboxExecution(
            id=execution_id,
            repository_id=repository_id,
            patch_id=patch_id,
            status=ExecutionStatus.PENDING,
            language=primary_lang,
            created_at=now,
        )

        self._save_local_execution(execution)
        await self._sync_execution_to_db(execution)

        # 4. Run through SandboxExecutionRunner
        final_execution = await sandbox_runner.execute(
            execution=execution,
            patch_diff=patch.patch_content,
            request=req,
        )

        # 5. Persist final state
        self._save_local_execution(final_execution)
        await self._sync_execution_to_db(final_execution)

        logger.info(
            "[SandboxService] Execution '%s' completed with status '%s' in %.2fs.",
            execution_id,
            final_execution.status,
            final_execution.duration_seconds,
        )
        return final_execution

    async def get_execution(self, execution_id: str) -> Optional[SandboxExecution]:
        """Retrieves an execution record by ID."""
        local = self._load_local_execution(execution_id)
        if local:
            return local

        if await check_database_connection():
            try:
                async with AsyncSessionLocal() as session:
                    stmt = select(SandboxExecutionModel).where(SandboxExecutionModel.id == execution_id)
                    res = await session.execute(stmt)
                    m = res.scalar_one_or_none()
                    if m:
                        return SandboxExecution.model_validate(m.to_dict())
            except Exception:
                pass
        return None

    async def get_execution_logs(self, execution_id: str) -> Optional[str]:
        """Retrieves raw execution logs for a run."""
        execution = await self.get_execution(execution_id)
        if not execution:
            return None
        return execution.logs

    async def get_execution_report(self, execution_id: str) -> Optional[ExecutionReportResponse]:
        """Retrieves structured before/after comparison report."""
        execution = await self.get_execution(execution_id)
        if not execution or not execution.comparison:
            return None

        return ExecutionReportResponse(
            execution_id=execution.id,
            repository_id=execution.repository_id,
            patch_id=execution.patch_id,
            status=execution.status,
            verdict=execution.comparison.verdict,
            comparison=execution.comparison,
            modified_files=execution.modified_files,
            duration_seconds=execution.duration_seconds,
            error_message=execution.error_message,
            created_at=execution.created_at,
            completed_at=execution.completed_at,
        )

    async def list_executions(self, repository_id: str) -> List[SandboxExecution]:
        """Lists all execution records for a repository."""
        return self._load_all_local_executions(repository_id)

    async def list_executions_for_patch(self, repository_id: str, patch_id: str) -> List[SandboxExecution]:
        """Lists all executions for a specific patch proposal."""
        all_execs = await self.list_executions(repository_id)
        return [e for e in all_execs if e.patch_id == patch_id]


sandbox_service = SandboxExecutionService()

