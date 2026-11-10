"""Embedding generation pipeline supporting Google Gemini and deterministic offline providers."""

import abc
import asyncio
import hashlib
import math
import random
import time
from typing import List, Optional, Tuple
import httpx

from app.core.config import settings
from app.core.logging import logger


class BaseEmbeddingProvider(abc.ABC):
    """Abstract interface for generating vector embeddings."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """Returns embedding vector dimensionality."""
        pass

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """Returns name of the active embedding model."""
        pass

    @abc.abstractmethod
    async def embed_query(self, text: str) -> List[float]:
        """Generates embedding for a single search query."""
        pass

    @abc.abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a batch of text chunks."""
        pass


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Deterministic, offline embedding provider for development and testing.

    Derives normalized unit vectors from token and character n-grams so similar
    phrases share geometric alignment without requiring external network calls.
    """

    def __init__(self, dimension: int = 768, model_name: str = "mock-embedding-004"):
        self._dim = dimension
        self._model = model_name

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model

    def _generate_vector(self, text: str) -> List[float]:
        clean = text.lower().strip()
        vec = [0.0] * self._dim

        # Global document hash base
        doc_hash = hashlib.sha256(clean.encode("utf-8")).hexdigest()
        rng = random.Random(int(doc_hash[:16], 16))
        for i in range(self._dim):
            vec[i] += rng.gauss(0, 0.5)

        # Word-level token frequency embedding components
        words = clean.split()
        for w in words:
            w_hash = hashlib.sha256(w.encode("utf-8")).hexdigest()
            w_idx = int(w_hash[:8], 16) % self._dim
            vec[w_idx] += 2.0
            alt_idx = int(w_hash[8:16], 16) % self._dim
            vec[alt_idx] += 1.0

        # L2 normalize
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            return [x / norm for x in vec]
        return [0.0] * self._dim

    async def embed_query(self, text: str) -> List[float]:
        return self._generate_vector(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_vector(t) for t in texts]


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Google Gemini text-embedding-004 provider with batching, retries, and rate limiting."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        dimension: int = 768,
        batch_size: int = 64,
        max_retries: int = 3,
    ):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model_name or settings.EMBEDDING_MODEL
        self._dim = dimension
        self._batch_size = batch_size
        self._max_retries = max_retries

        if not self._api_key:
            logger.warning(
                "GeminiEmbeddingProvider initialized without GEMINI_API_KEY. "
                "Embeddings will fail unless API key is provided."
            )

    @property
    def dimension(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._normalize_model_name().replace("models/", "")

    def _normalize_model_name(self) -> str:
        name = self._model.strip()
        # Migrate deprecated text-embedding-004 to current gemini-embedding-001
        if name in ("text-embedding-004", "models/text-embedding-004"):
            name = "gemini-embedding-001"
        if not name.startswith("models/"):
            return f"models/{name}"
        return name

    async def embed_query(self, text: str) -> List[float]:
        """Embeds a single query string using Gemini embedContent endpoint."""
        if not text or not text.strip():
            return [0.0] * self._dim

        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in .env "
                "or configure EMBEDDING_PROVIDER=mock for offline usage."
            )

        model_path = self._normalize_model_name()
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/{model_path}:embedContent"
            f"?key={self._api_key}"
        )
        payload = {
            "content": {"parts": [{"text": text[:8000]}]},
            "outputDimensionality": self._dim,
        }

        delay = 1.0
        last_error = None
        timeout_sec = getattr(settings, "EMBEDDING_REQUEST_TIMEOUT", 60.0)

        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            for attempt in range(self._max_retries):
                try:
                    response = await client.post(endpoint, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        vals = data.get("embedding", {}).get("values", [])
                        if vals:
                            return vals
                        return [0.0] * self._dim

                    if response.status_code in (429, 500, 502, 503, 504):
                        logger.warning(
                            "Gemini embed_query returned %d. Attempt %d/%d. Retrying in %.1fs...",
                            response.status_code,
                            attempt + 1,
                            self._max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue

                    error_detail = response.text
                    raise RuntimeError(
                        f"Gemini embed_query error (status {response.status_code}): {error_detail}"
                    )
                except (httpx.RequestError, httpx.TimeoutException) as e:
                    last_error = e
                    logger.warning("Network error in Gemini embed_query: %s. Retrying...", e)
                    await asyncio.sleep(delay)
                    delay *= 2

        raise RuntimeError(f"Gemini embed_query failed after {self._max_retries} retries: {last_error}")

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for code chunks in concurrent batches with detailed instrumentation."""
        if not texts:
            return []

        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in .env "
                "or configure EMBEDDING_PROVIDER=mock for offline usage."
            )

        model_path = self._normalize_model_name()
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/{model_path}:batchEmbedContents"
            f"?key={self._api_key}"
        )

        total_texts = len(texts)
        batches = [texts[i : i + self._batch_size] for i in range(0, total_texts, self._batch_size)]
        total_batches = len(batches)

        t_start = time.time()
        logger.info(
            "Embedding generation started for %d chunks using %s (dimension=%d, batch_size=%d, total_batches=%d)...",
            total_texts,
            model_path,
            self._dim,
            self._batch_size,
            total_batches,
        )

        concurrency = getattr(settings, "EMBEDDING_MAX_CONCURRENCY", 4)
        sem = asyncio.Semaphore(concurrency)

        async def _process_batch(batch_idx: int, batch_texts: List[str]) -> Tuple[int, List[List[float]]]:
            async with sem:
                t0 = time.time()
                logger.info(
                    "Embedding batch %d/%d (%d chunks) started...",
                    batch_idx + 1,
                    total_batches,
                    len(batch_texts),
                )
                payload = {
                    "requests": [
                        {
                            "model": model_path,
                            "content": {"parts": [{"text": t[:8000]}]},  # Safe token ceiling
                            "outputDimensionality": self._dim,
                        }
                        for t in batch_texts
                    ]
                }
                embeddings = await self._send_request_with_retry(endpoint, payload, batch_idx + 1, total_batches)
                elapsed = time.time() - t0
                logger.info(
                    "Embedding batch %d/%d completed in %.2fs (%d embeddings).",
                    batch_idx + 1,
                    total_batches,
                    elapsed,
                    len(embeddings),
                )
                return batch_idx, embeddings

        tasks = [_process_batch(idx, b) for idx, b in enumerate(batches)]
        batch_results = await asyncio.gather(*tasks)

        # Sort results by batch_idx to preserve original chunk order
        batch_results.sort(key=lambda x: x[0])
        all_embeddings: List[List[float]] = []
        for _, embs in batch_results:
            all_embeddings.extend(embs)

        total_elapsed = time.time() - t_start
        logger.info(
            "Embedding generation completed: %d total embeddings in %.2fs (%.1f chunks/sec).",
            len(all_embeddings),
            total_elapsed,
            len(all_embeddings) / max(total_elapsed, 0.001),
        )

        return all_embeddings

    async def _send_request_with_retry(
        self, endpoint: str, payload: dict, batch_num: int = 1, total_batches: int = 1
    ) -> List[List[float]]:
        delay = 1.0
        last_error = None
        timeout_sec = getattr(settings, "EMBEDDING_REQUEST_TIMEOUT", 60.0)

        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            for attempt in range(self._max_retries):
                try:
                    response = await client.post(endpoint, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        raw_embeddings = data.get("embeddings", [])
                        return [item.get("values", []) for item in raw_embeddings]

                    if response.status_code in (429, 500, 502, 503, 504):
                        logger.warning(
                            "Gemini embedding API returned status %d for batch %d/%d. Attempt %d/%d. Retrying in %.1fs...",
                            response.status_code,
                            batch_num,
                            total_batches,
                            attempt + 1,
                            self._max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue

                    # Non-retryable error
                    error_detail = response.text
                    logger.error(
                        "Gemini Embedding API fatal error (status %d) for batch %d/%d: %s",
                        response.status_code,
                        batch_num,
                        total_batches,
                        error_detail,
                    )
                    raise RuntimeError(
                        f"Gemini Embedding API error (status {response.status_code}): {error_detail}"
                    )

                except (httpx.RequestError, httpx.TimeoutException) as e:
                    last_error = e
                    logger.warning(
                        "Network error in Gemini embedding request for batch %d/%d (attempt %d/%d): %s. Retrying in %.1fs...",
                        batch_num,
                        total_batches,
                        attempt + 1,
                        self._max_retries,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 2

        logger.exception("Gemini Embedding API failed after %d retries for batch %d/%d: %s", self._max_retries, batch_num, total_batches, last_error)
        raise RuntimeError(
            f"Gemini Embedding API failed after {self._max_retries} retries: {last_error}"
        )


def get_embedding_provider() -> BaseEmbeddingProvider:
    """Factory creating the configured embedding provider."""
    provider_type = settings.EMBEDDING_PROVIDER.lower().strip()

    if provider_type == "mock":
        return MockEmbeddingProvider(
            dimension=settings.EMBEDDING_DIMENSION,
            model_name=settings.normalized_embedding_model,
        )

    if not settings.is_gemini_configured:
        logger.info(
            "Embeddings / RAG configured for '%s', but GEMINI_API_KEY is not set. Operating in Offline Mode (MockEmbeddingProvider).",
            provider_type,
        )
        return MockEmbeddingProvider(
            dimension=settings.EMBEDDING_DIMENSION,
            model_name=settings.normalized_embedding_model,
        )

    return GeminiEmbeddingProvider(
        api_key=settings.GEMINI_API_KEY,
        model_name=settings.normalized_embedding_model,
        dimension=settings.EMBEDDING_DIMENSION,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
    )

