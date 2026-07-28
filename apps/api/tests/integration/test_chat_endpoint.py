"""Chat endpoint: sourced answer, Guardrail 1 (threshold), Guardrail 2 (citations).

Retrieval and generation are monkeypatched, so no Ollama / no indexed corpus is
needed — the DB, persistence, and guardrail wiring are what's under test. Auth is
exercised through a dependency override rather than a real Keycloak token.
"""

import json
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import get_current_user
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AuditLog,
    Conversation,
    Document,
    DocumentChunk,
    DocumentStatus,
    Message,
    User,
    UserRole,
)
from app.services.rag.generator import GenerationResult, StreamChunk
from app.services.rag.retriever import RetrievedChunk


def _parse_sse(text: str) -> list[tuple[str, str]]:
    """Parse a raw SSE body into (event, data) pairs."""
    events: list[tuple[str, str]] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event = data = ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = line[len("data:") :].strip()
        events.append((event, data))
    return events


def _chunk(index: int, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        filename=f"doc{index}.pdf",
        content=f"Relevant passage {index}.",
        page_number=index,
        section_title=None,
        language="en",
        score=score,
    )


async def _seed_indexed_chunks(user: User, count: int) -> list[RetrievedChunk]:
    """Insert a real INDEXED document + chunks so citation FKs resolve."""
    async with SessionLocal() as db:
        document = Document(
            filename="seeded.pdf",
            mime_type="application/pdf",
            file_hash=uuid.uuid4().hex,
            status=DocumentStatus.INDEXED,
            uploaded_by=user.id,
        )
        db.add(document)
        await db.flush()
        chunks = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=i,
                content=f"Relevant passage {i + 1}.",
                page_number=i + 1,
                language="en",
            )
            for i in range(count)
        ]
        db.add_all(chunks)
        await db.commit()
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=document.id,
                filename=document.filename,
                content=chunk.content,
                page_number=chunk.page_number,
                section_title=None,
                language="en",
                score=0.9 - 0.1 * i,
            )
            for i, chunk in enumerate(chunks)
        ]


