"""Central RAG service orchestrating repository chunking, embeddings, and hybrid retrieval."""

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from app.code_analysis.service import code_analysis_service
from app.core.config import settings
from app.core.logging import logger
from app.rag.chunker import CodeChunker, default_chunker
from app.rag.embeddings import BaseEmbeddingProvider, get_embedding_provider
from app.rag.hybrid_search import HybridSearchRanker
from app.rag.schemas import (
    IndexingStatsResponse,
    IndexingStatusResponse,
    SearchQuery,
    SearchResponse,
    SearchResultChunk,
)
from app.rag.vector_store import VectorStore, default_vector_store
from app.repository.file_walker import walk_repository


# Binary, media, archive, and font extensions to exclude from code RAG
EXCLUDED_EXTENSIONS: Set[str] = {
    # Images & media
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    # Documents & archives
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar", ".bz2", ".xz",
    # Binaries & bytecode
    ".exe", ".dll", ".so", ".dylib", ".bin", ".pyc", ".pyo", ".class", ".o", ".a", ".wasm",
    # Fonts
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Data dumps & db
    ".db", ".sqlite", ".sqlite3", ".parquet",
    # Source maps
    ".map",
}

# Generated lockfiles to exclude from semantic code index
EXCLUDED_FILENAMES: Set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
    "poetry.lock",
    "gemfile.lock",
    "cargo.lock",
    "mix.lock",
}

# Maximum single source file size for RAG chunking (512 KB)
MAX_SOURCE_FILE_BYTES: int = 512 * 1024


def is_minified_or_bundle(filename: str) -> bool:
    """Checks if a file is a minified bundle or compiler artifact."""
    lower = filename.lower()
    return (
        lower.endswith(".min.js")
        or lower.endswith(".min.css")
        or ".bundle." in lower
        or ".chunk." in lower
    )


