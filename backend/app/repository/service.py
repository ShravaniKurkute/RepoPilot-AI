"""Repository ingestion and persistence service."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import List, Optional
import uuid

from app.core.config import settings
from app.core.logging import logger
from app.repository.file_walker import walk_repository
from app.repository.github_handler import clone_github_repository
from app.repository.language_detector import calculate_language_distribution
from app.repository.schemas import (
    RepositoryDetail,
    RepositorySummary,
    TreeNode,
)
from app.repository.zip_handler import extract_zip_archive


class RepositoryService:
    """Manages repository ingestion, storage, metadata persistence, and tree queries."""

    def __init__(self, storage_root: Optional[Path] = None):
        if storage_root is not None:
            self.storage_root = storage_root.resolve()
        else:
            p = Path(settings.WORKSPACE_STORAGE_PATH)
            self.storage_root = p if p.is_absolute() else (Path.cwd() / p).resolve()
        
        self.storage_root.mkdir(parents=True, exist_ok=True)

    def _get_repo_dir(self, repo_id: str) -> Path:
        return self.storage_root / repo_id

    def _get_metadata_path(self, repo_id: str) -> Path:
        return self._get_repo_dir(repo_id) / "metadata.json"

    def _sanitize_name(self, raw_name: str) -> str:
        """Sanitizes names into safe display and directory names."""
        cleaned = re.sub(r"[^\w\-\.]", "_", raw_name.strip())
        return cleaned or "repository"

    def ingest_zip(self, filename: str, content: bytes) -> RepositoryDetail:
        """Ingests an uploaded ZIP archive and extracts repository metadata.

        Args:
            filename: Original uploaded archive filename.
            content: Raw ZIP bytes.

        Returns:
            RepositoryDetail metadata and tree.
        """
        repo_id = str(uuid.uuid4())
        repo_dir = self._get_repo_dir(repo_id)
        source_dir = repo_dir / "source"

        logger.info("Ingesting ZIP archive '%s' into repo_id=%s...", filename, repo_id)

        # Sanitize repository name from filename
        base_name, _ = os.path.splitext(filename)
        repo_name = self._sanitize_name(base_name)

        # 1. Safely extract archive
        extract_zip_archive(
            archive_bytes=content,
            destination_dir=source_dir,
            max_file_count=5000,
            max_uncompressed_bytes=100 * 1024 * 1024,
        )

        # 2. Walk directory structure
        tree, total_files, total_dirs, total_bytes, file_records = walk_repository(
            repo_root=source_dir
        )

        # 3. Detect programming languages
        languages = calculate_language_distribution(file_records)

        # 4. Construct metadata
        metadata = RepositoryDetail(
            id=repo_id,
            name=repo_name,
            source_type="ZIP",
            remote_url=None,
            default_branch=None,
            total_files=total_files,
            total_directories=total_dirs,
            total_size_bytes=total_bytes,
            languages=languages,
            tree=tree,
            status="READY",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 5. Persist metadata to filesystem
        self._save_metadata(repo_id, metadata)
        logger.info("Successfully ingested ZIP repo_id=%s (%d files, %d bytes)", repo_id, total_files, total_bytes)
        return metadata

    def ingest_github(self, url: str, branch: Optional[str] = None) -> RepositoryDetail:
        """Clones a public GitHub repository and generates metadata.

        Args:
            url: GitHub HTTPS repository URL.
            branch: Optional branch/tag to clone.

        Returns:
            RepositoryDetail metadata and tree.
        """
        repo_id = str(uuid.uuid4())
        repo_dir = self._get_repo_dir(repo_id)
        source_dir = repo_dir / "source"

        logger.info("Cloning GitHub repository '%s' into repo_id=%s...", url, repo_id)

        # 1. Clone repository
        dest_path, active_branch, raw_repo_name = clone_github_repository(
            url=url,
            destination_dir=source_dir,
            branch=branch,
            timeout_seconds=60,
        )
        repo_name = self._sanitize_name(raw_repo_name)

        # 2. Walk directory structure
        tree, total_files, total_dirs, total_bytes, file_records = walk_repository(
            repo_root=dest_path
        )

        # 3. Detect programming languages
        languages = calculate_language_distribution(file_records)

        # 4. Construct metadata
        metadata = RepositoryDetail(
            id=repo_id,
            name=repo_name,
            source_type="GITHUB",
            remote_url=url,
            default_branch=active_branch,
            total_files=total_files,
            total_directories=total_dirs,
            total_size_bytes=total_bytes,
            languages=languages,
            tree=tree,
            status="READY",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 5. Persist metadata to filesystem
        self._save_metadata(repo_id, metadata)
        logger.info("Successfully ingested GitHub repo_id=%s (%d files, %d bytes)", repo_id, total_files, total_bytes)
        return metadata

    def _save_metadata(self, repo_id: str, metadata: RepositoryDetail) -> None:
        """Saves metadata to disk in JSON format."""
        meta_path = self._get_metadata_path(repo_id)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(metadata.model_dump_json(indent=2))

    def get_repository(self, repo_id: str) -> Optional[RepositoryDetail]:
        """Retrieves repository metadata and tree by repository ID."""
        meta_path = self._get_metadata_path(repo_id)
        if not meta_path.is_file():
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return RepositoryDetail.model_validate(data)
        except Exception as e:
            logger.error("Failed to read metadata for repo_id=%s: %s", repo_id, e)
            return None

    def get_repository_tree(self, repo_id: str) -> Optional[TreeNode]:
        """Retrieves only the directory tree for a given repository."""
        repo = self.get_repository(repo_id)
        return repo.tree if repo else None

    def list_repositories(self) -> List[RepositorySummary]:
        """Lists all ingested repositories ordered by creation date descending."""
        if not self.storage_root.exists():
            return []

        summaries: List[RepositorySummary] = []
        for entry in os.scandir(self.storage_root):
            if not entry.is_dir():
                continue
            meta_path = Path(entry.path) / "metadata.json"
            if meta_path.is_file():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # Exclude the large tree payload when returning summaries
                    data.pop("tree", None)
                    summaries.append(RepositorySummary.model_validate(data))
                except Exception as e:
                    logger.warning("Skipping corrupted metadata in %s: %s", entry.path, e)

        # Sort descending by creation timestamp
        summaries.sort(key=lambda s: s.created_at, reverse=True)
        return summaries


# Shared repository service instance
repository_service = RepositoryService()
