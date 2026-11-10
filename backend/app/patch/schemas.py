"""Pydantic schemas for Phase 5: Agentic Planning & Patch Generation."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

RiskLevel = Literal["Low", "Medium", "High", "Critical"]
ValidationStatus = Literal["valid", "invalid", "rejected"]
ReviewStatus = Literal["pending_review", "approved", "rejected"]
ReviewDecision = Literal["approved", "rejected", "regeneration_requested"]

WorkflowStatus = Literal[
    "pending",
    "understanding_issue",
    "retrieving_context",
    "planning_fix",
    "analyzing_impact",
    "generating_patch",
    "validating_patch",
    "awaiting_review",
    "approved",
    "rejected",
    "failed",
]


class FixPlan(BaseModel):
    """Structured remediation plan created by the planning agent."""

    id: str = Field(..., description="Unique plan ID")
    issue_id: str = Field(..., description="Target issue ID")
    repository_id: str = Field(..., description="Target repository ID")
    summary: str = Field(..., description="High-level summary of the bug and fix")
    root_cause: str = Field(..., description="Root cause explanation")
    proposed_solution: str = Field(..., description="Proposed technical solution")
    implementation_steps: List[str] = Field(default_factory=list, description="Step-by-step implementation plan")
    affected_files: List[str] = Field(default_factory=list, description="List of repository files to be modified")
    impact_report: Dict[str, Any] = Field(default_factory=dict, description="Impact and dependency analysis findings")
    risk_level: RiskLevel = Field(default="Low", description="Risk assessment: Low, Medium, High, Critical")
    expected_behavior: str = Field(default="", description="Expected repository behavior post-fix")
    recommended_tests: List[str] = Field(default_factory=list, description="Recommended unit or integration tests")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )


class ValidationDetail(BaseModel):
    """Deterministic validation results for a generated patch."""

    is_valid: bool = Field(..., description="Whether the patch passed all checks")
    syntax_valid: bool = Field(..., description="Whether unified-diff syntax is valid")
    paths_safe: bool = Field(..., description="Whether all paths are within repository boundary")
    files_exist: bool = Field(..., description="Whether modified files exist")
    can_apply_cleanly: bool = Field(..., description="Whether hunk line context matches cleanly")
    error_message: Optional[str] = Field(None, description="Detailed validation failure explanation")
    hunks_count: int = Field(0, description="Number of parsed diff hunks")


class PatchProposal(BaseModel):
    """Reviewable code patch proposal with diff hunks and risk analysis."""

    id: str = Field(..., description="Unique patch ID")
    repository_id: str = Field(..., description="Repository ID")
    issue_id: str = Field(..., description="Associated issue ID")
    fix_plan_id: str = Field(..., description="Associated fix plan ID")
    patch_content: str = Field(..., description="Full unified-diff patch string")
    affected_files: List[str] = Field(default_factory=list, description="Files affected by the patch")
    original_snippets: Dict[str, str] = Field(default_factory=dict, description="Original target file contents")
    modified_snippets: Dict[str, str] = Field(default_factory=dict, description="Modified target file contents")
    lines_added: int = Field(0, description="Count of added lines (+)")
    lines_removed: int = Field(0, description="Count of removed lines (-)")
    confidence_score: float = Field(0.8, ge=0.0, le=1.0, description="Agent confidence score")
    risk_level: RiskLevel = Field(default="Low", description="Assessed risk level")
    validation_status: ValidationStatus = Field(default="valid", description="Deterministic validation status")
    validation_details: Dict[str, Any] = Field(default_factory=dict, description="Granular validation check results")
    review_status: ReviewStatus = Field(default="pending_review", description="Human review status")
    workflow_status: str = Field(default="awaiting_review", description="Workflow state")
    regeneration_attempt: int = Field(0, description="Regeneration count")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )


class PatchReview(BaseModel):
    """Human review decision on a proposed patch."""

    id: str = Field(..., description="Review ID")
    patch_id: str = Field(..., description="Associated patch ID")
    decision: ReviewDecision = Field(..., description="Review decision")
    reviewer_feedback: Optional[str] = Field(None, description="Reviewer feedback or notes")
    reviewed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )


# Request and Response Schemas
class PatchReviewRequest(BaseModel):
    """Payload to approve, reject, or request regeneration of a patch proposal."""

    decision: ReviewDecision = Field(..., description="'approved', 'rejected', or 'regeneration_requested'")
    reviewer_feedback: Optional[str] = Field(None, description="Optional notes or feedback for regeneration")


class RegeneratePatchRequest(BaseModel):
    """Payload to request patch regeneration with guidance."""

    feedback: Optional[str] = Field(None, description="Guidance or correction instructions for the patch generator")


class GeneratePatchRequest(BaseModel):
    """Payload to trigger patch generation."""

    feedback: Optional[str] = Field(None, description="Optional user guidance")


class PatchProposalListResponse(BaseModel):
    """Collection of patch proposals for a repository."""

    repository_id: str
    total_patches: int
    patches: List[PatchProposal]


class WorkflowStatusResponse(BaseModel):
    """Live status report of an agentic patch generation workflow."""

    patch_id: Optional[str] = None
    repository_id: str
    issue_id: str
    status: str
    review_status: Optional[str] = None
    validation_status: Optional[str] = None
    risk_level: Optional[str] = None
    lines_added: int = 0
    lines_removed: int = 0
    current_step: Optional[str] = None
    regeneration_attempt: int = 0
    error_details: Optional[str] = None
