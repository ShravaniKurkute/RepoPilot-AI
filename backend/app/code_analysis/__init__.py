"""Syntactic and semantic code intelligence package.

Provides:
- Python AST symbol extraction (classes, functions, calls)
- Tree-sitter multi-language syntax tree parsing
- Import dependency graph generation and circular dependency detection
- Call graph resolution
- Central CodeAnalysisService
"""

from app.code_analysis.call_graph import CallGraphResolver
from app.code_analysis.dependency_resolver import DependencyResolver
from app.code_analysis.parser_manager import parse_source_file
from app.code_analysis.python_parser import parse_python_source
from app.code_analysis.schemas import (
    CallGraphEdge,
    FileAnalysisResult,
    FileDependency,
    ImportStatement,
    RepositoryAnalysisResponse,
    RepositoryAnalysisSummary,
    SourceLocation,
    Symbol,
)
from app.code_analysis.service import CodeAnalysisService, code_analysis_service
from app.code_analysis.tree_sitter_parser import parse_tree_sitter_source

__all__ = [
    "CallGraphEdge",
    "CallGraphResolver",
    "CodeAnalysisService",
    "DependencyResolver",
    "FileAnalysisResult",
    "FileDependency",
    "ImportStatement",
    "RepositoryAnalysisResponse",
    "RepositoryAnalysisSummary",
    "SourceLocation",
    "Symbol",
    "code_analysis_service",
    "parse_python_source",
    "parse_source_file",
    "parse_tree_sitter_source",
]
