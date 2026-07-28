"""Upload registration — hash-dedup, persist the file, insert the PENDING row.

Kept out of the endpoint so the route stays thin (docs.md: endpoints validate,
delegate, serialize). The actual parse/embed/index work happens later in a
BackgroundTask; this only gets the bytes onto disk and a row into the DB.
"""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Document
from app.services.ingestion.parsers import DOCX_MIME, PDF_MIME

_EXTENSION = {PDF_MIME: ".pdf", DOCX_MIME: ".docx"}


class UnsupportedDocumentType(ValueError):
    """The uploaded MIME type is not a PDF or DOCX."""


class DuplicateDocument(ValueError):
    """A document with the same content hash is already registered."""

    def __init__(self, existing_id: uuid.UUID) -> None:
        super().__init__(f"Document already registered: {existing_id}")
        self.existing_id = existing_id


async def register_upload(
    db: AsyncSession,
    *,
    filename: str,
    mime_type: str,
    contents: bytes,
    uploaded_by: uuid.UUID | None,
) -> tuple[Document, str]:
    """Validate, dedup by SHA-256, save the file, insert Document(PENDING).

    Returns the created row and the on-disk path for the ingestion task.
    """
    if mime_type not in _EXTENSION:
        raise UnsupportedDocumentType(mime_type)

    file_hash = hashlib.sha256(contents).hexdigest()
    existing = await db.scalar(select(Document.id).where(Document.file_hash == file_hash))
    if existing is not None:
        raise DuplicateDocument(existing)

    document = Document(
        filename=filename,
        mime_type=mime_type,
        file_hash=file_hash,
        uploaded_by=uploaded_by,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    storage = Path(get_settings().storage_path)
    storage.mkdir(parents=True, exist_ok=True)
    path = storage / f"{document.id}{_EXTENSION[mime_type]}"
    path.write_bytes(contents)

    return document, str(path)


def document_path(document: Document) -> Path:
    """The on-disk path for a stored document (mirrors register_upload's naming)."""
    return Path(get_settings().storage_path) / f"{document.id}{_EXTENSION[document.mime_type]}"


async def delete_document(db: AsyncSession, document: Document) -> None:
    """Delete the document row (cascades to chunks) then remove its file.

    DB first, file second: a leftover file is harmless, but a missing file with a
    live row is not. Chunks cascade away; message_citations keep their history
    row with a nulled chunk_id (ON DELETE SET NULL), preserving traceability.
    """
    path = document_path(document)
    await db.delete(document)
    await db.commit()
    path.unlink(missing_ok=True)
