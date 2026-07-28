"""Chat DTOs — request and grounded response with citations."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.services.rag.pipeline import ChatAnswer, Citation


class ChatRequest(BaseModel):
    """A question, optionally continuing an existing conversation."""

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None


class CitationRead(BaseModel):
    """One grounding source, mapped back to its document and page/section."""

    marker: str
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int | None
    section_title: str | None
    score: float

    @classmethod
    def from_citation(cls, citation: Citation) -> CitationRead:
        return cls(
            marker=citation.marker,
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            filename=citation.filename,
            page_number=citation.page_number,
            section_title=citation.section_title,
            score=citation.score,
        )


class ChatResponse(BaseModel):
    """The answer plus everything needed to verify and continue it."""

    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    language: str | None
    refused: bool
    unverified: bool
    model_used: str | None
    latency_ms: int | None
    citations: list[CitationRead]

    @classmethod
    def from_answer(cls, answer: ChatAnswer) -> ChatResponse:
        return cls(
            conversation_id=answer.conversation_id,
            message_id=answer.message_id,
            answer=answer.answer,
            language=answer.language,
            refused=answer.refused,
            unverified=answer.unverified,
            model_used=answer.model_used,
            latency_ms=answer.latency_ms,
            citations=[CitationRead.from_citation(c) for c in answer.citations],
        )
