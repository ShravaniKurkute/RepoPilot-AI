"""Dependency resolver for multi-language imports and circular dependency detection."""

import os
import posixpath
import sys
from typing import Dict, List, Optional, Set, Tuple

from app.code_analysis.schemas import FileAnalysisResult, FileDependency, ImportStatement

# Python standard library module names for accurate categorization
PYTHON_STDLIB = set(sys.builtin_module_names).union(
    {
        "abc", "argparse", "ast", "asyncio", "base64", "collections", "contextlib",
        "copy", "csv", "dataclasses", "datetime", "decimal", "enum", "errno",
        "functools", "glob", "hashlib", "http", "importlib", "inspect", "io",
        "itertools", "json", "logging", "math", "multiprocessing", "os", "pathlib",
        "pickle", "platform", "queue", "random", "re", "shutil", "signal",
        "socket", "sqlite3", "ssl", "stat", "string", "subprocess", "sys",
        "tempfile", "threading", "time", "traceback", "typing", "unittest",
        "urllib", "uuid", "warnings", "weakref", "zipfile", "zlib"
    }
)


def _normalize_path(p: str) -> str:
    """Normalizes path to forward slashes with no leading/trailing slashes."""
    return p.replace("\\", "/").strip("/")


def _find_cycles_in_graph(graph: Dict[str, List[str]]) -> List[List[str]]:
    """Detects simple circular dependency cycles using depth-first search."""
    cycles: List[List[str]] = []
    visited: Set[str] = set()
    rec_stack: List[str] = []

    def dfs(node: str) -> None:
        visited.add(node)
        rec_stack.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                dfs(neighbor)
            elif neighbor in rec_stack:
                cycle_start_idx = rec_stack.index(neighbor)
                cycle = rec_stack[cycle_start_idx:] + [neighbor]
                cycles.append(cycle)

        rec_stack.pop()

    for node in graph:
        if node not in visited:
            dfs(node)

    # Deduplicate cycles by rotating to smallest node
    unique_cycles: List[List[str]] = []
    seen: Set[Tuple[str, ...]] = set()

    for cycle in cycles:
        nodes = cycle[:-1]
        if len(nodes) < 2:
            continue
        min_node = min(nodes)
        min_idx = nodes.index(min_node)
        normalized = tuple(nodes[min_idx:] + nodes[:min_idx])
        if normalized not in seen:
            seen.add(normalized)
            unique_cycles.append(list(normalized) + [normalized[0]])

    return unique_cycles


