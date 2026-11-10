"""Hybrid search ranker combining semantic vector similarity and keyword search via Reciprocal Rank Fusion."""

from typing import Dict, List, Optional
from app.rag.schemas import SearchResultChunk


class HybridSearchRanker:
    """Combines dense vector similarity and lexical keyword retrieval using Reciprocal Rank Fusion (RRF)."""

    def __init__(
        self,
        default_semantic_weight: float = 0.6,
        default_keyword_weight: float = 0.4,
        rrf_constant: int = 60,
    ):
        self.semantic_weight = default_semantic_weight
        self.keyword_weight = default_keyword_weight
        self.rrf_constant = rrf_constant

    def combine_results(
        self,
        vector_results: List[SearchResultChunk],
        keyword_results: List[SearchResultChunk],
        top_k: int = 10,
        semantic_weight: Optional[float] = None,
        keyword_weight: Optional[float] = None,
    ) -> List[SearchResultChunk]:
        """Merges and ranks semantic and keyword results using weighted RRF.

        Args:
            vector_results: Ranked list of chunks from semantic vector search.
            keyword_results: Ranked list of chunks from keyword/lexical search.
            top_k: Maximum number of merged results to return.
            semantic_weight: Weight assigned to semantic vector rankings.
            keyword_weight: Weight assigned to keyword rankings.

        Returns:
            Deduplicated, re-ranked list of SearchResultChunk items.
        """
        w_sem = semantic_weight if semantic_weight is not None else self.semantic_weight
        w_kw = keyword_weight if keyword_weight is not None else self.keyword_weight
        k = self.rrf_constant

        # Max theoretical score when item is ranked #1 in both retrieval methods
        max_theoretical_score = (w_sem / (k + 1)) + (w_kw / (k + 1))

        # Collect map of chunk_id -> chunk data
        chunk_map: Dict[str, SearchResultChunk] = {}
        sem_ranks: Dict[str, int] = {}
        kw_ranks: Dict[str, int] = {}

        for rank, chunk in enumerate(vector_results, start=1):
            chunk_map[chunk.chunk_id] = chunk
            sem_ranks[chunk.chunk_id] = rank

        for rank, chunk in enumerate(keyword_results, start=1):
            if chunk.chunk_id not in chunk_map:
                chunk_map[chunk.chunk_id] = chunk
            kw_ranks[chunk.chunk_id] = rank

        # Compute RRF score for all candidate chunks
        scored_candidates = []
        for chunk_id, base_chunk in chunk_map.items():
            sem_rank = sem_ranks.get(chunk_id)
            kw_rank = kw_ranks.get(chunk_id)

            rrf_score = 0.0
            method = "hybrid"

            if sem_rank is not None and kw_rank is not None:
                rrf_score = (w_sem / (k + sem_rank)) + (w_kw / (k + kw_rank))
                method = "hybrid"
            elif sem_rank is not None:
                rrf_score = w_sem / (k + sem_rank)
                method = "semantic"
            elif kw_rank is not None:
                rrf_score = w_kw / (k + kw_rank)
                method = "keyword"

            # Normalize to 0.0 - 1.0 range
            normalized_score = min(1.0, max(0.0, rrf_score / max_theoretical_score))

            # Update scores on copy
            updated_chunk = base_chunk.model_copy(
                update={
                    "relevance_score": round(normalized_score, 4),
                    "retrieval_method": method,
                    "semantic_score": base_chunk.semantic_score,
                    "keyword_score": base_chunk.keyword_score,
                }
            )
            scored_candidates.append(updated_chunk)

        # Sort descending by normalized score
        scored_candidates.sort(key=lambda x: x.relevance_score, reverse=True)

        return scored_candidates[:top_k]

