"""Parser manager for dispatching files to appropriate AST parsers."""

import os
from typing import Optional

from app.code_analysis.python_parser import parse_python_source
from app.code_analysis.schemas import FileAnalysisResult
from app.code_analysis.tree_sitter_parser import parse_tree_sitter_source
from app.repository.language_detector import detect_language_by_extension

# Languages supported for AST parsing
PARSER_SUPPORTED_LANGUAGES = {
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "C",
    "C++",
    "Go",
    "Rust",
    "PHP",
    "Ruby",
}


def parse_source_file(file_path: str, source_code: str) -> FileAnalysisResult:
    """Dispatches a source file to the appropriate parser based on language detection.

    Args:
        file_path: Relative repository file path.
        source_code: Source code content.

    Returns:
        FileAnalysisResult with extracted symbols, imports, calls, and status.
    """
    total_lines = len(source_code.splitlines())
    language = detect_language_by_extension(file_path)

    if not language:
        # Check by filename extension fallback
        _, ext = os.path.splitext(file_path)
        if ext in (".ts", ".mts", ".cts"):
            language = "TypeScript"
        elif ext == ".tsx":
            language = "TypeScript"
        elif ext in (".js", ".mjs", ".cjs", ".jsx"):
            language = "JavaScript"
        elif ext in (".py", ".pyw"):
            language = "Python"

    if not language or language not in PARSER_SUPPORTED_LANGUAGES:
        return FileAnalysisResult(
            file_path=file_path,
            language=language or "Unknown",
            status="unsupported",
            error_message=f"No AST parser available for language: {language or 'Unknown'}",
            symbols=[],
            imports=[],
            function_calls=[],
            total_lines=total_lines,
        )

    # Python AST analysis using native ast module
    if language == "Python":
        result = parse_python_source(file_path, source_code)
        # If syntax error occurred with native ast, attempt tree-sitter partial recovery
        if result.status == "syntax_error":
            ts_res = parse_tree_sitter_source(file_path, source_code, "Python")
            if ts_res.status == "success" and (ts_res.symbols or ts_res.imports):
                ts_res.error_message = f"Parsed with partial Tree-sitter recovery: {result.error_message}"
                return ts_res
        return result

    # Polyglot analysis using Tree-sitter
    # Special handle .tsx extension as language 'tsx' for grammar loading
    target_lang = "tsx" if file_path.endswith(".tsx") else language
    return parse_tree_sitter_source(file_path, source_code, target_lang)

