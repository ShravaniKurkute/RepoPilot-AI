"""Patch application engine executing deterministic in-container unified-diff application."""

import io
import json
from pathlib import Path
import tarfile
from typing import List, Optional, Tuple

from app.core.logging import logger
from app.sandbox.container_manager import DockerSandboxContainer


# Self-contained in-container patch applier script
IN_CONTAINER_PATCH_SCRIPT = r'''
import sys
import os
import json
import re

def parse_and_apply(diff_path, workspace_root="/workspace"):
    if not os.path.exists(diff_path):
        sys.stderr.write(f"Diff file not found: {diff_path}\n")
        sys.exit(1)

    with open(diff_path, "r", encoding="utf-8", errors="replace") as f:
        diff_text = f.read()

    lines = diff_text.splitlines()
    i = 0
    modified_files = []

    while i < len(lines):
        line = lines[i]
        if line.startswith("--- a/") or line.startswith("--- "):
            old_path = line[6:].strip() if line.startswith("--- a/") else line[4:].strip()
            i += 1
            if i >= len(lines):
                break
            line2 = lines[i]
            if not (line2.startswith("+++ b/") or line2.startswith("+++ ")):
                i += 1
                continue
            new_path = line2[6:].strip() if line2.startswith("+++ b/") else line2[4:].strip()
            target_rel = new_path if new_path != "/dev/null" else old_path
            target_full = os.path.join(workspace_root, target_rel.replace("\\", "/").strip("/"))

            # Security check: prevent escaping workspace
            norm_target = os.path.abspath(target_full)
            norm_root = os.path.abspath(workspace_root)
            if not norm_target.startswith(norm_root):
                sys.stderr.write(f"Security error: Target path '{target_rel}' escapes workspace root\n")
                sys.exit(2)

            if not os.path.exists(norm_target):
                sys.stderr.write(f"Error: Target file does not exist: {target_rel}\n")
                sys.exit(3)

            with open(norm_target, "r", encoding="utf-8", errors="replace") as tf:
                source_lines = tf.read().splitlines()

            i += 1
            hunks = []
            while i < len(lines):
                if lines[i].startswith("--- "):
                    break
                if lines[i].startswith("@@"):
                    hunk_header = lines[i]
                    i += 1
                    hunk_lines = []
                    while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("--- "):
                        hunk_lines.append(lines[i])
                        i += 1
                    hunks.append((hunk_header, hunk_lines))
                else:
                    i += 1

            # Apply hunks to source_lines
            current_lines = list(source_lines)
            offset = 0

            for header, h_lines in hunks:
                m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", header)
                if not m:
                    sys.stderr.write(f"Malformed hunk header: {header}\n")
                    sys.exit(4)

                old_start = int(m.group(1))
                hunk_idx = max(0, old_start - 1 + offset)

                # Collect expected old lines and replacement new lines
                expected_old = []
                replacement = []
                for hl in h_lines:
                    if hl.startswith("-"):
                        expected_old.append(hl[1:])
                    elif hl.startswith("+"):
                        replacement.append(hl[1:])
                    elif hl.startswith(" "):
                        expected_old.append(hl[1:])
                        replacement.append(hl[1:])
                    elif hl == "":
                        expected_old.append("")
                        replacement.append("")

                # Search around hunk_idx for matching context
                matched_idx = -1
                search_radius = 50
                best_idx = hunk_idx

                # Check exact position first
                sub = current_lines[hunk_idx : hunk_idx + len(expected_old)]
                if sub == expected_old:
                    matched_idx = hunk_idx
                else:
                    # Search within radius
                    for d in range(1, search_radius + 1):
                        for candidate in (hunk_idx + d, hunk_idx - d):
                            if 0 <= candidate <= len(current_lines) - len(expected_old):
                                if current_lines[candidate : candidate + len(expected_old)] == expected_old:
                                    matched_idx = candidate
                                    break
                        if matched_idx != -1:
                            break

                if matched_idx == -1:
                    sys.stderr.write(f"Failed to match context for hunk in {target_rel}: {header}\n")
                    sys.exit(5)

                # Replace lines
                current_lines[matched_idx : matched_idx + len(expected_old)] = replacement
                offset += len(replacement) - len(expected_old)

            # Write updated file
            with open(norm_target, "w", encoding="utf-8") as wf:
                wf.write("\n".join(current_lines) + "\n")

            modified_files.append(target_rel)
        else:
            i += 1

    print(json.dumps(modified_files))

if __name__ == "__main__":
    diff_file = sys.argv[1] if len(sys.argv) > 1 else "/workspace/patch.diff"
    parse_and_apply(diff_file)
'''


class PatchApplicationResult:
    """Outcome of patch application inside container."""

    def __init__(
        self,
        success: bool,
        modified_files: List[str],
        error_message: Optional[str] = None,
        stdout: str = "",
        stderr: str = "",
    ):
        self.success = success
        self.modified_files = modified_files
        self.error_message = error_message
        self.stdout = stdout
        self.stderr = stderr


class InContainerPatchApplier:
    """Injects and applies patches inside isolated Docker containers."""

    async def apply_patch(
        self,
        container: DockerSandboxContainer,
        patch_diff: str,
        target_workdir: str = "/workspace",
    ) -> PatchApplicationResult:
        """Transfers patch and applier into container and applies changes safely."""
        if not patch_diff or not patch_diff.strip():
            return PatchApplicationResult(
                success=False,
                modified_files=[],
                error_message="Patch diff content is empty.",
            )

        logger.info("[PatchApplier] Injecting patch into container %s...", container.short_id)

        # Create tar with patch.diff and _apply_patch.py
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w") as tar:
            # Add patch.diff
            diff_bytes = patch_diff.encode("utf-8")
            diff_info = tarfile.TarInfo(name="patch.diff")
            diff_info.size = len(diff_bytes)
            tar.addfile(diff_info, io.BytesIO(diff_bytes))

            # Add _apply_patch.py
            script_bytes = IN_CONTAINER_PATCH_SCRIPT.encode("utf-8")
            script_info = tarfile.TarInfo(name="_apply_patch.py")
            script_info.size = len(script_bytes)
            tar.addfile(script_info, io.BytesIO(script_bytes))

        tar_buf.seek(0)
        container.put_tar_bytes(target_workdir, tar_buf.getvalue())

        # Execute application script inside container using container python
        cmd = ["python3", f"{target_workdir}/_apply_patch.py", f"{target_workdir}/patch.diff"]
        res = await container.exec_command(cmd, workdir=target_workdir, timeout=20.0)

        # Cleanup patch artifacts inside container
        await container.exec_command(
            ["rm", "-f", f"{target_workdir}/patch.diff", f"{target_workdir}/_apply_patch.py"],
            workdir=target_workdir,
        )

        if res.exit_code != 0:
            err_msg = res.stderr.strip() or f"Patch application failed with exit code {res.exit_code}"
            logger.warning("[PatchApplier] Patch application rejected inside container: %s", err_msg)
            return PatchApplicationResult(
                success=False,
                modified_files=[],
                error_message=err_msg,
                stdout=res.stdout,
                stderr=res.stderr,
            )

        try:
            modified = json.loads(res.stdout.strip())
            if not isinstance(modified, list):
                modified = []
        except Exception:
            modified = []

        logger.info(
            "[PatchApplier] Patch applied successfully inside container %s (modified: %s)",
            container.short_id,
            modified,
        )
        return PatchApplicationResult(
            success=True,
            modified_files=modified,
            stdout=res.stdout,
            stderr=res.stderr,
        )


patch_applier = InContainerPatchApplier()

