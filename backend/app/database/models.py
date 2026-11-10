"""SQLAlchemy models for code chunks, metadata, and pgvector embeddings."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class CodeAnalysisRunModel(Base):
    """Tracks execution status and metrics for repository code analysis runs."""

    __tablename__ = "analysis_runs"

    id = Column(String(128), primary_key=True, index=True)
    repository_id = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    target_type = Column(String(32), nullable=False, default="repository")
    target_path = Column(String(512), nullable=True)
    total_files = Column(Integer, default=0, nullable=False)
    analyzed_files = Column(Integer, default=0, nullable=False)
    total_issues = Column(Integer, default=0, nullable=False)
    critical_count = Column(Integer, default=0, nullable=False)
    high_count = Column(Integer, default=0, nullable=False)
    medium_count = Column(Integer, default=0, nullable=False)
    low_count = Column(Integer, default=0, nullable=False)
    informational_count = Column(Integer, default=0, nullable=False)
    started_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.id,
            "repository_id": self.repository_id,
            "status": self.status,
            "target_type": self.target_type,
            "target_path": self.target_path,
            "total_files": self.total_files,
            "analyzed_files": self.analyzed_files,
            "total_issues": self.total_issues,
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "informational_count": self.informational_count,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


class CodeIssueModel(Base):
    """Persists structured logic bugs, security vulnerabilities, and code smells."""

    __tablename__ = "code_issues"

    id = Column(String(128), primary_key=True, index=True)
    analysis_run_id = Column(String(128), nullable=False, index=True)
    repository_id = Column(String(64), nullable=False, index=True)
    file_path = Column(String(512), nullable=False, index=True)
    language = Column(String(64), nullable=False)
    issue_title = Column(String(256), nullable=False)
    issue_description = Column(Text, nullable=False)
    category = Column(String(64), nullable=False, index=True)
    subcategory = Column(String(64), nullable=True)
    severity = Column(String(32), nullable=False, index=True)
    confidence_score = Column(Float, nullable=False)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    affected_symbol = Column(String(256), nullable=True)
    evidence = Column(Text, nullable=False)
    technical_explanation = Column(Text, nullable=False)
    potential_impact = Column(Text, nullable=False)
    suggested_fix = Column(Text, nullable=False)
    related_files = Column(JSON, nullable=True)
    cwe_id = Column(String(64), nullable=True, index=True)
    detection_method = Column(String(64), default="ast_rag_llm")
    status = Column(String(32), default="Open", nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_id": self.id,
            "analysis_run_id": self.analysis_run_id,
            "repository_id": self.repository_id,
            "file_path": self.file_path,
            "language": self.language,
            "issue_title": self.issue_title,
            "issue_description": self.issue_description,
            "category": self.category,
            "subcategory": self.subcategory,
            "severity": self.severity,
            "confidence_score": self.confidence_score,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "affected_symbol": self.affected_symbol,
            "evidence": self.evidence,
            "technical_explanation": self.technical_explanation,
            "potential_impact": self.potential_impact,
            "suggested_fix": self.suggested_fix,
            "related_files": self.related_files or [],
            "cwe_id": self.cwe_id,
            "detection_method": self.detection_method,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CodeChunkModel(Base):
    """Stores source code chunks with AST metadata and dense vector embeddings."""

    __tablename__ = "code_chunks"

    id = Column(String(128), primary_key=True, index=True)
    repository_id = Column(String(64), nullable=False, index=True)
    file_path = Column(String(512), nullable=False, index=True)
    language = Column(String(64), nullable=False)
    symbol_name = Column(String(256), nullable=True, index=True)
    symbol_type = Column(String(64), nullable=True)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    associated_class_or_function = Column(String(256), nullable=True)
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)
    import_references = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    # 768-dimensional dense vector embedding (matches Gemini text-embedding-004)
    embedding = Column(Vector(768), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        """Converts model to dictionary representation."""
        return {
            "chunk_id": self.id,
            "repository_id": self.repository_id,
            "file_path": self.file_path,
            "language": self.language,
            "symbol_name": self.symbol_name,
            "symbol_type": self.symbol_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "associated_class_or_function": self.associated_class_or_function,
            "content": self.content,
            "content_hash": self.content_hash,
            "import_references": self.import_references or [],
            "metadata_json": self.metadata_json or {},
            "embedding": self.embedding.tolist() if hasattr(self.embedding, "tolist") else self.embedding,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ==============================================================================
# Phase 5: Agentic Planning & Patch Generation Models
# ==============================================================================
class FixPlanModel(Base):
    """Persists structured remediation plans generated by the AI Fix Planning Agent."""

    __tablename__ = "fix_plans"

    id = Column(String(128), primary_key=True, index=True)
    issue_id = Column(String(128), nullable=False, index=True)
    repository_id = Column(String(64), nullable=False, index=True)
    summary = Column(String(512), nullable=False)
    root_cause = Column(Text, nullable=False)
    proposed_solution = Column(Text, nullable=False)
    implementation_steps = Column(JSON, nullable=False)
    affected_files = Column(JSON, nullable=False)
    impact_report = Column(JSON, nullable=True)
    risk_level = Column(String(32), nullable=False, default="Low", index=True)
    expected_behavior = Column(Text, nullable=True)
    recommended_tests = Column(JSON, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "issue_id": self.issue_id,
            "repository_id": self.repository_id,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "proposed_solution": self.proposed_solution,
            "implementation_steps": self.implementation_steps or [],
            "affected_files": self.affected_files or [],
            "impact_report": self.impact_report or {},
            "risk_level": self.risk_level,
            "expected_behavior": self.expected_behavior or "",
            "recommended_tests": self.recommended_tests or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PatchProposalModel(Base):
    """Persists reviewable unified-diff code patch proposals with risk assessments."""

    __tablename__ = "patch_proposals"

    id = Column(String(128), primary_key=True, index=True)
    repository_id = Column(String(64), nullable=False, index=True)
    issue_id = Column(String(128), nullable=False, index=True)
    fix_plan_id = Column(String(128), nullable=False, index=True)
    patch_content = Column(Text, nullable=False)
    affected_files = Column(JSON, nullable=False)
    original_snippets = Column(JSON, nullable=True)
    modified_snippets = Column(JSON, nullable=True)
    lines_added = Column(Integer, default=0, nullable=False)
    lines_removed = Column(Integer, default=0, nullable=False)
    confidence_score = Column(Float, nullable=False, default=0.8)
    risk_level = Column(String(32), nullable=False, default="Low", index=True)
    validation_status = Column(String(32), nullable=False, default="valid", index=True)
    validation_details = Column(JSON, nullable=True)
    review_status = Column(String(32), nullable=False, default="pending_review", index=True)
    workflow_status = Column(String(64), nullable=False, default="awaiting_review")
    regeneration_attempt = Column(Integer, default=0, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "repository_id": self.repository_id,
            "issue_id": self.issue_id,
            "fix_plan_id": self.fix_plan_id,
            "patch_content": self.patch_content,
            "affected_files": self.affected_files or [],
            "original_snippets": self.original_snippets or {},
            "modified_snippets": self.modified_snippets or {},
            "lines_added": self.lines_added,
            "lines_removed": self.lines_removed,
            "confidence_score": self.confidence_score,
            "risk_level": self.risk_level,
            "validation_status": self.validation_status,
            "validation_details": self.validation_details or {},
            "review_status": self.review_status,
            "workflow_status": self.workflow_status,
            "regeneration_attempt": self.regeneration_attempt,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PatchReviewModel(Base):
    """Tracks human review decisions and feedback on proposed patches."""

    __tablename__ = "patch_reviews"

    id = Column(String(128), primary_key=True, index=True)
    patch_id = Column(String(128), nullable=False, index=True)
    decision = Column(String(32), nullable=False)
    reviewer_feedback = Column(Text, nullable=True)
    reviewed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "patch_id": self.patch_id,
            "decision": self.decision,
            "reviewer_feedback": self.reviewer_feedback,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
        }


# ==============================================================================
# Phase 6: Docker Sandbox Execution Models
# ==============================================================================
class SandboxExecutionModel(Base):
    """Persists containerized execution runs, automated test comparisons, and logs."""

    __tablename__ = "sandbox_executions"

    id = Column(String(128), primary_key=True, index=True)
    repository_id = Column(String(64), nullable=False, index=True)
    patch_id = Column(String(128), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="PENDING", index=True)
    language = Column(String(64), nullable=False, default="python")
    container_id = Column(String(128), nullable=True)
    patch_applied = Column(Integer, default=0, nullable=False)
    modified_files = Column(JSON, nullable=True)
    dependencies_installed = Column(Integer, default=0, nullable=False)
    baseline_result = Column(JSON, nullable=True)
    patched_result = Column(JSON, nullable=True)
    comparison = Column(JSON, nullable=True)
    duration_seconds = Column(Float, default=0.0, nullable=False)
    logs = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "repository_id": self.repository_id,
            "patch_id": self.patch_id,
            "status": self.status,
            "language": self.language,
            "container_id": self.container_id,
            "patch_applied": bool(self.patch_applied),
            "modified_files": self.modified_files or [],
            "dependencies_installed": bool(self.dependencies_installed),
            "baseline_result": self.baseline_result,
            "patched_result": self.patched_result,
            "comparison": self.comparison,
            "duration_seconds": self.duration_seconds,
            "logs": self.logs or "",
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


