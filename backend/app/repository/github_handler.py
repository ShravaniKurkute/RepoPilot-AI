"""Public GitHub repository cloning service with cross-platform timeout and cleanup."""

import os
from pathlib import Path
import shutil
import stat
import subprocess
from typing import Optional, Tuple
import git

from app.core.logging import logger
from app.repository.validators import validate_github_url


def _remove_readonly(func, path, _) -> None:
    """Helper to remove read-only attribute from files on Windows during cleanup."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass


def _cleanup_directory(directory: Path) -> None:
    """Safely removes a directory and all its contents, handling Windows read-only locks."""
    if directory.exists():
        try:
            shutil.rmtree(directory, onerror=_remove_readonly)
        except Exception as e:
            logger.warning("Failed to remove directory '%s': %s", directory, e)


def clone_github_repository(
    url: str,
    destination_dir: Path,
    branch: Optional[str] = None,
    timeout_seconds: int = 60,
) -> Tuple[Path, str, str]:
    """Clones a public GitHub repository using shallow clone for security and speed.

    Cross-Platform Security & Safety Guarantees:
    - Only public HTTPS github.com URLs are accepted.
    - Uses shallow clone (--depth 1) to conserve network and disk resources.
    - Enforces timeout via Python's subprocess module (natively supported on Windows, Linux, macOS).
    - Avoids GitPython's 'kill_after_timeout' which raises errors on Windows.
    - Cleans up partially cloned or corrupted destination directories on any failure or timeout.
    - Never executes hooks or custom scripts during cloning.

    Args:
        url: Remote repository URL.
        destination_dir: Isolated target directory where repository should be cloned.
        branch: Optional branch, tag, or commit to clone.
        timeout_seconds: Maximum clone execution timeout.

    Returns:
        (resolved_destination_path, active_branch_name, repository_name)

    Raises:
        ValueError: If URL is invalid, remote is unsupported, or parameters are unsafe.
        RuntimeError: If Git clone fails due to missing repo, authentication, network, or timeout.
    """
    is_valid, normalized_url, owner, repo_name = validate_github_url(url)
    if not is_valid or not normalized_url or not repo_name:
        raise ValueError(
            "Invalid GitHub URL. Only public HTTPS repositories from 'github.com' are supported "
            "(e.g., 'https://github.com/owner/repository')."
        )

    destination_dir = destination_dir.resolve()
    if destination_dir.exists() and any(destination_dir.iterdir()):
        raise ValueError(f"Destination directory '{destination_dir}' already exists and is not empty.")

    # Ensure parent directory exists
    destination_dir.parent.mkdir(parents=True, exist_ok=True)

    # Build cross-platform git clone command
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        "--single-branch",
    ]

    if branch and branch.strip():
        clean_branch = branch.strip()
        # Reject suspicious branch names containing flags or control characters
        if clean_branch.startswith("-") or ";" in clean_branch or " " in clean_branch:
            raise ValueError(f"Invalid branch name '{branch}'.")
        cmd.extend(["--branch", clean_branch])

    cmd.extend([normalized_url, str(destination_dir)])

    # Environment overrides to disable interactive credential prompts
    git_env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "echo",
    }

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            env=git_env,
        )
    except subprocess.TimeoutExpired as e:
        logger.error("Git clone timed out after %d seconds for '%s'", timeout_seconds, normalized_url)
        _cleanup_directory(destination_dir)
        raise RuntimeError(
            f"Repository clone timed out after {timeout_seconds} seconds. "
            f"The repository may be too large or the connection is too slow."
        ) from e
    except Exception as e:
        logger.error("Subprocess execution failed while cloning '%s': %s", normalized_url, e)
        _cleanup_directory(destination_dir)
        raise RuntimeError(f"Failed to execute Git clone: {str(e)}") from e

    # Check git returncode
    if result.returncode != 0:
        _cleanup_directory(destination_dir)
        stderr = (result.stderr or "").strip()
        stderr_lower = stderr.lower()

        if (
            ("repository" in stderr_lower and "not found" in stderr_lower)
            or "could not read username" in stderr_lower
            or "authentication failed" in stderr_lower
        ):
            raise RuntimeError(
                "Repository not found or private. Ensure the GitHub repository exists and is public."
            )
        elif "remote branch" in stderr_lower and "not found" in stderr_lower:
            raise RuntimeError(
                f"Specified branch '{branch}' was not found in remote repository."
            )
        elif "could not resolve host" in stderr_lower:
            raise RuntimeError(
                "Network error: Unable to resolve 'github.com'. Please check your internet connection."
            )
        else:
            # Extract the last error line for a clean message
            err_lines = [line.strip() for line in stderr.splitlines() if line.strip()]
            clean_err = err_lines[-1] if err_lines else f"Exit code {result.returncode}"
            raise RuntimeError(f"Git clone failed: {clean_err}")

    # Inspect the cloned repository with GitPython for branch confirmation
    active_branch = branch or "main"
    try:
        repo = git.Repo(destination_dir)
        try:
            active_branch = repo.active_branch.name
        except Exception:
            pass
    except Exception as e:
        logger.warning("Could not read active branch via GitPython: %s", e)

    return destination_dir, active_branch, repo_name
