"""Context builder combining Phase 2 AST symbols and Phase 3 RAG retrieved context."""

from dataclasses import dataclass, field
import hashlib
from typing import Dict, List, Optional, Set

from app.code_analysis.schemas import FileAnalysisResult, Symbol
from app.core.config import settings
from app.core.logging import logger
from app.rag.schemas import SearchQuery
from app.rag.service import rag_service


@dataclass
class AnalysisContext:
    """Bounded, high-relevance code and architectural context supplied to the AI analyzer."""

    repository_id: str
    file_path: str
    language: str
    target_code: str
    start_line: int
    end_line: int
    symbol_name: Optional[str] = None
    symbol_type: Optional[str] = None
    ast_summary: str = ""
    imports_context: List[str] = field(default_factory=list)
    related_rag_contexts: List[Dict[str, str]] = field(default_factory=list)


class AnalysisContextBuilder:
    """Extracts target source slices, formats AST signatures, and queries RAG for related code."""

    def __init__(self, max_rag_chunks: Optional[int] = None):
        self._max_rag_chunks = max_rag_chunks

    @property
    def max_rag_chunks(self) -> int:
        if self._max_rag_chunks is not None:
            return self._max_rag_chunks
        return settings.ANALYSIS_MAX_CONTEXT_CHUNKS

    @max_rag_chunks.setter
    def max_rag_chunks(self, val: int) -> None:
        self._max_rag_chunks = val

    async def build_context_for_symbol(
        self,
        repository_id: str,
        file_path: str,
        source_code: str,
        symbol: Symbol,
        file_analysis: Optional[FileAnalysisResult] = None,
    ) -> AnalysisContext:
        """Builds context for an individual function, method, or class."""
        lines = source_code.splitlines()
        start = symbol.location.start_line
        end = min(symbol.location.end_line, len(lines))

        target_lines = lines[start - 1 : end]
        target_code = "\n".join(target_lines)

        # Format AST summary
        ast_parts = [
            f"Symbol: {symbol.name} ({symbol.symbol_type})",
            f"Defined at lines {start}-{end} in {file_path}",
        ]
        if symbol.parameters:
            ast_parts.append(f"Parameters: ({', '.join(symbol.parameters)})")
        if symbol.return_type:
            ast_parts.append(f"Return Type: {symbol.return_type}")
        if symbol.decorators:
            ast_parts.append(f"Decorators: {', '.join(symbol.decorators)}")
        if symbol.docstring:
            ast_parts.append(f"Docstring: {symbol.docstring.strip()}")

        # Call sites within this symbol
        called: List[str] = []
        if file_analysis:
            called = list(dict.fromkeys(
                c.callee_name
                for c in file_analysis.function_calls
                if start <= c.line_number <= end
            ))
            if called:
                ast_parts.append(f"Internal Calls: {', '.join(called[:10])}")

        ast_summary = "\n".join(ast_parts)

        # Extract unique file imports
        imports_list: List[str] = []
        if file_analysis and file_analysis.imports:
            seen_imports: Set[str] = set()
            for imp in file_analysis.imports:
                stmt = imp.statement.strip()
                if stmt and stmt not in seen_imports:
                    seen_imports.add(stmt)
                    imports_list.append(stmt)
                    if len(imports_list) >= 15:
                        break

        # Query Phase 3 RAG prioritizing callers and callees
        rag_contexts = await self._retrieve_related_context(
            repository_id=repository_id,
            target_symbol=symbol.name,
            target_file=file_path,
            callees=called[:3],
        )

        return AnalysisContext(
            repository_id=repository_id,
            file_path=file_path,
            language=symbol.language,
            target_code=target_code,
            start_line=start,
            end_line=end,
            symbol_name=symbol.name,
            symbol_type=symbol.symbol_type,
            ast_summary=ast_summary,
            imports_context=imports_list,
            related_rag_contexts=rag_contexts,
        )

    async def build_context_for_file(
        self,
        repository_id: str,
        file_path: str,
        source_code: str,
        file_analysis: Optional[FileAnalysisResult] = None,
    ) -> AnalysisContext:
        """Builds context for an entire source file."""
        lines = source_code.splitlines()
        total_lines = len(lines)
        language = file_analysis.language if file_analysis else "Code"

        # AST summary of symbols declared in file
        ast_parts = [f"File: {file_path} (Total lines: {total_lines})"]
        primary_symbols: List[str] = []
        if file_analysis and file_analysis.symbols:
            sym_names = [f"{s.symbol_type} {s.name}" for s in file_analysis.symbols[:20]]
            ast_parts.append(f"Declared Symbols: {', '.join(sym_names)}")
            primary_symbols = [
                s.name for s in file_analysis.symbols
                if s.symbol_type in ("function", "class", "method")
            ][:3]
        ast_summary = "\n".join(ast_parts)

        # Extract unique imports
        imports_list: List[str] = []
        if file_analysis and file_analysis.imports:
            seen_imports: Set[str] = set()
            for imp in file_analysis.imports:
                stmt = imp.statement.strip()
                if stmt and stmt not in seen_imports:
                    seen_imports.add(stmt)
                    imports_list.append(stmt)
                    if len(imports_list) >= 15:
                        break

        # RAG context for primary symbols declared in this file
        search_target = " ".join(primary_symbols) if primary_symbols else file_path.split("/")[-1].split(".")[0]
        rag_contexts = await self._retrieve_related_context(
            repository_id=repository_id,
            target_symbol=search_target,
            target_file=file_path,
        )

        return AnalysisContext(
            repository_id=repository_id,
            file_path=file_path,
            language=language,
            target_code=source_code,
            start_line=1,
            end_line=total_lines,
            symbol_name=None,
            symbol_type="file",
            ast_summary=ast_summary,
            imports_context=imports_list,
            related_rag_contexts=rag_contexts,
        )

    async def _retrieve_related_context(
        self,
        repository_id: str,
        target_symbol: str,
        target_file: str,
        callees: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Queries Phase 3 RAG for caller and callee contexts, strictly deduplicating and bounding tokens."""
        contexts: List[Dict[str, str]] = []
        seen_keys: Set[str] = set()
        seen_hashes: Set[str] = set()

        queries: List[str] = []
        if target_symbol and target_symbol.strip():
            queries.append(f"{target_symbol} callers and usages")
        if callees:
            queries.append(f"implementation of {' '.join(callees)}")

        for query_text in queries:
            if len(contexts) >= self.max_rag_chunks:
                break
            try:
                search_res = await rag_service.search(
                    repository_id=repository_id,
                    search_query=SearchQuery(
                        query=query_text,
                        top_k=min(self.max_rag_chunks, settings.ANALYSIS_MAX_CONTEXT_CHUNKS),
                        search_mode="hybrid",
                    ),
                )

                for chunk in search_res.results:
                    if len(contexts) >= self.max_rag_chunks:
                        break

                    # Exclude chunks from the same file to prevent self-duplication
                    if chunk.file_path == target_file:
                        continue

                    chunk_key = f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
                    if chunk_key in seen_keys:
                        continue

                    raw_content = chunk.content.strip()
                    if len(raw_content) < 20:
                        continue

                    # Content deduplication hash
                    content_hash = hashlib.md5(raw_content.encode("utf-8", errors="ignore")).hexdigest()
                    if content_hash in seen_hashes:
                        continue

                    seen_keys.add(chunk_key)
                    seen_hashes.add(content_hash)

                    contexts.append(
                        {
                            "file_path": chunk.file_path,
                            "lines": f"{chunk.start_line}-{chunk.end_line}",
                            "symbol": chunk.symbol_name or "<anonymous>",
                            "content": raw_content[:600],  # Bounded, high-relevance snippet
                        }
                    )
            except Exception as search_err:
                # Log warning with full context instead of silently silencing
                logger.warning(
                    "RAG search error during context retrieval for repository '%s' (query: '%s'): %s",
                    repository_id,
                    query_text,
                    search_err,
                    exc_info=True,
                )

        return contexts[: self.max_rag_chunks]


default_context_builder = AnalysisContextBuilder()


