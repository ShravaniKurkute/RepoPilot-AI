"""Multi-language AST parser using Tree-sitter for RepoPilot AI.

Supports JavaScript, TypeScript, TSX, Java, C, C++, Go, Rust, PHP, Ruby, and Python.
Extracts functions, classes, methods, interfaces, structs, enums, imports, and calls.
"""

import re
from typing import Dict, List, Optional, Set, Tuple

import tree_sitter
import tree_sitter_c
import tree_sitter_cpp
import tree_sitter_go
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_php
import tree_sitter_python
import tree_sitter_ruby
import tree_sitter_rust
import tree_sitter_typescript

from app.code_analysis.schemas import (
    CallGraphEdge,
    FileAnalysisResult,
    ImportStatement,
    SourceLocation,
    Symbol,
)

# Cached tree_sitter.Language instances
_LANGUAGES: Dict[str, tree_sitter.Language] = {}


def _get_language(lang_name: str) -> Optional[tree_sitter.Language]:
    """Retrieves or initializes the tree_sitter.Language instance for a given language."""
    canonical = lang_name.lower().strip()
    if canonical in _LANGUAGES:
        return _LANGUAGES[canonical]

    lang_obj: Optional[tree_sitter.Language] = None
    try:
        if canonical in ("javascript", "js", "jsx"):
            lang_obj = tree_sitter.Language(tree_sitter_javascript.language())
        elif canonical in ("typescript", "ts"):
            lang_obj = tree_sitter.Language(tree_sitter_typescript.language_typescript())
        elif canonical in ("tsx",):
            lang_obj = tree_sitter.Language(tree_sitter_typescript.language_tsx())
        elif canonical in ("java",):
            lang_obj = tree_sitter.Language(tree_sitter_java.language())
        elif canonical in ("c", "h"):
            lang_obj = tree_sitter.Language(tree_sitter_c.language())
        elif canonical in ("cpp", "c++", "hpp", "cc", "cxx"):
            lang_obj = tree_sitter.Language(tree_sitter_cpp.language())
        elif canonical in ("go", "golang"):
            lang_obj = tree_sitter.Language(tree_sitter_go.language())
        elif canonical in ("rust", "rs"):
            lang_obj = tree_sitter.Language(tree_sitter_rust.language())
        elif canonical in ("php",):
            lang_obj = tree_sitter.Language(tree_sitter_php.language_php())
        elif canonical in ("ruby", "rb"):
            lang_obj = tree_sitter.Language(tree_sitter_ruby.language())
        elif canonical in ("python", "py"):
            lang_obj = tree_sitter.Language(tree_sitter_python.language())
    except Exception:
        return None

    if lang_obj:
        _LANGUAGES[canonical] = lang_obj
    return lang_obj


def _node_text(node: tree_sitter.Node, source_bytes: bytes) -> str:
    """Returns decoded text representation of a node."""
    try:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _to_source_location(node: tree_sitter.Node) -> SourceLocation:
    """Converts a Tree-sitter node's 0-based coordinates to 1-based SourceLocation."""
    return SourceLocation(
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        start_column=node.start_point.column + 1,
        end_column=node.end_point.column + 1,
    )


def _clean_string_literal(raw: str) -> str:
    """Strips quotes and whitespace from import specifiers or string literals."""
    s = raw.strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if s.startswith("<") and s.endswith(">"):
        return s[1:-1]
    if s.startswith("`") and s.endswith("`"):
        return s[1:-1]
    return s


