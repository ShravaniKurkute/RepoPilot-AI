"""Unit and integration tests for Phase 2: Code Intelligence & AST Parsing."""

import io
from pathlib import Path
import tempfile
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.code_analysis.call_graph import CallGraphResolver
from app.code_analysis.dependency_resolver import DependencyResolver
from app.code_analysis.parser_manager import parse_source_file
from app.code_analysis.python_parser import parse_python_source
from app.code_analysis.schemas import CallGraphEdge, ImportStatement, Symbol
from app.code_analysis.service import CodeAnalysisService
from app.code_analysis.tree_sitter_parser import parse_tree_sitter_source
from app.main import app

client = TestClient(app)


# -------------------------------------------------------------
# 1. Python AST Parser Tests
# -------------------------------------------------------------
def test_python_ast_functions_and_classes():
    code = '''"""Module docstring."""
import os
from typing import Optional

def add(a: int, b: int = 0) -> int:
    """Adds two integers."""
    return a + b

class Calculator:
    """Calculator class."""
    def __init__(self, name: str):
        self.name = name

    async def compute(self, x: int) -> int:
        return add(x, 10)
'''
    res = parse_python_source("calc.py", code)
    assert res.status == "success"
    assert res.total_lines > 10

    sym_names = [s.name for s in res.symbols]
    assert "add" in sym_names
    assert "Calculator" in sym_names
    assert "__init__" in sym_names
    assert "compute" in sym_names

    # Check function add
    add_sym = next(s for s in res.symbols if s.name == "add")
    assert add_sym.symbol_type == "function"
    assert "a: int" in add_sym.parameters[0]
    assert add_sym.return_type == "int"
    assert add_sym.docstring == "Adds two integers."
    assert not add_sym.is_async

    # Check async method compute
    compute_sym = next(s for s in res.symbols if s.name == "compute")
    assert compute_sym.symbol_type == "method"
    assert compute_sym.is_async is True
    assert compute_sym.parent_symbol_id is not None

    # Check imports
    imp_modules = [i.module for i in res.imports]
    assert "os" in imp_modules
    assert "typing" in imp_modules

    # Check calls
    calls = [c.callee_name for c in res.function_calls]
    assert "add" in calls


def test_python_ast_syntax_error_graceful():
    bad_code = "def broken_func(\n    return 42\n"
    res = parse_python_source("broken.py", bad_code)
    assert res.status == "syntax_error"
    assert res.error_message is not None
    assert "SyntaxError" in res.error_message


# -------------------------------------------------------------
# 2. Tree-sitter Multi-Language Parser Tests
# -------------------------------------------------------------
def test_tree_sitter_typescript():
    ts_code = '''import { useState } from 'react';
import { helper } from './utils';

export interface User {
    id: string;
    name: string;
}

export class UserService {
    async getUser(id: string): Promise<User> {
        helper();
        return { id, name: 'Alice' };
    }
}
'''
    res = parse_tree_sitter_source("service.ts", ts_code, "TypeScript")
    assert res.status == "success"
    names = [s.name for s in res.symbols]
    assert "UserService" in names
    assert "getUser" in names

    # Imports
    assert len(res.imports) >= 2
    modules = [i.module for i in res.imports]
    assert "react" in modules
    assert "./utils" in modules

    # Calls
    call_names = [c.callee_name for c in res.function_calls]
    assert "helper" in call_names


def test_tree_sitter_polyglot_languages():
    # Go
    go_code = '''package main
import "fmt"
type Server struct {}
func (s *Server) Start() {
    fmt.Println("Server started")
}
func main() {}
'''
    go_res = parse_tree_sitter_source("main.go", go_code, "Go")
    assert go_res.status == "success"
    assert any(s.name in ("Start", "main") for s in go_res.symbols)

    # Rust
    rust_code = '''use std::io;
pub struct Client {}
impl Client {
    pub fn connect() -> bool {
        println!("connecting");
        true
    }
}
'''
    rs_res = parse_tree_sitter_source("client.rs", rust_code, "Rust")
    assert rs_res.status == "success"
    assert any(s.name in ("Client", "connect") for s in rs_res.symbols)

    # Java
    java_code = '''package com.app;
import java.util.List;
public class Runner {
    public static void run() {
        System.out.println("running");
    }
}
'''
    java_res = parse_tree_sitter_source("Runner.java", java_code, "Java")
    assert java_res.status == "success"
    assert any(s.name in ("Runner", "run") for s in java_res.symbols)


