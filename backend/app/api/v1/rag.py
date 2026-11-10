"""FastAPI router for repository code indexing, embedding generation, and hybrid search."""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from app.core.logging import logger
from app.rag.schemas import (
    IndexingStatsResponse,
    IndexingStatusResponse,
    SearchQuery,
    SearchResponse,
)
from app.rag.service import rag_service
from app.schemas.common import APIResponse

router = APIRouter(prefix="/repositories", tags=["Code RAG & Search"])


@router.post(
    "/{repository_id}/index",
    response_model=APIResponse[IndexingStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Index Repository Codebase",
    description="Extracts AST-aware code chunks, computes embeddings, and indexes chunks into the vector store.",
)
async def index_repository(
    repository_id: str,
    force: bool = Query(default=False, description="If true, forces re-embedding of all chunks"),
) -> APIResponse[IndexingStatusResponse]:
    """Generates code chunks, vector embeddings, and indexes the repository."""
    try:
        result = await rag_service.index_repository(repository_id, force_reindex=force)
        return APIResponse(
            success=True,
            message=f"Repository '{repository_id}' indexed successfully: {result.total_chunks} chunks ({result.new_chunks_embedded} new, {result.cached_chunks} cached).",
            data=result,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Indexing failed for repository '{repository_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to index repository: {str(e)}",
        )


@router.get(
    "/{repository_id}/index/status",
    response_model=APIResponse[IndexingStatusResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Repository Indexing Status",
    description="Returns whether the repository is indexed and summary metrics of stored chunks.",
)
async def get_index_status(
    repository_id: str,
) -> APIResponse[IndexingStatusResponse]:
    """Fetches indexing status for a repository."""
    try:
        status_res = rag_service.get_indexing_status(repository_id)
        return APIResponse(
            success=True,
            message="Indexing status retrieved successfully.",
            data=status_res,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{repository_id}/index/stats",
    response_model=APIResponse[IndexingStatsResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Repository Indexing Statistics",
    description="Returns detailed statistics on chunk count, distinct files, languages, and embedding models.",
)
async def get_index_stats(
    repository_id: str,
) -> APIResponse[IndexingStatsResponse]:
    """Fetches chunk and language breakdown for a repository."""
    try:
        stats = rag_service.get_indexing_stats(repository_id)
        return APIResponse(
            success=True,
            message="Indexing statistics retrieved successfully.",
            data=stats,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{repository_id}/search",
    response_model=APIResponse[SearchResponse],
    status_code=status.HTTP_200_OK,
    summary="Hybrid Code Search",
    description="Retrieves ranked code snippets using semantic vector search, keyword search, or hybrid RRF ranking.",
)
async def search_codebase(
    repository_id: str,
    query: SearchQuery,
) -> APIResponse[SearchResponse]:
    """Executes hybrid, semantic, or keyword retrieval across repository code chunks."""
    try:
        search_res = await rag_service.search(repository_id, query)
        return APIResponse(
            success=True,
            message=f"Retrieved {search_res.total_results} code snippets matching query.",
            data=search_res,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Search failed for repository '{repository_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute code search: {str(e)}",
        )


@router.delete(
    "/{repository_id}/index",
    response_model=APIResponse[dict],
    status_code=status.HTTP_200_OK,
    summary="Delete Repository Index",
    description="Safely removes all vector embeddings and chunk records for a repository.",
)
async def delete_index(
    repository_id: str,
) -> APIResponse[dict]:
    """Clears repository vector index."""
    try:
        await rag_service.delete_index(repository_id)
        return APIResponse(
            success=True,
            message=f"Vector index for repository '{repository_id}' deleted successfully.",
            data={"repository_id": repository_id, "deleted": True},
        )
    except Exception as e:
        logger.error(f"Failed to delete index for '{repository_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete index: {str(e)}",
        )

