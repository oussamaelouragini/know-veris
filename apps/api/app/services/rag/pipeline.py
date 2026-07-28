"""Chat pipeline — retrieve → guard → generate → guard → persist (PLAN Flow B).

Retrieval is hybrid (vector + FTS + RRF) with an optional cross-encoder reranker
(feature-flagged). Response is still non-streamed — SSE is the remaining Week 2
item. The two non-negotiable guardrails (docs.md §RAG) are always enforced:

* **Guardrail 1** — refuse *before* the LLM when the best retrieval score is
  below the threshold. No context → no call → zero hallucination, answer in <2 s.
* **Guardrail 2** — after generation, keep only `[Sx]` citations that point at a
  chunk actually supplied. An answer citing nothing is flagged `unverified`.

Everything traceable is written down: the conversation, both messages, the
citations that ground the answer (`message_citations`), and an audit log entry.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    AuditLog,
    Conversation,
    Message,
    MessageCitation,
    MessageRole,
    User,
)
from app.services.ingestion.language import detect_language
from app.services.rag import generator, prompt, reranker
from app.services.rag.retriever import RetrievedChunk, retrieve

settings = get_settings()

# Refusal wording in each supported language (Guardrail 1 / sentinel fallback).
_REFUSAL = {
    "fr": "Information introuvable dans les documents indexés.",
    "en": "Information not found in the indexed documents.",
    "ar": "لم يتم العثور على المعلومات في المستندات المفهرسة.",
}
_REFUSAL_DEFAULT = _REFUSAL["en"]

_CITATION_RE = re.compile(r"\[S(\d+)\]")


class ConversationNotFound(Exception):
    """Raised when a caller references a conversation that isn't theirs / doesn't exist."""


@dataclass
class Citation:
    marker: str  # "S1"
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_number: int | None
    section_title: str | None
    score: float


@dataclass
class ChatAnswer:
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    answer: str
    language: str | None
    refused: bool
    unverified: bool
    model_used: str | None
    latency_ms: int | None
    citations: list[Citation] = field(default_factory=list)


def _refusal_text(language: str | None) -> str:
    return _REFUSAL.get(language or "", _REFUSAL_DEFAULT)


def _cited_markers(answer: str, chunk_count: int) -> set[int]:
    """Distinct 1-based `[Sx]` indices in `answer` that map to a supplied chunk."""
    return {n for m in _CITATION_RE.findall(answer) if 1 <= (n := int(m)) <= chunk_count}


def _build_citations(answer: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    cited = _cited_markers(answer, len(chunks))
    return [
        Citation(
            marker=f"S{i}",
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            filename=chunk.filename,
            page_number=chunk.page_number,
            section_title=chunk.section_title,
            score=chunk.score,
        )
        for i, chunk in enumerate(chunks, start=1)
        if i in cited
    ]


def _title_from(question: str) -> str:
    """Derive a short conversation title from its opening question, so the
    history list reads as questions rather than a column of "Untitled"."""
    title = " ".join(question.split())
    return title[:117] + "…" if len(title) > 118 else title


async def _resolve_conversation(
    db: AsyncSession, user: User, conversation_id: uuid.UUID | None, question: str
) -> Conversation:
    """Reuse the caller's conversation, or create a fresh one titled after the
    opening question."""
    if conversation_id is None:
        conversation = Conversation(user_id=user.id, title=_title_from(question))
        db.add(conversation)
        await db.flush()
        return conversation

    conversation = (
        await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise ConversationNotFound(str(conversation_id))
    return conversation


async def _retrieve_chunks(
    question: str, db: AsyncSession, language: str | None
) -> list[RetrievedChunk]:
    """Hybrid retrieval, optionally reranked. With the reranker on, pull the full
    candidate pool then let the cross-encoder pick the top-k."""
    if settings.reranker_enabled:
        candidates = await retrieve(question, db, top_k=settings.retrieval_top_k, language=language)
        return reranker.rerank(question, candidates, top_k=settings.rerank_top_k)
    return await retrieve(question, db, top_k=settings.rerank_top_k, language=language)


def _is_refusal(chunks: list[RetrievedChunk]) -> bool:
    """Guardrail 1 — best cosine similarity across results below the threshold
    (RRF/reranker may not order by it, so take the max)."""
    best_score = max((chunk.score for chunk in chunks), default=0.0)
    return not chunks or best_score < settings.relevance_threshold


async def answer_question(
    question: str,
    db: AsyncSession,
    user: User,
    *,
    conversation_id: uuid.UUID | None = None,
) -> ChatAnswer:
    """Run the full pipeline for one question and persist everything it touched."""
    language = detect_language(question)
    conversation = await _resolve_conversation(db, user, conversation_id, question)

    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.user,
            content=question,
            language=language,
        )
    )

    chunks = await _retrieve_chunks(question, db, language)

    # Guardrail 1 — refuse before the LLM if nothing is relevant enough.
    if _is_refusal(chunks):
        return await _persist_answer(
            db,
            conversation=conversation,
            user=user,
            question=question,
            answer=_refusal_text(language),
            language=language,
            refused=True,
            unverified=False,
            model_used=None,
            latency_ms=None,
            citations=[],
        )

    system_prompt = prompt.SYSTEM_PROMPT
    user_prompt = prompt.build_user_prompt(question, chunks, language)
    result = await generator.generate(system_prompt, user_prompt)

    # Sentinel: the model itself judged the context insufficient.
    if result.text == prompt.NOT_FOUND_SENTINEL:
        return await _persist_answer(
            db,
            conversation=conversation,
            user=user,
            question=question,
            answer=_refusal_text(language),
            language=language,
            refused=True,
            unverified=False,
            model_used=result.model_used,
            latency_ms=result.latency_ms,
            citations=[],
        )

    # Guardrail 2 — keep only citations that point at a supplied chunk.
    citations = _build_citations(result.text, chunks)
    return await _persist_answer(
        db,
        conversation=conversation,
        user=user,
        question=question,
        answer=result.text,
        language=language,
        refused=False,
        unverified=not citations,
        model_used=result.model_used,
        latency_ms=result.latency_ms,
        citations=citations,
    )


async def _persist_answer(
    db: AsyncSession,
    *,
    conversation: Conversation,
    user: User,
    question: str,
    answer: str,
    language: str | None,
    refused: bool,
    unverified: bool,
    model_used: str | None,
    latency_ms: int | None,
    citations: list[Citation],
) -> ChatAnswer:
    """Write the assistant message + citations + audit trail, then commit."""
    assistant = Message(
        conversation_id=conversation.id,
        role=MessageRole.assistant,
        content=answer,
        language=language,
        model_used=model_used,
        latency_ms=latency_ms,
        refused=refused,
    )
    db.add(assistant)
    await db.flush()  # assign assistant.id before wiring citations to it

    for citation in citations:
        db.add(
            MessageCitation(
                message_id=assistant.id,
                chunk_id=citation.chunk_id,
                relevance_score=citation.score,
            )
        )

    db.add(
        AuditLog(
            user_id=user.id,
            action="chat.answer",
            resource_type="conversation",
            resource_id=str(conversation.id),
            meta={"refused": refused, "language": language, "model": model_used},
        )
    )

    await db.commit()

    return ChatAnswer(
        conversation_id=conversation.id,
        message_id=assistant.id,
        answer=answer,
        language=language,
        refused=refused,
        unverified=unverified,
        model_used=model_used,
        latency_ms=latency_ms,
        citations=citations,
    )


# What answer_question_stream yields: ("token", delta) while generating, then
# exactly one ("final", ChatAnswer) — the authoritative result the UI renders
# (on refusal it carries the localized message; the client trusts it over any
# streamed tokens).
StreamEvent = tuple[str, str] | tuple[str, ChatAnswer]


async def answer_question_stream(
    question: str,
    db: AsyncSession,
    user: User,
    *,
    conversation_id: uuid.UUID | None = None,
) -> AsyncIterator[StreamEvent]:
    """Stream the answer token-by-token, then persist and emit the final result."""
    language = detect_language(question)
    conversation = await _resolve_conversation(db, user, conversation_id, question)

    db.add(
        Message(
            conversation_id=conversation.id,
            role=MessageRole.user,
            content=question,
            language=language,
        )
    )

    chunks = await _retrieve_chunks(question, db, language)

    # Guardrail 1 — refuse before the LLM, no tokens streamed.
    if _is_refusal(chunks):
        answer = await _persist_answer(
            db,
            conversation=conversation,
            user=user,
            question=question,
            answer=_refusal_text(language),
            language=language,
            refused=True,
            unverified=False,
            model_used=None,
            latency_ms=None,
            citations=[],
        )
        yield ("final", answer)
        return

    user_prompt = prompt.build_user_prompt(question, chunks, language)
    result = None
    async for chunk in generator.stream_generate(prompt.SYSTEM_PROMPT, user_prompt):
        if chunk.done:
            result = chunk.result
        elif chunk.delta:
            yield ("token", chunk.delta)

    if result is None:  # stream ended without a terminal chunk
        raise generator.GenerationError("Stream ended without a final chunk")

    # Sentinel: the model judged the context insufficient -> refusal wins.
    if result.text == prompt.NOT_FOUND_SENTINEL:
        answer = await _persist_answer(
            db,
            conversation=conversation,
            user=user,
            question=question,
            answer=_refusal_text(language),
            language=language,
            refused=True,
            unverified=False,
            model_used=result.model_used,
            latency_ms=result.latency_ms,
            citations=[],
        )
        yield ("final", answer)
        return

    # Guardrail 2 — keep only citations that point at a supplied chunk.
    citations = _build_citations(result.text, chunks)
    answer = await _persist_answer(
        db,
        conversation=conversation,
        user=user,
        question=question,
        answer=result.text,
        language=language,
        refused=False,
        unverified=not citations,
        model_used=result.model_used,
        latency_ms=result.latency_ms,
        citations=citations,
    )
    yield ("final", answer)
