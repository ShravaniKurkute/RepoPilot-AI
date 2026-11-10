"""Pydantic schemas for code intelligence, AST parsing, symbols, dependencies, and call graphs."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SourceLocation(BaseModel):
    """Source code coordinates within a file (1-based line numbers)."""

    start_line: int = Field(..., ge=1, description="1-based starting line number")
    end_line: int = Field(..., ge=1, description="1-based ending line number")
    start_column: int = Field(..., ge=1, description="1-based starting column number")
    end_column: int = Field(..., ge=1, description="1-based ending column number")


class Symbol(BaseModel):
    """Extracted structural code symbol (function, class, interface, method, etc.)."""

    id: str = Field(..., description="Unique deterministic symbol ID (e.g. file::name::line)")
    name: str = Field(..., description="Symbol name (e.g. function or class name)")
    symbol_type: str = Field(
        ...,
        description="Type of symbol: function, class, method, interface, struct, enum, variable, import, export, namespace",
    )
    file_path: str = Field(..., description="Relative repository path of the source file")
    location: SourceLocation = Field(..., description="Source code location")
    parent_symbol_id: Optional[str] = Field(None, description="Parent symbol ID if nested (e.g. class of a method)")
    language: str = Field(..., description="Programming language of the source file")
    parameters: Optional[List[str]] = Field(default_factory=list, description="Function or method parameter names")
    return_type: Optional[str] = Field(None, description="Annotated return type if present")
    decorators: Optional[List[str]] = Field(default_factory=list, description="Applied decorators")
    visibility: Optional[str] = Field(None, description="'public', 'private', or 'protected'")
    docstring: Optional[str] = Field(None, description="Extracted docstring or leading comment")
    is_async: bool = Field(default=False, description="True if function is asynchronous")


class ImportStatement(BaseModel):
    """Structured representation of an import or dependency declaration."""

    source_file: str = Field(..., description="File containing the import statement")
    statement: str = Field(..., description="Exact raw import statement code")
    module: str = Field(..., description="Imported module or target package")
    names: List[str] = Field(default_factory=list, description="Imported symbols or '*'")
    aliases: Dict[str, str] = Field(default_factory=dict, description="Symbol alias mapping")
    is_relative: bool = Field(default=False, description="True for relative imports (e.g. .utils)")
    resolved_target_file: Optional[str] = Field(
        None, description="Relative repo path of target file if locally resolved"
    )
    import_type: str = Field(
        ..., description="'local' (in-repo), 'external' (third-party/stdlib), or 'unresolved'"
    )
    line_number: int = Field(..., ge=1, description="1-based line number of import statement")


class CallGraphEdge(BaseModel):
    """Represents a caller-to-callee function or method invocation."""

    id: str = Field(..., description="Unique ID for this call edge")
    caller_id: str = Field(..., description="Symbol ID of the caller function or file scope")
    caller_name: str = Field(..., description="Name of calling function or '<module>'")
    caller_file: str = Field(..., description="File path of the caller")
    callee_name: str = Field(..., description="Name of the called function or method")
    resolved_callee_id: Optional[str] = Field(
        None, description="Symbol ID of called function if locally resolved"
    )
    resolved_callee_file: Optional[str] = Field(
        None, description="File path of called function if locally resolved"
    )
    is_resolved: bool = Field(default=False, description="True if statically resolved to a local symbol")
    line_number: int = Field(..., ge=1, description="1-based line number where the call occurs")


class FileAnalysisResult(BaseModel):
    """Analysis output for an individual source code file."""

    file_path: str = Field(..., description="Relative repository path")
    language: str = Field(..., description="Identified language")
    status: str = Field(..., description="'success', 'syntax_error', or 'unsupported'")
    error_message: Optional[str] = Field(None, description="Error detail if parsing failed")
    symbols: List[Symbol] = Field(default_factory=list, description="Extracted symbols")
    imports: List[ImportStatement] = Field(default_factory=list, description="Extracted imports")
    function_calls: List[CallGraphEdge] = Field(default_factory=list, description="Extracted calls")
    total_lines: int = Field(0, ge=0, description="Total lines in source file")


class FileDependency(BaseModel):
    """Dependency relationships for a specific file."""

    file_path: str = Field(..., description="Relative repository path")
    depends_on: List[str] = Field(
        default_factory=list, description="Local repository files directly imported by this file"
    )
    imported_by: List[str] = Field(
        default_factory=list, description="Local repository files that import this file"
    )
    external_dependencies: List[str] = Field(
        default_factory=list, description="External package/library dependencies"
    )
    unresolved_imports: List[str] = Field(
        default_factory=list, description="Imports that could not be resolved to local or standard libraries"
    )


class RepositoryAnalysisSummary(BaseModel):
    """Aggregated statistics for repository code intelligence."""

    repository_id: str = Field(..., description="Unique repository UUID")
    total_files_scanned: int = Field(0, ge=0, description="Total files evaluated")
    successfully_parsed_files: int = Field(0, ge=0, description="Files successfully parsed")
    failed_files: int = Field(0, ge=0, description="Files with syntax or parse errors")
    unsupported_files: int = Field(0, ge=0, description="Files in unsupported languages")
    total_symbols: int = Field(0, ge=0, description="Total symbols extracted")
    total_functions: int = Field(0, ge=0, description="Total functions and methods")
    total_classes: int = Field(0, ge=0, description="Total classes and interfaces")
    total_imports: int = Field(0, ge=0, description="Total import statements")
    total_call_edges: int = Field(0, ge=0, description="Total function calls recorded")
    resolved_call_edges: int = Field(0, ge=0, description="Statically resolved function calls")
    has_circular_dependencies: bool = Field(default=False, description="True if circular imports detected")
    circular_dependency_cycles: List[List[str]] = Field(default_factory=list, description="Identified dependency cycles")
    languages_analyzed: List[str] = Field(default_factory=list, description="Unique languages analyzed")
    analyzed_at: str = Field(..., description="ISO 8601 timestamp of analysis completion")


class RepositoryAnalysisResponse(BaseModel):
    """Complete code intelligence payload for a repository."""

    summary: RepositoryAnalysisSummary
    symbols: List[Symbol]
    dependencies: Dict[str, FileDependency]
    call_graph: List[CallGraphEdge]
    files: Dict[str, FileAnalysisResult]

