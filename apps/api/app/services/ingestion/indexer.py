"""Ingestion orchestrator — the PENDING → INDEXED state machine.

Drives one document through parse → detect language → chunk → embed → index,
advancing `documents.status` at each stage and recording an error message on
failure. Runs in a BackgroundTask (PLAN Flow A), so it owns its own DB session
and must never let an exception escape without marking the document FAILED.

The embedder is injected so the pipeline is testable without Ollama.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk, DocumentStatus
from app.services.ingestion.chunker import chunk_blocks
from app.services.ingestion.language import detect_language, fts_config_for
from app.services.ingestion.parsers import parse_document
from app.services.rag.embedder import embed_texts

Embedder = Callable[[list[str]], Awaitable[list[list[float]]]]


async def ingest_document(
    document_id: uuid.UUID,
    file_path: str,
    db: AsyncSession,
    *,
    embed: Embedder = embed_texts,
) -> None:
    """Ingest one document end-to-end, updating its status as it goes."""
    document = await db.get(Document, document_id)
    if document is None:
        return

    try:
        document.status = DocumentStatus.PARSING
        await db.commit()

        result = parse_document(file_path, document.mime_type)
        sample = "\n".join(block.text for block in result.blocks[:5])
        language = detect_language(sample)
        document.page_count = result.page_count
        document.language = language

        chunks = chunk_blocks(result.blocks)
        if not chunks:
            raise ValueError("No extractable text (scanned or empty document?)")

        document.status = DocumentStatus.EMBEDDING
        await db.commit()

        embeddings = await embed([chunk.content for chunk in chunks])

        config = fts_config_for(language)
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    language=language,
                    embedding=embedding,
                    # Build the tsvector with the detected language's FTS config.
                    content_tsv=func.to_tsvector(cast(config, REGCONFIG), chunk.content),
                )
            )

        document.status = DocumentStatus.INDEXED
        await db.commit()
    except Exception as exc:  # noqa: BLE001 - failure must be recorded, not raised
        await db.rollback()
        document = await db.get(Document, document_id)
        if document is not None:
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:1000]
            await db.commit()


async def count_chunks(document_id: uuid.UUID, db: AsyncSession) -> int:
    """Small helper used by tests / status views."""
    result = await db.execute(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
    )
    return result.scalar_one()
