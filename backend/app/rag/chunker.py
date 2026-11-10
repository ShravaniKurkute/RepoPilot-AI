"""Repository-aware code chunking system using AST symbol boundaries and fallback splitting."""

import hashlib
import os
from typing import Dict, List, Optional, Set, Tuple

from app.code_analysis.schemas import FileAnalysisResult, RepositoryAnalysisResponse, Symbol
from app.core.config import settings
from app.rag.schemas import CodeChunk


def _compute_hash(content: str) -> str:
    """Computes SHA-256 digest of content."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def _get_comment_prefix(language: str) -> str:
    """Returns appropriate comment prefix for a language."""
    if language in ("Python", "Ruby"):
        return "#"
    return "//"


class CodeChunker:
    """Extracts semantic, repository-aware code chunks using AST structures and fallback windowing."""

    def __init__(
        self,
        max_chunk_lines: int = settings.MAX_CHUNK_LINES,
        chunk_overlap_lines: int = settings.CHUNK_OVERLAP_LINES,
    ):
        self.max_chunk_lines = max_chunk_lines
        self.chunk_overlap_lines = chunk_overlap_lines

    def chunk_repository(
        self,
        repository_id: str,
        source_files: Dict[str, str],
        repository_analysis: Optional[RepositoryAnalysisResponse] = None,
    ) -> List[CodeChunk]:
        """Processes an entire repository into structured chunks.

        Args:
            repository_id: Unique repository ID.
            source_files: Mapping of relative file_path -> file text content.
            repository_analysis: Optional Phase 2 AST analysis.

        Returns:
            List of CodeChunk instances across all files.
        """
        all_chunks: List[CodeChunk] = []

        files_map = repository_analysis.files if repository_analysis else {}

        for file_path, content in source_files.items():
            norm_path = file_path.replace("\\", "/").strip("/")
            file_analysis = files_map.get(norm_path)
            chunks = self.chunk_file(
                repository_id=repository_id,
                file_path=norm_path,
                source_code=content,
                file_analysis=file_analysis,
            )
            all_chunks.extend(chunks)

        return all_chunks

    def chunk_file(
        self,
        repository_id: str,
        file_path: str,
        source_code: str,
        file_analysis: Optional[FileAnalysisResult] = None,
    ) -> List[CodeChunk]:
        """Generates AST-aware chunks for a single source file, or falls back to sliding windows.

        Args:
            repository_id: Repository identifier.
            file_path: Relative file path.
            source_code: Source code text.
            file_analysis: Optional AST analysis result.

        Returns:
            List of CodeChunk objects.
        """
        lines = source_code.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return []

        language = file_analysis.language if file_analysis else self._infer_language(file_path)

        # If AST analysis was successful and contains symbols, perform AST-aware chunking
        if file_analysis and file_analysis.status == "success" and file_analysis.symbols:
            return self._chunk_with_ast(
                repository_id=repository_id,
                file_path=file_path,
                source_code=source_code,
                lines=lines,
                language=language,
                file_analysis=file_analysis,
            )

        # Fallback to sliding-window line chunker
        return self._chunk_fallback(
            repository_id=repository_id,
            file_path=file_path,
            lines=lines,
            language=language,
        )

    def _chunk_with_ast(
        self,
        repository_id: str,
        file_path: str,
        source_code: str,
        lines: List[str],
        language: str,
        file_analysis: FileAnalysisResult,
    ) -> List[CodeChunk]:
        """Splits code along class, method, function, and module-level AST boundaries."""
        chunks: List[CodeChunk] = []
        total_lines = len(lines)
        comment_prefix = _get_comment_prefix(language)

        # Collect available import names for cross-referencing
        available_imports: Set[str] = set()
        for imp in file_analysis.imports:
            available_imports.add(imp.module)
            available_imports.update(imp.names)

        # 1. Preamble & Module Context (Leading comments, docstrings, imports)
        first_symbol_line = min((s.location.start_line for s in file_analysis.symbols), default=total_lines + 1)
        if first_symbol_line > 1:
            preamble_end = min(first_symbol_line - 1, total_lines)
            preamble_lines = lines[:preamble_end]
            preamble_text = "\n".join(preamble_lines).strip()
            if preamble_text and any(line.strip() for line in preamble_lines):
                content_hash = _compute_hash(preamble_text)
                chunk_id = f"{repository_id}::{file_path}::preamble::1_{preamble_end}::{content_hash[:8]}"
                chunks.append(
                    CodeChunk(
                        chunk_id=chunk_id,
                        repository_id=repository_id,
                        file_path=file_path,
                        language=language,
                        symbol_name="<module_preamble>",
                        symbol_type="module_context",
                        start_line=1,
                        end_line=preamble_end,
                        associated_class_or_function=None,
                        import_references=list(available_imports),
                        content=preamble_text,
                        content_hash=content_hash,
                    )
                )

        # 2. Organize symbols by hierarchy
        classes: Dict[str, Symbol] = {}
        methods_by_class: Dict[str, List[Symbol]] = {}
        standalone_funcs: List[Symbol] = []

        for s in file_analysis.symbols:
            if s.symbol_type in ("class", "interface", "struct"):
                classes[s.id] = s
                methods_by_class.setdefault(s.id, [])
            elif s.symbol_type == "method" and s.parent_symbol_id:
                methods_by_class.setdefault(s.parent_symbol_id, []).append(s)
            elif s.symbol_type in ("function", "method"):
                standalone_funcs.append(s)

        # 3. Process Classes & Methods
        covered_lines: Set[int] = set()

        for class_id, class_sym in classes.items():
            cls_start = class_sym.location.start_line
            cls_end = min(class_sym.location.end_line, total_lines)
            methods = methods_by_class.get(class_id, [])

            # Class Overview Chunk (class definition up to first method, or full class if small)
            if methods:
                # Find start of first method
                first_method_start = min(m.location.start_line for m in methods)
                overview_end = max(cls_start, first_method_start - 1)
            else:
                overview_end = cls_end

            cls_overview_lines = lines[cls_start - 1 : overview_end]
            cls_overview_text = "\n".join(cls_overview_lines).strip()

            if cls_overview_text:
                for ln in range(cls_start, overview_end + 1):
                    covered_lines.add(ln)

                # Add method summaries to class overview for high-level semantic retrieval
                if methods:
                    method_signatures = [f"{comment_prefix} Method: {m.name}" for m in methods]
                    cls_content = f"{cls_overview_text}\n\n{comment_prefix} Declared Methods:\n" + "\n".join(method_signatures)
                else:
                    cls_content = cls_overview_text

                content_hash = _compute_hash(cls_content)
                chunk_id = f"{repository_id}::{file_path}::{class_sym.name}::{cls_start}_{overview_end}::{content_hash[:8]}"
                chunks.append(
                    CodeChunk(
                        chunk_id=chunk_id,
                        repository_id=repository_id,
                        file_path=file_path,
                        language=language,
                        symbol_name=class_sym.name,
                        symbol_type=class_sym.symbol_type,
                        start_line=cls_start,
                        end_line=overview_end,
                        associated_class_or_function=None,
                        import_references=self._find_references(cls_content, available_imports),
                        content=cls_content,
                        content_hash=content_hash,
                    )
                )

            # Process individual methods in class
            for method in methods:
                m_start = method.location.start_line
                m_end = min(method.location.end_line, total_lines)
                for ln in range(m_start, m_end + 1):
                    covered_lines.add(ln)

                method_chunks = self._chunk_symbol(
                    repository_id=repository_id,
                    file_path=file_path,
                    lines=lines,
                    symbol=method,
                    associated_scope=class_sym.name,
                    language=language,
                    available_imports=available_imports,
                )
                chunks.extend(method_chunks)

        # 4. Process Standalone Functions
        for fn in standalone_funcs:
            fn_start = fn.location.start_line
            fn_end = min(fn.location.end_line, total_lines)
            for ln in range(fn_start, fn_end + 1):
                covered_lines.add(ln)

            fn_chunks = self._chunk_symbol(
                repository_id=repository_id,
                file_path=file_path,
                lines=lines,
                symbol=fn,
                associated_scope=None,
                language=language,
                available_imports=available_imports,
            )
            chunks.extend(fn_chunks)

        # 5. Check for uncovered line spans (e.g. scripts, top-level code blocks)
        uncovered_start = None
        for idx in range(1, total_lines + 1):
            if idx not in covered_lines and idx >= first_symbol_line:
                if uncovered_start is None:
                    uncovered_start = idx
            else:
                if uncovered_start is not None:
                    span_end = idx - 1
                    span_text = "\n".join(lines[uncovered_start - 1 : span_end]).strip()
                    if span_text and len(span_text) > 20:
                        content_hash = _compute_hash(span_text)
                        chunk_id = f"{repository_id}::{file_path}::block::{uncovered_start}_{span_end}::{content_hash[:8]}"
                        chunks.append(
                            CodeChunk(
                                chunk_id=chunk_id,
                                repository_id=repository_id,
                                file_path=file_path,
                                language=language,
                                symbol_name=None,
                                symbol_type="code_block",
                                start_line=uncovered_start,
                                end_line=span_end,
                                associated_class_or_function=None,
                                import_references=self._find_references(span_text, available_imports),
                                content=span_text,
                                content_hash=content_hash,
                            )
                        )
                    uncovered_start = None

        if uncovered_start is not None:
            span_text = "\n".join(lines[uncovered_start - 1 : total_lines]).strip()
            if span_text and len(span_text) > 20:
                content_hash = _compute_hash(span_text)
                chunk_id = f"{repository_id}::{file_path}::block::{uncovered_start}_{total_lines}::{content_hash[:8]}"
                chunks.append(
                    CodeChunk(
                        chunk_id=chunk_id,
                        repository_id=repository_id,
                        file_path=file_path,
                        language=language,
                        symbol_name=None,
                        symbol_type="code_block",
                        start_line=uncovered_start,
                        end_line=total_lines,
                        associated_class_or_function=None,
                        import_references=self._find_references(span_text, available_imports),
                        content=span_text,
                        content_hash=content_hash,
                    )
                )

        return chunks

    def _chunk_symbol(
        self,
        repository_id: str,
        file_path: str,
        lines: List[str],
        symbol: Symbol,
        associated_scope: Optional[str],
        language: str,
        available_imports: Set[str],
    ) -> List[CodeChunk]:
        """Creates chunks for a single symbol (function or method), handling oversized bodies."""
        start_line = symbol.location.start_line
        end_line = min(symbol.location.end_line, len(lines))
        symbol_lines = lines[start_line - 1 : end_line]
        total_sym_lines = len(symbol_lines)
        comment_prefix = _get_comment_prefix(language)

        scope_header = f"{comment_prefix} Scope: {associated_scope}.{symbol.name}\n" if associated_scope else ""

        # Case A: Symbol fits within standard max_chunk_lines
        if total_sym_lines <= self.max_chunk_lines:
            raw_text = "\n".join(symbol_lines).strip()
            content = f"{scope_header}{raw_text}" if scope_header else raw_text
            content_hash = _compute_hash(content)
            chunk_id = f"{repository_id}::{file_path}::{symbol.name}::{start_line}_{end_line}::{content_hash[:8]}"
            return [
                CodeChunk(
                    chunk_id=chunk_id,
                    repository_id=repository_id,
                    file_path=file_path,
                    language=language,
                    symbol_name=symbol.name,
                    symbol_type=symbol.symbol_type,
                    start_line=start_line,
                    end_line=end_line,
                    associated_class_or_function=associated_scope,
                    import_references=self._find_references(content, available_imports),
                    content=content,
                    content_hash=content_hash,
                )
            ]

        # Case B: Large symbol - Sub-chunk with overlap while preserving signature header
        sub_chunks: List[CodeChunk] = []
        signature_line = symbol_lines[0].strip()
        step = max(1, self.max_chunk_lines - self.chunk_overlap_lines)

        curr = 0
        part_idx = 1
        while curr < total_sym_lines:
            window_end = min(curr + self.max_chunk_lines, total_sym_lines)
            sub_lines = symbol_lines[curr:window_end]
            sub_text = "\n".join(sub_lines).strip()

            chunk_start_line = start_line + curr
            chunk_end_line = start_line + window_end - 1

            # Header preservation for continuations
            if curr > 0:
                header = f"{scope_header}{comment_prefix} {signature_line} [Part {part_idx}]\n"
            else:
                header = scope_header

            full_content = f"{header}{sub_text}" if header else sub_text
            content_hash = _compute_hash(full_content)
            chunk_id = f"{repository_id}::{file_path}::{symbol.name}_p{part_idx}::{chunk_start_line}_{chunk_end_line}::{content_hash[:8]}"

            sub_chunks.append(
                CodeChunk(
                    chunk_id=chunk_id,
                    repository_id=repository_id,
                    file_path=file_path,
                    language=language,
                    symbol_name=symbol.name,
                    symbol_type=symbol.symbol_type,
                    start_line=chunk_start_line,
                    end_line=chunk_end_line,
                    associated_class_or_function=associated_scope,
                    import_references=self._find_references(full_content, available_imports),
                    content=full_content,
                    content_hash=content_hash,
                )
            )

            if window_end >= total_sym_lines:
                break
            curr += step
            part_idx += 1

        return sub_chunks

    def _chunk_fallback(
        self,
        repository_id: str,
        file_path: str,
        lines: List[str],
        language: str,
    ) -> List[CodeChunk]:
        """Safe sliding-window chunker for unsupported languages and non-code files."""
        total_lines = len(lines)
        if total_lines == 0:
            return []

        chunks: List[CodeChunk] = []
        step = max(1, self.max_chunk_lines - self.chunk_overlap_lines)
        curr = 0
        part_idx = 1

        while curr < total_lines:
            window_end = min(curr + self.max_chunk_lines, total_lines)
            window_lines = lines[curr:window_end]
            text = "\n".join(window_lines).strip()

            if text:
                chunk_start = curr + 1
                chunk_end = window_end
                content_hash = _compute_hash(text)
                chunk_id = f"{repository_id}::{file_path}::chunk_{part_idx}::{chunk_start}_{chunk_end}::{content_hash[:8]}"

                chunks.append(
                    CodeChunk(
                        chunk_id=chunk_id,
                        repository_id=repository_id,
                        file_path=file_path,
                        language=language,
                        symbol_name=None,
                        symbol_type="fallback",
                        start_line=chunk_start,
                        end_line=chunk_end,
                        associated_class_or_function=None,
                        import_references=[],
                        content=text,
                        content_hash=content_hash,
                    )
                )

            if window_end >= total_lines:
                break
            curr += step
            part_idx += 1

        return chunks

    def _find_references(self, text: str, available_imports: Set[str]) -> List[str]:
        """Identifies which imported names appear in the given chunk text."""
        if not available_imports:
            return []
        refs = []
        for name in available_imports:
            if len(name) > 1 and name in text:
                refs.append(name)
        return sorted(refs)

    def _infer_language(self, file_path: str) -> str:
        """Infers language from extension when analysis is missing."""
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        mapping = {
            ".py": "Python",
            ".ts": "TypeScript",
            ".tsx": "TypeScript",
            ".js": "JavaScript",
            ".jsx": "JavaScript",
            ".java": "Java",
            ".c": "C",
            ".cpp": "C++",
            ".go": "Go",
            ".rs": "Rust",
            ".php": "PHP",
            ".rb": "Ruby",
            ".md": "Markdown",
            ".json": "JSON",
            ".yaml": "YAML",
            ".yml": "YAML",
            ".sql": "SQL",
            ".sh": "Shell",
        }
        return mapping.get(ext, "Plaintext")


# Global default chunker instance
default_chunker = CodeChunker()