# -------------------------------------------------------------
# 3. Dependency Resolver & Circular Dependency Tests
# -------------------------------------------------------------
def test_dependency_resolver_relative_and_circular():
    all_files = ["app/a.py", "app/b.py", "app/c.py"]
    resolver = DependencyResolver(all_files)

    # A imports B, B imports C, C imports A (circular!)
    from app.code_analysis.schemas import FileAnalysisResult

    file_results = {
        "app/a.py": FileAnalysisResult(
            file_path="app/a.py",
            language="Python",
            status="success",
            imports=[
                ImportStatement(
                    source_file="app/a.py",
                    statement="from .b import func_b",
                    module=".b",
                    names=["func_b"],
                    is_relative=True,
                    line_number=1,
                    import_type="local",
                )
            ],
            symbols=[],
            function_calls=[],
            total_lines=5,
        ),
        "app/b.py": FileAnalysisResult(
            file_path="app/b.py",
            language="Python",
            status="success",
            imports=[
                ImportStatement(
                    source_file="app/b.py",
                    statement="from .c import func_c",
                    module=".c",
                    names=["func_c"],
                    is_relative=True,
                    line_number=1,
                    import_type="local",
                )
            ],
            symbols=[],
            function_calls=[],
            total_lines=5,
        ),
        "app/c.py": FileAnalysisResult(
            file_path="app/c.py",
            language="Python",
            status="success",
            imports=[
                ImportStatement(
                    source_file="app/c.py",
                    statement="from .a import func_a",
                    module=".a",
                    names=["func_a"],
                    is_relative=True,
                    line_number=1,
                    import_type="local",
                )
            ],
            symbols=[],
            function_calls=[],
            total_lines=5,
        ),
    }

    # Resolve each file's imports
    for path, res in file_results.items():
        res.imports = resolver.resolve_file_imports(path, res.language, res.imports)

    deps, cycles = resolver.build_dependencies(file_results)

    assert len(cycles) > 0
    # Cycle should include a.py, b.py, c.py
    cycle_files = set(cycles[0])
    assert "app/a.py" in cycle_files
    assert "app/b.py" in cycle_files
    assert "app/c.py" in cycle_files

    assert deps["app/a.py"].depends_on == ["app/b.py"]
    assert "app/c.py" in deps["app/a.py"].imported_by


# -------------------------------------------------------------
# 4. Call Graph Resolver Tests
# -------------------------------------------------------------
def test_call_graph_resolution():
    sym_a = Symbol(
        id="math.py::calc::10",
        name="calc",
        symbol_type="function",
        file_path="math.py",
        location={"start_line": 10, "end_line": 15, "start_column": 1, "end_column": 10},
        language="Python",
    )
    sym_main = Symbol(
        id="main.py::run::5",
        name="run",
        symbol_type="function",
        file_path="main.py",
        location={"start_line": 5, "end_line": 12, "start_column": 1, "end_column": 10},
        language="Python",
    )

    symbols_by_file = {
        "math.py": [sym_a],
        "main.py": [sym_main],
    }
    imports_by_file = {
        "main.py": [
            ImportStatement(
                source_file="main.py",
                statement="from math import calc",
                module="math",
                names=["calc"],
                resolved_target_file="math.py",
                import_type="local",
                line_number=1,
            )
        ]
    }

    raw_edges = [
        CallGraphEdge(
            id="edge1",
            caller_id="main.py::run::5",
            caller_name="run",
            caller_file="main.py",
            callee_name="calc",
            line_number=8,
        ),
        CallGraphEdge(
            id="edge2",
            caller_id="main.py::run::5",
            caller_name="run",
            caller_file="main.py",
            callee_name="unknown_external_func",
            line_number=9,
        ),
    ]

    cg_resolver = CallGraphResolver(symbols_by_file, imports_by_file)
    resolved_edges, count = cg_resolver.resolve_edges(raw_edges)

    assert count == 1
    assert resolved_edges[0].is_resolved is True
    assert resolved_edges[0].resolved_callee_id == "math.py::calc::10"
    assert resolved_edges[0].resolved_callee_file == "math.py"

    assert resolved_edges[1].is_resolved is False


