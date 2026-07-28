"""Admin user-management endpoints, with the Keycloak Admin client mocked.

No live Keycloak: a fake KeycloakAdmin records calls and returns canned data, so
the provisioning orchestration (create → password → role → Postgres mirror →
audit), listing, enable/disable, and reset-password are what's under test.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.security import get_current_user, require_admin
from app.db.session import SessionLocal
from app.main import app
from app.models import AuditLog, User, UserRole
from app.services.keycloak.admin_client import KeycloakAdminError

FAKE_KC_USER_ID = "kc-user-abc123"


class _FakeKeycloakAdmin:
    """Async-context-manager stand-in for KeycloakAdmin; records what it was asked."""

    calls: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def create_user(self, *, username, email, first_name, last_name):
        _FakeKeycloakAdmin.calls.append(("create_user", username, email))
        return FAKE_KC_USER_ID

    async def set_password(self, user_id, password, *, temporary=True):
        _FakeKeycloakAdmin.calls.append(("set_password", user_id, temporary))

    async def assign_realm_role(self, user_id, role_name):
        _FakeKeycloakAdmin.calls.append(("assign_realm_role", user_id, role_name))

    async def list_users(self):
        return [
            {
                "id": FAKE_KC_USER_ID,
                "username": "alice",
                "email": "alice@bank.local",
                "enabled": True,
                "firstName": "Alice",
                "lastName": "Martin",
            }
        ]

    async def set_enabled(self, user_id, enabled):
        _FakeKeycloakAdmin.calls.append(("set_enabled", user_id, enabled))

    async def delete_user(self, user_id):
        _FakeKeycloakAdmin.calls.append(("delete_user", user_id))


class _RoleAssignmentFails(_FakeKeycloakAdmin):
    """Keycloak accepts the user but refuses the role — the exact shape of the
    403 seen live when the service account could not read realm roles."""

    async def assign_realm_role(self, user_id, role_name):
        _FakeKeycloakAdmin.calls.append(("assign_realm_role", user_id, role_name))
        raise KeycloakAdminError("role 'employee' lookup failed: 403")


@pytest.fixture
async def admin_user(monkeypatch):
    _FakeKeycloakAdmin.calls = []
    monkeypatch.setattr("app.services.keycloak.provisioning.KeycloakAdmin", _FakeKeycloakAdmin)

    async with SessionLocal() as db:
        user = User(
            keycloak_sub=f"pytest-admin-{uuid.uuid4().hex}",
            email="admin@example.com",
            role=UserRole.admin,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    app.dependency_overrides[require_admin] = lambda: user
    yield user
    app.dependency_overrides.clear()

    async with SessionLocal() as db:
        await db.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
        await db.execute(delete(User).where(User.keycloak_sub == FAKE_KC_USER_ID))
        await db.execute(delete(User).where(User.id == user.id))
        await db.commit()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_create_user_provisions_mirrors_and_audits(admin_user):
    async with _client() as client:
        resp = await client.post(
            "/api/v1/admin/users",
            json={
                "username": "alice",
                "email": "alice@bank.local",
                "first_name": "Alice",
                "last_name": "Martin",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == FAKE_KC_USER_ID
    assert body["temporary_password"]  # shown once

    # Keycloak flow: create -> set temp password -> assign employee role.
    actions = [c[0] for c in _FakeKeycloakAdmin.calls]
    assert actions == ["create_user", "set_password", "assign_realm_role"]
    assert _FakeKeycloakAdmin.calls[1][2] is True  # temporary password
    assert _FakeKeycloakAdmin.calls[2][2] == "employee"

    # Mirrored into Postgres + audited.
    async with SessionLocal() as db:
        mirrored = (
            await db.execute(select(User).where(User.keycloak_sub == FAKE_KC_USER_ID))
        ).scalar_one()
        assert mirrored.role == UserRole.employee
        audits = (
            (await db.execute(select(AuditLog).where(AuditLog.action == "user.created")))
            .scalars()
            .all()
        )
        assert any(a.resource_id == FAKE_KC_USER_ID for a in audits)


async def test_failed_role_assignment_rolls_back_the_keycloak_account(admin_user, monkeypatch):
    """A creation that fails partway must leave nothing behind: no roleless
    Keycloak account (it would also block the retry with a 409), no Postgres
    mirror, no audit entry."""
    monkeypatch.setattr(
        "app.services.keycloak.provisioning.KeycloakAdmin", _RoleAssignmentFails
    )

    async with _client() as client:
        resp = await client.post(
            "/api/v1/admin/users",
            json={
                "username": "bob",
                "email": "bob@bank.local",
                "first_name": "Bob",
                "last_name": "Durand",
            },
        )

    assert resp.status_code == 502
    assert "role 'employee' lookup failed: 403" in resp.json()["detail"]

    actions = [c[0] for c in _FakeKeycloakAdmin.calls]
    assert actions == ["create_user", "set_password", "assign_realm_role", "delete_user"]

    async with SessionLocal() as db:
        mirrored = (
            await db.execute(select(User).where(User.keycloak_sub == FAKE_KC_USER_ID))
        ).scalar_one_or_none()
        assert mirrored is None
        audits = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "user.created",
                        AuditLog.user_id == admin_user.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert audits == []


async def test_list_users(admin_user):
    async with _client() as client:
        resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 200
    users = resp.json()
    assert users[0]["username"] == "alice"
    assert users[0]["enabled"] is True


async def test_disable_user_audits(admin_user):
    async with _client() as client:
        resp = await client.patch(f"/api/v1/admin/users/{FAKE_KC_USER_ID}", json={"enabled": False})
    assert resp.status_code == 204
    assert ("set_enabled", FAKE_KC_USER_ID, False) in _FakeKeycloakAdmin.calls
    async with SessionLocal() as db:
        audits = (
            (await db.execute(select(AuditLog).where(AuditLog.action == "user.disabled")))
            .scalars()
            .all()
        )
        assert any(a.resource_id == FAKE_KC_USER_ID for a in audits)


async def test_reset_password_returns_new_secret(admin_user):
    async with _client() as client:
        resp = await client.post(f"/api/v1/admin/users/{FAKE_KC_USER_ID}/reset-password")
    assert resp.status_code == 200
    assert resp.json()["temporary_password"]
    assert ("set_password", FAKE_KC_USER_ID, True) in _FakeKeycloakAdmin.calls


async def test_non_admin_is_forbidden(admin_user):
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_current_user] = lambda: User(
        keycloak_sub="pytest-employee", email="e@example.com", role=UserRole.employee
    )
    async with _client() as client:
        resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 403