class TreeSitterExtractor:
    """Traverses a Tree-sitter syntax tree and extracts symbols, imports, and calls."""

    def __init__(self, file_path: str, source_bytes: bytes, language: str):
        self.file_path = file_path
        self.source_bytes = source_bytes
        self.language = language
        self.symbols: List[Symbol] = []
        self.imports: List[ImportStatement] = []
        self.function_calls: List[CallGraphEdge] = []
        self.scope_stack: List[Tuple[str, str]] = []  # (symbol_id, symbol_name)

    def _current_scope(self) -> Tuple[str, str]:
        if self.scope_stack:
            return self.scope_stack[-1]
        return (f"{self.file_path}::<module>::1", "<module>")

    def extract(self, root_node: tree_sitter.Node) -> None:
        """Entry point to walk the CST."""
        self._walk(root_node)

    def _walk(self, node: tree_sitter.Node) -> None:
        """Recursive node processor with scope tracking."""
        node_type = node.type

        # Dispatch based on node type
        handled_as_scope = False

        if self._is_import_node(node):
            self._handle_import(node)
        elif self._is_class_or_type_node(node):
            handled_as_scope = self._handle_class_or_type(node)
        elif self._is_function_or_method_node(node):
            handled_as_scope = self._handle_function_or_method(node)
        elif self._is_call_node(node):
            self._handle_call(node)

        # If it was handled as a scoped declaration, child traversal was already done inside the handler
        if not handled_as_scope:
            for child in node.children:
                self._walk(child)

    # ---------------------------------------------------------
    # Node classification helpers
    # ---------------------------------------------------------
    def _is_import_node(self, node: tree_sitter.Node) -> bool:
        t = node.type
        return t in (
            "import_statement",
            "import_declaration",
            "preproc_include",
            "use_declaration",
            "namespace_use_declaration",
        )

    def _is_class_or_type_node(self, node: tree_sitter.Node) -> bool:
        t = node.type
        return t in (
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "type_declaration",
            "type_spec",
            "struct_specifier",
            "class_specifier",
            "enum_specifier",
            "struct_item",
            "enum_item",
            "trait_item",
            "impl_item",
            "record_declaration",
            "class",
            "module",
        )

    def _is_function_or_method_node(self, node: tree_sitter.Node) -> bool:
        t = node.type
        if t in (
            "function_declaration",
            "generator_function_declaration",
            "method_definition",
            "method_declaration",
            "constructor_declaration",
            "function_definition",
            "function_item",
            "method",
            "singleton_method",
        ):
            return True
        # Check arrow function assigned to variable: const foo = () => ...
        if t == "variable_declarator":
            val = node.child_by_field_name("value")
            if val and val.type in ("arrow_function", "function_expression"):
                return True
        return False

    def _is_call_node(self, node: tree_sitter.Node) -> bool:
        t = node.type
        return t in (
            "call_expression",
            "method_invocation",
            "function_call_expression",
            "scoped_call_expression",
            "member_call_expression",
            "call",
            "macro_invocation",
        )

    # ---------------------------------------------------------
    # Import Handlers
    # ---------------------------------------------------------
    def _handle_import(self, node: tree_sitter.Node) -> None:
        statement = _node_text(node, self.source_bytes).strip()
        line_num = node.start_point.row + 1
        module = ""
        names: List[str] = []
        is_relative = False

        if node.type == "import_statement":
            # JS/TS: import { a, b } from './module'; or import React from 'react';
            source_node = node.child_by_field_name("source")
            if source_node:
                module = _clean_string_literal(_node_text(source_node, self.source_bytes))
            else:
                # Fallback regex extraction of from '...'
                m = re.search(r"['\"]([^'\"]+)['\"]", statement)
                module = m.group(1) if m else ""

            # Check if relative
            is_relative = module.startswith(".") or module.startswith("/")

            # Extract names
            clause = node.child_by_field_name("clause") or node
            for c in clause.children:
                if c.type in ("identifier", "import_specifier", "namespace_import"):
                    n_text = _node_text(c, self.source_bytes).strip()
                    if n_text:
                        names.append(n_text)

        elif node.type == "import_declaration":
            # Go: import "fmt" or Java: import java.util.List;
            if self.language in ("go", "golang"):
                path_node = node.child_by_field_name("path")
                if path_node:
                    module = _clean_string_literal(_node_text(path_node, self.source_bytes))
                else:
                    # Could be import ( "a"; "b" )
                    matches = re.findall(r"['\"]([^'\"]+)['\"]", statement)
                    for m_path in matches:
                        is_rel = m_path.startswith(".")
                        self.imports.append(
                            ImportStatement(
                                source_file=self.file_path,
                                statement=f'import "{m_path}"',
                                module=m_path,
                                names=[],
                                aliases={},
                                is_relative=is_rel,
                                resolved_target_file=None,
                                import_type="local" if is_rel else "external",
                                line_number=line_num,
                            )
                        )
                    return
                is_relative = module.startswith(".")
            else:
                # Java: import com.example.MyClass;
                raw = statement.replace("import", "").replace("static", "").replace(";", "").strip()
                module = raw
                is_relative = False

        elif node.type == "preproc_include":
            # C/C++: #include <stdio.h> or #include "my_header.h"
            path_node = node.child_by_field_name("path")
            raw_path = _node_text(path_node, self.source_bytes) if path_node else statement
            module = _clean_string_literal(raw_path)
            is_relative = statement.startswith('#include "')

        elif node.type == "use_declaration":
            # Rust: use std::io::Read; or use crate::models::User;
            raw = statement.replace("use", "").replace("pub", "").replace(";", "").strip()
            module = raw
            is_relative = raw.startswith("crate::") or raw.startswith("super::") or raw.startswith("self::")

        elif node.type == "namespace_use_declaration":
            # PHP: use App\Models\User;
            raw = statement.replace("use", "").replace(";", "").strip()
            module = raw
            is_relative = False

        if module:
            self.imports.append(
                ImportStatement(
                    source_file=self.file_path,
                    statement=statement,
                    module=module,
                    names=names,
                    aliases={},
                    is_relative=is_relative,
                    resolved_target_file=None,
                    import_type="local" if is_relative else "external",
                    line_number=line_num,
                )
            )

    # ---------------------------------------------------------
    # Class / Interface / Struct Handlers
    # ---------------------------------------------------------
    def _handle_class_or_type(self, node: tree_sitter.Node) -> bool:
        name_node = node.child_by_field_name("name")
        name = _node_text(name_node, self.source_bytes) if name_node else None

        # C/C++ struct Point or class Animal
        if not name and node.type in ("struct_specifier", "class_specifier", "enum_specifier"):
            for c in node.children:
                if c.type == "type_identifier":
                    name = _node_text(c, self.source_bytes)
                    break

        if not name:
            # Fallback identifier search
            for c in node.children:
                if c.type in ("identifier", "type_identifier", "constant"):
                    name = _node_text(c, self.source_bytes)
                    break

        if not name:
            return False

        parent_id, _ = self._current_scope() if self.scope_stack else (None, None)
        line_num = node.start_point.row + 1
        symbol_id = f"{self.file_path}::{name}::{line_num}::class"

        sym_type = "class"
        if "interface" in node.type:
            sym_type = "interface"
        elif "struct" in node.type:
            sym_type = "struct"
        elif "enum" in node.type:
            sym_type = "enum"
        elif "trait" in node.type:
            sym_type = "interface"

        # Check visibility
        visibility = "public"
        text = _node_text(node, self.source_bytes)
        if "private " in text[:50]:
            visibility = "private"
        elif "protected " in text[:50]:
            visibility = "protected"

        symbol = Symbol(
            id=symbol_id,
            name=name,
            symbol_type=sym_type,
            file_path=self.file_path,
            location=_to_source_location(node),
            parent_symbol_id=parent_id,
            language=self.language,
            parameters=[],
            visibility=visibility,
            is_async=False,
        )
        self.symbols.append(symbol)

        # Push scope and visit children
        self.scope_stack.append((symbol_id, name))
        for child in node.children:
            self._walk(child)
        self.scope_stack.pop()
        return True

    # ---------------------------------------------------------
    # Function / Method Handlers
    # ---------------------------------------------------------
    def _handle_function_or_method(self, node: tree_sitter.Node) -> bool:
        name: Optional[str] = None
        params: List[str] = []
        return_type: Optional[str] = None
        is_async = False

        if node.type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            name = _node_text(name_node, self.source_bytes) if name_node else None
            val = node.child_by_field_name("value")
            if val:
                is_async = "async" in _node_text(val, self.source_bytes)[:15]
                params_node = val.child_by_field_name("parameters")
                if params_node:
                    params = [_node_text(p, self.source_bytes) for p in params_node.children if p.type in ("identifier", "required_parameter")]
        else:
            name_node = node.child_by_field_name("name")
            if not name_node and node.child_by_field_name("declarator"):
                # C/C++ style declarator
                decl = node.child_by_field_name("declarator")
                if decl:
                    inner_decl = decl.child_by_field_name("declarator") or decl
                    for c in inner_decl.children:
                        if c.type == "identifier":
                            name_node = c
                            break
                    if not name_node and inner_decl.type == "identifier":
                        name_node = inner_decl

            name = _node_text(name_node, self.source_bytes) if name_node else None

            # Parameters
            params_node = node.child_by_field_name("parameters")
            if params_node:
                raw_params = _node_text(params_node, self.source_bytes)
                params = [p.strip() for p in raw_params.strip("()").split(",") if p.strip()]

            # Return type
            ret_node = (
                node.child_by_field_name("return_type")
                or node.child_by_field_name("type")
                or node.child_by_field_name("result")
            )
            if ret_node:
                return_type = _node_text(ret_node, self.source_bytes).strip(": ")

            # Async check
            raw_head = _node_text(node, self.source_bytes)[:30]
            is_async = "async" in raw_head

        if not name:
            return False

        parent_id, _ = self._current_scope() if self.scope_stack else (None, None)
        line_num = node.start_point.row + 1
        symbol_id = f"{self.file_path}::{name}::{line_num}"

        sym_type = "method" if (self.scope_stack and "class" in self.scope_stack[-1][0]) else "function"

        visibility = "public"
        head_text = _node_text(node, self.source_bytes)[:50]
        if "private" in head_text:
            visibility = "private"
        elif "protected" in head_text:
            visibility = "protected"
        elif name.startswith("_"):
            visibility = "private"

        symbol = Symbol(
            id=symbol_id,
            name=name,
            symbol_type=sym_type,
            file_path=self.file_path,
            location=_to_source_location(node),
            parent_symbol_id=parent_id,
            language=self.language,
            parameters=params,
            return_type=return_type,
            visibility=visibility,
            is_async=is_async,
        )
        self.symbols.append(symbol)

        # Push scope, visit children, pop scope
        self.scope_stack.append((symbol_id, name))
        for child in node.children:
            self._walk(child)
        self.scope_stack.pop()
        return True

    # ---------------------------------------------------------
    # Call Expression Handlers
    # ---------------------------------------------------------
    def _handle_call(self, node: tree_sitter.Node) -> None:
        caller_id, caller_name = self._current_scope()
        line_num = node.start_point.row + 1

        callee_name = ""
        # Function or method being called
        fn_node = (
            node.child_by_field_name("function")
            or node.child_by_field_name("name")
            or node.child_by_field_name("method")
        )

        if fn_node:
            callee_name = _node_text(fn_node, self.source_bytes).strip()
        else:
            # Fallback: extract identifier from call text
            raw = _node_text(node, self.source_bytes).strip()
            paren_idx = raw.find("(")
            if paren_idx > 0:
                callee_name = raw[:paren_idx].strip()
            else:
                callee_name = raw.split()[0] if raw else "unknown_call"

        if callee_name:
            # Clean up callee_name if it has newlines
            callee_name = callee_name.splitlines()[0].strip()
            edge_id = f"{self.file_path}::{caller_name}->{callee_name}::{line_num}"
            self.function_calls.append(
                CallGraphEdge(
                    id=edge_id,
                    caller_id=caller_id,
                    caller_name=caller_name,
                    caller_file=self.file_path,
                    callee_name=callee_name,
                    resolved_callee_id=None,
                    resolved_callee_file=None,
                    is_resolved=False,
                    line_number=line_num,
                )
            )