@pytest.fixture
async def employee_user(monkeypatch):
    """A real user row (FK target) with the auth dependency overridden."""
    async with SessionLocal() as db:
        user = User(
            keycloak_sub=f"pytest-chat-{uuid.uuid4().hex}",
            email="employee@example.com",
            role=UserRole.employee,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.clear()

    async with SessionLocal() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
        await db.execute(delete(Conversation).where(Conversation.user_id == user.id))
        await db.execute(delete(Document).where(Document.uploaded_by == user.id))
        await db.execute(delete(User).where(User.id == user.id))
        await db.commit()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_answer_is_grounded_and_cited(employee_user, monkeypatch):
    seeded = await _seed_indexed_chunks(employee_user, 2)

    async def _retrieve(question, db, **kwargs):
        return seeded

    async def _generate(system, user, **kwargs):
        return GenerationResult(
            text="Enhanced due diligence is required [S1].",
            model_used="qwen3-test",
            latency_ms=1234,
            prompt_tokens=100,
            completion_tokens=20,
            tokens_per_second=8.0,
        )

    monkeypatch.setattr("app.services.rag.pipeline.retrieve", _retrieve)
    monkeypatch.setattr("app.services.rag.pipeline.generator.generate", _generate)

    async with _client() as client:
        resp = await client.post("/api/v1/chat", json={"question": "What is EDD?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is False
    assert body["unverified"] is False
    assert body["model_used"] == "qwen3-test"
    # Only [S1] was cited, so exactly one citation survives Guardrail 2.
    assert [c["marker"] for c in body["citations"]] == ["S1"]

    # Persistence: user + assistant messages and the citation are written.
    async with SessionLocal() as db:
        messages = (
            (
                await db.execute(
                    select(Message).where(
                        Message.conversation_id == uuid.UUID(body["conversation_id"])
                    )
                )
            )
            .scalars()
            .all()
        )
    assert {m.role.value for m in messages} == {"user", "assistant"}


async def test_low_score_refuses_before_llm(employee_user, monkeypatch):
    async def _retrieve(question, db, **kwargs):
        return [_chunk(1, 0.10)]  # below relevance_threshold (0.35)

    async def _generate(system, user, **kwargs):
        raise AssertionError("Guardrail 1 must refuse before calling the LLM")

    monkeypatch.setattr("app.services.rag.pipeline.retrieve", _retrieve)
    monkeypatch.setattr("app.services.rag.pipeline.generator.generate", _generate)

    async with _client() as client:
        resp = await client.post("/api/v1/chat", json={"question": "unrelated question"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["refused"] is True
    assert body["citations"] == []
    assert body["model_used"] is None


async def test_answer_without_citation_is_unverified(employee_user, monkeypatch):
    async def _retrieve(question, db, **kwargs):
        return [_chunk(1, 0.82)]

    async def _generate(system, user, **kwargs):
        return GenerationResult(
            text="A confident answer with no source marker.",
            model_used="qwen3-test",
            latency_ms=500,
            prompt_tokens=50,
            completion_tokens=10,
            tokens_per_second=8.0,
        )

    monkeypatch.setattr("app.services.rag.pipeline.retrieve", _retrieve)
    monkeypatch.setattr("app.services.rag.pipeline.generator.generate", _generate)

    async with _client() as client:
        resp = await client.post("/api/v1/chat", json={"question": "What is EDD?"})

    body = resp.json()
    assert resp.status_code == 200
    assert body["refused"] is False
    assert body["unverified"] is True
    assert body["citations"] == []


async def test_unknown_conversation_is_404(employee_user, monkeypatch):
    async def _retrieve(question, db, **kwargs):
        return [_chunk(1, 0.82)]

    monkeypatch.setattr("app.services.rag.pipeline.retrieve", _retrieve)

    async with _client() as client:
        resp = await client.post(
            "/api/v1/chat",
            json={"question": "hi", "conversation_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 404


async def test_reranker_enabled_pulls_candidates_and_reranks(employee_user, monkeypatch):
    """With the flag on, retrieval draws the full candidate pool and the reranker
    picks the final set (stubbed here so no cross-encoder loads)."""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "reranker_enabled", True)

    calls: dict = {}

    async def _retrieve(question, db, **kwargs):
        calls["retrieve_top_k"] = kwargs.get("top_k")
        return [_chunk(i, 0.9) for i in range(1, 6)]

    def _rerank(question, chunks, *, top_k, **kwargs):
        calls["reranked"] = True
        # Return a single low-cosine chunk so Guardrail 1 refuses (no generation).
        return [_chunk(1, 0.10)]

    monkeypatch.setattr("app.services.rag.pipeline.retrieve", _retrieve)
    monkeypatch.setattr("app.services.rag.pipeline.reranker.rerank", _rerank)

    async with _client() as client:
        resp = await client.post("/api/v1/chat", json={"question": "hello"})

    assert resp.status_code == 200
    assert calls["retrieve_top_k"] == settings.retrieval_top_k  # full pool, not top-3
    assert calls.get("reranked") is True
    assert resp.json()["refused"] is True  # 0.10 < calibrated 0.50


async def test_chat_stream_emits_tokens_then_final(employee_user, monkeypatch):
    seeded = await _seed_indexed_chunks(employee_user, 2)

    async def _retrieve(question, db, **kwargs):
        return seeded

    async def _stream(system, user, **kwargs):
        for delta in ["Enhanced ", "due ", "diligence [S1]."]:
            yield StreamChunk(delta=delta, done=False)
        yield StreamChunk(
            delta="",
            done=True,
            result=GenerationResult(
                text="Enhanced due diligence [S1].",
                model_used="qwen3-test",
                latency_ms=100,
                prompt_tokens=10,
                completion_tokens=5,
                tokens_per_second=8.0,
            ),
        )

    monkeypatch.setattr("app.services.rag.pipeline.retrieve", _retrieve)
    monkeypatch.setattr("app.services.rag.pipeline.generator.stream_generate", _stream)

    async with _client() as client:
        resp = await client.post("/api/v1/chat/stream", json={"question": "What is EDD?"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(resp.text)
    tokens = [data for kind, data in events if kind == "token"]
    assert len(tokens) == 3  # one per delta
    assert json.loads(tokens[0])["delta"] == "Enhanced "

    final = [data for kind, data in events if kind == "final"]
    assert len(final) == 1
    body = json.loads(final[0])
    assert body["refused"] is False
    assert [c["marker"] for c in body["citations"]] == ["S1"]


async def test_chat_stream_refusal_streams_no_tokens(employee_user, monkeypatch):
    async def _retrieve(question, db, **kwargs):
        return [_chunk(1, 0.10)]  # below calibrated threshold

    async def _stream(system, user, **kwargs):
        raise AssertionError("generation must not run on a Guardrail-1 refusal")
        yield  # pragma: no cover  (makes this an async generator)

    monkeypatch.setattr("app.services.rag.pipeline.retrieve", _retrieve)
    monkeypatch.setattr("app.services.rag.pipeline.generator.stream_generate", _stream)

    async with _client() as client:
        resp = await client.post("/api/v1/chat/stream", json={"question": "unrelated"})

    events = _parse_sse(resp.text)
    assert not [e for e in events if e[0] == "token"]
    final = [data for kind, data in events if kind == "final"]
    assert len(final) == 1
    assert json.loads(final[0])["refused"] is True
