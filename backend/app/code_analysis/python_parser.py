"""Dedicated Python AST parser for functions, classes, imports, and calls."""

import ast
from typing import List, Optional, Tuple
from app.code_analysis.schemas import (
    CallGraphEdge,
    FileAnalysisResult,
    ImportStatement,
    SourceLocation,
    Symbol,
)


def _safe_unparse(node: Optional[ast.AST]) -> Optional[str]:
    """Safely unparses an AST node into source string representation."""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _get_visibility(name: str) -> str:
    """Determines visibility from Python naming convention."""
    if name.startswith("__") and not name.endswith("__"):
        return "private"
    elif name.startswith("_") and not name.endswith("__"):
        return "protected"
    return "public"


class PythonASTVisitor(ast.NodeVisitor):
    """Walks Python AST to extract symbols, imports, calls, and scope hierarchies."""

    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_code = source_code
        self.lines = source_code.splitlines()

        self.symbols: List[Symbol] = []
        self.imports: List[ImportStatement] = []
        self.function_calls: List[CallGraphEdge] = []

        # Scope stack: list of (symbol_id, symbol_name)
        self.scope_stack: List[Tuple[str, str]] = []

    def _current_scope(self) -> Tuple[str, str]:
        """Returns the current enclosing scope (symbol_id, symbol_name)."""
        if self.scope_stack:
            return self.scope_stack[-1]
        return (f"{self.file_path}::<module>::1", "<module>")

    def visit_Import(self, node: ast.Import) -> None:
        names = [alias.name for alias in node.names]
        aliases = {alias.name: alias.asname for alias in node.names if alias.asname}
        statement = _safe_unparse(node) or f"import {', '.join(names)}"

        for alias in node.names:
            self.imports.append(
                ImportStatement(
                    source_file=self.file_path,
                    statement=statement,
                    module=alias.name,
                    names=[alias.name],
                    aliases={alias.name: alias.asname} if alias.asname else {},
                    is_relative=False,
                    resolved_target_file=None,
                    import_type="external",  # Will be resolved by dependency resolver
                    line_number=node.lineno,
                )
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        is_relative = node.level > 0
        names = [alias.name for alias in node.names]
        aliases = {alias.name: alias.asname for alias in node.names if alias.asname}
        statement = _safe_unparse(node) or f"from {'.' * node.level}{module} import {', '.join(names)}"

        full_module = ("." * node.level) + module if is_relative else module

        self.imports.append(
            ImportStatement(
                source_file=self.file_path,
                statement=statement,
                module=full_module,
                names=names,
                aliases=aliases,
                is_relative=is_relative,
                resolved_target_file=None,
                import_type="local" if is_relative else "external",
                line_number=node.lineno,
            )
        )
        self.generic_visit(node)

    def _extract_function_params(self, args: ast.arguments) -> List[str]:
        """Extracts formal parameter signatures."""
        params: List[str] = []
        for a in args.posonlyargs + args.args:
            p_str = a.arg
            if a.annotation:
                ann = _safe_unparse(a.annotation)
                if ann:
                    p_str += f": {ann}"
            params.append(p_str)

        if args.vararg:
            params.append(f"*{args.vararg.arg}")

        for a in args.kwonlyargs:
            p_str = a.arg
            if a.annotation:
                ann = _safe_unparse(a.annotation)
                if ann:
                    p_str += f": {ann}"
            params.append(p_str)

        if args.kwarg:
            params.append(f"**{args.kwarg.arg}")

        return params

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    def _handle_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
    ) -> None:
        parent_id, _ = self._current_scope() if self.scope_stack else (None, None)
        symbol_type = "method" if (self.scope_stack and "class" in self.scope_stack[-1][0]) else "function"
        symbol_id = f"{self.file_path}::{node.name}::{node.lineno}"

        location = SourceLocation(
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            start_column=node.col_offset + 1,
            end_column=(node.end_col_offset + 1) if node.end_col_offset else node.col_offset + 1,
        )

        decorators = [_safe_unparse(d) for d in node.decorator_list if d]
        params = self._extract_function_params(node.args)
        return_type = _safe_unparse(node.returns) if node.returns else None
        docstring = ast.get_docstring(node)

        symbol = Symbol(
            id=symbol_id,
            name=node.name,
            symbol_type=symbol_type,
            file_path=self.file_path,
            location=location,
            parent_symbol_id=parent_id,
            language="Python",
            parameters=params,
            return_type=return_type,
            decorators=[d for d in decorators if d],
            visibility=_get_visibility(node.name),
            docstring=docstring,
            is_async=is_async,
        )
        self.symbols.append(symbol)

        # Push scope, visit body, pop scope
        self.scope_stack.append((symbol_id, node.name))
        for item in node.body:
            self.visit(item)
        self.scope_stack.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        parent_id, _ = self._current_scope() if self.scope_stack else (None, None)
        symbol_id = f"{self.file_path}::{node.name}::{node.lineno}::class"

        location = SourceLocation(
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            start_column=node.col_offset + 1,
            end_column=(node.end_col_offset + 1) if node.end_col_offset else node.col_offset + 1,
        )

        bases = [_safe_unparse(b) for b in node.bases if b]
        decorators = [_safe_unparse(d) for d in node.decorator_list if d]
        docstring = ast.get_docstring(node)

        symbol = Symbol(
            id=symbol_id,
            name=node.name,
            symbol_type="class",
            file_path=self.file_path,
            location=location,
            parent_symbol_id=parent_id,
            language="Python",
            parameters=[b for b in bases if b],  # Use parameters field for base classes
            decorators=[d for d in decorators if d],
            visibility=_get_visibility(node.name),
            docstring=docstring,
            is_async=False,
        )
        self.symbols.append(symbol)

        self.scope_stack.append((symbol_id, node.name))
        for item in node.body:
            self.visit(item)
        self.scope_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        caller_id, caller_name = self._current_scope()
        callee_name = _safe_unparse(node.func) or "unknown_call"

        edge = CallGraphEdge(
            id=f"{self.file_path}::{caller_name}->{callee_name}::{node.lineno}",
            caller_id=caller_id,
            caller_name=caller_name,
            caller_file=self.file_path,
            callee_name=callee_name,
            resolved_callee_id=None,
            resolved_callee_file=None,
            is_resolved=False,
            line_number=node.lineno,
        )
        self.function_calls.append(edge)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Capture module-level assignments
        if not self.scope_stack:
            for target in node.targets:
                target_name = _safe_unparse(target)
                if target_name and not target_name.startswith("_"):
                    symbol_id = f"{self.file_path}::{target_name}::{node.lineno}"
                    location = SourceLocation(
                        start_line=node.lineno,
                        end_line=node.end_lineno or node.lineno,
                        start_column=node.col_offset + 1,
                        end_column=(node.end_col_offset + 1) if node.end_col_offset else node.col_offset + 1,
                    )
                    self.symbols.append(
                        Symbol(
                            id=symbol_id,
                            name=target_name,
                            symbol_type="variable",
                            file_path=self.file_path,
                            location=location,
                            parent_symbol_id=None,
                            language="Python",
                            visibility="public",
                        )
                    )
        self.generic_visit(node)


def parse_python_source(file_path: str, source_code: str) -> FileAnalysisResult:
    """Parses Python source code with ast, handling syntax errors gracefully.

    Returns:
        FileAnalysisResult with extracted symbols, imports, and function calls.
    """
    total_lines = len(source_code.splitlines())

    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError as e:
        error_msg = f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        return FileAnalysisResult(
            file_path=file_path,
            language="Python",
            status="syntax_error",
            error_message=error_msg,
            symbols=[],
            imports=[],
            function_calls=[],
            total_lines=total_lines,
        )
    except Exception as e:
        return FileAnalysisResult(
            file_path=file_path,
            language="Python",
            status="syntax_error",
            error_message=f"AST parse failure: {str(e)}",
            symbols=[],
            imports=[],
            function_calls=[],
            total_lines=total_lines,
        )

    visitor = PythonASTVisitor(file_path=file_path, source_code=source_code)
    visitor.visit(tree)

    return FileAnalysisResult(
        file_path=file_path,
        language="Python",
        status="success",
        error_message=None,
        symbols=visitor.symbols,
        imports=visitor.imports,
        function_calls=visitor.function_calls,
        total_lines=total_lines,
    )

