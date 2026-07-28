"""Background tasks — run after the HTTP response is returned (PLAN Flow A).

Each task owns its own DB session: the request-scoped session is already closed
by the time a BackgroundTask runs.
"""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.services.ingestion.indexer import ingest_document


async def process_document(document_id: uuid.UUID, file_path: str) -> None:
    """Ingest an uploaded document end-to-end (parse → embed → index)."""
    async with SessionLocal() as db:
        await ingest_document(document_id, file_path, db)
