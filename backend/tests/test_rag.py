"""Comprehensive unit and integration tests for Phase 3: Repository-Aware RAG & Hybrid Retrieval."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.code_analysis.schemas import FileAnalysisResult, SourceLocation, Symbol
from app.main import app
from app.rag.chunker import CodeChunker
from app.rag.embeddings import MockEmbeddingProvider
from app.rag.hybrid_search import HybridSearchRanker
from app.rag.schemas import CodeChunk, SearchQuery, SearchResultChunk
from app.rag.service import RAGService
from app.rag.vector_store import VectorStore

client = TestClient(app)


# -------------------------------------------------------------
# 1. AST Code Chunking Tests
# -------------------------------------------------------------
def test_ast_code_chunking():
    chunker = CodeChunker(max_chunk_lines=50, chunk_overlap_lines=10)
    source = '''"""Module docstring for auth."""
import os
import sys

class AuthManager:
    """Class handling authentication."""
    def __init__(self, key: str):
        self.key = key

    def verify_token(self, token: str) -> bool:
        """Verifies JWT token."""
        return len(token) > 10

def generate_key() -> str:
    return "secret-key"
'''
    symbols = [
        Symbol(
            id="auth.py::AuthManager::5::class",
            name="AuthManager",
            symbol_type="class",
            file_path="auth.py",
            location=SourceLocation(start_line=5, end_line=13, start_column=1, end_column=1),
            language="Python",
        ),
        Symbol(
            id="auth.py::__init__::7",
            name="__init__",
            symbol_type="method",
            file_path="auth.py",
            location=SourceLocation(start_line=7, end_line=8, start_column=5, end_column=23),
            parent_symbol_id="auth.py::AuthManager::5::class",
            language="Python",
        ),
        Symbol(
            id="auth.py::verify_token::10",
            name="verify_token",
            symbol_type="method",
            file_path="auth.py",
            location=SourceLocation(start_line=10, end_line=12, start_column=5, end_column=35),
            parent_symbol_id="auth.py::AuthManager::5::class",
            language="Python",
        ),
        Symbol(
            id="auth.py::generate_key::14",
            name="generate_key",
            symbol_type="function",
            file_path="auth.py",
            location=SourceLocation(start_line=14, end_line=15, start_column=1, end_column=24),
            language="Python",
        ),
    ]

    analysis = FileAnalysisResult(
        file_path="auth.py",
        language="Python",
        status="success",
        symbols=symbols,
        imports=[],
        function_calls=[],
        total_lines=15,
    )

    chunks = chunker.chunk_file(
        repository_id="repo-123",
        file_path="auth.py",
        source_code=source,
        file_analysis=analysis,
    )

    assert len(chunks) >= 4
    types = [c.symbol_type for c in chunks]
    names = [c.symbol_name for c in chunks]

    # Preamble chunk
    assert "module_context" in types
    # Class overview
    assert "AuthManager" in names
    # Methods
    assert "verify_token" in names
    # Standalone function
    assert "generate_key" in names

    # Method association
    vt_chunk = next(c for c in chunks if c.symbol_name == "verify_token")
    assert vt_chunk.associated_class_or_function == "AuthManager"
    assert "AuthManager.verify_token" in vt_chunk.content


def test_oversized_symbol_subchunking():
    chunker = CodeChunker(max_chunk_lines=20, chunk_overlap_lines=5)
    # Generate large function of 50 lines
    body_lines = ["def huge_function():"]
    for i in range(1, 50):
        body_lines.append(f"    var_{i} = compute_value({i})")
    source = "\n".join(body_lines)

    symbol = Symbol(
        id="big.py::huge_function::1",
        name="huge_function",
        symbol_type="function",
        file_path="big.py",
        location=SourceLocation(start_line=1, end_line=50, start_column=1, end_column=1),
        language="Python",
    )

    analysis = FileAnalysisResult(
        file_path="big.py",
        language="Python",
        status="success",
        symbols=[symbol],
        imports=[],
        function_calls=[],
        total_lines=50,
    )

    chunks = chunker.chunk_file(
        repository_id="repo-123",
        file_path="big.py",
        source_code=source,
        file_analysis=analysis,
    )

    # Must be sub-chunked into multiple parts with signature preservation
    assert len(chunks) > 1
    assert "Part 1" not in chunks[0].content
    assert "Part 2" in chunks[1].content
    assert "huge_function" in chunks[1].content


def test_fallback_chunker():
    chunker = CodeChunker(max_chunk_lines=10, chunk_overlap_lines=2)
    doc_lines = [f"# Documentation Heading {i}\nSome description paragraph." for i in range(25)]
    doc_text = "\n".join(doc_lines)

    chunks = chunker.chunk_file(
        repository_id="repo-123",
        file_path="README.md",
        source_code=doc_text,
        file_analysis=None,
    )

    assert len(chunks) > 1
    for c in chunks:
        assert c.symbol_type == "fallback"
        assert c.language == "Markdown"
        assert c.content_hash is not None


# -------------------------------------------------------------
# 2. Embedding Provider Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_mock_embedding_provider():
    provider = MockEmbeddingProvider(dimension=768)
    assert provider.dimension == 768

    v1 = await provider.embed_query("authenticate user token")
    v2 = await provider.embed_query("authenticate user token")
    v3 = await provider.embed_query("render frontend table component")

    assert len(v1) == 768
    # Exact match must equal 1.0
    from app.rag.vector_store import _cosine_similarity
    assert pytest.approx(_cosine_similarity(v1, v2), 0.0001) == 1.0

    # Batch embedding
    batch = await provider.embed_batch(["text one", "text two", "text three"])
    assert len(batch) == 3
    assert len(batch[0]) == 768


# -------------------------------------------------------------
# 3. Vector Similarity & Keyword Search Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_vector_and_keyword_search(tmp_path: Path):
    store = VectorStore(storage_root=tmp_path)
    provider = MockEmbeddingProvider(dimension=768)

    chunk1 = CodeChunk(
        chunk_id="chunk1",
        repository_id="repo-search-test",
        file_path="auth.py",
        language="Python",
        symbol_name="login",
        symbol_type="function",
        start_line=1,
        end_line=10,
        content="def login(username, password): return verify_credentials(username, password)",
        content_hash="hash1",
    )
    chunk2 = CodeChunk(
        chunk_id="chunk2",
        repository_id="repo-search-test",
        file_path="math.py",
        language="Python",
        symbol_name="calculate_sum",
        symbol_type="function",
        start_line=1,
        end_line=5,
        content="def calculate_sum(a, b): return a + b",
        content_hash="hash2",
    )

    new_count, cached_count = await store.upsert_chunks(
        repository_id="repo-search-test",
        chunks=[chunk1, chunk2],
        embedding_provider=provider,
    )
    assert new_count == 2
    assert cached_count == 0

    # Vector search for login
    q_vec = await provider.embed_query("login user credentials")
    vec_results = await store.search_vector(
        repository_id="repo-search-test",
        query_vector=q_vec,
        top_k=5,
    )
    assert len(vec_results) == 2
    assert vec_results[0].symbol_name == "login"
    assert vec_results[0].relevance_score > vec_results[1].relevance_score

    # Keyword search for calculate
    kw_results = await store.search_keyword(
        repository_id="repo-search-test",
        query_text="calculate_sum",
        top_k=5,
    )
    assert len(kw_results) >= 1
    assert kw_results[0].symbol_name == "calculate_sum"


# -------------------------------------------------------------
# 4. Hybrid Search & RRF Ranking Tests
# -------------------------------------------------------------
def test_hybrid_rrf_ranking():
    ranker = HybridSearchRanker(default_semantic_weight=0.6, default_keyword_weight=0.4, rrf_constant=60)

    vec_results = [
        SearchResultChunk(
            chunk_id="c1",
            file_path="auth.py",
            start_line=1,
            end_line=10,
            language="Python",
            symbol_name="auth",
            content="def auth(): pass",
            relevance_score=0.9,
            retrieval_method="semantic",
            semantic_score=0.9,
        ),
        SearchResultChunk(
            chunk_id="c2",
            file_path="db.py",
            start_line=1,
            end_line=10,
            language="Python",
            symbol_name="db",
            content="def db(): pass",
            relevance_score=0.7,
            retrieval_method="semantic",
            semantic_score=0.7,
        ),
    ]

    kw_results = [
        SearchResultChunk(
            chunk_id="c1",  # present in both -> should be boosted
            file_path="auth.py",
            start_line=1,
            end_line=10,
            language="Python",
            symbol_name="auth",
            content="def auth(): pass",
            relevance_score=1.0,
            retrieval_method="keyword",
            keyword_score=3.0,
        ),
        SearchResultChunk(
            chunk_id="c3",
            file_path="net.py",
            start_line=1,
            end_line=10,
            language="Python",
            symbol_name="net",
            content="def net(): pass",
            relevance_score=0.5,
            retrieval_method="keyword",
            keyword_score=1.5,
        ),
    ]

    combined = ranker.combine_results(vec_results, kw_results, top_k=5)
    assert len(combined) == 3
    # c1 was in both vector and keyword -> highest score and hybrid tag
    assert combined[0].chunk_id == "c1"
    assert combined[0].retrieval_method == "hybrid"
    assert combined[0].relevance_score > combined[1].relevance_score


# -------------------------------------------------------------
# 5. Repository Isolation & Incremental Indexing Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_repository_isolation_and_incremental_indexing(tmp_path: Path):
    store = VectorStore(storage_root=tmp_path)
    provider = MockEmbeddingProvider(dimension=768)

    chunk_repo_a = CodeChunk(
        chunk_id="repo_a_chunk",
        repository_id="repo-A",
        file_path="main.py",
        language="Python",
        symbol_name="secret_function_A",
        start_line=1,
        end_line=5,
        content="def secret_function_A(): return 'alpha'",
        content_hash="hash_a",
    )
    chunk_repo_b = CodeChunk(
        chunk_id="repo_b_chunk",
        repository_id="repo-B",
        file_path="main.py",
        language="Python",
        symbol_name="secret_function_B",
        start_line=1,
        end_line=5,
        content="def secret_function_B(): return 'beta'",
        content_hash="hash_b",
    )

    await store.upsert_chunks("repo-A", [chunk_repo_a], provider)
    await store.upsert_chunks("repo-B", [chunk_repo_b], provider)

    # Search repo-A for "secret_function"
    results_a = await store.search_keyword("repo-A", "secret_function")
    assert all(r.chunk_id != "repo_b_chunk" for r in results_a)
    assert len(results_a) == 1
    assert results_a[0].chunk_id == "repo_a_chunk"

    # Incremental update: Re-indexing with same hash reuses cached embedding
    new_embedded, cached = await store.upsert_chunks("repo-A", [chunk_repo_a], provider)
    assert new_embedded == 0
    assert cached == 1


# -------------------------------------------------------------
# 6. End-to-End RAG Service & REST API Integration
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_rag_service_and_api(tmp_path: Path):
    repo_id = "test-repo-rag-phase3"
    repo_dir = tmp_path / repo_id
    source_dir = repo_dir / "source"
    source_dir.mkdir(parents=True)

    (source_dir / "service.py").write_text(
        "def fetch_user_data(user_id: str):\n    return {'user_id': user_id, 'active': True}\n",
        encoding="utf-8",
    )

    service = RAGService(
        vector_store=VectorStore(storage_root=tmp_path),
        chunker=CodeChunker(max_chunk_lines=50),
        embedding_provider=MockEmbeddingProvider(dimension=768),
        storage_root=tmp_path,
    )

    # Trigger indexing
    index_res = await service.index_repository(repo_id)
    assert index_res.status == "completed"
    assert index_res.total_chunks >= 1
    assert index_res.new_chunks_embedded >= 1

    # Search
    search_q = SearchQuery(query="fetch user data", top_k=5, search_mode="hybrid")
    search_res = await service.search(repo_id, search_q)
    assert search_res.total_results >= 1
    assert "service.py" in search_res.results[0].file_path

    # Wire into API router
    from app.api.v1 import rag
    orig_service = rag.rag_service
    rag.rag_service = service

    try:
        # Index status API
        status_resp = client.get(f"/api/v1/repositories/{repo_id}/index/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["data"]["status"] == "completed"

        # Index stats API
        stats_resp = client.get(f"/api/v1/repositories/{repo_id}/index/stats")
        assert stats_resp.status_code == 200
        assert stats_resp.json()["data"]["total_chunks"] >= 1

        # Search API
        post_search = client.post(
            f"/api/v1/repositories/{repo_id}/search",
            json={"query": "fetch user data", "top_k": 3, "search_mode": "hybrid"},
        )
        assert post_search.status_code == 200
        search_data = post_search.json()["data"]
        assert search_data["total_results"] >= 1
        assert "fetch_user_data" in search_data["results"][0]["content"]

        # Delete index API
        del_resp = client.delete(f"/api/v1/repositories/{repo_id}/index")
        assert del_resp.status_code == 200
        assert del_resp.json()["data"]["deleted"] is True

        # Verify index is cleared
        stats_after = client.get(f"/api/v1/repositories/{repo_id}/index/stats")
        assert stats_after.json()["data"]["total_chunks"] == 0

    finally:
        rag.rag_service = orig_service

