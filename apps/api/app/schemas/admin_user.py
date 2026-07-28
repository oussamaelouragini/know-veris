"""Admin user-management DTOs — separated by intent (docs.md conventions)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AdminUserCreate(BaseModel):
    """Admin-supplied fields to provision a new employee."""

    username: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=3, max_length=256)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)


class AdminUserCreated(BaseModel):
    """Returned once on creation — the temporary password is shown only here."""

    id: str  # Keycloak user id (the JWT `sub`)
    username: str
    email: str
    temporary_password: str


class AdminUserRead(BaseModel):
    """A Keycloak user as listed in the admin screen."""

    id: str
    username: str
    email: str | None = None
    enabled: bool
    first_name: str | None = None
    last_name: str | None = None


class AdminUserUpdate(BaseModel):
    """Enable or disable an account (we disable, never delete — traceability)."""

    enabled: bool


class PasswordReset(BaseModel):
    """Returned once on reset — the new temporary password is shown only here."""

    temporary_password: str
