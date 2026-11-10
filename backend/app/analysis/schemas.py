"""Pydantic schemas for AI-powered code analysis, bug detection, and security issues."""

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

IssueSeverity = Literal["Critical", "High", "Medium", "Low", "Informational"]
IssueCategory = Literal["logic_bug", "security_vulnerability", "code_smell"]
IssueStatus = Literal["Open", "Confirmed", "False Positive", "Resolved", "Ignored"]


class CodeIssue(BaseModel):
    """Structured code issue identified by AI code analysis."""

    issue_id: str = Field(..., description="Unique deterministic issue identifier")
    repository_id: str = Field(..., description="Repository ID")
    analysis_run_id: str = Field(..., description="Associated analysis run ID")
    file_path: str = Field(..., description="Relative repository file path")
    language: str = Field(..., description="Programming language")
    issue_title: str = Field(..., description="Short descriptive title of the issue")
    issue_description: str = Field(..., description="High-level description of what is wrong")
    category: IssueCategory = Field(
        ..., description="Category: 'logic_bug', 'security_vulnerability', or 'code_smell'"
    )
    subcategory: Optional[str] = Field(
        None, description="Detailed subcategory (e.g. 'sql_injection', 'off_by_one', 'dead_code')"
    )
    severity: IssueSeverity = Field(
        ..., description="Severity level: 'Critical', 'High', 'Medium', 'Low', 'Informational'"
    )
    confidence_score: float = Field(
        ..., ge=0.0, le=1.0, description="Numerical confidence between 0.0 and 1.0"
    )
    start_line: int = Field(..., ge=1, description="1-based starting line of the issue")
    end_line: int = Field(..., ge=1, description="1-based ending line of the issue")
    affected_symbol: Optional[str] = Field(
        None, description="Name of affected function, method, class, or variable"
    )
    evidence: str = Field(..., description="Exact code snippet demonstrating the problem")
    technical_explanation: str = Field(
        ..., description="Deep architectural and control-flow explanation of why this is a bug"
    )
    potential_impact: str = Field(
        ..., description="Potential security, data integrity, or runtime impact"
    )
    suggested_fix: str = Field(
        ..., description="Concrete code or architectural remediation advice"
    )
    related_files: List[str] = Field(
        default_factory=list, description="Other repository files related to this issue"
    )
    cwe_id: Optional[str] = Field(
        None, description="Common Weakness Enumeration ID (e.g. 'CWE-89' for SQLi)"
    )
    detection_method: str = Field(
        default="ast_rag_llm",
        description="Method used to detect issue ('ast_rag_llm', 'ast_heuristic', etc.)",
    )
    status: IssueStatus = Field(
        default="Open",
        description="Triage status: 'Open', 'Confirmed', 'False Positive', 'Resolved', 'Ignored'",
    )
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp",
    )


class AnalysisRun(BaseModel):
    """Execution status and aggregated statistics of an analysis run."""

    run_id: str = Field(..., description="Unique run identifier")
    repository_id: str = Field(..., description="Repository ID")
    status: Literal["pending", "running", "completed", "failed", "timed_out"] = Field(
        ..., description="Current status of the analysis run"
    )
    current_stage: Optional[str] = Field(
        "Initializing",
        description="Current lifecycle stage: 'Discovering Files', 'Extracting Source Code', 'Generating Code Chunks', 'Generating Embeddings', 'Building Vector Index', 'Running AI Analysis', 'Analysis Completed', 'Analysis Failed'",
    )
    stage_message: Optional[str] = Field(None, description="Detailed stage progress description")
    target_type: Literal["repository", "file", "symbol"] = Field(
        default="repository", description="Scope of the analysis"
    )
    target_path: Optional[str] = Field(
        None, description="Target file path or symbol name if target_type is not 'repository'"
    )
    total_files: int = Field(0, ge=0, description="Total files to analyze")
    analyzed_files: int = Field(0, ge=0, description="Files processed so far")
    total_issues: int = Field(0, ge=0, description="Total detected issues")
    critical_count: int = Field(0, ge=0, description="Count of Critical issues")
    high_count: int = Field(0, ge=0, description="Count of High issues")
    medium_count: int = Field(0, ge=0, description="Count of Medium issues")
    low_count: int = Field(0, ge=0, description="Count of Low issues")
    informational_count: int = Field(0, ge=0, description="Count of Informational findings")
    started_at: str = Field(..., description="ISO 8601 timestamp of run start")
    completed_at: Optional[str] = Field(None, description="ISO 8601 timestamp of completion")
    error_message: Optional[str] = Field(None, description="Error detail if run failed")


class AnalyzeFileRequest(BaseModel):
    """Request payload to analyze a specific source file."""

    file_path: str = Field(..., min_length=1, description="Relative repository file path to analyze")
    categories: Optional[List[IssueCategory]] = Field(
        None, description="Optional categories to restrict analysis to"
    )


class AnalyzeFunctionRequest(BaseModel):
    """Request payload to analyze an individual function or symbol."""

    file_path: str = Field(..., min_length=1, description="Relative file path")
    symbol_name: str = Field(..., min_length=1, description="Target function or class name")


class UpdateIssueStatusRequest(BaseModel):
    """Request payload to change issue triage status."""

    status: IssueStatus = Field(
        ..., description="New status: 'Open', 'Confirmed', 'False Positive', 'Resolved', 'Ignored'"
    )
    notes: Optional[str] = Field(None, description="Optional triage note or reasoning")


class IssueListResponse(BaseModel):
    """Paginated or filtered list of detected code issues."""

    repository_id: str = Field(..., description="Repository ID")
    total_issues: int = Field(..., ge=0, description="Total issues matching criteria")
    severity_breakdown: Dict[str, int] = Field(
        default_factory=dict, description="Counts by severity level"
    )
    category_breakdown: Dict[str, int] = Field(
        default_factory=dict, description="Counts by category"
    )
    issues: List[CodeIssue] = Field(default_factory=list, description="List of issues")


class AnalysisRunStatusResponse(BaseModel):
    """Analysis run status payload."""

    run: AnalysisRun
    recent_issues: List[CodeIssue] = Field(
        default_factory=list, description="Sample of latest issues discovered in this run"
    )

