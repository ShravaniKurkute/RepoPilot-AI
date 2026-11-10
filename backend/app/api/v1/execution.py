"""FastAPI router for Phase 6: Docker Sandbox Execution Engine."""

import asyncio
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import PlainTextResponse

from app.core.logging import logger
from app.sandbox.schemas import (
    ExecutionListResponse,
    ExecutionReportResponse,
    SandboxExecution,
    SandboxExecutionRequest,
)
from app.sandbox.service import sandbox_service
from app.schemas.common import APIResponse

router = APIRouter(tags=["Phase 6: Docker Sandbox Execution Engine"])


@router.post(
    "/repositories/{repository_id}/patches/{patch_id}/execute",
    response_model=APIResponse[SandboxExecution],
    status_code=status.HTTP_200_OK,
    summary="Execute Patch Proposal in Docker Sandbox",
    description="Deploys an ephemeral Docker container, applies the patch, executes automated tests, and compares before/after results.",
)
async def execute_patch_in_sandbox(
    repository_id: str,
    patch_id: str,
    request: Optional[SandboxExecutionRequest] = None,
) -> APIResponse[SandboxExecution]:
    """Triggers containerized test execution for an approved patch proposal."""
    logger.info(
        "[API Execution] Received request to execute patch '%s' for repository '%s'",
        patch_id,
        repository_id,
    )
    t0 = time.time()
    try:
        execution = await sandbox_service.execute_patch(
            repository_id=repository_id,
            patch_id=patch_id,
            request=request,
        )
        elapsed = time.time() - t0
        logger.info(
            "[API Execution] Execution '%s' completed in %.2fs (status: %s, verdict: %s)",
            execution.id,
            elapsed,
            execution.status,
            execution.comparison.verdict if execution.comparison else "NONE",
        )
        return APIResponse(
            success=True,
            message=f"Sandbox execution '{execution.id}' completed with status '{execution.status}'.",
            data=execution,
        )
    except ValueError as e:
        logger.warning("[API Execution] Validation error for patch '%s': %s", patch_id, e)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        elapsed = time.time() - t0
        err_msg = str(e)
        logger.exception("[API Execution] Execution failed for patch '%s': %s", patch_id, err_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sandbox execution failed: {err_msg}",
        )


@router.get(
    "/executions/{execution_id}",
    response_model=APIResponse[SandboxExecution],
    status_code=status.HTTP_200_OK,
    summary="Get Sandbox Execution Details",
    description="Retrieves the execution status, test metrics, and metadata for a specific run.",
)
async def get_execution(execution_id: str) -> APIResponse[SandboxExecution]:
    """Retrieves detailed information for an execution run."""
    execution = await sandbox_service.get_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox execution '{execution_id}' not found.",
        )
    return APIResponse(
        success=True,
        message=f"Execution '{execution_id}' retrieved.",
        data=execution,
    )


@router.get(
    "/executions/{execution_id}/logs",
    summary="Get Sandbox Execution Logs",
    description="Retrieves stdout/stderr terminal logs from the sandbox container.",
    responses={
        200: {
            "content": {"text/plain": {}, "application/json": {}},
            "description": "Plain text logs or JSON APIResponse",
        }
    },
)
async def get_execution_logs(
    execution_id: str,
    format: Optional[str] = Query("raw", description="Return format: 'raw' for text/plain or 'json' for APIResponse"),
) -> Response:
    """Retrieves container logs for a sandbox execution run."""
    logs = await sandbox_service.get_execution_logs(execution_id)
    if logs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sandbox execution '{execution_id}' not found.",
        )

    if format == "json":
        return APIResponse(
            success=True,
            message="Execution logs retrieved.",
            data={"execution_id": execution_id, "logs": logs},
        )
    return PlainTextResponse(content=logs, media_type="text/plain")


@router.get(
    "/executions/{execution_id}/report",
    response_model=APIResponse[ExecutionReportResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Sandbox Execution Report",
    description="Retrieves a structured comparison report with before/after test metrics and verdict.",
)
async def get_execution_report(execution_id: str) -> APIResponse[ExecutionReportResponse]:
    """Retrieves the comparative validation report for a sandbox execution run."""
    report = await sandbox_service.get_execution_report(execution_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report for sandbox execution '{execution_id}' not found or execution incomplete.",
        )
    return APIResponse(
        success=True,
        message=f"Report for execution '{execution_id}' retrieved (Verdict: {report.verdict}).",
        data=report,
    )


@router.get(
    "/repositories/{repository_id}/executions",
    response_model=APIResponse[ExecutionListResponse],
    status_code=status.HTTP_200_OK,
    summary="List Sandbox Executions for Repository",
    description="Lists all previous sandbox execution runs for a repository.",
)
async def list_repository_executions(repository_id: str) -> APIResponse[ExecutionListResponse]:
    """Lists all previous execution runs for a given repository."""
    executions = await sandbox_service.list_executions(repository_id)
    return APIResponse(
        success=True,
        message=f"Retrieved {len(executions)} execution records for repository '{repository_id}'.",
        data=ExecutionListResponse(
            repository_id=repository_id,
            total_executions=len(executions),
            executions=executions,
        ),
    )


@router.get(
    "/repositories/{repository_id}/patches/{patch_id}/executions",
    response_model=APIResponse[ExecutionListResponse],
    status_code=status.HTTP_200_OK,
    summary="List Sandbox Executions for Specific Patch",
    description="Lists all previous sandbox execution runs for a specific patch proposal.",
)
async def list_patch_executions(
    repository_id: str,
    patch_id: str,
) -> APIResponse[ExecutionListResponse]:
    """Lists all execution records for a specific patch proposal."""
    executions = await sandbox_service.list_executions_for_patch(repository_id, patch_id)
    return APIResponse(
        success=True,
        message=f"Retrieved {len(executions)} execution records for patch '{patch_id}'.",
        data=ExecutionListResponse(
            repository_id=repository_id,
            total_executions=len(executions),
            executions=executions,
        ),
    )

