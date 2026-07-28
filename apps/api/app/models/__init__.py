"""Model registry.

Importing every model here means a single `import app.models` populates
`Base.metadata` fully — which is what Alembic's env.py relies on.
"""

from app.db.base import Base
from app.models.audit_log import AuditLog
from app.models.conversation import (
    Conversation,
    Message,
    MessageCitation,
    MessageRole,
)
from app.models.document import (
    EMBEDDING_DIM,
    Document,
    DocumentChunk,
    DocumentStatus,
)
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "User",
    "UserRole",
    "Document",
    "DocumentChunk",
    "DocumentStatus",
    "EMBEDDING_DIM",
    "Conversation",
    "Message",
    "MessageCitation",
    "MessageRole",
    "AuditLog",
]
