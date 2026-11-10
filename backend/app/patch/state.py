"""LangGraph state representation for the Agentic Planning & Patch Generation workflow."""

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict


class AgentWorkflowState(TypedDict, total=False):
    """Strongly typed state passed through LangGraph nodes."""

    repository_id: str
    issue_id: str
    analysis_run_id: Optional[str]
    issue_data: Optional[Dict[str, Any]]
    target_file_path: Optional[str]
    source_code_snapshot: Optional[str]
    source_snapshot_hash: Optional[str]
    retrieved_context: Optional[Dict[str, Any]]
    affected_symbols: Optional[List[Dict[str, Any]]]
    fix_plan: Optional[Dict[str, Any]]
    impact_report: Optional[Dict[str, Any]]
    generated_patches: Optional[str]
    original_snippets: Optional[Dict[str, str]]
    modified_snippets: Optional[Dict[str, str]]
    lines_added: int
    lines_removed: int
    validation_results: Optional[Dict[str, Any]]
    risk_assessment: Optional[Dict[str, Any]]
    confidence_score: float
    workflow_status: str
    human_feedback: Optional[str]
    regeneration_count: int
    max_regenerations: int
    error_details: Optional[str]