# -------------------------------------------------------------
# 5. Integration: CodeAnalysisService & Endpoints
# -------------------------------------------------------------
def test_code_analysis_service_and_endpoints(tmp_path: Path):
    # Create test repository directory with source files
    repo_id = "test-repo-phase2"
    repo_dir = tmp_path / repo_id
    source_dir = repo_dir / "source"
    source_dir.mkdir(parents=True)

    # Write source files
    (source_dir / "helper.py").write_text("def helper_func():\n    return 42\n", encoding="utf-8")
    (source_dir / "main.py").write_text(
        "from helper import helper_func\n\ndef main():\n    helper_func()\n",
        encoding="utf-8",
    )
    (source_dir / "index.ts").write_text(
        "export function greet(name: string): string {\n    return `Hello, ${name}`;\n}\n",
        encoding="utf-8",
    )

    service = CodeAnalysisService(storage_root=tmp_path)
    res = service.analyze_repository(repo_id)

    assert res.summary.total_files_scanned == 3
    assert res.summary.successfully_parsed_files == 3
    assert res.summary.total_symbols >= 3
    assert "Python" in res.summary.languages_analyzed
    assert "TypeScript" in res.summary.languages_analyzed

    # Verify query methods
    assert service.get_analysis(repo_id) is not None
    symbols = service.get_symbols(repo_id, name="helper_func")
    assert len(symbols) == 1
    assert symbols[0].name == "helper_func"

    deps = service.get_dependencies(repo_id)
    assert deps is not None
    assert "main.py" in deps

    # Wire service into app dependency and test FastAPI endpoints
    from app.api.v1 import code_analysis
    orig_service = code_analysis.code_analysis_service
    code_analysis.code_analysis_service = service

    try:
        # Trigger analyze endpoint
        post_resp = client.post(f"/api/v1/repositories/{repo_id}/analyze")
        assert post_resp.status_code == 200
        data = post_resp.json()["data"]
        assert data["summary"]["total_files_scanned"] == 3

        # Get analysis endpoint
        get_resp = client.get(f"/api/v1/repositories/{repo_id}/analysis")
        assert get_resp.status_code == 200

        # Filter symbols
        sym_resp = client.get(f"/api/v1/repositories/{repo_id}/symbols?name=greet")
        assert sym_resp.status_code == 200
        sym_data = sym_resp.json()["data"]
        assert len(sym_data) == 1
        assert sym_data[0]["name"] == "greet"

        # Dependencies endpoint
        dep_resp = client.get(f"/api/v1/repositories/{repo_id}/dependencies")
        assert dep_resp.status_code == 200

        # Call graph endpoint
        cg_resp = client.get(f"/api/v1/repositories/{repo_id}/call-graph")
        assert cg_resp.status_code == 200

        # File analysis endpoint
        file_resp = client.get(f"/api/v1/repositories/{repo_id}/files/helper.py/analysis")
        assert file_resp.status_code == 200
        assert file_resp.json()["data"]["file_path"] == "helper.py"

        # 404 test for nonexistent repo
        not_found = client.get("/api/v1/repositories/non-existent-id/analysis")
        assert not_found.status_code == 404

    finally:
        code_analysis.code_analysis_service = orig_service

