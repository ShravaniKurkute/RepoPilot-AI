"""Patch Validation Node: invokes deterministic validator and checks hunk veracity."""

from pathlib import Path
from typing import Any, Dict

from app.core.config import settings
from app.patch.state import AgentWorkflowState
from app.patch.validator import PatchValidator


async def validate_patch_node(state: AgentWorkflowState) -> Dict[str, Any]:
    """Validates unified diff syntax, path bounds, and simulates hunk application."""
    repo_id = state["repository_id"]
    diff_text = state.get("generated_patches") or ""
    target_file = state.get("target_file_path")

    from app.repository.service import repository_service
    storage_root = repository_service.storage_root
    source_dir = storage_root / repo_id / "source"
    if not source_dir.exists():
        source_dir = storage_root / repo_id

    validator = PatchValidator(repo_root=source_dir)
    res = validator.validate_patch(diff_text=diff_text, expected_target_file=target_file)

    val_dict = {
        "is_valid": res.is_valid,
        "syntax_valid": res.is_valid or "syntax" not in (res.error_message or "").lower(),
        "paths_safe": "traversal" not in (res.error_message or "").lower(),
        "files_exist": "exist" not in (res.error_message or "").lower(),
        "can_apply_cleanly": res.is_valid,
        "error_message": res.error_message,
        "hunks_count": res.hunks_count,
    }

    if not res.is_valid:
        return {
            "validation_results": val_dict,
            "workflow_status": "patch_invalid",
            "error_details": res.error_message,
        }

    return {
        "validation_results": val_dict,
        "lines_added": res.lines_added,
        "lines_removed": res.lines_removed,
        "original_snippets": res.original_snippets,
        "modified_snippets": res.modified_snippets,
        "workflow_status": "assessing_risk",
    }
