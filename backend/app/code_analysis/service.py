"""Code analysis service for orchestrating AST parsing, dependencies, and call graphs."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from app.code_analysis.call_graph import CallGraphResolver
from app.code_analysis.dependency_resolver import DependencyResolver
from app.code_analysis.parser_manager import parse_source_file
from app.code_analysis.schemas import (
    CallGraphEdge,
    FileAnalysisResult,
    FileDependency,
    RepositoryAnalysisResponse,
    RepositoryAnalysisSummary,
    Symbol,
)
from app.core.config import settings
from app.core.logging import logger
from app.repository.file_walker import walk_repository


class CodeAnalysisService:
    """Orchestrates multi-language parsing, dependency graphs, and call graphs."""

    def __init__(self, storage_root: Optional[Path] = None):
        if storage_root is not None:
            self.storage_root = storage_root.resolve()
        else:
            p = Path(settings.WORKSPACE_STORAGE_PATH)
            self.storage_root = p if p.is_absolute() else (Path.cwd() / p).resolve()

    def _get_repo_dir(self, repo_id: str) -> Path:
        return self.storage_root / repo_id

    def _get_analysis_path(self, repo_id: str) -> Path:
        return self._get_repo_dir(repo_id) / "analysis.json"

    def analyze_repository(self, repository_id: str) -> RepositoryAnalysisResponse:
        """Parses all source code in the repository and generates code intelligence.

        Args:
            repository_id: Repository identifier.

        Returns:
            RepositoryAnalysisResponse with symbols, dependencies, and call graphs.

        Raises:
            ValueError: If repository directory does not exist.
        """
        repo_dir = self._get_repo_dir(repository_id)
        if not repo_dir.exists():
            raise ValueError(f"Repository '{repository_id}' does not exist.")

        source_dir = repo_dir / "source"
        if not source_dir.exists():
            source_dir = repo_dir

        logger.info(f"Starting code intelligence analysis for repository '{repository_id}'...")

        # Walk repository files safely respecting .gitignore
        _, total_files, _, _, file_records = walk_repository(repo_root=source_dir)
        all_repo_files = [rel_path.replace("\\", "/").strip("/") for rel_path, _ in file_records]

        file_results: Dict[str, FileAnalysisResult] = {}
        all_symbols: List[Symbol] = []
        languages_seen = set()

        for rel_path, _ in file_records:
            norm_rel_path = rel_path.replace("\\", "/").strip("/")
            full_file_path = source_dir / rel_path

            if not full_file_path.is_file():
                continue

            # Read source code safely
            try:
                content = full_file_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                file_results[norm_rel_path] = FileAnalysisResult(
                    file_path=norm_rel_path,
                    language="Unknown",
                    status="unsupported",
                    error_message=f"Failed to read file: {str(e)}",
                    symbols=[],
                    imports=[],
                    function_calls=[],
                    total_lines=0,
                )
                continue

            parse_res = parse_source_file(norm_rel_path, content)
            file_results[norm_rel_path] = parse_res
            if parse_res.language and parse_res.language != "Unknown":
                languages_seen.add(parse_res.language)

        # Step 2: Resolve Imports & Build Dependencies
        resolver = DependencyResolver(all_repo_files)

        # Resolve imports per file
        for rel_path, parse_res in list(file_results.items()):
            if parse_res.imports:
                resolved_imports = resolver.resolve_file_imports(
                    rel_path, parse_res.language, parse_res.imports
                )
                file_results[rel_path] = parse_res.model_copy(
                    update={"imports": resolved_imports}
                )

        dependencies, cycles = resolver.build_dependencies(file_results)

        # Step 3: Call Graph Resolution
        symbols_by_file: Dict[str, List[Symbol]] = {}
        imports_by_file: Dict[str, List[any]] = {}
        all_raw_calls: List[CallGraphEdge] = []

        for rel_path, parse_res in file_results.items():
            symbols_by_file[rel_path] = parse_res.symbols
            imports_by_file[rel_path] = parse_res.imports
            all_symbols.extend(parse_res.symbols)
            all_raw_calls.extend(parse_res.function_calls)

        call_graph_resolver = CallGraphResolver(symbols_by_file, imports_by_file)
        resolved_call_edges, resolved_calls_count = call_graph_resolver.resolve_edges(
            all_raw_calls
        )

        # Step 4: Summary Computation
        total_files = len(file_records)
        success_count = sum(1 for r in file_results.values() if r.status == "success")
        failed_count = sum(1 for r in file_results.values() if r.status == "syntax_error")
        unsupported_count = sum(1 for r in file_results.values() if r.status == "unsupported")

        total_funcs = sum(
            1 for s in all_symbols if s.symbol_type in ("function", "method")
        )
        total_classes = sum(
            1
            for s in all_symbols
            if s.symbol_type in ("class", "interface", "struct", "enum")
        )
        total_imports_count = sum(len(r.imports) for r in file_results.values())

        summary = RepositoryAnalysisSummary(
            repository_id=repository_id,
            total_files_scanned=total_files,
            successfully_parsed_files=success_count,
            failed_files=failed_count,
            unsupported_files=unsupported_count,
            total_symbols=len(all_symbols),
            total_functions=total_funcs,
            total_classes=total_classes,
            total_imports=total_imports_count,
            total_call_edges=len(resolved_call_edges),
            resolved_call_edges=resolved_calls_count,
            has_circular_dependencies=len(cycles) > 0,
            circular_dependency_cycles=cycles,
            languages_analyzed=sorted(list(languages_seen)),
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

        response = RepositoryAnalysisResponse(
            summary=summary,
            symbols=all_symbols,
            dependencies=dependencies,
            call_graph=resolved_call_edges,
            files=file_results,
        )

        # Persist analysis to disk
        self._save_analysis(repository_id, response)
        logger.info(
            f"Code intelligence analysis completed for '{repository_id}': "
            f"{len(all_symbols)} symbols, {len(resolved_call_edges)} calls, "
            f"{len(dependencies)} files analyzed."
        )

        return response

    def _save_analysis(self, repository_id: str, data: RepositoryAnalysisResponse) -> None:
        """Persists analysis payload to analysis.json in the repository directory."""
        analysis_path = self._get_analysis_path(repository_id)
        temp_path = analysis_path.with_suffix(".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))
        temp_path.replace(analysis_path)

    def get_analysis(self, repository_id: str) -> Optional[RepositoryAnalysisResponse]:
        """Retrieves existing analysis from disk, or None if not analyzed yet."""
        analysis_path = self._get_analysis_path(repository_id)
        if not analysis_path.exists():
            return None
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            return RepositoryAnalysisResponse.model_validate(content)
        except Exception as e:
            logger.error(f"Failed to read analysis for repository '{repository_id}': {e}")
            return None

    def get_symbols(
        self,
        repository_id: str,
        name: Optional[str] = None,
        symbol_type: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> List[Symbol]:
        """Returns filtered symbol list from repository analysis."""
        analysis = self.get_analysis(repository_id)
        if not analysis:
            return []

        symbols = analysis.symbols
        if name:
            name_lower = name.lower()
            symbols = [s for s in symbols if name_lower in s.name.lower()]
        if symbol_type:
            type_lower = symbol_type.lower()
            symbols = [s for s in symbols if s.symbol_type.lower() == type_lower]
        if file_path:
            norm_file = file_path.replace("\\", "/").strip("/")
            symbols = [s for s in symbols if norm_file in s.file_path]

        return symbols

    def get_dependencies(
        self, repository_id: str
    ) -> Optional[Dict[str, FileDependency]]:
        """Returns file dependencies map."""
        analysis = self.get_analysis(repository_id)
        return analysis.dependencies if analysis else None

    def get_call_graph(self, repository_id: str) -> Optional[List[CallGraphEdge]]:
        """Returns call graph edge list."""
        analysis = self.get_analysis(repository_id)
        return analysis.call_graph if analysis else None

    def get_file_analysis(
        self, repository_id: str, file_path: str
    ) -> Optional[FileAnalysisResult]:
        """Returns analysis result for a single source file."""
        analysis = self.get_analysis(repository_id)
        if not analysis:
            return None
        norm_path = file_path.replace("\\", "/").strip("/")
        return analysis.files.get(norm_path)


# Default singleton instance
code_analysis_service = CodeAnalysisService()
