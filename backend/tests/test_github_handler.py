"""Unit tests for GitHub URL validation, cross-platform cloning, timeout handling, and cleanup."""

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch
import pytest

from app.repository.github_handler import clone_github_repository
from app.repository.validators import validate_github_url


@pytest.mark.parametrize(
    "url, expected_normalized, expected_owner, expected_repo",
    [
        (
            "https://github.com/torvalds/linux",
            "https://github.com/torvalds/linux",
            "torvalds",
            "linux",
        ),
        (
            "https://github.com/facebook/react.git",
            "https://github.com/facebook/react",
            "facebook",
            "react",
        ),
        (
            "https://www.github.com/pallets/flask/",
            "https://github.com/pallets/flask",
            "pallets",
            "flask",
        ),
    ],
)
def test_valid_github_urls(url, expected_normalized, expected_owner, expected_repo):
    """Verify valid public GitHub HTTPS URLs are recognized and normalized."""
    is_valid, normalized, owner, repo = validate_github_url(url)
    assert is_valid is True
    assert normalized == expected_normalized
    assert owner == expected_owner
    assert repo == expected_repo


@pytest.mark.parametrize(
    "invalid_url",
    [
        "git@github.com:torvalds/linux.git",           # SSH format
        "http://github.com/torvalds/linux",            # Plain HTTP
        "https://gitlab.com/owner/repo",               # Non-GitHub host
        "https://bitbucket.org/owner/repo",            # Non-GitHub host
        "https://malicious.com/github.com/owner/repo", # Deceptive host
        "file:///etc/passwd",                           # Local file protocol
        "/local/path/to/repo",                         # Local filesystem path
        "https://user:pass@github.com/owner/repo",      # Credentials in URL
        "",                                            # Empty string
        "not a url",                                   # Malformed
    ],
)
def test_invalid_github_urls(invalid_url):
    """Verify disallowed, non-GitHub, SSH, and suspicious URLs are rejected."""
    is_valid, normalized, owner, repo = validate_github_url(invalid_url)
    assert is_valid is False
    assert normalized is None


def test_clone_invalid_url_raises_error(tmp_path: Path):
    """Verify clone function immediately raises ValueError on invalid URL."""
    with pytest.raises(ValueError, match="Invalid GitHub URL"):
        clone_github_repository("https://gitlab.com/evil/repo", tmp_path / "repo")


def test_clone_suspicious_branch_raises_error(tmp_path: Path):
    """Verify suspicious branch names with command injection flags are rejected."""
    with pytest.raises(ValueError, match="Invalid branch name"):
        clone_github_repository(
            "https://github.com/fastapi/fastapi",
            tmp_path / "repo",
            branch="--upload-pack=evil",
        )


@patch("git.Repo")
@patch("subprocess.run")
def test_clone_github_repository_success(mock_subproc, mock_repo_cls, tmp_path: Path):
    """Verify successful clone invocation returns correct metadata without using kill_after_timeout."""
    mock_subproc.return_value = subprocess.CompletedProcess(
        args=["git", "clone"],
        returncode=0,
        stdout="",
        stderr="",
    )
    mock_repo_instance = MagicMock()
    mock_repo_instance.active_branch.name = "main"
    mock_repo_cls.return_value = mock_repo_instance

    dest = tmp_path / "cloned_repo"
    dest_path, branch, name = clone_github_repository(
        url="https://github.com/encode/uvicorn",
        destination_dir=dest,
        branch="main",
        timeout_seconds=30,
    )

    assert dest_path == dest.resolve()
    assert branch == "main"
    assert name == "uvicorn"

    # Verify subprocess was called with cross-platform timeout argument
    mock_subproc.assert_called_once()
    _, kwargs = mock_subproc.call_args
    assert kwargs.get("timeout") == 30
    assert "kill_after_timeout" not in kwargs


@patch("subprocess.run")
def test_clone_github_repository_timeout(mock_subproc, tmp_path: Path):
    """Verify timeout triggers clean failure and removes destination directory."""
    dest = tmp_path / "timeout_repo"

    def simulate_partial_clone_then_timeout(*args, **kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "partial_file.txt").write_text("incomplete data")
        raise subprocess.TimeoutExpired(cmd=["git", "clone"], timeout=15)

    mock_subproc.side_effect = simulate_partial_clone_then_timeout

    with pytest.raises(RuntimeError, match="timed out after 15 seconds"):
        clone_github_repository(
            url="https://github.com/huge/repository",
            destination_dir=dest,
            timeout_seconds=15,
        )

    # Destination directory must be cleaned up
    assert not dest.exists()


@patch("subprocess.run")
def test_clone_github_repository_git_failure(mock_subproc, tmp_path: Path):
    """Verify Git non-zero returncode raises user-friendly error and cleans up."""
    dest = tmp_path / "failed_repo"

    def simulate_partial_clone_then_fail(*args, **kwargs):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "failed.txt").write_text("failed")
        return subprocess.CompletedProcess(
            args=["git", "clone"],
            returncode=128,
            stdout="",
            stderr="fatal: repository 'https://github.com/private/repo' not found",
        )

    mock_subproc.side_effect = simulate_partial_clone_then_fail

    with pytest.raises(RuntimeError, match="not found or private"):
        clone_github_repository(
            url="https://github.com/private/repo",
            destination_dir=dest,
        )

    # Destination directory must be cleaned up
    assert not dest.exists()


@patch("subprocess.run")
def test_clone_github_repository_missing_branch(mock_subproc, tmp_path: Path):
    """Verify missing branch failure raises appropriate error and cleans up."""
    dest = tmp_path / "missing_branch_repo"

    mock_subproc.return_value = subprocess.CompletedProcess(
        args=["git", "clone"],
        returncode=128,
        stdout="",
        stderr="fatal: Remote branch non-existent-branch not found in upstream origin",
    )

    with pytest.raises(RuntimeError, match="branch 'non-existent-branch' was not found"):
        clone_github_repository(
            url="https://github.com/fastapi/fastapi",
            destination_dir=dest,
            branch="non-existent-branch",
        )

    assert not dest.exists()


@patch("subprocess.run")
def test_clone_github_repository_network_error(mock_subproc, tmp_path: Path):
    """Verify network resolution errors are converted to clear error message."""
    dest = tmp_path / "network_err_repo"

    mock_subproc.return_value = subprocess.CompletedProcess(
        args=["git", "clone"],
        returncode=128,
        stdout="",
        stderr="fatal: unable to access 'https://github.com/fastapi/fastapi/': Could not resolve host: github.com",
    )

    with pytest.raises(RuntimeError, match="Network error: Unable to resolve 'github.com'"):
        clone_github_repository(
            url="https://github.com/fastapi/fastapi",
            destination_dir=dest,
        )

    assert not dest.exists()
