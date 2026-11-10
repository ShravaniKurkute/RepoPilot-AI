"""Retrieval-Augmented Generation (RAG) and hybrid code retrieval package.

Provides:
- AST-guided code chunker with fallback windowing
- Embedding generation with Gemini and offline mock providers
- PostgreSQL + pgvector persistent vector store
- Reciprocal Rank Fusion (RRF) hybrid search
- Central RAGService orchestrator
"""

from app.rag.chunker import CodeChunker, default_chunker
from app.rag.embeddings import (
    BaseEmbeddingProvider,
    GeminiEmbeddingProvider,
    MockEmbeddingProvider,
    get_embedding_provider,
)
from app.rag.hybrid_search import HybridSearchRanker
from app.rag.schemas import (
    CodeChunk,
    IndexingStatsResponse,
    IndexingStatusResponse,
    SearchQuery,
    SearchResponse,
    SearchResultChunk,
)
from app.rag.service import RAGService, rag_service
from app.rag.vector_store import VectorStore, default_vector_store

__all__ = [
    "BaseEmbeddingProvider",
    "CodeChunk",
    "CodeChunker",
    "GeminiEmbeddingProvider",
    "HybridSearchRanker",
    "IndexingStatsResponse",
    "IndexingStatusResponse",
    "MockEmbeddingProvider",
    "RAGService",
    "SearchQuery",
    "SearchResponse",
    "SearchResultChunk",
    "VectorStore",
    "default_chunker",
    "default_vector_store",
    "get_embedding_provider",
    "rag_service",
]
