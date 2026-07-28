"""Retriever — hybrid search (pgvector cosine + Postgres FTS) fused with RRF.

Week 1 shipped the vector-only version; Week 2 D1 adds keyword search and
Reciprocal Rank Fusion on top of the same entry point. The vector leg carries
cross-lingual retrieval (BGE-M3 bridges AR→FR); the FTS leg catches exact tokens
the vector alone misses — acronyms and jargon like "PEP", "AML-CFT" (PLAN Flow B).

Fusion decides *ordering*, but each returned chunk keeps its **cosine similarity**
as `score`, so Guardrail 1's relevance threshold keeps a stable, interpretable
meaning (and the UI shows a semantic score, not an opaque RRF value). `use_fts`
is a switch so the golden set can A/B hybrid vs vector-only.

Every result carries its citation metadata — an answer without a verifiable
source is the one thing the project must never produce (ADR-005).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Document, DocumentChunk, DocumentStatus
from app.services.ingestion.language import detect_language, fts_config_for
from app.services.rag.embedder import embed_query

settings = get_settings()

QueryEmbedder = Callable[[str], Awaitable[list[float]]]

# Reciprocal Rank Fusion constant. 60 is the value from the original RRF paper
# (Cormack et al.) and the de-facto standard; it damps the weight of deep ranks
# so a strong hit in either leg still surfaces.
RRF_K = 60


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    page_number: int | None
    section_title: str | None
    language: str | None
    score: float  # cosine similarity in [0, 1]; higher is closer
    rrf_score: float | None = None  # fusion score used for ordering (debug/eval)
    rerank_score: float | None = None  # cross-encoder score when the reranker ran


async def _vector_ranks(
    question_vector: list[float], db: AsyncSession, limit: int
) -> dict[uuid.UUID, int]:
    """Top-`limit` chunk ids by cosine distance, mapped to their 1-based rank."""
    distance = DocumentChunk.embedding.cosine_distance(question_vector)
    stmt = (
        select(DocumentChunk.id)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            Document.status == DocumentStatus.INDEXED,
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {chunk_id: rank for rank, chunk_id in enumerate(rows, start=1)}


async def _fts_ranks(
    question: str, language: str | None, db: AsyncSession, limit: int
) -> dict[uuid.UUID, int]:
    """Top-`limit` chunk ids by full-text rank, mapped to their 1-based rank.

    The tsquery is built with the question's language config; it matches chunks
    whose `content_tsv` was built with the same config (same-language keyword
    hits). Cross-lingual bridging is the vector leg's job, not FTS's.
    """
    config = fts_config_for(language)
    tsquery = func.websearch_to_tsquery(cast(config, REGCONFIG), question)
    rank = func.ts_rank_cd(DocumentChunk.content_tsv, tsquery)
    stmt = (
        select(DocumentChunk.id)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            Document.status == DocumentStatus.INDEXED,
            DocumentChunk.content_tsv.op("@@")(tsquery),
        )
        .order_by(rank.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {chunk_id: rank_ for rank_, chunk_id in enumerate(rows, start=1)}


async def _hydrate(
    ids: list[uuid.UUID],
    question_vector: list[float],
    rrf: dict[uuid.UUID, float],
    db: AsyncSession,
) -> list[RetrievedChunk]:
    """Fetch full rows + cosine similarity for `ids`, returned in RRF order."""
    if not ids:
        return []
    distance = DocumentChunk.embedding.cosine_distance(question_vector).label("distance")
    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            Document.filename,
            DocumentChunk.content,
            DocumentChunk.page_number,
            DocumentChunk.section_title,
            DocumentChunk.language,
            distance,
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(DocumentChunk.id.in_(ids))
    )
    by_id = {row.id: row for row in (await db.execute(stmt)).all()}
    chunks: list[RetrievedChunk] = []
    for chunk_id in ids:  # `ids` is already in RRF order
        row = by_id[chunk_id]
        chunks.append(
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                filename=row.filename,
                content=row.content,
                page_number=row.page_number,
                section_title=row.section_title,
                language=row.language,
                score=1.0 - float(row.distance),
                rrf_score=rrf[chunk_id],
            )
        )
    return chunks


async def retrieve(
    question: str,
    db: AsyncSession,
    *,
    top_k: int | None = None,
    embed: QueryEmbedder = embed_query,
    language: str | None = None,
    use_fts: bool = True,
) -> list[RetrievedChunk]:
    """Return the top-k chunks for a question via hybrid search + RRF.

    `top_k` defaults to `rerank_top_k`. Candidates are drawn `retrieval_top_k`
    deep from each leg before fusion. `language` selects the FTS config (detected
    from the question when omitted); `use_fts=False` falls back to vector-only.
    """
    limit = top_k if top_k is not None else settings.rerank_top_k
    candidate_depth = settings.retrieval_top_k
    question_vector = await embed(question)

    vector_ranks = await _vector_ranks(question_vector, db, candidate_depth)

    fts_ranks: dict[uuid.UUID, int] = {}
    if use_fts:
        lang = language if language is not None else detect_language(question)
        fts_ranks = await _fts_ranks(question, lang, db, candidate_depth)

    all_ids = set(vector_ranks) | set(fts_ranks)
    if not all_ids:
        return []

    rrf = {
        chunk_id: (
            (1.0 / (RRF_K + vector_ranks[chunk_id]) if chunk_id in vector_ranks else 0.0)
            + (1.0 / (RRF_K + fts_ranks[chunk_id]) if chunk_id in fts_ranks else 0.0)
        )
        for chunk_id in all_ids
    }
    ordered_ids = sorted(all_ids, key=lambda cid: rrf[cid], reverse=True)[:limit]

    return await _hydrate(ordered_ids, question_vector, rrf, db)
