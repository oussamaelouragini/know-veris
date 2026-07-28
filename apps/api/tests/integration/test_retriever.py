"""Retriever vector search, with the query embedder mocked (no Ollama).

Uses one-hot embeddings so cosine ordering is exact and deterministic, and
checks that non-INDEXED documents and null-embedding chunks are excluded.
"""

import uuid

import pytest
from sqlalchemy import cast, delete, func
from sqlalchemy.dialects.postgresql import REGCONFIG

from app.db.session import SessionLocal
from app.models import (
    EMBEDDING_DIM,
    Document,
    DocumentChunk,
    DocumentStatus,
)
from app.services.rag.retriever import retrieve


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    vec[index] = 1.0
    return vec


def _query_embed(vector: list[float]):
    async def _embed(_question: str) -> list[float]:
        return vector

    return _embed


async def _seed() -> tuple[uuid.UUID, uuid.UUID]:
    """Indexed doc with two real chunks + one null-embedding; plus a PENDING doc."""
    async with SessionLocal() as db:
        indexed = Document(
            filename="fr-obligations-vigilance.pdf",
            mime_type="application/pdf",
            file_hash=uuid.uuid4().hex,
            status=DocumentStatus.INDEXED,
            language="fr",
        )
        pending = Document(
            filename="pending.pdf",
            mime_type="application/pdf",
            file_hash=uuid.uuid4().hex,
            status=DocumentStatus.PENDING,
        )
        db.add_all([indexed, pending])
        await db.flush()

        db.add_all(
            [
                DocumentChunk(
                    document_id=indexed.id,
                    chunk_index=0,
                    content="chunk zero",
                    page_number=1,
                    language="fr",
                    embedding=_one_hot(0),
                ),
                DocumentChunk(
                    document_id=indexed.id,
                    chunk_index=1,
                    content="chunk one",
                    page_number=2,
                    language="fr",
                    embedding=_one_hot(1),
                ),
                # Null embedding -> must be excluded from search.
                DocumentChunk(
                    document_id=indexed.id,
                    chunk_index=2,
                    content="no vector",
                    page_number=3,
                    language="fr",
                    embedding=None,
                ),
                # In a PENDING doc -> must be excluded.
                DocumentChunk(
                    document_id=pending.id,
                    chunk_index=0,
                    content="not ready",
                    page_number=1,
                    language="fr",
                    embedding=_one_hot(1),
                ),
            ]
        )
        await db.commit()
        return indexed.id, pending.id


async def _cleanup(*doc_ids: uuid.UUID) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Document).where(Document.id.in_(doc_ids)))
        await db.commit()


async def test_retrieve_ranks_by_cosine_and_carries_citation():
    indexed_id, pending_id = await _seed()
    try:
        async with SessionLocal() as db:
            # Query closest to chunk one (page 2).
            results = await retrieve("q", db, top_k=3, embed=_query_embed(_one_hot(1)))

        # Only the two real, indexed chunks come back (null + PENDING excluded).
        assert len(results) == 2
        top, second = results
        assert top.page_number == 2
        assert top.content == "chunk one"
        assert top.filename == "fr-obligations-vigilance.pdf"
        assert top.score == pytest.approx(1.0, abs=1e-6)
        assert second.page_number == 1
        assert second.score == pytest.approx(0.0, abs=1e-6)
        assert top.score > second.score
    finally:
        await _cleanup(indexed_id, pending_id)


async def test_retrieve_respects_top_k():
    indexed_id, pending_id = await _seed()
    try:
        async with SessionLocal() as db:
            results = await retrieve("q", db, top_k=1, embed=_query_embed(_one_hot(0)))
        assert len(results) == 1
        assert results[0].page_number == 1  # one-hot(0) closest to chunk zero
    finally:
        await _cleanup(indexed_id, pending_id)


async def _seed_hybrid() -> uuid.UUID:
    """One indexed EN doc: a keyword chunk (vector-far) + a generic chunk (vector-near)."""
    async with SessionLocal() as db:
        doc = Document(
            filename="en-sanctions-screening.pdf",
            mime_type="application/pdf",
            file_hash=uuid.uuid4().hex,
            status=DocumentStatus.INDEXED,
            language="en",
        )
        db.add(doc)
        await db.flush()

        def tsv(text: str):
            return func.to_tsvector(cast("english", REGCONFIG), text)

        keyword_text = "The PEP screening procedure applies to politically exposed persons."
        generic_text = "General banking information for everyday retail customers."
        db.add_all(
            [
                # Keyword chunk: matches FTS on "PEP" but sits far from the query vector.
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=0,
                    content=keyword_text,
                    page_number=7,
                    language="en",
                    embedding=_one_hot(5),
                    content_tsv=tsv(keyword_text),
                ),
                # Generic chunk: closest to the query vector, no "PEP" token.
                DocumentChunk(
                    document_id=doc.id,
                    chunk_index=1,
                    content=generic_text,
                    page_number=1,
                    language="en",
                    embedding=_one_hot(1),
                    content_tsv=tsv(generic_text),
                ),
            ]
        )
        await db.commit()
        return doc.id


async def test_hybrid_fts_surfaces_keyword_chunk_the_vector_misses():
    doc_id = await _seed_hybrid()
    try:
        # Query vector is closest to the generic chunk (page 1). Vector-only would
        # rank the generic chunk first; the acronym "PEP" only matches via FTS.
        async with SessionLocal() as db:
            vector_only = await retrieve(
                "PEP", db, top_k=2, embed=_query_embed(_one_hot(1)), language="en", use_fts=False
            )
        assert vector_only[0].page_number == 1  # generic chunk wins without FTS

        async with SessionLocal() as db:
            hybrid = await retrieve(
                "PEP", db, top_k=2, embed=_query_embed(_one_hot(1)), language="en", use_fts=True
            )
        # RRF: the keyword chunk scores in both legs and overtakes the generic one.
        assert hybrid[0].page_number == 7
        assert "PEP" in hybrid[0].content
        assert hybrid[0].rrf_score is not None and hybrid[0].rrf_score > 0
    finally:
        await _cleanup(doc_id)
