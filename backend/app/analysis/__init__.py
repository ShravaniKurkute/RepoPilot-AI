"""AI-Powered Code Analysis & Bug Detection Package (Phase 4).

Provides:
- AI code analyzer interfacing with Google Gemini and offline heuristic mock
- Context builder combining Phase 2 AST symbols and Phase 3 RAG hybrid retrieval
- CWE taxonomy classification and severity normalization
- Confidence validation and finding deduplication
- BugDetectionService orchestrator
"""

from app.analysis.analyzer import (
    BaseCodeAnalyzer,
    GeminiCodeAnalyzer,
    MockCodeAnalyzer,
    get_code_analyzer,
)
from app.analysis.confidence import ConfidenceValidator, default_confidence_validator
from app.analysis.context_builder import AnalysisContext, AnalysisContextBuilder, default_context_builder
from app.analysis.issue_classifier import IssueClassifier, default_classifier
from app.analysis.schemas import (
    AnalysisRun,
    AnalysisRunStatusResponse,
    AnalyzeFileRequest,
    AnalyzeFunctionRequest,
    CodeIssue,
    IssueCategory,
    IssueListResponse,
    IssueSeverity,
    IssueStatus,
    UpdateIssueStatusRequest,
)
from app.analysis.service import BugDetectionService, bug_detection_service

__all__ = [
    "AnalysisContext",
    "AnalysisContextBuilder",
    "AnalysisRun",
    "AnalysisRunStatusResponse",
    "AnalyzeFileRequest",
    "AnalyzeFunctionRequest",
    "BaseCodeAnalyzer",
    "BugDetectionService",
    "CodeIssue",
    "ConfidenceValidator",
    "GeminiCodeAnalyzer",
    "IssueCategory",
    "IssueClassifier",
    "IssueListResponse",
    "IssueSeverity",
    "IssueStatus",
    "MockCodeAnalyzer",
    "UpdateIssueStatusRequest",
    "bug_detection_service",
    "default_classifier",
    "default_confidence_validator",
    "default_context_builder",
    "get_code_analyzer",
]

