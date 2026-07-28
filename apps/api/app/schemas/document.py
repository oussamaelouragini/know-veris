"""Document DTOs — separated by intent (docs.md conventions)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import DocumentStatus


class DocumentRead(BaseModel):
    """What the admin UI sees for an uploaded document."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    mime_type: str
    page_count: int | None
    language: str | None
    status: DocumentStatus
    error_message: str | None
    created_at: datetime
