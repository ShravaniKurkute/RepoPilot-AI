"""FastAPI router for code intelligence, AST parsing, symbols, dependencies, and call graphs."""

from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.code_analysis.schemas import (
    CallGraphEdge,
    FileAnalysisResult,
    FileDependency,
    RepositoryAnalysisResponse,
    Symbol,
)
from app.code_analysis.service import code_analysis_service
from app.core.logging import logger
from app.schemas.common import APIResponse

router = APIRouter(prefix="/repositories", tags=["Code Intelligence"])


@router.post(
    "/{repository_id}/analyze",
    response_model=APIResponse[RepositoryAnalysisResponse],
    status_code=status.HTTP_200_OK,
    summary="Trigger Code Intelligence Analysis",
    description="Parses all source code in the repository, extracting symbols, imports, calls, and dependencies.",
)
async def analyze_repository(
    repository_id: str,
) -> APIResponse[RepositoryAnalysisResponse]:
    """Triggers complete AST parsing and code intelligence analysis for a repository."""
    try:
        result = code_analysis_service.analyze_repository(repository_id)
        return APIResponse(
            success=True,
            message="Repository code intelligence analysis completed successfully.",
            data=result,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Analysis failed for repository '{repository_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to analyze repository: {str(e)}",
        )


@router.get(
    "/{repository_id}/analysis",
    response_model=APIResponse[RepositoryAnalysisResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Complete Repository Analysis",
    description="Returns the stored code intelligence analysis including summary, symbols, dependencies, and call graph.",
)
async def get_repository_analysis(
    repository_id: str,
) -> APIResponse[RepositoryAnalysisResponse]:
    """Fetches previously computed analysis for a repository."""
    analysis = code_analysis_service.get_analysis(repository_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis not found for repository '{repository_id}'. Please run POST /analyze first.",
        )
    return APIResponse(
        success=True,
        message="Repository analysis retrieved successfully.",
        data=analysis,
    )


@router.get(
    "/{repository_id}/symbols",
    response_model=APIResponse[List[Symbol]],
    status_code=status.HTTP_200_OK,
    summary="Search & Filter Extracted Symbols",
    description="Returns extracted code symbols filtered by name, symbol type, or file path.",
)
async def get_repository_symbols(
    repository_id: str,
    name: Optional[str] = Query(None, description="Filter symbols by partial name matching"),
    type: Optional[str] = Query(None, description="Filter by symbol type (function, class, method, etc.)"),
    file: Optional[str] = Query(None, description="Filter symbols by file path"),
) -> APIResponse[List[Symbol]]:
    """Retrieves code symbols with optional filtering."""
    analysis = code_analysis_service.get_analysis(repository_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis not found for repository '{repository_id}'. Please run POST /analyze first.",
        )

    symbols = code_analysis_service.get_symbols(
        repository_id=repository_id,
        name=name,
        symbol_type=type,
        file_path=file,
    )
    return APIResponse(
        success=True,
        message=f"Retrieved {len(symbols)} symbols matching criteria.",
        data=symbols,
    )


@router.get(
    "/{repository_id}/dependencies",
    response_model=APIResponse[Dict[str, FileDependency]],
    status_code=status.HTTP_200_OK,
    summary="Get File Dependency Graph",
    description="Returns the file-level import and dependency relationships across the repository.",
)
async def get_repository_dependencies(
    repository_id: str,
) -> APIResponse[Dict[str, FileDependency]]:
    """Retrieves file dependency mappings."""
    analysis = code_analysis_service.get_analysis(repository_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis not found for repository '{repository_id}'. Please run POST /analyze first.",
        )

    deps = code_analysis_service.get_dependencies(repository_id)
    return APIResponse(
        success=True,
        message=f"Retrieved dependencies for {len(deps or {})} files.",
        data=deps or {},
    )


@router.get(
    "/{repository_id}/call-graph",
    response_model=APIResponse[List[CallGraphEdge]],
    status_code=status.HTTP_200_OK,
    summary="Get Function Call Graph",
    description="Returns caller-to-callee call graph edges with static resolution status.",
)
async def get_repository_call_graph(
    repository_id: str,
) -> APIResponse[List[CallGraphEdge]]:
    """Retrieves call graph edge invocations."""
    analysis = code_analysis_service.get_analysis(repository_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis not found for repository '{repository_id}'. Please run POST /analyze first.",
        )

    call_graph = code_analysis_service.get_call_graph(repository_id)
    return APIResponse(
        success=True,
        message=f"Retrieved {len(call_graph or [])} call graph edges.",
        data=call_graph or [],
    )


@router.get(
    "/{repository_id}/files/{file_path:path}/analysis",
    response_model=APIResponse[FileAnalysisResult],
    status_code=status.HTTP_200_OK,
    summary="Get Single File Analysis",
    description="Returns AST analysis details, symbols, imports, and calls for a specific source file.",
)
async def get_file_analysis(
    repository_id: str,
    file_path: str,
) -> APIResponse[FileAnalysisResult]:
    """Retrieves AST analysis for a specific source file."""
    analysis = code_analysis_service.get_analysis(repository_id)
    if not analysis:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis not found for repository '{repository_id}'. Please run POST /analyze first.",
        )

    file_res = code_analysis_service.get_file_analysis(repository_id, file_path)
    if not file_res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File '{file_path}' was not found in analysis for repository '{repository_id}'.",
        )

    return APIResponse(
        success=True,
        message=f"Analysis for file '{file_path}' retrieved successfully.",
        data=file_res,
    )

