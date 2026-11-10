"""FastAPI router for repository ingestion and directory queries."""

from typing import List
from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.logging import logger
from app.repository.schemas import (
    CloneRepoRequest,
    RepositoryDetail,
    RepositorySummary,
    RepositoryTreeResponse,
)
from app.repository.service import repository_service
from app.schemas.common import APIResponse

router = APIRouter(prefix="/repositories", tags=["Repositories"])


@router.post(
    "/upload",
    response_model=APIResponse[RepositoryDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Upload & Ingest ZIP Repository",
    description="Accepts a ZIP archive of a software codebase, validates boundaries, and extracts metadata.",
)
async def upload_repository(
    file: UploadFile = File(..., description="ZIP archive of the codebase"),
) -> APIResponse[RepositoryDetail]:
    """Ingests a repository via ZIP archive upload."""
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is missing from the uploaded file.",
        )

    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Only .zip archives are supported.",
        )

    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty.",
            )

        repo = repository_service.ingest_zip(
            filename=file.filename,
            content=content,
        )

        return APIResponse(
            success=True,
            message=f"Repository '{repo.name}' successfully ingested from ZIP archive.",
            data=repo,
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("ZIP validation failed for '%s': %s", file.filename, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error("Unexpected error ingesting ZIP '%s': %s", file.filename, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal failure during repository ingestion: {str(e)}",
        ) from e


@router.post(
    "/clone",
    response_model=APIResponse[RepositoryDetail],
    status_code=status.HTTP_201_CREATED,
    summary="Clone Public GitHub Repository",
    description="Clones a public GitHub repository via HTTPS and indexes its directory structure.",
)
async def clone_repository(
    payload: CloneRepoRequest,
) -> APIResponse[RepositoryDetail]:
    """Ingests a repository by cloning from GitHub."""
    try:
        repo = repository_service.ingest_github(
            url=payload.url,
            branch=payload.branch,
        )
        return APIResponse(
            success=True,
            message=f"Repository '{repo.name}' successfully cloned and ingested.",
            data=repo,
        )
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning("Invalid GitHub clone request for '%s': %s", payload.url, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except RuntimeError as e:
        logger.error("Git clone failed for '%s': %s", payload.url, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error("Unexpected error during GitHub clone '%s': %s", payload.url, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clone repository: {str(e)}",
        ) from e


@router.get(
    "",
    response_model=APIResponse[List[RepositorySummary]],
    status_code=status.HTTP_200_OK,
    summary="List Ingested Repositories",
    description="Returns a list of all repositories currently ingested, ordered most recent first.",
)
async def list_repositories() -> APIResponse[List[RepositorySummary]]:
    """Retrieves all ingested repository summaries."""
    repos = repository_service.list_repositories()
    return APIResponse(
        success=True,
        message=f"Retrieved {len(repos)} repositories.",
        data=repos,
    )


@router.get(
    "/{repository_id}",
    response_model=APIResponse[RepositoryDetail],
    status_code=status.HTTP_200_OK,
    summary="Get Repository Details",
    description="Returns detailed metadata and the complete directory tree of an ingested repository.",
)
async def get_repository_details(
    repository_id: str,
) -> APIResponse[RepositoryDetail]:
    """Retrieves detailed metadata for a specific repository."""
    repo = repository_service.get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID '{repository_id}' was not found.",
        )
    return APIResponse(
        success=True,
        message="Repository details retrieved successfully.",
        data=repo,
    )


@router.get(
    "/{repository_id}/tree",
    response_model=APIResponse[RepositoryTreeResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Repository Directory Tree",
    description="Returns only the recursive directory tree for a repository.",
)
async def get_repository_tree(
    repository_id: str,
) -> APIResponse[RepositoryTreeResponse]:
    """Retrieves directory tree hierarchy for a specific repository."""
    repo = repository_service.get_repository(repository_id)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository with ID '{repository_id}' was not found.",
        )
    return APIResponse(
        success=True,
        message="Repository tree retrieved successfully.",
        data=RepositoryTreeResponse(
            repository_id=repo.id,
            name=repo.name,
            tree=repo.tree,
        ),
    )
