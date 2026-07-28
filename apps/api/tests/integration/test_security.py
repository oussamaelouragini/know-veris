"""Security layer: JWT validation, JIT provisioning, RBAC.

Self-contained — mints its own RSA keypair and stubs the JWKS cache, so it
never touches Keycloak. Exercises the real DB session (JIT provisioning writes
a row), cleaning up after itself.
"""

import base64
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from jose import jwt
from sqlalchemy import delete, select

from app.core import security
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import User, UserRole

settings = get_settings()
KID = "test-kid"
TEST_SUB = "pytest-security-sub"


def _b64u(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture
def signing_keys(monkeypatch):
    """Generate a keypair, expose its public JWK via the (stubbed) JWKS cache."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": KID,
        "use": "sig",
        "alg": "RS256",
        "n": _b64u(numbers.n),
        "e": _b64u(numbers.e),
    }
    monkeypatch.setattr(security._jwks_cache, "_keys", [jwk])
    monkeypatch.setattr(security._jwks_cache, "_fetched_at", time.monotonic())
    return private_pem


def _make_token(private_pem: bytes, *, roles: list[str], expired: bool = False, **over):
    now = int(time.time())
    claims = {
        "sub": TEST_SUB,
        "iss": settings.keycloak_issuer,
        "aud": settings.keycloak_audience,
        "exp": now - 60 if expired else now + 3600,
        "iat": now,
        "email": "pytest@example.com",
        "name": "Pytest User",
        "realm_access": {"roles": roles},
    }
    claims.update(over)
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": KID})


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def _cleanup() -> None:
    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.keycloak_sub == TEST_SUB))
        await db.commit()


async def test_jit_provisioning_creates_and_syncs_user(signing_keys):
    await _cleanup()
    try:
        # First call as employee -> row created.
        async with SessionLocal() as db:
            token = _make_token(signing_keys, roles=["employee"])
            user = await security.get_current_user(_creds(token), db)
            assert user.role is UserRole.employee
            assert user.email == "pytest@example.com"
            assert user.last_login_at is not None

        # Second call promoted to admin -> same row, role re-synced.
        async with SessionLocal() as db:
            token = _make_token(signing_keys, roles=["employee", "admin"])
            user = await security.get_current_user(_creds(token), db)
            assert user.role is UserRole.admin
            rows = (
                (await db.execute(select(User).where(User.keycloak_sub == TEST_SUB)))
                .scalars()
                .all()
            )
            assert len(rows) == 1  # provisioned once, not duplicated
    finally:
        await _cleanup()


async def test_require_admin_rejects_employee(signing_keys):
    await _cleanup()
    try:
        async with SessionLocal() as db:
            token = _make_token(signing_keys, roles=["employee"])
            user = await security.get_current_user(_creds(token), db)
            with pytest.raises(HTTPException) as exc:
                await security.require_admin(user)
            assert exc.value.status_code == 403
    finally:
        await _cleanup()


async def test_expired_token_is_rejected(signing_keys):
    async with SessionLocal() as db:
        token = _make_token(signing_keys, roles=["employee"], expired=True)
        with pytest.raises(HTTPException) as exc:
            await security.get_current_user(_creds(token), db)
        assert exc.value.status_code == 401


async def test_wrong_audience_is_rejected(signing_keys):
    async with SessionLocal() as db:
        token = _make_token(signing_keys, roles=["employee"], aud="some-other-client")
        with pytest.raises(HTTPException) as exc:
            await security.get_current_user(_creds(token), db)
        assert exc.value.status_code == 401
