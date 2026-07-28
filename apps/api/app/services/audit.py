"""Audit trail helper — one place to append to `audit_logs`.

The audit log is the append-only record of who did what (upload, delete, user
creation…). Keeping a single writer keeps the action vocabulary consistent and
the endpoints thin.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    meta: dict | None = None,
    commit: bool = True,
) -> None:
    """Append one audit entry. `commit=False` to enlist it in a caller's transaction."""
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=meta,
        )
    )
    if commit:
        await db.commit()
