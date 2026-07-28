"""Conversation history — the signed-in user's own conversations. Any user.

Thin by convention: one query, serialize. A user only ever sees their own
conversations (filtered on user_id), never anyone else's.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import CurrentUser
from app.db.session import get_db
from app.models import Conversation, Message, UserRole
from app.schemas.conversation import ConversationRead
from app.services import audit

router = APIRouter(prefix="/conversations", tags=["conversations"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[ConversationRead])
async def list_conversations(user: CurrentUser, db: DbSession) -> list[ConversationRead]:
    """The user's conversations, most recently active first, each with its
    message count (drives the dashboard StatsCard and HistoryCard)."""
    stmt = (
        select(Conversation, func.count(Message.id).label("message_count"))
        .outerjoin(Message, Message.conversation_id == Conversation.id)
        .where(Conversation.user_id == user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        ConversationRead(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            message_count=count,
        )
        for conversation, count in rows
    ]


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Delete a conversation (cascades to its messages and citations).

    A user may delete their own conversations; an admin may delete any. To avoid
    leaking existence, a conversation the caller may not touch returns 404, not
    403 — same shape as a missing one.
    """
    conversation = await db.get(Conversation, conversation_id)
    owned = conversation is not None and conversation.user_id == user.id
    if conversation is None or not (owned or user.role == UserRole.admin):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )

    await db.delete(conversation)  # cascades to messages, then message_citations
    await db.commit()
    await audit.record(
        db,
        user_id=user.id,
        action="conversation.deleted",
        resource_type="conversation",
        resource_id=str(conversation_id),
    )
