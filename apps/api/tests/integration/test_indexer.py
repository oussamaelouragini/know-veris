"""Indexer state machine + DB indexing, with the embedder mocked (no Ollama).

Exercises the real parse → chunk → index path and the actual Postgres
`to_tsvector` FTS build, so everything but the Ollama embedding call is covered.
"""

import uuid
from pathlib import Path

from sqlalchemy import cast, delete, func, select
from sqlalchemy.dialects.postgresql import REGCONFIG

from app.db.session import SessionLocal
from app.models import EMBEDDING_DIM, Document, DocumentChunk, DocumentStatus
from app.services.ingestion.indexer import count_chunks, ingest_document
from app.services.ingestion.parsers import PDF_MIME

BOOTSTRAP = Path(__file__).parents[1] / "data" / "bootstrap"
FR_PDF = str(BOOTSTRAP / "fr-obligations-vigilance.pdf")
MISSING_PDF = str(BOOTSTRAP / "does-not-exist.pdf")


async def _fake_embed(texts: list[str]) -> list[list[float]]:
    # Deterministic unit-ish vectors; only shape matters for indexing.
    return [[0.01] * EMBEDDING_DIM for _ in texts]


async def _new_document(db, mime=PDF_MIME) -> Document:
    doc = Document(
        filename="fr-obligations-vigilance.pdf",
        mime_type=mime,
        file_hash=uuid.uuid4().hex,  # unique per test run
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


async def _cleanup(doc_id) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(Document).where(Document.id == doc_id))
        await db.commit()


async def test_ingest_indexes_document_end_to_end():
    async with SessionLocal() as db:
        doc = await _new_document(db)
    doc_id = doc.id
    try:
        async with SessionLocal() as db:
            await ingest_document(doc_id, FR_PDF, db, embed=_fake_embed)

        async with SessionLocal() as db:
            refreshed = await db.get(Document, doc_id)
            assert refreshed.status is DocumentStatus.INDEXED
            assert refreshed.language == "fr"
            assert refreshed.page_count == 2
            assert refreshed.error_message is None

            n = await count_chunks(doc_id, db)
            assert n > 0

            chunk = (
                await db.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == doc_id).limit(1)
                )
            ).scalar_one()
            assert len(chunk.embedding) == EMBEDDING_DIM
            assert chunk.page_number in (1, 2)
            assert chunk.language == "fr"

            # The tsvector was built with the french config and is searchable.
            matches = (
                await db.execute(
                    select(func.count())
                    .select_from(DocumentChunk)
                    .where(
                        DocumentChunk.document_id == doc_id,
                        DocumentChunk.content_tsv.op("@@")(
                            func.to_tsquery(cast("french", REGCONFIG), "vigilance")
                        ),
                    )
                )
            ).scalar_one()
            assert matches >= 1
    finally:
        await _cleanup(doc_id)


async def test_ingest_marks_failed_on_unreadable_file():
    async with SessionLocal() as db:
        doc = await _new_document(db)
    doc_id = doc.id
    try:
        async with SessionLocal() as db:
            await ingest_document(doc_id, MISSING_PDF, db, embed=_fake_embed)

        async with SessionLocal() as db:
            refreshed = await db.get(Document, doc_id)
            assert refreshed.status is DocumentStatus.FAILED
            assert refreshed.error_message
            assert await count_chunks(doc_id, db) == 0
    finally:
        await _cleanup(doc_id)