def is_binary_file(file_path: Path) -> bool:
    """Detects binary content by scanning the first 1024 bytes for null bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return False


class RAGService:
    """Coordinates AST-guided code chunking, vector embeddings, and hybrid code retrieval."""

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        chunker: Optional[CodeChunker] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
        ranker: Optional[HybridSearchRanker] = None,
        storage_root: Optional[Path] = None,
    ):
        self.vector_store = vector_store or default_vector_store
        self.chunker = chunker or default_chunker
        self.embedding_provider = embedding_provider or get_embedding_provider()
        self.ranker = ranker or HybridSearchRanker(
            default_semantic_weight=settings.RAG_SEMANTIC_WEIGHT,
            default_keyword_weight=settings.RAG_KEYWORD_WEIGHT,
        )

        if storage_root is not None:
            self.storage_root = storage_root.resolve()
        else:
            p = Path(settings.WORKSPACE_STORAGE_PATH)
            self.storage_root = p if p.is_absolute() else (Path.cwd() / p).resolve()

        # In-memory indexing locks and active tasks to prevent duplicate simultaneous indexing
        self._indexing_locks: Dict[str, asyncio.Lock] = {}
        self._active_status: Dict[str, IndexingStatusResponse] = {}

    def _get_lock(self, repository_id: str) -> asyncio.Lock:
        """Retrieves or creates an asyncio.Lock for a specific repository."""
        if repository_id not in self._indexing_locks:
            self._indexing_locks[repository_id] = asyncio.Lock()
        return self._indexing_locks[repository_id]

    def _get_repo_dir(self, repo_id: str) -> Path:
        return self.storage_root / repo_id

    async def index_repository(
        self,
        repository_id: str,
        force_reindex: bool = False,
        progress_callback: Optional[Callable[[str, str], Any]] = None,
    ) -> IndexingStatusResponse:
        """Indexes all code in repository: parses ASTs, generates chunks, and creates vector embeddings.

        Guarantees:
        - Prevents duplicate indexing jobs for the same repository via mutex.
        - Emits detailed structured logs with timestamps and execution durations.
        - Transitions cleanly to FAILED status with error details if an exception occurs.
        - Reports lifecycle progress stages through optional progress_callback.
        """
        lock = self._get_lock(repository_id)

        # Check if already locked (in progress by another coroutine)
        if lock.locked():
            logger.info(
                "RAG indexing for repository '%s' is already in progress. Awaiting completion of existing job...",
                repository_id,
            )
            async with lock:
                return self.get_indexing_status(repository_id)

        async with lock:
            return await self._execute_index_repository(
                repository_id=repository_id,
                force_reindex=force_reindex,
                progress_callback=progress_callback,
            )

    async def _execute_index_repository(
        self,
        repository_id: str,
        force_reindex: bool = False,
        progress_callback: Optional[Callable[[str, str], Any]] = None,
    ) -> IndexingStatusResponse:
        """Internal execution body guarded by per-repository mutex."""
        t_start_total = time.time()
        start_iso = datetime.now(timezone.utc).isoformat()

        repo_dir = self._get_repo_dir(repository_id)
        if not repo_dir.exists():
            raise ValueError(f"Repository '{repository_id}' does not exist.")

        source_dir = repo_dir / "source"
        if not source_dir.exists():
            source_dir = repo_dir

        async def _notify(stage: str, msg: str, status: str = "indexing") -> None:
            self._active_status[repository_id] = IndexingStatusResponse(
                repository_id=repository_id,
                status=status,
                current_stage=stage,
                stage_message=msg,
                total_chunks=0,
                total_files_indexed=0,
                new_chunks_embedded=0,
                cached_chunks=0,
                last_indexed_at=start_iso,
                error_message=None,
            )
            if progress_callback:
                try:
                    res = progress_callback(stage, msg)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as cb_err:
                    logger.debug("Progress callback error: %s", cb_err)

        logger.info(
            "=== Starting RAG indexing for repository '%s' (force_reindex=%s, provider=%s, model=%s) ===",
            repository_id,
            force_reindex,
            self.embedding_provider.__class__.__name__,
            self.embedding_provider.model_name,
        )

        try:
            # -------------------------------------------------------------
            # Stage 1: File Discovery & AST Analysis
            # -------------------------------------------------------------
            await _notify("Discovering Files", "Discovering repository source files and extracting AST syntax...")
            t_disc_start = time.time()
            logger.info("[1/10] Repository file discovery started for '%s' in %s...", repository_id, source_dir)

            # Ensure Phase 2 AST analysis is ready
            ast_analysis = code_analysis_service.get_analysis(repository_id)
            if not ast_analysis:
                logger.info("Computing Phase 2 AST analysis before indexing for '%s'...", repository_id)
                try:
                    ast_analysis = code_analysis_service.analyze_repository(repository_id)
                except Exception as ast_err:
                    logger.warning("Could not compute Phase 2 AST analysis for '%s': %s", repository_id, ast_err)
                    ast_analysis = None

            _, total_walked_files, _, _, file_records = walk_repository(repo_root=source_dir)
            t_disc_elapsed = time.time() - t_disc_start

            logger.info(
                "[2/10] Number of files discovered by file walker: %d (discovery completed in %.3fs).",
                len(file_records),
                t_disc_elapsed,
            )

            # Filter out non-code, binary, lockfiles, minified files, and oversized files
            valid_file_records: List[Tuple[str, int]] = []
            exclusion_reasons: Dict[str, int] = {
                "binary_extension": 0,
                "lockfile": 0,
                "minified_or_bundle": 0,
                "oversized": 0,
                "binary_null_byte": 0,
            }

            for rel_path, file_size in file_records:
                norm_path = rel_path.replace("\\", "/").strip("/")
                file_name = os.path.basename(norm_path).lower()
                _, ext = os.path.splitext(file_name)

                if ext in EXCLUDED_EXTENSIONS:
                    exclusion_reasons["binary_extension"] += 1
                    continue

                if file_name in EXCLUDED_FILENAMES:
                    exclusion_reasons["lockfile"] += 1
                    continue

                if is_minified_or_bundle(file_name):
                    exclusion_reasons["minified_or_bundle"] += 1
                    continue

                if file_size > MAX_SOURCE_FILE_BYTES:
                    exclusion_reasons["oversized"] += 1
                    continue

                full_path = source_dir / rel_path
                if not full_path.is_file():
                    continue

                if is_binary_file(full_path):
                    exclusion_reasons["binary_null_byte"] += 1
                    continue

                valid_file_records.append((rel_path, file_size))

            total_excluded = len(file_records) - len(valid_file_records)
            logger.info(
                "[3/10] Number of files excluded: %d (Breakdown: %s). Retained %d source files for RAG indexing.",
                total_excluded,
                exclusion_reasons,
                len(valid_file_records),
            )

            # -------------------------------------------------------------
            # Stage 2: Source-Code Extraction
            # -------------------------------------------------------------
            await _notify("Extracting Source Code", f"Extracting text from {len(valid_file_records)} source files...")
            t_extract_start = time.time()
            logger.info("[4/10] Source-code extraction started for %d files...", len(valid_file_records))

            source_files: Dict[str, str] = {}
            total_bytes_read = 0

            for rel_path, _ in valid_file_records:
                norm_path = rel_path.replace("\\", "/").strip("/")
                full_path = source_dir / rel_path
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    source_files[norm_path] = content
                    total_bytes_read += len(content.encode("utf-8"))
                except Exception as read_err:
                    logger.warning("Failed to read source file '%s': %s", norm_path, read_err)

            t_extract_elapsed = time.time() - t_extract_start
            logger.info(
                "[4/10] Source-code extraction completed in %.3fs: successfully extracted %d files (%.2f KB total).",
                t_extract_elapsed,
                len(source_files),
                total_bytes_read / 1024.0,
            )

            # -------------------------------------------------------------
            # Stage 3: Code Chunking
            # -------------------------------------------------------------
            await _notify("Generating Code Chunks", f"Generating AST symbol chunks across {len(source_files)} files...")
            t_chunk_start = time.time()
            logger.info("[5/10] Code chunk generation started across %d source files...", len(source_files))

            chunks = self.chunker.chunk_repository(
                repository_id=repository_id,
                source_files=source_files,
                repository_analysis=ast_analysis,
            )
            t_chunk_elapsed = time.time() - t_chunk_start

            logger.info(
                "[5/10] Number of code chunks generated: %d chunks in %.3fs across %d files.",
                len(chunks),
                t_chunk_elapsed,
                len(source_files),
            )

            # -------------------------------------------------------------
            # Stage 4: Embedding Generation & Vector Store Upsert
            # -------------------------------------------------------------
            await _notify(
                "Generating Embeddings",
                f"Generating embeddings for code chunks ({self.embedding_provider.model_name})...",
            )
            t_embed_start = time.time()
            logger.info(
                "[6/10] Embedding generation and vector store insertion started (target chunks: %d)...",
                len(chunks),
            )

            new_count, cached_count = await self.vector_store.upsert_chunks(
                repository_id=repository_id,
                chunks=chunks,
                embedding_provider=self.embedding_provider,
                force_reindex=force_reindex,
            )
            t_embed_elapsed = time.time() - t_embed_start

            logger.info(
                "[8/10] Vector database insertion & embedding completed in %.2fs: %d new embeddings generated, %d cached reused.",
                t_embed_elapsed,
                new_count,
                cached_count,
            )

            # -------------------------------------------------------------
            # Stage 5: Index Persistence Verification
            # -------------------------------------------------------------
            await _notify("Building Vector Index", "Verifying index persistence and stats...")
            t_persist_start = time.time()
            stats = self.vector_store.get_stats(repository_id)
            t_persist_elapsed = time.time() - t_persist_start

            logger.info(
                "[9/10] Index persistence completed in %.3fs: verified %d total chunks in index.",
                t_persist_elapsed,
                stats.total_chunks,
            )

            # -------------------------------------------------------------
            # Stage 6: Completion
            # -------------------------------------------------------------
            t_total_elapsed = time.time() - t_start_total
            logger.info(
                "[10/10] Total indexing duration for repository '%s': %.2fs (%d total chunks stored).",
                repository_id,
                t_total_elapsed,
                len(chunks),
            )

            completed_resp = IndexingStatusResponse(
                repository_id=repository_id,
                status="completed",
                current_stage="Analysis Completed",
                stage_message=f"Indexed {len(chunks)} chunks across {len(source_files)} files in {t_total_elapsed:.1f}s.",
                total_chunks=len(chunks),
                total_files_indexed=len(source_files),
                new_chunks_embedded=new_count,
                cached_chunks=cached_count,
                last_indexed_at=datetime.now(timezone.utc).isoformat(),
                error_message=None,
            )
            await _notify("Analysis Completed", completed_resp.stage_message or "Indexing completed.", status="completed")
            self._active_status[repository_id] = completed_resp
            return completed_resp

        except Exception as e:
            total_elapsed = time.time() - t_start_total
            err_msg = str(e)
            logger.exception(
                "RAG indexing FAILED for repository '%s' after %.2fs: %s",
                repository_id,
                total_elapsed,
                err_msg,
            )
            failed_resp = IndexingStatusResponse(
                repository_id=repository_id,
                status="failed",
                current_stage="Analysis Failed",
                stage_message=f"Indexing failed: {err_msg}",
                total_chunks=0,
                total_files_indexed=0,
                new_chunks_embedded=0,
                cached_chunks=0,
                last_indexed_at=datetime.now(timezone.utc).isoformat(),
                error_message=err_msg,
            )
            self._active_status[repository_id] = failed_resp
            if progress_callback:
                try:
                    res = progress_callback("Analysis Failed", f"Indexing error: {err_msg}")
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass
            raise RuntimeError(f"RAG indexing failed for repository '{repository_id}': {err_msg}") from e

    def get_indexing_status(self, repository_id: str) -> IndexingStatusResponse:
        """Retrieves indexing status for a repository."""
        # Return active status if an in-memory job is running or recently finished
        if repository_id in self._active_status:
            return self._active_status[repository_id]

        stats = self.vector_store.get_stats(repository_id)
        status = "completed" if stats.total_chunks > 0 else "idle"

        return IndexingStatusResponse(
            repository_id=repository_id,
            status=status,
            current_stage="Completed" if status == "completed" else "Idle",
            stage_message=f"{stats.total_chunks} chunks indexed" if status == "completed" else "Not yet indexed",
            total_chunks=stats.total_chunks,
            total_files_indexed=stats.total_files,
            new_chunks_embedded=stats.total_chunks,
            cached_chunks=0,
            last_indexed_at=stats.last_indexed_at,
            error_message=None,
        )

    def get_indexing_stats(self, repository_id: str) -> IndexingStatsResponse:
        """Retrieves detailed chunk and language statistics."""
        return self.vector_store.get_stats(repository_id)

    async def search(
        self,
        repository_id: str,
        search_query: SearchQuery,
    ) -> SearchResponse:
        """Executes hybrid, semantic, or keyword search across indexed repository code.

        Args:
            repository_id: Repository ID.
            search_query: SearchQuery specification.

        Returns:
            SearchResponse containing ranked code chunks.
        """
        repo_dir = self._get_repo_dir(repository_id)
        if not repo_dir.exists():
            raise ValueError(f"Repository '{repository_id}' does not exist.")

        mode = search_query.search_mode.lower().strip()
        top_k = search_query.top_k
        query = search_query.query

        # Check if repository has indexed chunks
        stats = self.vector_store.get_stats(repository_id)
        if stats.total_chunks == 0:
            logger.info("Repository '%s' not yet indexed. Running initial indexing before search...", repository_id)
            await self.index_repository(repository_id)

        results: List[SearchResultChunk] = []

        if mode == "semantic":
            # Semantic Vector Search
            query_vec = await self.embedding_provider.embed_query(query)
            results = await self.vector_store.search_vector(
                repository_id=repository_id,
                query_vector=query_vec,
                top_k=top_k,
                language=search_query.language,
                file_path=search_query.file_path,
            )

        elif mode == "keyword":
            # Lexical Keyword Search
            results = await self.vector_store.search_keyword(
                repository_id=repository_id,
                query_text=query,
                top_k=top_k,
                language=search_query.language,
                file_path=search_query.file_path,
            )

        else:
            # Hybrid Search (Semantic + Keyword + RRF)
            query_vec = await self.embedding_provider.embed_query(query)

            vector_task = self.vector_store.search_vector(
                repository_id=repository_id,
                query_vector=query_vec,
                top_k=top_k * 2,
                language=search_query.language,
                file_path=search_query.file_path,
            )
            keyword_task = self.vector_store.search_keyword(
                repository_id=repository_id,
                query_text=query,
                top_k=top_k * 2,
                language=search_query.language,
                file_path=search_query.file_path,
            )

            vec_res, kw_res = await asyncio.gather(vector_task, keyword_task)
            results = self.ranker.combine_results(
                vector_results=vec_res,
                keyword_results=kw_res,
                top_k=top_k,
            )

        return SearchResponse(
            repository_id=repository_id,
            query=query,
            search_mode=mode,
            total_results=len(results),
            results=results,
        )

    async def delete_index(self, repository_id: str) -> bool:
        """Deletes all indexed chunks and embeddings for a repository."""
        return await self.vector_store.delete_repository_index(repository_id)


# Global default RAG service instance
rag_service = RAGService()
