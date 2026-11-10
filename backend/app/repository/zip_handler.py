"""Secure ZIP archive extraction and validation service."""

import io
import os
from pathlib import Path
import zipfile

from app.repository.validators import validate_zip_archive


def extract_zip_archive(
    archive_bytes: bytes,
    destination_dir: Path,
    max_file_count: int = 5000,
    max_uncompressed_bytes: int = 100 * 1024 * 1024,
) -> Path:
    """Safely validates and extracts a ZIP archive into the destination directory.

    Guarantees:
    - Path traversal / Zip Slip protection: files cannot escape destination_dir.
    - Resource limits (file count, total uncompressed size, compression ratio).
    - Prevents arbitrary symlink creation pointing outside destination_dir.

    Args:
        archive_bytes: In-memory byte array of the uploaded ZIP file.
        destination_dir: Isolated target directory where files should be extracted.
        max_file_count: Maximum entries allowed in the archive.
        max_uncompressed_bytes: Maximum uncompressed byte limit.

    Returns:
        The resolved Path of destination_dir containing the extracted files.

    Raises:
        ValueError: If archive fails validation or attempts path traversal.
    """
    is_valid, error_msg = validate_zip_archive(
        archive_bytes=archive_bytes,
        max_file_count=max_file_count,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    if not is_valid:
        raise ValueError(error_msg or "Invalid ZIP archive.")

    destination_dir = destination_dir.resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        for member in zf.infolist():
            # Sanitize member path
            norm_name = member.filename.replace("\\", "/").strip()
            if not norm_name or norm_name.endswith("/."):
                continue

            target_path = (destination_dir / norm_name).resolve()

            # Strict boundary check: target must be inside destination_dir
            try:
                # os.path.commonpath raises ValueError if on different drives (Windows)
                common = Path(os.path.commonpath([str(destination_dir), str(target_path)]))
                if common != destination_dir:
                    raise ValueError(
                        f"Zip Slip attack prevented: target '{norm_name}' escapes destination boundary."
                    )
            except ValueError as e:
                raise ValueError(
                    f"Zip Slip attack prevented: invalid path '{norm_name}'."
                ) from e

            # If entry is directory
            if member.is_dir() or norm_name.endswith("/"):
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            # Ensure parent directories exist
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Prevent symbolic link creation that could escape sandbox
            # Check upper byte of external_attr for symlink flag (0o120000)
            is_symlink = (member.external_attr >> 16) & 0o170000 == 0o120000
            if is_symlink:
                # Disallow symlinks in uploaded archives for security
                continue

            # Write file content safely in chunks
            with zf.open(member, "r") as src, open(target_path, "wb") as dst:
                while chunk := src.read(64 * 1024):
                    dst.write(chunk)

    return destination_dir
