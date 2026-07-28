"""BGE-M3 embeddings via Ollama (ADR-004).

Served by Ollama, not an in-process SentenceTransformer: Ollama unloads idle
models and the RAM budget can't keep everything resident (docs.md/PLAN §5).
Both ingestion (batch) and retrieval (single query) go through here so the two
paths can never disagree on model or dimensionality.
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.models import EMBEDDING_DIM

settings = get_settings()

_EMBED_ENDPOINT = "/api/embed"
# CPU embedding of a batch is slow; give it room but still bound it.
_TIMEOUT = httpx.Timeout(120.0, connect=5.0)


class EmbeddingError(RuntimeError):
    """Raised when Ollama returns no / malformed / wrong-dimension embeddings."""


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch; returns one 1024-d vector per input, in order."""
    if not texts:
        return []

    payload = {"model": settings.ollama_embedding_model, "input": texts}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(f"{settings.ollama_url}{_EMBED_ENDPOINT}", json=payload)
        response.raise_for_status()
        data = response.json()

    embeddings = data.get("embeddings")
    if not embeddings or len(embeddings) != len(texts):
        raise EmbeddingError(f"Expected {len(texts)} embeddings, got {len(embeddings or [])}")
    if len(embeddings[0]) != EMBEDDING_DIM:
        raise EmbeddingError(f"Expected dimension {EMBEDDING_DIM}, got {len(embeddings[0])}")
    return embeddings


async def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    return (await embed_texts([text]))[0]
