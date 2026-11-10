"""Security and structural validators for repository ingestion."""

import io
import re
import zipfile
from typing import Optional, Tuple
from urllib.parse import urlparse

# Strict regex matching public GitHub HTTPS repository URLs (supports optional www.)
GITHUB_URL_PATTERN = re.compile(
    r"^https://(?:www\.)?github\.com/([a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+?)(?:\.git)?/?$"
)


def validate_github_url(url: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """Validates and normalizes a public GitHub repository HTTPS URL.

    Returns:
        (is_valid, normalized_url, owner, repo_name)
    """
    if not url or not isinstance(url, str):
        return False, None, None, None

    url = url.strip()

    # Disallow credentials in URL
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        return False, None, None, None

    # Enforce HTTPS scheme and github.com host
    if parsed.scheme != "https" or parsed.netloc.lower() not in ("github.com", "www.github.com"):
        return False, None, None, None

    match = GITHUB_URL_PATTERN.match(url)
    if not match:
        return False, None, None, None

    owner = match.group(1)
    repo_name = match.group(2)

    # Prevent path traversal components in owner or repo name
    if owner in (".", "..") or repo_name in (".", ".."):
        return False, None, None, None

    # Canonical normalized URL
    normalized = f"https://github.com/{owner}/{repo_name}"
    return True, normalized, owner, repo_name


def validate_zip_archive(
    archive_bytes: bytes,
    max_file_count: int = 5000,
    max_uncompressed_bytes: int = 100 * 1024 * 1024,
) -> Tuple[bool, Optional[str]]:
    """Validates ZIP archive format, size limits, and security boundaries.

    Checks:
    1. Valid ZIP magic bytes and header structure.
    2. Total file count within threshold.
    3. Uncompressed total size within threshold.
    4. Path traversal / Zip Slip attempts (e.g., '..', absolute paths).
    5. Suspicious compression ratio (Zip bomb protection).

    Returns:
        (is_valid, error_message_if_invalid)
    """
    if not archive_bytes or len(archive_bytes) < 4:
        return False, "Uploaded file is empty or too small to be a valid ZIP archive."

    # Validate ZIP magic bytes (PK\x03\x04 or empty archive PK\x05\x06)
    if not (archive_bytes.startswith(b"PK\x03\x04") or archive_bytes.startswith(b"PK\x05\x06")):
        return False, "Invalid archive format. Magic bytes do not match ZIP specification."

    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            members = zf.infolist()
            total_count = len(members)

            if total_count == 0:
                return False, "ZIP archive contains no files or directories."

            if total_count > max_file_count:
                return False, (
                    f"Archive exceeds maximum allowable file count of {max_file_count} "
                    f"(archive contains {total_count} entries)."
                )

            total_uncompressed = 0
            for member in members:
                # Path traversal / Zip Slip guards
                filename = member.filename

                # Reject null bytes
                if "\0" in filename:
                    return False, f"Malicious archive structure detected: null byte in file path."

                # Normalize slashes and check path parts
                normalized_path = filename.replace("\\", "/").strip()

                # Disallow absolute paths (leading slash or Windows drive letters)
                if normalized_path.startswith("/") or re.match(r"^[a-zA-Z]:", normalized_path):
                    return False, f"Zip Slip attempt detected: absolute path '{filename}' is prohibited."

                parts = [p for p in normalized_path.split("/") if p]
                if ".." in parts:
                    return False, f"Zip Slip attempt detected: directory traversal '..' in '{filename}'."

                total_uncompressed += member.file_size
                if total_uncompressed > max_uncompressed_bytes:
                    limit_mb = max_uncompressed_bytes // (1024 * 1024)
                    return False, (
                        f"Archive uncompressed size exceeds maximum allowable limit of {limit_mb}MB."
                    )

            # Zip bomb compression ratio guard
            compressed_len = len(archive_bytes)
            if compressed_len > 0 and total_uncompressed > 10 * 1024 * 1024:
                ratio = total_uncompressed / compressed_len
                if ratio > 100:
                    return False, "Suspicious compression ratio detected (potential Zip Bomb attack)."

    except zipfile.BadZipFile as e:
        return False, f"Corrupted or invalid ZIP archive: {str(e)}"
    except Exception as e:
        return False, f"Failed to inspect ZIP archive: {str(e)}"

    return True, None
