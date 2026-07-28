"""Keycloak Admin REST API client — employee account management (ADR-006).

Keycloak owns identity; FastAPI never runs a homegrown auth system. Account
creation goes through the Admin REST API using the confidential service account
`knowveris-admin-cli` (client_credentials), reached over the docker network
(`keycloak_internal_url`), not the browser-facing host.

Used as an async context manager so one service-account token is fetched per
operation and the HTTP client is always closed:

    async with KeycloakAdmin() as kc:
        user_id = await kc.create_user(...)
        await kc.set_password(user_id, temp, temporary=True)
        await kc.assign_realm_role(user_id, "employee")
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

settings = get_settings()


class KeycloakAdminError(RuntimeError):
    """A Keycloak Admin REST call failed (auth, network, or unexpected status)."""


class KeycloakConflict(KeycloakAdminError):
    """The username or email already exists in Keycloak (409)."""


class KeycloakAdmin:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=10.0)
        self._token: str | None = None
        self._realm = settings.keycloak_realm
        self._base = settings.keycloak_internal_url.rstrip("/")

    async def __aenter__(self) -> KeycloakAdmin:
        self._token = await self._fetch_token()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    async def _fetch_token(self) -> str:
        url = f"{self._base}/realms/{self._realm}/protocol/openid-connect/token"
        resp = await self._client.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": settings.keycloak_admin_client_id,
                "client_secret": settings.keycloak_admin_client_secret,
            },
        )
        if resp.status_code != 200:
            raise KeycloakAdminError(f"service-account token failed: {resp.status_code}")
        return resp.json()["access_token"]

    def _admin(self, path: str) -> str:
        return f"{self._base}/admin/realms/{self._realm}{path}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def create_user(
        self, *, username: str, email: str, first_name: str, last_name: str
    ) -> str:
        """Create an enabled user; return the new Keycloak user id (the JWT `sub`)."""
        resp = await self._client.post(
            self._admin("/users"),
            headers=self._headers,
            json={
                "username": username,
                "email": email,
                "firstName": first_name,
                "lastName": last_name,
                "enabled": True,
                "emailVerified": True,
            },
        )
        if resp.status_code == 409:
            raise KeycloakConflict("username or email already exists")
        if resp.status_code != 201:
            raise KeycloakAdminError(f"create user failed: {resp.status_code}")
        # 201 Location: .../users/{id}
        return resp.headers["Location"].rstrip("/").rsplit("/", 1)[-1]

    async def set_password(self, user_id: str, password: str, *, temporary: bool = True) -> None:
        resp = await self._client.put(
            self._admin(f"/users/{user_id}/reset-password"),
            headers=self._headers,
            json={"type": "password", "value": password, "temporary": temporary},
        )
        if resp.status_code not in (204, 200):
            raise KeycloakAdminError(f"set password failed: {resp.status_code}")

    async def assign_realm_role(self, user_id: str, role_name: str) -> None:
        role = await self._client.get(self._admin(f"/roles/{role_name}"), headers=self._headers)
        if role.status_code != 200:
            raise KeycloakAdminError(f"role '{role_name}' lookup failed: {role.status_code}")
        assign = await self._client.post(
            self._admin(f"/users/{user_id}/role-mappings/realm"),
            headers=self._headers,
            json=[role.json()],
        )
        if assign.status_code not in (204, 200):
            raise KeycloakAdminError(f"assign role failed: {assign.status_code}")

    async def delete_user(self, user_id: str) -> None:
        """Remove a user from Keycloak.

        Reserved for rolling back a half-created account: the API never exposes
        deletion, because an account that ever existed is disabled and kept for
        traceability (PLAN §3). An account whose creation failed mid-flow never
        existed as far as the business is concerned.

        404 is treated as success so the rollback is idempotent.
        """
        resp = await self._client.delete(self._admin(f"/users/{user_id}"), headers=self._headers)
        if resp.status_code not in (204, 200, 404):
            raise KeycloakAdminError(f"delete user failed: {resp.status_code}")

    async def list_users(self) -> list[dict[str, Any]]:
        resp = await self._client.get(self._admin("/users"), headers=self._headers)
        if resp.status_code != 200:
            raise KeycloakAdminError(f"list users failed: {resp.status_code}")
        return resp.json()

    async def set_enabled(self, user_id: str, enabled: bool) -> None:
        resp = await self._client.put(
            self._admin(f"/users/{user_id}"),
            headers=self._headers,
            json={"enabled": enabled},
        )
        if resp.status_code not in (204, 200):
            raise KeycloakAdminError(f"set enabled failed: {resp.status_code}")
