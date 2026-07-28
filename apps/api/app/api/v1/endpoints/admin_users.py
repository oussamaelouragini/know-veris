"""Admin user-management endpoints — employee accounts via Keycloak (ADR-006).

Admin-only. Thin: validate, delegate to the provisioning service, serialize.
No DELETE — accounts are disabled, never deleted (traceability, PLAN §3).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AdminUser
from app.db.session import get_db
from app.schemas.admin_user import (
    AdminUserCreate,
    AdminUserCreated,
    AdminUserRead,
    AdminUserUpdate,
    PasswordReset,
)
from app.services.keycloak import provisioning
from app.services.keycloak.admin_client import KeycloakAdminError, KeycloakConflict

router = APIRouter(prefix="/admin/users", tags=["admin"])

DbSession = Annotated[AsyncSession, Depends(get_db)]


def _keycloak_http_error(exc: KeycloakAdminError) -> HTTPException:
    if isinstance(exc, KeycloakConflict):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Keycloak: {exc}")


@router.post("", status_code=status.HTTP_201_CREATED, response_model=AdminUserCreated)
async def create_user(
    admin: AdminUser, db: DbSession, payload: AdminUserCreate
) -> AdminUserCreated:
    try:
        return await provisioning.create_employee(db, admin_id=admin.id, data=payload)
    except KeycloakAdminError as exc:
        raise _keycloak_http_error(exc) from exc


@router.get("", response_model=list[AdminUserRead])
async def list_users(admin: AdminUser, db: DbSession) -> list[AdminUserRead]:
    try:
        return await provisioning.list_employees()
    except KeycloakAdminError as exc:
        raise _keycloak_http_error(exc) from exc


@router.patch("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_user(
    user_id: str, payload: AdminUserUpdate, admin: AdminUser, db: DbSession
) -> None:
    try:
        await provisioning.set_user_enabled(
            db, admin_id=admin.id, user_id=user_id, enabled=payload.enabled
        )
    except KeycloakAdminError as exc:
        raise _keycloak_http_error(exc) from exc


@router.post("/{user_id}/reset-password", response_model=PasswordReset)
async def reset_password(user_id: str, admin: AdminUser, db: DbSession) -> PasswordReset:
    try:
        return await provisioning.reset_password(db, admin_id=admin.id, user_id=user_id)
    except KeycloakAdminError as exc:
        raise _keycloak_http_error(exc) from exc
