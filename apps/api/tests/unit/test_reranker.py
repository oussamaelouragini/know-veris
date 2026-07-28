"""Reranker reordering logic, with an injected scorer (no cross-encoder loaded)."""

import uuid

from app.services.rag.reranker import rerank
from app.services.rag.retriever import RetrievedChunk


def _chunk(content: str, cosine: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename="doc.pdf",
        content=content,
        page_number=1,
        section_title=None,
        language="en",
        score=cosine,
    )


def test_rerank_reorders_and_trims_and_keeps_cosine():
    chunks = [_chunk("alpha", 0.9), _chunk("beta", 0.8), _chunk("gamma", 0.7)]

    # Fake cross-encoder: beta most relevant, then gamma, then alpha.
    def scorer(question: str, passages: list[str]) -> list[float]:
        table = {"alpha": 0.1, "beta": 0.95, "gamma": 0.5}
        return [table[p] for p in passages]

    result = rerank("q", chunks, top_k=2, score=scorer)

    # Reordered by rerank score, trimmed to top_k.
    assert [c.content for c in result] == ["beta", "gamma"]
    assert result[0].rerank_score == 0.95
    # Cosine score is preserved (threshold signal must not change).
    assert result[0].score == 0.8


def test_rerank_empty_returns_empty():
    assert rerank("q", [], top_k=3, score=lambda q, p: []) == []