def parse_tree_sitter_source(
    file_path: str, source_code: str, language: str
) -> FileAnalysisResult:
    """Parses source code using Tree-sitter for polyglot language support.

    Args:
        file_path: Relative repository file path.
        source_code: Full text of source code file.
        language: Programming language identifier.

    Returns:
        FileAnalysisResult containing extracted symbols, imports, calls, and metrics.
    """
    total_lines = len(source_code.splitlines())
    lang_obj = _get_language(language)

    if not lang_obj:
        return FileAnalysisResult(
            file_path=file_path,
            language=language,
            status="unsupported",
            error_message=f"Tree-sitter grammar not available for language: {language}",
            symbols=[],
            imports=[],
            function_calls=[],
            total_lines=total_lines,
        )

    try:
        source_bytes = source_code.encode("utf-8")
        parser = tree_sitter.Parser(lang_obj)
        tree = parser.parse(source_bytes)
    except Exception as e:
        return FileAnalysisResult(
            file_path=file_path,
            language=language,
            status="syntax_error",
            error_message=f"Tree-sitter parse exception: {str(e)}",
            symbols=[],
            imports=[],
            function_calls=[],
            total_lines=total_lines,
        )

    extractor = TreeSitterExtractor(
        file_path=file_path, source_bytes=source_bytes, language=language
    )
    extractor.extract(tree.root_node)

    return FileAnalysisResult(
        file_path=file_path,
        language=language,
        status="success",
        error_message=None,
        symbols=extractor.symbols,
        imports=extractor.imports,
        function_calls=extractor.function_calls,
        total_lines=total_lines,
    )

