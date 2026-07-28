"""Chat endpoint — ask a question, get a sourced answer. Any authenticated user.

Thin by convention: validate, delegate to the RAG pipeline, serialize. All the
retrieval, guardrail, generation, and persistence logic lives in the service.

Two shapes of the same pipeline:
* `POST /chat`        — blocks, returns the full ChatResponse (simple, testable).
* `POST /chat/stream` — Server-Sent Events: `token` deltas then one `final`
  event carrying the full ChatResponse (citations, refused, timings). SSE is
  about perceived latency on CPU (first token in seconds, not a blank minute).
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag.pipeline import (
    ConversationNotFound,
    answer_question,
    answer_question_stream,
)

router = APIRouter(prefix="/chat", tags=["chat"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ChatResponse)
async def chat(user: CurrentUser, db: DbSession, request: ChatRequest) -> ChatResponse:
    try:
        answer = await answer_question(
            request.question,
            db,
            user,
            conversation_id=request.conversation_id,
        )
    except ConversationNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        ) from exc
    return ChatResponse.from_answer(answer)


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/stream")
async def chat_stream(user: CurrentUser, db: DbSession, request: ChatRequest) -> StreamingResponse:
    async def event_source():
        try:
            async for kind, payload in answer_question_stream(
                request.question, db, user, conversation_id=request.conversation_id
            ):
                if kind == "token":
                    yield _sse("token", json.dumps({"delta": payload}))
                else:  # ("final", ChatAnswer)
                    yield _sse("final", ChatResponse.from_answer(payload).model_dump_json())
        except ConversationNotFound:
            yield _sse("error", json.dumps({"detail": "Conversation not found"}))

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
