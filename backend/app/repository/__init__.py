"""Repository ingestion, cloning, traversal, and language detection package."""

from app.repository.schemas import (
    CloneRepoRequest,
    LanguageDistribution,
    RepositoryDetail,
    RepositorySummary,
    RepositoryTreeResponse,
    TreeNode,
)
from app.repository.service import RepositoryService, repository_service
from app.repository.validators import validate_github_url, validate_zip_archive
from app.repository.zip_handler import extract_zip_archive
from app.repository.github_handler import clone_github_repository
from app.repository.file_walker import walk_repository
from app.repository.language_detector import (
    calculate_language_distribution,
    detect_language_by_extension,
)

__all__ = [
    "CloneRepoRequest",
    "LanguageDistribution",
    "RepositoryDetail",
    "RepositorySummary",
    "RepositoryTreeResponse",
    "TreeNode",
    "RepositoryService",
    "repository_service",
    "validate_github_url",
    "validate_zip_archive",
    "extract_zip_archive",
    "clone_github_repository",
    "walk_repository",
    "calculate_language_distribution",
    "detect_language_by_extension",
]
