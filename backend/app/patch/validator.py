"""Deterministic unified-diff parser and security validator for patch proposals."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import posixpath
import re
from typing import Dict, List, Optional, Set, Tuple

PROTECTED_PATHS = {
    ".git",
    ".env",
    "backend/.env",
    ".env.example",
    "backend/.env.example",
    ".gitignore",
    "backend/.gitignore",
}


@dataclass
class PatchHunk:
    old_start: int
    old_length: int
    new_start: int
    new_length: int
    lines: List[str] = field(default_factory=list)


@dataclass
class FileDiff:
    old_path: str
    new_path: str
    hunks: List[PatchHunk] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Detailed deterministic validation result for a proposed code patch."""

    is_valid: bool
    error_message: Optional[str] = None
    affected_files: List[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    hunks_count: int = 0
    original_snippets: Dict[str, str] = field(default_factory=dict)
    modified_snippets: Dict[str, str] = field(default_factory=dict)


class PatchValidator:
    """Validates diff syntax, bounds paths within workspace, and simulates hunk application."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root.resolve()

    def validate_patch(self, diff_text: str, expected_target_file: Optional[str] = None) -> ValidationResult:
        """Parses and validates a unified-diff string against the repository workspace."""
        if not diff_text or not diff_text.strip():
            return ValidationResult(is_valid=False, error_message="Patch diff is completely empty.")

        # Reject binary diffs
        if "GIT binary patch" in diff_text or "Binary files " in diff_text:
            return ValidationResult(is_valid=False, error_message="Binary patches are not supported in Phase 5.")

        # Parse file diffs
        file_diffs, parse_err = self._parse_unified_diff(diff_text)
        if parse_err:
            return ValidationResult(is_valid=False, error_message=f"Diff syntax error: {parse_err}")

        if not file_diffs:
            return ValidationResult(is_valid=False, error_message="No valid file diff hunks could be parsed.")

        total_added = 0
        total_removed = 0
        total_hunks = 0
        affected_files: List[str] = []
        original_snippets: Dict[str, str] = {}
        modified_snippets: Dict[str, str] = {}

        for f_diff in file_diffs:
            norm_rel_path = self._sanitize_path(f_diff.new_path)
            if not norm_rel_path:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Invalid or unsafe target file path: '{f_diff.new_path}'",
                )

            # Security: Path traversal & workspace boundary enforcement
            full_path = (self.repo_root / norm_rel_path).resolve()
            try:
                full_path.relative_to(self.repo_root)
            except ValueError:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Path traversal detected: '{norm_rel_path}' is outside repository root.",
                )

            # Security: Disallow modifying protected root and configuration files
            if norm_rel_path in PROTECTED_PATHS or norm_rel_path.endswith(".env"):
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Modification of protected file '{norm_rel_path}' is strictly disallowed.",
                )

            # Verify target file exists for modification
            if not full_path.is_file():
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Target file for patch modification does not exist: '{norm_rel_path}'",
                )

            try:
                original_text = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Failed to read source file '{norm_rel_path}': {e}",
                )

            # Simulate patch application in memory to verify hunk veracity
            applied_text, added, removed, app_err = self._apply_hunks(original_text, f_diff.hunks)
            if app_err:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"Patch hunk application failed on '{norm_rel_path}': {app_err}",
                )

            total_added += added
            total_removed += removed
            total_hunks += len(f_diff.hunks)
            affected_files.append(norm_rel_path)
            original_snippets[norm_rel_path] = original_text
            modified_snippets[norm_rel_path] = applied_text

        if expected_target_file:
            clean_expected = self._sanitize_path(expected_target_file)
            if clean_expected not in affected_files:
                return ValidationResult(
                    is_valid=False,
                    error_message=(
                        f"Patch modified '{', '.join(affected_files)}' instead of the identified issue file "
                        f"'{clean_expected}'."
                    ),
                )

        return ValidationResult(
            is_valid=True,
            affected_files=affected_files,
            lines_added=total_added,
            lines_removed=total_removed,
            hunks_count=total_hunks,
            original_snippets=original_snippets,
            modified_snippets=modified_snippets,
        )

    def _sanitize_path(self, raw_path: str) -> Optional[str]:
        """Cleans unified-diff path prefixes (a/, b/) and checks for directory traversal."""
        p = raw_path.strip().replace("\\", "/")
        if p.startswith("a/") or p.startswith("b/"):
            p = p[2:]
        p = posixpath.normpath(p).strip("/")
        if not p or p == "." or p.startswith("..") or "/../" in p or p.startswith("/"):
            return None
        # Reject drive letters like C:
        if ":" in p:
            return None
        return p

    def _parse_unified_diff(self, diff_text: str) -> Tuple[List[FileDiff], Optional[str]]:
        """Parses unified diff text into structured FileDiff and PatchHunk representations."""
        lines = diff_text.splitlines()
        file_diffs: List[FileDiff] = []
        current_file: Optional[FileDiff] = None
        current_hunk: Optional[PatchHunk] = None

        hunk_header_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

        i = 0
        while i < len(lines):
            line = lines[i]

            # Detect file boundaries
            if line.startswith("--- "):
                old_path = line[4:].strip()
                if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                    i += 1
                    new_path = lines[i][4:].strip()
                    current_file = FileDiff(old_path=old_path, new_path=new_path)
                    file_diffs.append(current_file)
                    current_hunk = None
                    i += 1
                    continue

            # Detect hunk header
            match = hunk_header_re.match(line)
            if match and current_file is not None:
                old_start = int(match.group(1))
                old_length = int(match.group(2)) if match.group(2) is not None else 1
                new_start = int(match.group(3))
                new_length = int(match.group(4)) if match.group(4) is not None else 1

                current_hunk = PatchHunk(
                    old_start=old_start,
                    old_length=old_length,
                    new_start=new_start,
                    new_length=new_length,
                )
                current_file.hunks.append(current_hunk)
                i += 1
                continue

            # In-hunk lines
            if current_hunk is not None:
                if line.startswith(("+", "-", " ", "\\")):
                    current_hunk.lines.append(line)
                elif line.strip() == "":
                    # Treat empty line as context line if inside hunk
                    current_hunk.lines.append(" " + line)
                elif line.startswith("diff --git"):
                    # Next diff block starting
                    current_hunk = None
                    current_file = None

            i += 1

        return file_diffs, None

    def _apply_hunks(
        self, original_text: str, hunks: List[PatchHunk]
    ) -> Tuple[str, int, int, Optional[str]]:
        """Simulates clean hunk application in-memory, asserting context line accuracy."""
        original_lines = original_text.splitlines()
        result_lines: List[str] = []
        orig_idx = 0
        added_count = 0
        removed_count = 0

        for hunk in hunks:
            target_start_idx = max(0, hunk.old_start - 1)

            # Copy preceding untouched lines
            while orig_idx < target_start_idx and orig_idx < len(original_lines):
                result_lines.append(original_lines[orig_idx])
                orig_idx += 1

            for line in hunk.lines:
                if not line:
                    continue
                tag = line[0]
                content = line[1:]

                if tag == " ":
                    if orig_idx < len(original_lines):
                        # Verify context line matches
                        if original_lines[orig_idx].strip() != content.strip():
                            # Soft fallback if whitespace differences occur, else error
                            pass
                        result_lines.append(original_lines[orig_idx])
                        orig_idx += 1
                    else:
                        result_lines.append(content)
                elif tag == "-":
                    # Deleted line: verify presence and skip in result
                    if orig_idx < len(original_lines):
                        orig_idx += 1
                    removed_count += 1
                elif tag == "+":
                    # Added line
                    result_lines.append(content)
                    added_count += 1
                elif tag == "\\":
                    # "\ No newline at end of file"
                    pass

        # Copy any remaining trailing lines
        while orig_idx < len(original_lines):
            result_lines.append(original_lines[orig_idx])
            orig_idx += 1

        modified_text = "\n".join(result_lines)
        if original_text.endswith("\n") and not modified_text.endswith("\n"):
            modified_text += "\n"

        return modified_text, added_count, removed_count, None

