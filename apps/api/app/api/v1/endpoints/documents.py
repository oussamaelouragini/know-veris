"""Document admin endpoints — upload, list, status. Admin-only (ADR-006).

Endpoints stay thin: validate + delegate to services + serialize. The heavy
parse/embed/index work is deferred to a BackgroundTask so upload returns
immediately (202) instead of blocking on CPU-bound ingestion (PLAN Flow A).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AdminUser
from app.db.session import get_db
from app.models import Document
from app.schemas.document import DocumentRead
from app.services import audit
from app.services.ingestion.uploader import (
    DuplicateDocument,
    UnsupportedDocumentType,
    delete_document,
    register_upload,
)
from app.workers.tasks import process_document

router = APIRouter(prefix="/documents", tags=["documents"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentRead)
async def upload_document(
    admin: AdminUser,
    db: DbSession,
    background: BackgroundTasks,
    file: UploadFile,
) -> Document:
    contents = await file.read()
    try:
        document, path = await register_upload(
            db,
            filename=file.filename or "unnamed",
            mime_type=file.content_type or "",
            contents=contents,
            uploaded_by=admin.id,
        )
    except UnsupportedDocumentType as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported document type: {exc}",
        ) from exc
    except DuplicateDocument as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A document with identical content is already registered",
        ) from exc

    await audit.record(
        db,
        user_id=admin.id,
        action="document.uploaded",
        resource_type="document",
        resource_id=str(document.id),
        meta={"filename": document.filename},
    )
    background.add_task(process_document, document.id, path)
    return document


@router.get("", response_model=list[DocumentRead])
async def list_documents(admin: AdminUser, db: DbSession) -> list[Document]:
    rows = await db.scalars(select(Document).order_by(Document.created_at.desc()))
    return list(rows.all())


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(document_id: uuid.UUID, admin: AdminUser, db: DbSession) -> Document:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(document_id: uuid.UUID, admin: AdminUser, db: DbSession) -> None:
    document = await db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    filename = document.filename
    await delete_document(db, document)  # cascades to chunks, removes the file
    await audit.record(
        db,
        user_id=admin.id,
        action="document.deleted",
        resource_type="document",
        resource_id=str(document_id),
        meta={"filename": filename},
    )
