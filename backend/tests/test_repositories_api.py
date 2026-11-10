"""Integration tests for repositories API endpoints."""

import io
from unittest.mock import MagicMock, patch
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repository.service import repository_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_storage(tmp_path):
    """Isolates repository storage directory for tests using pytest tmp_path."""
    orig_root = repository_service.storage_root
    repository_service.storage_root = tmp_path
    yield
    repository_service.storage_root = orig_root


def create_test_zip() -> bytes:
    """Creates a sample test repository ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", "# Test Repository")
        zf.writestr("src/main.py", "def main(): print('hello')")
        zf.writestr("src/test.py", "def test_ok(): assert True")
    return buf.getvalue()


def test_upload_repository_success():
    """Verify uploading a valid ZIP archive ingests repository and returns metadata."""
    zip_bytes = create_test_zip()
    response = client.post(
        "/api/v1/repositories/upload",
        files={"file": ("sample_project.zip", zip_bytes, "application/zip")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert "id" in data
    assert data["name"] == "sample_project"
    assert data["source_type"] == "ZIP"
    assert data["total_files"] == 3
    assert len(data["languages"]) > 0
    assert data["languages"][0]["name"] in ("Python", "Markdown")
    assert "tree" in data


def test_upload_invalid_file_format():
    """Verify uploading non-zip extension is rejected with 400."""
    response = client.post(
        "/api/v1/repositories/upload",
        files={"file": ("script.py", b"print('hi')", "text/x-python")},
    )
    assert response.status_code == 400
    assert "Only .zip archives are supported" in response.json()["detail"]


def test_upload_empty_file():
    """Verify uploading empty file returns 400."""
    response = client.post(
        "/api/v1/repositories/upload",
        files={"file": ("empty.zip", b"", "application/zip")},
    )
    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


def test_clone_invalid_github_url():
    """Verify clone endpoint rejects non-GitHub URLs."""
    response = client.post(
        "/api/v1/repositories/clone",
        json={"url": "https://gitlab.com/owner/repo"},
    )
    assert response.status_code == 400
    assert "Invalid GitHub URL" in response.json()["detail"]


@patch("app.repository.service.clone_github_repository")
def test_clone_github_repository_success(mock_clone, tmp_path):
    """Verify clone endpoint successfully ingests repository when Git succeeds."""
    mock_source = tmp_path / "mock_git_source"
    mock_source.mkdir(parents=True, exist_ok=True)
    (mock_source / "README.md").write_text("# FastAPI")
    mock_clone.return_value = (mock_source, "main", "fastapi")

    response = client.post(
        "/api/v1/repositories/clone",
        json={"url": "https://github.com/fastapi/fastapi", "branch": "main"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["name"] == "fastapi"
    assert data["source_type"] == "GITHUB"
    assert data["default_branch"] == "main"


def test_list_and_get_repository():
    """Verify listing and retrieving specific repository by ID."""
    zip_bytes = create_test_zip()
    upload_res = client.post(
        "/api/v1/repositories/upload",
        files={"file": ("query_repo.zip", zip_bytes, "application/zip")},
    )
    assert upload_res.status_code == 201
    repo_id = upload_res.json()["data"]["id"]

    # 1. List repositories
    list_res = client.get("/api/v1/repositories")
    assert list_res.status_code == 200
    repos = list_res.json()["data"]
    assert any(r["id"] == repo_id for r in repos)

    # 2. Get specific repository
    get_res = client.get(f"/api/v1/repositories/{repo_id}")
    assert get_res.status_code == 200
    assert get_res.json()["data"]["id"] == repo_id
    assert get_res.json()["data"]["name"] == "query_repo"

    # 3. Get repository tree
    tree_res = client.get(f"/api/v1/repositories/{repo_id}/tree")
    assert tree_res.status_code == 200
    assert tree_res.json()["data"]["repository_id"] == repo_id
    assert "tree" in tree_res.json()["data"]


def test_get_nonexistent_repository_404():
    """Verify querying unknown repository ID returns 404."""
    response = client.get("/api/v1/repositories/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
