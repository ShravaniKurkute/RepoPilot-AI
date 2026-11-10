"""FastAPI router for AI code analysis, bug detection, and issue triage."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.analysis.schemas import (
    AnalysisRun,
    AnalyzeFileRequest,
    AnalyzeFunctionRequest,
    CodeIssue,
    IssueCategory,
    IssueListResponse,
    IssueSeverity,
    IssueStatus,
    UpdateIssueStatusRequest,
)
from app.analysis.service import bug_detection_service
from app.core.logging import logger
from app.schemas.common import APIResponse

router = APIRouter(tags=["AI Code Analysis & Bug Detection"])


# -------------------------------------------------------------
# Trigger Analysis Endpoints
# -------------------------------------------------------------
@router.post(
    "/repositories/{repository_id}/ai-analyze",
    response_model=APIResponse[AnalysisRun],
    status_code=status.HTTP_200_OK,
    summary="Trigger Repository-Wide AI Bug & Security Analysis",
    description="Analyzes the entire repository for logic bugs, OWASP/CWE vulnerabilities, and code smells.",
)
async def analyze_repository(
    repository_id: str,
    categories: Optional[List[IssueCategory]] = Query(None, description="Filter categories to analyze"),
) -> APIResponse[AnalysisRun]:
    """Runs repository-wide AI analysis incorporating AST metadata and RAG contexts."""
    try:
        run = await bug_detection_service.analyze_repository(
            repository_id=repository_id, categories=categories
        )
        msg = (
            f"Analysis run '{run.run_id}' completed. Detected {run.total_issues} issues."
            if run.status == "completed"
            else f"Analysis run '{run.run_id}' {run.status}: {run.error_message or 'No issues detected.'}"
        )
        return APIResponse(
            success=run.status != "failed",
            message=msg,
            data=run,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        err_str = str(e)
        logger.error(f"Repository analysis failed for '{repository_id}': {err_str}", exc_info=True)
        status_code = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if "timed out" in err_str.lower()
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to analyze repository: {err_str}",
        )


@router.post(
    "/repositories/{repository_id}/ai-analyze/file",
    response_model=APIResponse[AnalysisRun],
    status_code=status.HTTP_200_OK,
    summary="Trigger Single-File AI Code Analysis",
    description="Analyzes a specific source file for logic bugs, vulnerabilities, and code quality issues.",
)
async def analyze_file(
    repository_id: str,
    payload: AnalyzeFileRequest,
) -> APIResponse[AnalysisRun]:
    """Runs targeted AI analysis on a single source file."""
    try:
        run = await bug_detection_service.analyze_file(
            repository_id=repository_id,
            file_path=payload.file_path,
            categories=payload.categories,
        )
        return APIResponse(
            success=True,
            message=f"File '{payload.file_path}' analyzed: {run.total_issues} issues found.",
            data=run,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        err_str = str(e)
        logger.error(f"File analysis failed for '{payload.file_path}': {err_str}", exc_info=True)
        status_code = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if "timed out" in err_str.lower()
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to analyze file: {err_str}",
        )


@router.post(
    "/repositories/{repository_id}/ai-analyze/function",
    response_model=APIResponse[AnalysisRun],
    status_code=status.HTTP_200_OK,
    summary="Trigger Targeted Function/Symbol Analysis",
    description="Analyzes an individual function, method, or class using AST symbols and caller context.",
)
async def analyze_function(
    repository_id: str,
    payload: AnalyzeFunctionRequest,
) -> APIResponse[AnalysisRun]:
    """Runs deep AI analysis on a specific function or class symbol."""
    try:
        run = await bug_detection_service.analyze_function(
            repository_id=repository_id,
            file_path=payload.file_path,
            symbol_name=payload.symbol_name,
        )
        return APIResponse(
            success=True,
            message=f"Symbol '{payload.symbol_name}' analyzed: {run.total_issues} issues found.",
            data=run,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        err_str = str(e)
        logger.error(f"Symbol analysis failed for '{payload.symbol_name}': {err_str}", exc_info=True)
        status_code = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if "timed out" in err_str.lower()
            else status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        raise HTTPException(
            status_code=status_code,
            detail=f"Failed to analyze symbol: {err_str}",
        )


# -------------------------------------------------------------
# Status & Query Endpoints
# -------------------------------------------------------------
@router.get(
    "/repositories/{repository_id}/ai-analysis/status",
    response_model=APIResponse[AnalysisRun],
    status_code=status.HTTP_200_OK,
    summary="Get Analysis Run Status",
    description="Returns current progress, status, and issue counts for the latest or specified analysis run.",
)
async def get_analysis_status(
    repository_id: str,
    run_id: Optional[str] = Query(None, description="Optional specific run ID"),
) -> APIResponse[AnalysisRun]:
    """Fetches analysis run progress."""
    run = bug_detection_service.get_run_status(repository_id=repository_id, run_id=run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No analysis runs found for repository '{repository_id}'. Please run analysis first.",
        )
    return APIResponse(success=True, message="Analysis status retrieved.", data=run)


@router.get(
    "/repositories/{repository_id}/issues",
    response_model=APIResponse[IssueListResponse],
    status_code=status.HTTP_200_OK,
    summary="List Detected Code Issues",
    description="Returns detected logic bugs, security vulnerabilities, and code smells with flexible filtering.",
)
async def get_issues(
    repository_id: str,
    severity: Optional[str] = Query(None, description="Filter by severity (Critical, High, Medium, Low, Informational)"),
    category: Optional[str] = Query(None, description="Filter by category (logic_bug, security_vulnerability, code_smell)"),
    file: Optional[str] = Query(None, description="Filter by file path substring"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (Open, Confirmed, False Positive, Resolved, Ignored)"),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0, description="Minimum confidence threshold"),
) -> APIResponse[IssueListResponse]:
    """Queries detected issues for a repository."""
    issues_resp = bug_detection_service.get_issues(
        repository_id=repository_id,
        severity=severity,
        category=category,
        file_path=file,
        status=status_filter,
        min_confidence=min_confidence,
    )
    return APIResponse(
        success=True,
        message=f"Retrieved {issues_resp.total_issues} issues matching criteria.",
        data=issues_resp,
    )


@router.get(
    "/repositories/{repository_id}/issues/{issue_id}",
    response_model=APIResponse[CodeIssue],
    status_code=status.HTTP_200_OK,
    summary="Get Single Issue Details",
    description="Returns full technical explanation, evidence, potential impact, and suggested remediation for an issue.",
)
async def get_issue(
    repository_id: str,
    issue_id: str,
) -> APIResponse[CodeIssue]:
    """Fetches details for a specific issue."""
    issue = bug_detection_service.get_issue(repository_id, issue_id)
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found in repository '{repository_id}'.",
        )
    return APIResponse(success=True, message="Issue retrieved successfully.", data=issue)


# -------------------------------------------------------------
# Issue Status Mutation
# -------------------------------------------------------------
@router.patch(
    "/issues/{issue_id}/status",
    response_model=APIResponse[CodeIssue],
    status_code=status.HTTP_200_OK,
    summary="Update Issue Triage Status",
    description="Transitions issue status to 'Confirmed', 'False Positive', 'Resolved', or 'Ignored'.",
)
async def update_issue_status(
    issue_id: str,
    payload: UpdateIssueStatusRequest,
) -> APIResponse[CodeIssue]:
    """Updates issue triage status."""
    updated = await bug_detection_service.update_issue_status(
        issue_id=issue_id,
        new_status=payload.status,
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Issue '{issue_id}' not found.",
        )
    return APIResponse(
        success=True,
        message=f"Issue '{issue_id}' status updated to '{payload.status}'.",
        data=updated,
    )

