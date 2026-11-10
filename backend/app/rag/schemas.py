"""Pydantic schemas for code chunking, embeddings, vector indexing, and hybrid retrieval."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CodeChunk(BaseModel):
    """Structured code chunk representation with AST and contextual metadata."""

    chunk_id: str = Field(..., description="Unique deterministic chunk ID (e.g. repo::path::symbol::start-end)")
    repository_id: str = Field(..., description="Target repository ID")
    file_path: str = Field(..., description="Relative file path within repository")
    language: str = Field(..., description="Programming language of chunk")
    symbol_name: Optional[str] = Field(None, description="Name of function/class/method symbol")
    symbol_type: Optional[str] = Field(
        None, description="Symbol type: function, method, class, module_context, fallback"
    )
    start_line: int = Field(..., ge=1, description="1-based starting line number")
    end_line: int = Field(..., ge=1, description="1-based ending line number")
    associated_class_or_function: Optional[str] = Field(
        None, description="Enclosing class or outer function name if nested"
    )
    import_references: List[str] = Field(
        default_factory=list, description="Referenced imports or package names relevant to this chunk"
    )
    content: str = Field(..., description="Source code text of this chunk")
    content_hash: str = Field(..., description="SHA-256 hash of chunk content for change detection")
    embedding: Optional[List[float]] = Field(None, description="Vector embedding representation")


class SearchQuery(BaseModel):
    """User search query request payload."""

    query: str = Field(..., min_length=1, description="Natural language or code query string")
    top_k: int = Field(default=10, ge=1, le=50, description="Maximum number of chunks to retrieve")
    search_mode: str = Field(
        default="hybrid",
        description="Retrieval mode: 'hybrid', 'semantic', or 'keyword'",
    )
    language: Optional[str] = Field(None, description="Optional filter by language")
    file_path: Optional[str] = Field(None, description="Optional filter by file path substring")


class SearchResultChunk(BaseModel):
    """Ranked code snippet retrieved from hybrid search."""

    chunk_id: str = Field(..., description="Chunk identifier")
    file_path: str = Field(..., description="Relative file path")
    start_line: int = Field(..., ge=1, description="1-based starting line")
    end_line: int = Field(..., ge=1, description="1-based ending line")
    language: str = Field(..., description="Programming language")
    symbol_name: Optional[str] = Field(None, description="Symbol name if applicable")
    symbol_type: Optional[str] = Field(None, description="Symbol type (function, method, class, etc.)")
    associated_class_or_function: Optional[str] = Field(None, description="Parent class or scope")
    content: str = Field(..., description="Code snippet content")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Normalized ranking score (0.0 - 1.0)")
    retrieval_method: str = Field(
        ..., description="Retrieval source: 'hybrid', 'semantic', or 'keyword'"
    )
    semantic_score: Optional[float] = Field(None, description="Cosine similarity score if matched in vector search")
    keyword_score: Optional[float] = Field(None, description="Keyword rank score if matched in keyword search")


class SearchResponse(BaseModel):
    """Standardized search response payload."""

    repository_id: str = Field(..., description="Repository ID")
    query: str = Field(..., description="Original search query")
    search_mode: str = Field(..., description="Search mode executed")
    total_results: int = Field(..., ge=0, description="Count of returned results")
    results: List[SearchResultChunk] = Field(default_factory=list, description="Ranked code snippets")


class IndexingStatusResponse(BaseModel):
    """Indexing status report for a repository."""

    repository_id: str = Field(..., description="Repository ID")
    status: str = Field(..., description="'idle', 'indexing', 'completed', or 'failed'")
    current_stage: Optional[str] = Field(None, description="Current lifecycle stage of indexing")
    stage_message: Optional[str] = Field(None, description="Detailed stage progress description")
    total_chunks: int = Field(0, ge=0, description="Total chunks currently stored")
    total_files_indexed: int = Field(0, ge=0, description="Total files indexed")
    new_chunks_embedded: int = Field(0, ge=0, description="Count of new chunks embedded in latest run")
    cached_chunks: int = Field(0, ge=0, description="Count of unchanged chunks reused via content hash")
    last_indexed_at: Optional[str] = Field(None, description="ISO 8601 timestamp of indexing completion")
    error_message: Optional[str] = Field(None, description="Error message if indexing failed")


class IndexingStatsResponse(BaseModel):
    """Aggregated vector and chunk statistics for an indexed repository."""

    repository_id: str = Field(..., description="Repository ID")
    total_chunks: int = Field(0, ge=0, description="Total chunks in vector store")
    total_files: int = Field(0, ge=0, description="Distinct files indexed")
    total_symbols_indexed: int = Field(0, ge=0, description="Named symbols captured in chunks")
    languages: Dict[str, int] = Field(default_factory=dict, description="Chunk count per language")
    embedding_dimension: int = Field(..., description="Vector embedding dimension (e.g. 768)")
    embedding_model: str = Field(..., description="Embedding model name")
    last_indexed_at: Optional[str] = Field(None, description="ISO 8601 timestamp")

