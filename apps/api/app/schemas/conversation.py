"""Conversation DTOs — the history list for the dashboard."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConversationRead(BaseModel):
    """One row in the user's history: titled after its opening question, with a
    message count so the UI can show length without fetching every message."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int
