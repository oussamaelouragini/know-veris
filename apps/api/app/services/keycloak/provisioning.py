"""Employee account provisioning — orchestrates Keycloak + the mirrored users row.

Keeps the endpoints thin (docs.md): the multi-step create flow (Keycloak user →
temp password → realm role → Postgres mirror → audit) lives here. Passwords are
temporary (`temporary=True` forces a change at first login) and returned to the
admin exactly once. We disable accounts, never delete them (traceability).
"""

from __future__ import annotations

import secrets
import uuid
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserCreated,
    AdminUserRead,
    PasswordReset,
)
from app.services import audit
from app.services.keycloak.admin_client import KeycloakAdmin, KeycloakAdminError


def _temp_password() -> str:
    return secrets.token_urlsafe(12)


async def create_employee(
    db: AsyncSession, *, admin_id: uuid.UUID, data: AdminUserCreate
) -> AdminUserCreated:
    """Create the Keycloak user, mirror it into `users`, and audit — atomically."""
    temp = _temp_password()
    async with KeycloakAdmin() as kc:
        user_id = await kc.create_user(
            username=data.username,
            email=data.email,
            first_name=data.first_name,
            last_name=data.last_name,
        )
        try:
            await kc.set_password(user_id, temp, temporary=True)
            await kc.assign_realm_role(user_id, "employee")
        except KeycloakAdminError:
            # Compensating delete. Creation is three Keycloak calls with no
            # transaction around them: a failure after the first leaves an
            # account with no role (it can authenticate but reaches nothing) and
            # no Postgres mirror, and its username silently blocks the admin's
            # retry with a 409. Rolling it back is cleanup of a creation that
            # never completed — not the account lifecycle, where we disable and
            # never delete.
            with suppress(KeycloakAdminError):
                await kc.delete_user(user_id)
            raise  # the original failure is what the admin needs to see

    # Mirror into Postgres (keycloak_sub == the JWT `sub`), like JIT provisioning.
    db.add(
        User(
            keycloak_sub=user_id,
            email=data.email,
            full_name=f"{data.first_name} {data.last_name}",
            role=UserRole.employee,
        )
    )
    await audit.record(
        db,
        user_id=admin_id,
        action="user.created",
        resource_type="user",
        resource_id=user_id,
        meta={"username": data.username, "email": data.email},
        commit=False,
    )
    await db.commit()

    return AdminUserCreated(
        id=user_id, username=data.username, email=data.email, temporary_password=temp
    )


async def list_employees() -> list[AdminUserRead]:
    async with KeycloakAdmin() as kc:
        raw = await kc.list_users()
    return [
        AdminUserRead(
            id=u["id"],
            username=u.get("username", ""),
            email=u.get("email"),
            enabled=u.get("enabled", False),
            first_name=u.get("firstName"),
            last_name=u.get("lastName"),
        )
        for u in raw
    ]


async def set_user_enabled(
    db: AsyncSession, *, admin_id: uuid.UUID, user_id: str, enabled: bool
) -> None:
    async with KeycloakAdmin() as kc:
        await kc.set_enabled(user_id, enabled)
    await audit.record(
        db,
        user_id=admin_id,
        action="user.enabled" if enabled else "user.disabled",
        resource_type="user",
        resource_id=user_id,
    )


async def reset_password(db: AsyncSession, *, admin_id: uuid.UUID, user_id: str) -> PasswordReset:
    temp = _temp_password()
    async with KeycloakAdmin() as kc:
        await kc.set_password(user_id, temp, temporary=True)
    await audit.record(
        db,
        user_id=admin_id,
        action="user.password_reset",
        resource_type="user",
        resource_id=user_id,
    )
    return PasswordReset(temporary_password=temp)
