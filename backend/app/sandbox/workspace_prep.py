"""Repository preparation module packing isolated repository snapshots for container transfer."""

import io
from pathlib import Path
import tarfile
from typing import Optional, Set
from app.core.logging import logger
from app.repository.service import repository_service


# Excluded build artifacts and virtual environments
DEFAULT_SNAPSHOT_EXCLUSIONS: Set[str] = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    ".DS_Store",
}


class WorkspacePreparer:
    """Packages repository snapshots into safe tar archives for container injection."""

    def __init__(self, storage_root: Optional[Path | str] = None):
        if storage_root is not None:
            self._custom_storage_root = Path(storage_root)
        else:
            self._custom_storage_root = None

    @property
    def storage_root(self) -> Path:
        if self._custom_storage_root is not None:
            return self._custom_storage_root
        return repository_service.storage_root

    def get_source_dir(self, repository_id: str) -> Path:
        """Locates the repository source directory."""
        repo_dir = self.storage_root / repository_id
        source_dir = repo_dir / "source"
        if source_dir.exists() and source_dir.is_dir():
            return source_dir
        if repo_dir.exists() and repo_dir.is_dir():
            return repo_dir
        raise ValueError(f"Repository source directory for '{repository_id}' does not exist.")

    def create_repository_tar(self, repository_id: str) -> bytes:
        """Packages the repository source into an in-memory tar archive, ensuring path safety."""
        source_dir = self.get_source_dir(repository_id)
        logger.info("[WorkspacePrep] Packaging snapshot for '%s' from %s...", repository_id, source_dir)

        tar_buffer = io.BytesIO()
        file_count = 0
        total_bytes = 0

        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            for item in source_dir.rglob("*"):
                rel_parts = item.relative_to(source_dir).parts

                # Skip excluded directories and hidden cache files
                if any(part in DEFAULT_SNAPSHOT_EXCLUSIONS for part in rel_parts):
                    continue

                # Protect against symlink escapes
                if item.is_symlink():
                    try:
                        resolved = item.resolve()
                        if not resolved.is_relative_to(source_dir):
                            logger.warning("[WorkspacePrep] Skipping unsafe symlink '%s' escaping root", item)
                            continue
                    except Exception:
                        continue

                rel_posix = item.relative_to(source_dir).as_posix()
                if item.is_file():
                    tar.add(item, arcname=rel_posix, recursive=False)
                    file_count += 1
                    total_bytes += item.stat().st_size
                elif item.is_dir():
                    tar.add(item, arcname=rel_posix, recursive=False)

        tar_buffer.seek(0)
        data = tar_buffer.getvalue()
        logger.info(
            "[WorkspacePrep] Created snapshot archive for '%s': %d files, %.2f KB",
            repository_id,
            file_count,
            len(data) / 1024.0,
        )
        return data


workspace_preparer = WorkspacePreparer()