class DependencyResolver:
    """Resolves raw import statements against repository files and builds dependency graphs."""

    def __init__(self, all_repo_files: List[str]):
        self.all_files: Set[str] = {_normalize_path(f) for f in all_repo_files}
        # Precompute file basename and stem lookup maps
        self._stem_to_files: Dict[str, List[str]] = {}
        for f in self.all_files:
            stem = posixpath.splitext(posixpath.basename(f))[0]
            self._stem_to_files.setdefault(stem, []).append(f)

    def resolve_python_import(
        self, source_file: str, imp: ImportStatement
    ) -> Tuple[str, Optional[str]]:
        """Resolves Python import statements to local repository files or external modules."""
        source_norm = _normalize_path(source_file)
        source_dir = posixpath.dirname(source_norm)
        module = imp.module

        # Relative import
        if imp.is_relative or module.startswith("."):
            dots = 0
            while dots < len(module) and module[dots] == ".":
                dots += 1
            rel_name = module[dots:].replace(".", "/")

            # Traverse directory levels based on dots
            curr_dir = source_dir
            for _ in range(dots - 1):
                curr_dir = posixpath.dirname(curr_dir)

            candidate_base = posixpath.normpath(
                posixpath.join(curr_dir, rel_name) if rel_name else curr_dir
            )
            candidate_base = _normalize_path(candidate_base)

            # Check candidate.py, candidate/__init__.py
            for target in [f"{candidate_base}.py", f"{candidate_base}/__init__.py", candidate_base]:
                if target in self.all_files:
                    return "local", target

            return "unresolved", None

        # Check Python standard library
        top_module = module.split(".")[0]
        if top_module in PYTHON_STDLIB:
            return "external", None

        # Non-relative local import check (e.g. app.core.config)
        mod_as_path = module.replace(".", "/")
        candidates = [
            f"{mod_as_path}.py",
            f"{mod_as_path}/__init__.py",
        ]

        # Also check relative to repository subdirectories (e.g. backend/app/core/config.py)
        for target in candidates:
            if target in self.all_files:
                return "local", target

        for f in self.all_files:
            for target in candidates:
                if f.endswith(f"/{target}"):
                    return "local", f

        # If it doesn't match any repo file, classify as external
        return "external", None

    def resolve_js_ts_import(
        self, source_file: str, imp: ImportStatement
    ) -> Tuple[str, Optional[str]]:
        """Resolves JavaScript and TypeScript import specifiers."""
        source_norm = _normalize_path(source_file)
        source_dir = posixpath.dirname(source_norm)
        module = imp.module

        # Relative import (./ or ../)
        if module.startswith("./") or module.startswith("../"):
            candidate_base = _normalize_path(posixpath.normpath(posixpath.join(source_dir, module)))
            extensions = [
                "",
                ".ts",
                ".tsx",
                ".js",
                ".jsx",
                "/index.ts",
                "/index.tsx",
                "/index.js",
                "/index.jsx",
                ".json",
                ".css",
            ]
            for ext in extensions:
                target = f"{candidate_base}{ext}" if ext else candidate_base
                if target in self.all_files:
                    return "local", target

            return "unresolved", None

        # Path alias e.g. @/components/Button
        if module.startswith("@/") or module.startswith("~/"):
            stripped = module[2:]
            for prefix in ["src/", "app/", ""]:
                candidate = f"{prefix}{stripped}"
                for ext in ["", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx"]:
                    target = f"{candidate}{ext}" if ext else candidate
                    if target in self.all_files:
                        return "local", target

        # External package (react, axios, lodash, @tanstack/..., etc.)
        return "external", None

    def resolve_general_import(
        self, source_file: str, imp: ImportStatement
    ) -> Tuple[str, Optional[str]]:
        """Resolves imports for Go, Rust, C/C++, PHP, Ruby."""
        source_norm = _normalize_path(source_file)
        source_dir = posixpath.dirname(source_norm)
        module = imp.module

        # Relative import check
        if imp.is_relative or module.startswith("./") or module.startswith("../"):
            candidate = _normalize_path(posixpath.normpath(posixpath.join(source_dir, module)))
            for ext in ["", ".h", ".hpp", ".c", ".cpp", ".go", ".rs", ".php", ".rb"]:
                t = f"{candidate}{ext}" if ext else candidate
                if t in self.all_files:
                    return "local", t
            return "unresolved", None

        # C/C++ header include e.g. "header.h"
        if imp.statement.startswith('#include "'):
            cand = _normalize_path(posixpath.normpath(posixpath.join(source_dir, module)))
            if cand in self.all_files:
                return "local", cand
            # Search anywhere in repo
            for f in self.all_files:
                if f.endswith(f"/{module}") or f == module:
                    return "local", f

        # Rust crate::
        if module.startswith("crate::"):
            rust_path = "src/" + module[7:].replace("::", "/")
            for ext in [".rs", "/mod.rs"]:
                t = f"{rust_path}{ext}"
                if t in self.all_files:
                    return "local", t

        return "external", None

    def resolve_file_imports(
        self, source_file: str, language: str, imports: List[ImportStatement]
    ) -> List[ImportStatement]:
        """Resolves all import statements in a file and returns updated ImportStatement models."""
        resolved_list: List[ImportStatement] = []

        for imp in imports:
            imp_type = imp.import_type
            resolved_target = imp.resolved_target_file

            if language == "Python":
                imp_type, resolved_target = self.resolve_python_import(source_file, imp)
            elif language in ("JavaScript", "TypeScript", "tsx"):
                imp_type, resolved_target = self.resolve_js_ts_import(source_file, imp)
            else:
                imp_type, resolved_target = self.resolve_general_import(source_file, imp)

            # Return updated copy
            resolved_list.append(
                imp.model_copy(
                    update={
                        "import_type": imp_type,
                        "resolved_target_file": resolved_target,
                    }
                )
            )

        return resolved_list

    def build_dependencies(
        self, file_results: Dict[str, FileAnalysisResult]
    ) -> Tuple[Dict[str, FileDependency], List[List[str]]]:
        """Builds full dependency map and detects circular dependencies.

        Args:
            file_results: Mapping from normalized file path to FileAnalysisResult.

        Returns:
            Tuple of (dependencies_map, circular_dependency_cycles).
        """
        # Graph for cycle detection: file -> set of local files it depends on
        dep_graph: Dict[str, Set[str]] = {}
        # Reverse map: file -> set of local files that import it
        reverse_graph: Dict[str, Set[str]] = {}
        # External dependencies per file
        external_map: Dict[str, Set[str]] = {}
        # Unresolved imports per file
        unresolved_map: Dict[str, Set[str]] = {}

        for file_path, result in file_results.items():
            norm_path = _normalize_path(file_path)
            dep_graph.setdefault(norm_path, set())
            reverse_graph.setdefault(norm_path, set())
            external_map.setdefault(norm_path, set())
            unresolved_map.setdefault(norm_path, set())

            for imp in result.imports:
                if imp.import_type == "local" and imp.resolved_target_file:
                    target_norm = _normalize_path(imp.resolved_target_file)
                    dep_graph[norm_path].add(target_norm)
                    reverse_graph.setdefault(target_norm, set()).add(norm_path)
                elif imp.import_type == "external":
                    external_map[norm_path].add(imp.module)
                elif imp.import_type == "unresolved":
                    unresolved_map[norm_path].add(imp.module)

        # Convert sets to sorted lists for deterministic responses
        dependencies: Dict[str, FileDependency] = {}
        serializable_graph: Dict[str, List[str]] = {}

        for file_path in file_results.keys():
            norm_path = _normalize_path(file_path)
            local_deps = sorted(list(dep_graph.get(norm_path, set())))
            imported_by = sorted(list(reverse_graph.get(norm_path, set())))
            externals = sorted(list(external_map.get(norm_path, set())))
            unresolved = sorted(list(unresolved_map.get(norm_path, set())))

            serializable_graph[norm_path] = local_deps
            dependencies[file_path] = FileDependency(
                file_path=file_path,
                depends_on=local_deps,
                imported_by=imported_by,
                external_dependencies=externals,
                unresolved_imports=unresolved,
            )

        # Detect circular dependencies
        cycles = _find_cycles_in_graph(serializable_graph)

        return dependencies, cycles

