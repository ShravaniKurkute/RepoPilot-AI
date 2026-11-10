"""Recursive repository directory traverser with .gitignore and security filtering."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import pathspec

from app.repository.language_detector import detect_language_by_extension
from app.repository.schemas import TreeNode

# Directories and files always excluded from indexing
DEFAULT_EXCLUDED_NAMES: Set[str] = {
    # Version Control
    ".git",
    ".svn",
    ".hg",
    # Dependencies & Environments
    "node_modules",
    ".venv",
    "venv",
    "env",
    "ENV",
    # Build & Bundling
    "dist",
    "build",
    "target",
    "out",
    ".next",
    ".nuxt",
    # Cache & Bytecode
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    # IDE & Editor metadata
    ".idea",
    ".vscode",
    # OS files
    ".DS_Store",
    "Thumbs.db",
}


def load_gitignore_spec(repo_root: Path) -> Optional[pathspec.PathSpec]:
    """Loads and compiles .gitignore patterns from repository root if present."""
    gitignore_path = repo_root / ".gitignore"
    if not gitignore_path.is_file():
        return None

    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        return pathspec.PathSpec.from_lines("gitignore", lines)
    except Exception:
        return None


def walk_repository(
    repo_root: Path,
    max_files: int = 5000,
    max_file_size_bytes: int = 10 * 1024 * 1024,  # Skip single files > 10MB
) -> Tuple[TreeNode, int, int, int, List[Tuple[str, int]]]:
    """Traverses repository files recursively and builds the TreeNode hierarchy.

    Args:
        repo_root: Absolute path to the repository directory.
        max_files: Maximum number of files to index before truncating.
        max_file_size_bytes: File size threshold above which contents are not parsed.

    Returns:
        (root_tree_node, total_files, total_dirs, total_bytes, list_of_file_records)
    """
    repo_root = repo_root.resolve()
    gitignore_spec = load_gitignore_spec(repo_root)

    total_files = 0
    total_dirs = 0
    total_bytes = 0
    file_records: List[Tuple[str, int]] = []

    def is_symlink_unsafe(target_path: Path) -> bool:
        """Verifies if a symlink escapes repo boundaries or points to non-existent location."""
        if not target_path.is_symlink():
            return False
        try:
            resolved = target_path.resolve()
            # If resolved path is outside repo_root, it is unsafe
            return not (resolved == repo_root or repo_root in resolved.parents)
        except Exception:
            return True

    def build_tree(current_dir: Path, rel_dir_path: str = "") -> TreeNode:
        nonlocal total_files, total_dirs, total_bytes

        dir_node = TreeNode(
            name=current_dir.name if rel_dir_path else repo_root.name,
            path=rel_dir_path,
            type="directory",
            size_bytes=0,
            children=[],
        )
        total_dirs += 1

        try:
            entries = sorted(list(os.scandir(current_dir)), key=lambda e: (not e.is_dir(), e.name.lower()))
        except (PermissionError, OSError):
            return dir_node

        dir_size = 0
        for entry in entries:
            name = entry.name
            entry_path = Path(entry.path)

            # Exclude default system/build artifacts
            if name in DEFAULT_EXCLUDED_NAMES:
                continue

            # Prevent dangerous symlinks
            if is_symlink_unsafe(entry_path):
                continue

            rel_path = f"{rel_dir_path}/{name}" if rel_dir_path else name

            # Respect .gitignore if spec is present
            if gitignore_spec is not None:
                # Add trailing slash for directories to match directory-only patterns
                test_path = f"{rel_path}/" if entry.is_dir() else rel_path
                if gitignore_spec.match_file(test_path):
                    continue

            if entry.is_dir():
                sub_node = build_tree(entry_path, rel_path)
                dir_size += sub_node.size_bytes
                if dir_node.children is not None:
                    dir_node.children.append(sub_node)
            elif entry.is_file():
                if total_files >= max_files:
                    continue

                try:
                    stat = entry.stat()
                    file_size = stat.st_size
                except (PermissionError, OSError):
                    file_size = 0

                # Skip oversized binaries or files
                if file_size > max_file_size_bytes:
                    continue

                _, ext = os.path.splitext(name)
                ext = ext.lower() if ext else None
                lang = detect_language_by_extension(rel_path)

                file_node = TreeNode(
                    name=name,
                    path=rel_path,
                    type="file",
                    size_bytes=file_size,
                    extension=ext,
                    language=lang,
                )

                dir_size += file_size
                total_files += 1
                total_bytes += file_size
                file_records.append((rel_path, file_size))

                if dir_node.children is not None:
                    dir_node.children.append(file_node)

        dir_node.size_bytes = dir_size
        return dir_node

    root_tree = build_tree(repo_root)
    return root_tree, total_files, total_dirs, total_bytes, file_records
