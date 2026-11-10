"""Unit tests for ZIP validation and secure archive extraction."""

import io
from pathlib import Path
import zipfile
import pytest

from app.repository.validators import validate_zip_archive
from app.repository.zip_handler import extract_zip_archive


def create_mock_zip(entries: dict[str, str | bytes]) -> bytes:
    """Helper to create an in-memory ZIP archive from a dict of relative paths -> content."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in entries.items():
            if isinstance(content, str):
                zf.writestr(path, content.encode("utf-8"))
            else:
                zf.writestr(path, content)
    return buf.getvalue()


def test_valid_zip_archive():
    """Verify a well-formed ZIP archive passes validation."""
    zip_bytes = create_mock_zip({
        "README.md": "# Sample Project",
        "src/main.py": "print('hello world')",
    })
    is_valid, error = validate_zip_archive(zip_bytes)
    assert is_valid is True
    assert error is None


def test_invalid_zip_magic_bytes():
    """Verify non-ZIP files fail validation."""
    is_valid, error = validate_zip_archive(b"NOT A REAL ZIP FILE")
    assert is_valid is False
    assert "Magic bytes do not match" in error


def test_corrupted_zip_archive():
    """Verify truncated or corrupted ZIP raises error."""
    corrupted = b"PK\x03\x04" + b"\x00" * 30
    is_valid, error = validate_zip_archive(corrupted)
    assert is_valid is False
    assert "Corrupted or invalid" in error or "structure" in error.lower()


def test_empty_zip_archive():
    """Verify empty archive is rejected."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as _:
        pass
    is_valid, error = validate_zip_archive(buf.getvalue())
    assert is_valid is False
    assert "contains no files" in error


def test_zip_slip_relative_path_traversal():
    """Verify Zip Slip path traversal with '../' is blocked during validation."""
    zip_bytes = create_mock_zip({
        "../../evil.py": "import os; os.system('echo hacked')",
    })
    is_valid, error = validate_zip_archive(zip_bytes)
    assert is_valid is False
    assert "Zip Slip" in error


def test_zip_slip_absolute_path():
    """Verify Zip Slip with absolute paths is blocked."""
    zip_bytes = create_mock_zip({
        "/etc/passwd": "root:x:0:0::/root:/bin/bash",
    })
    is_valid, error = validate_zip_archive(zip_bytes)
    assert is_valid is False
    assert "Zip Slip" in error


def test_zip_file_count_limit():
    """Verify archives with excessive files are rejected."""
    entries = {f"file_{i}.txt": "data" for i in range(15)}
    zip_bytes = create_mock_zip(entries)
    is_valid, error = validate_zip_archive(zip_bytes, max_file_count=10)
    assert is_valid is False
    assert "maximum allowable file count" in error


def test_zip_uncompressed_size_limit():
    """Verify archives exceeding uncompressed byte limits are rejected."""
    entries = {"large.txt": "A" * 1024 * 100}  # 100KB
    zip_bytes = create_mock_zip(entries)
    is_valid, error = validate_zip_archive(zip_bytes, max_uncompressed_bytes=50 * 1024)
    assert is_valid is False
    assert "uncompressed size exceeds" in error


def test_safe_extract_zip_archive(tmp_path: Path):
    """Verify safe extraction creates files properly inside destination directory."""
    zip_bytes = create_mock_zip({
        "module/__init__.py": "",
        "module/app.py": "def run(): pass\n",
        "docs/guide.md": "# Guide\n",
    })
    dest = tmp_path / "extracted_repo"
    result = extract_zip_archive(zip_bytes, dest)

    assert result == dest.resolve()
    assert (dest / "module" / "__init__.py").exists()
    assert (dest / "module" / "app.py").read_text() == "def run(): pass\n"
    assert (dest / "docs" / "guide.md").exists()
