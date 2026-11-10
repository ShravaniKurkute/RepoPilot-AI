"""FastAPI router for Phase 5: Agentic Planning & Patch Generation."""

import asyncio
import time
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.core.logging import logger
from app.patch.schemas import (
    FixPlan,
    GeneratePatchRequest,
    PatchProposal,
    PatchProposalListResponse,
    PatchReviewRequest,
    RegeneratePatchRequest,
    WorkflowStatusResponse,
)
from app.patch.service import patch_service
from app.schemas.common import APIResponse

router = APIRouter(tags=["Phase 5: Agentic Planning & Patch Generation"])


# -----------------------------------------------------------------------------
# 1. Fix Plan Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/repositories/{repository_id}/issues/{issue_id}/fix-plan",
    response_model=APIResponse[FixPlan],
    status_code=status.HTTP_200_OK,
    summary="Generate Fix Plan for Issue",
    description="Invokes understanding, context enrichment, and planning agents to produce a structured remediation plan.",
)
async def create_fix_plan(
    repository_id: str,
    issue_id: str,
) -> APIResponse[FixPlan]:
    """Generates a structured remediation plan for a detected issue."""
    logger.info("[API FixPlan] POST request received for repository '%s', issue '%s'", repository_id, issue_id)
    t0 = time.time()
    try:
        plan = await asyncio.wait_for(
            patch_service.create_fix_plan(repository_id, issue_id),
            timeout=75.0,
        )
        elapsed = time.time() - t0
        logger.info("[API FixPlan] Successfully generated plan '%s' in %.2fs", plan.id, elapsed)
        return APIResponse(
            success=True,
            message=f"Fix plan '{plan.id}' generated successfully for issue '{issue_id}'.",
            data=plan,
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        logger.error("[API FixPlan] Request timed out after %.2fs for repository '%s', issue '%s'", elapsed, repository_id, issue_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Fix plan generation timed out after 75 seconds. The AI service took too long to respond. Please check Gemini API status or retry.",
        )
    except ValueError as e:
        logger.warning("[API FixPlan] Fix plan validation error for issue '%s': %s", issue_id, e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        elapsed = time.time() - t0
        err_msg = str(e)
        logger.exception("[API FixPlan] Fix plan generation failed after %.2fs for repository '%s', issue '%s': %s", elapsed, repository_id, issue_id, err_msg)
        is_quota = any(term in err_msg.lower() for term in ("429", "resource_exhausted", "quota", "limit exceeded"))
        status_code = status.HTTP_429_TOO_MANY_REQUESTS if is_quota else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to generate fix plan: {err_msg}",
        )


@router.get(
    "/repositories/{repository_id}/issues/{issue_id}/fix-plan",
    response_model=APIResponse[FixPlan],
    status_code=status.HTTP_200_OK,
    summary="Retrieve Fix Plan for Issue",
    description="Retrieves the latest structured fix plan created for an issue.",
)
async def get_fix_plan(
    repository_id: str,
    issue_id: str,
) -> APIResponse[FixPlan]:
    """Retrieves an existing fix plan for an issue."""
    plan = await patch_service.get_fix_plan(repository_id, issue_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No fix plan found for issue '{issue_id}' in repository '{repository_id}'.",
        )
    return APIResponse(
        success=True,
        message=f"Fix plan '{plan.id}' retrieved.",
        data=plan,
    )


# -----------------------------------------------------------------------------
# 2. Patch Proposal Generation & Listing Endpoints
# -----------------------------------------------------------------------------
@router.post(
    "/repositories/{repository_id}/issues/{issue_id}/generate-patch",
    response_model=APIResponse[PatchProposal],
    status_code=status.HTTP_200_OK,
    summary="Generate Unified-Diff Patch Proposal",
    description="Runs the full LangGraph agentic loop to synthesize, validate, and score a unified-diff patch proposal.",
)
async def generate_patch_proposal(
    repository_id: str,
    issue_id: str,
    body: Optional[GeneratePatchRequest] = None,
) -> APIResponse[PatchProposal]:
    """Generates a verified, context-aware unified diff patch proposal."""
    feedback = body.feedback if body else None
    logger.info("[API GeneratePatch] POST request received for repository '%s', issue '%s' (feedback: %s)", repository_id, issue_id, bool(feedback))
    t0 = time.time()
    try:
        proposal = await asyncio.wait_for(
            patch_service.generate_patch_proposal(
                repository_id=repository_id,
                issue_id=issue_id,
                feedback=feedback,
            ),
            timeout=90.0,
        )
        elapsed = time.time() - t0
        logger.info(
            "[API GeneratePatch] Successfully synthesized proposal '%s' in %.2fs (validation: %s)",
            proposal.id,
            elapsed,
            proposal.validation_status,
        )
        return APIResponse(
            success=True,
            message=f"Patch proposal '{proposal.id}' generated successfully with status '{proposal.validation_status}'.",
            data=proposal,
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        logger.error("[API GeneratePatch] Request timed out after %.2fs for repository '%s', issue '%s'", elapsed, repository_id, issue_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Patch synthesis workflow timed out after 90 seconds. The AI service took too long to complete.",
        )
    except ValueError as e:
        logger.warning("[API GeneratePatch] Patch proposal request error for issue '%s': %s", issue_id, e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        elapsed = time.time() - t0
        err_msg = str(e)
        logger.exception("[API GeneratePatch] Patch generation workflow failed after %.2fs for repository '%s', issue '%s': %s", elapsed, repository_id, issue_id, err_msg)
        is_quota = any(term in err_msg.lower() for term in ("429", "resource_exhausted", "quota", "limit exceeded"))
        status_code = status.HTTP_429_TOO_MANY_REQUESTS if is_quota else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(
            status_code=status_code,
            detail=f"Patch proposal generation failed: {err_msg}",
        )


@router.get(
    "/repositories/{repository_id}/patches",
    response_model=APIResponse[PatchProposalListResponse],
    status_code=status.HTTP_200_OK,
    summary="List Patch Proposals for Repository",
    description="Lists all patch proposals generated for the repository.",
)
async def list_patches(
    repository_id: str,
) -> APIResponse[PatchProposalListResponse]:
    """Returns all patch proposals generated for a given repository."""
    patches = await patch_service.list_patches(repository_id)
    return APIResponse(
        success=True,
        message=f"Retrieved {len(patches)} patch proposals for repository '{repository_id}'.",
        data=PatchProposalListResponse(
            repository_id=repository_id,
            total_patches=len(patches),
            patches=patches,
        ),
    )


# -----------------------------------------------------------------------------
# 3. Patch Inspection, Diff, Review, and Regeneration Endpoints
# -----------------------------------------------------------------------------
@router.get(
    "/patches/{patch_id}",
    response_model=APIResponse[PatchProposal],
    status_code=status.HTTP_200_OK,
    summary="Get Patch Proposal Details",
    description="Retrieves a patch proposal including affected files, snippets, and validation details.",
)
async def get_patch(patch_id: str) -> APIResponse[PatchProposal]:
    """Retrieves detailed information for a specific patch proposal."""
    patch = await patch_service.get_patch(patch_id)
    if not patch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch proposal '{patch_id}' not found.",
        )
    return APIResponse(
        success=True,
        message=f"Patch proposal '{patch_id}' retrieved.",
        data=patch,
    )


@router.get(
    "/patches/{patch_id}/diff",
    summary="Get Raw Unified Diff of Patch Proposal",
    description="Returns the raw unified diff text for a patch proposal.",
    responses={
        200: {
            "content": {"text/plain": {}, "application/json": {}},
            "description": "Raw unified-diff string or JSON object",
        }
    },
)
async def get_patch_diff(
    patch_id: str,
    format: Optional[str] = Query("raw", description="Return format: 'raw' for text/plain or 'json' for APIResponse"),
) -> Response:
    """Returns the unified-diff representation of a patch proposal."""
    diff = await patch_service.get_patch_diff(patch_id)
    if diff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patch proposal '{patch_id}' not found.",
        )

    if format == "json":
        return APIResponse(
            success=True,
            message="Patch diff retrieved.",
            data={"patch_id": patch_id, "diff": diff},
        )

    return PlainTextResponse(content=diff, media_type="text/x-diff")


@router.post(
    "/patches/{patch_id}/review",
    response_model=APIResponse[PatchProposal],
    status_code=status.HTTP_200_OK,
    summary="Record Human Review Decision",
    description="Submits an approval, rejection, or request for regeneration on a patch proposal.",
)
async def review_patch(
    patch_id: str,
    request: PatchReviewRequest,
) -> APIResponse[PatchProposal]:
    """Records human review decision (approved/rejected/regeneration_requested)."""
    try:
        updated_patch = await patch_service.review_patch(
            patch_id=patch_id,
            decision=request.decision,
            feedback=request.reviewer_feedback,
        )
        return APIResponse(
            success=True,
            message=f"Patch '{patch_id}' review recorded as '{request.decision}'.",
            data=updated_patch,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Failed to record review for patch '%s': %s", patch_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record review: {str(e)}",
        )


@router.post(
    "/patches/{patch_id}/regenerate",
    response_model=APIResponse[PatchProposal],
    status_code=status.HTTP_200_OK,
    summary="Regenerate Patch Proposal with Human Feedback",
    description="Triggers a new patch generation cycle incorporating human guidance or reviewer feedback.",
)
async def regenerate_patch(
    patch_id: str,
    body: Optional[RegeneratePatchRequest] = None,
) -> APIResponse[PatchProposal]:
    """Regenerates a patch proposal incorporating human feedback."""
    feedback = body.feedback if body else None
    logger.info("[API RegeneratePatch] Request received for patch '%s' (feedback: %s)", patch_id, bool(feedback))
    t0 = time.time()
    try:
        new_proposal = await asyncio.wait_for(
            patch_service.regenerate_patch(patch_id=patch_id, feedback=feedback),
            timeout=90.0,
        )
        elapsed = time.time() - t0
        logger.info("[API RegeneratePatch] Patch '%s' regenerated as '%s' in %.2fs", patch_id, new_proposal.id, elapsed)
        return APIResponse(
            success=True,
            message=f"Regenerated patch proposal '{new_proposal.id}' successfully.",
            data=new_proposal,
        )
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        logger.error("[API RegeneratePatch] Request timed out after %.2fs for patch '%s'", elapsed, patch_id)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Patch regeneration timed out after 90 seconds. The AI service took too long to complete.",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        elapsed = time.time() - t0
        err_msg = str(e)
        logger.exception("[API RegeneratePatch] Patch regeneration failed after %.2fs for patch '%s': %s", elapsed, patch_id, err_msg)
        is_quota = any(term in err_msg.lower() for term in ("429", "resource_exhausted", "quota", "limit exceeded"))
        status_code = status.HTTP_429_TOO_MANY_REQUESTS if is_quota else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(
            status_code=status_code,
            detail=f"Patch regeneration failed: {err_msg}",
        )


@router.get(
    "/patches/{patch_id}/status",
    response_model=APIResponse[WorkflowStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Patch Workflow Status",
    description="Retrieves the current execution and validation status of a patch proposal.",
)
async def get_patch_workflow_status(
    patch_id: str,
) -> APIResponse[WorkflowStatusResponse]:
    """Returns the current workflow and review status of a patch proposal."""
    try:
        status_data = await patch_service.get_workflow_status(patch_id)
        resp = WorkflowStatusResponse(
            patch_id=status_data.get("patch_id"),
            repository_id=status_data.get("repository_id", ""),
            issue_id=status_data.get("issue_id", ""),
            status=status_data.get("status", "unknown"),
            review_status=status_data.get("review_status"),
            validation_status=status_data.get("validation_status"),
            risk_level=status_data.get("risk_level"),
            lines_added=status_data.get("lines_added", 0),
            lines_removed=status_data.get("lines_removed", 0),
            current_step="completed",
            regeneration_attempt=status_data.get("regeneration_attempt", 0),
        )
        return APIResponse(
            success=True,
            message=f"Status for patch '{patch_id}' retrieved.",
            data=resp,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Failed to get workflow status for patch '%s': %s", patch_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get workflow status: {str(e)}",
        )

