"""Cross-encoder reranker (bge-reranker-v2-m3), behind a feature flag.

The retriever fuses two cheap signals (vector + FTS); a cross-encoder reads the
query and each passage *together* and scores true relevance far more precisely —
but at 3-8 s on CPU (PLAN §5), so it is off by default (`RERANKER_ENABLED`).

It only **reorders and trims** the fused candidates; each chunk keeps its cosine
`score`, so Guardrail 1's calibrated threshold stays on the same stable signal
whether or not the reranker ran. The heavy model is lazy-imported the first time
it is actually used, and the scorer is injectable so tests need no torch.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.core.config import get_settings
from app.services.rag.retriever import RetrievedChunk

settings = get_settings()

# (question, [passage, ...]) -> [relevance_score, ...], one per passage.
RerankScorer = Callable[[str, list[str]], list[float]]


@lru_cache(maxsize=1)
def _model():
    """Lazy-load the cross-encoder once. Requires the optional `FlagEmbedding`
    dependency; only imported when the reranker is actually enabled."""
    from FlagEmbedding import FlagReranker

    # normalize=True maps raw logits to [0, 1]; use_fp16 is a no-op on CPU.
    return FlagReranker(settings.reranker_model, use_fp16=False)


def _default_scorer(question: str, passages: list[str]) -> list[float]:
    reranker = _model()
    scores = reranker.compute_score([[question, p] for p in passages], normalize=True)
    # FlagReranker returns a float for a single pair, a list otherwise.
    return [float(scores)] if isinstance(scores, float) else [float(s) for s in scores]


def rerank(
    question: str,
    chunks: list[RetrievedChunk],
    *,
    top_k: int,
    score: RerankScorer = _default_scorer,
) -> list[RetrievedChunk]:
    """Reorder `chunks` by cross-encoder relevance and keep the top_k.

    `score` is injectable so tests avoid loading the model. The cosine `score`
    on each chunk is left untouched; only `rerank_score` is set.
    """
    if not chunks:
        return []
    scores = score(question, [c.content for c in chunks])
    for chunk, s in zip(chunks, scores, strict=True):
        chunk.rerank_score = s
    ordered = sorted(chunks, key=lambda c: c.rerank_score or 0.0, reverse=True)
    return ordered[:top_k]
