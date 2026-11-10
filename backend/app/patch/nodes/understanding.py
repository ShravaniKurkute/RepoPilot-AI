"""Issue Understanding Node: verifies issue veracity against active repository code."""

import hashlib
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings
from app.core.logging import logger
from app.patch.state import AgentWorkflowState
from app.repository.service import repository_service


async def understand_issue_node(state: AgentWorkflowState) -> Dict[str, Any]:
    """Inspects target source code, asserts that the reported issue still exists, and computes snapshot hash."""
    repo_id = state.get("repository_id")
    issue_data = state.get("issue_data") or {}
    rel_path = issue_data.get("file_path") or state.get("target_file_path")

    if not rel_path:
        return {
            "workflow_status": "failed",
            "error_details": "Target file path missing from issue context.",
        }

    storage_root = repository_service.storage_root
    source_dir = storage_root / repo_id / "source"
    if not source_dir.exists():
        source_dir = storage_root / repo_id

    full_path = (source_dir / rel_path.replace("\\", "/").strip("/")).resolve()

    # Workspace boundary & existence check
    try:
        full_path.relative_to(source_dir.resolve())
    except ValueError:
        return {
            "workflow_status": "failed",
            "error_details": f"Target path '{rel_path}' is outside repository workspace.",
        }

    if not full_path.is_file():
        return {
            "workflow_status": "failed",
            "error_details": f"Target source file '{rel_path}' does not exist in repository.",
        }

    try:
        source_code = full_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {
            "workflow_status": "failed",
            "error_details": f"Failed to read source code for '{rel_path}': {e}",
        }

    # Verify that the reported bug evidence still exists in the source code
    evidence = (issue_data.get("evidence") or "").strip()
    evidence_found = True
    if evidence:
        first_ev_line = evidence.splitlines()[0].strip()
        if first_ev_line and first_ev_line not in source_code:
            evidence_found = False

    if not evidence_found:
        logger.warning("Issue '%s' in '%s' appears outdated: evidence not found in source code.", state.get("issue_id"), rel_path)
        return {
            "workflow_status": "issue_outdated",
            "error_details": (
                f"Source code has changed since analysis. The reported issue evidence '{evidence[:80]}' "
                f"is no longer present in '{rel_path}'."
            ),
        }

    # Compute source snapshot hash (SHA-256)
    source_hash = hashlib.sha256(source_code.encode("utf-8")).hexdigest()

    return {
        "target_file_path": rel_path,
        "source_code_snapshot": source_code,
        "source_snapshot_hash": source_hash,
        "workflow_status": "retrieving_context",
    }
