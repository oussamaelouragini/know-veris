"""Document and DocumentChunk — the ingested corpus and its indexed pieces.

A chunk without a source anchor (page_number OR section_title) is a bug: the
CHECK constraint enforces that citation is always possible (ADR-005). The
vector + tsvector columns back the hybrid search (pgvector cosine + Postgres FTS).
"""

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

EMBEDDING_DIM = 1024  # BGE-M3 (ADR-004)


class DocumentStatus(enum.StrEnum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    EMBEDDING = "EMBEDDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    # SHA-256, hex — duplicate upload is rejected with 409 (PLAN.md Flow A).
    file_hash: Mapped[str] = mapped_column(String(64), unique=True)
    page_count: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(8))
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status"), default=DocumentStatus.PENDING
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    uploaded_by_user: Mapped["User | None"] = relationship(  # noqa: F821
        back_populates="documents"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint(
            "page_number IS NOT NULL OR section_title IS NOT NULL",
            name="page_or_section",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)  # PDF anchor
    section_title: Mapped[str | None] = mapped_column(String(512))  # DOCX anchor
    language: Mapped[str | None] = mapped_column(String(8))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Populated by the indexer with the FTS config of the detected language
    # (french | english | arabic | simple); language varies per chunk, so this
    # is a plain column, not a single-config generated column.
    content_tsv: Mapped[str | None] = mapped_column(TSVECTOR)

    document: Mapped["Document"] = relationship(back_populates="chunks")
    citations: Mapped[list["MessageCitation"]] = relationship(  # noqa: F821
        back_populates="chunk"
    )
