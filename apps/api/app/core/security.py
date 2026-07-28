"""JWT validation (Keycloak JWKS), RBAC dependencies, and JIT provisioning.

Keycloak owns authentication; this module is the resource-server side (ADR-006).
Every protected request carries a Bearer access token that we validate against
Keycloak's published signing keys (JWKS), then mirror the identity into the
`users` table on first sight (JIT provisioning) so business rows have a stable FK.

Trust boundary: signatures are checked against JWKS fetched over the internal
docker network (`keycloak:8080`), while `iss`/`aud` are checked against the
front-channel values the browser actually received — hence two distinct URLs in
settings (keycloak_jwks_url vs keycloak_issuer / keycloak_audience).
"""

import time
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.models import User, UserRole

settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=True)


def _credentials_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


class _JWKSCache:
    """Caches Keycloak's signing keys; refetches on TTL expiry or a `kid` miss.

    A `kid` miss means Keycloak likely rotated its keys, so we force one refetch
    before giving up — this avoids a hard outage every time keys rotate.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._keys: list[dict[str, Any]] | None = None
        self._fetched_at = 0.0
        self._ttl = ttl_seconds

    async def get_keys(self, *, force: bool = False) -> list[dict[str, Any]]:
        age = time.monotonic() - self._fetched_at
        if force or self._keys is None or age > self._ttl:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(settings.keycloak_jwks_url)
                response.raise_for_status()
                self._keys = response.json()["keys"]
                self._fetched_at = time.monotonic()
        return self._keys

    async def find_key(self, kid: str | None) -> dict[str, Any] | None:
        for key in await self.get_keys():
            if key.get("kid") == kid:
                return key
        # Not found with cached keys — force one refetch in case of rotation.
        for key in await self.get_keys(force=True):
            if key.get("kid") == kid:
                return key
        return None


_jwks_cache = _JWKSCache()


async def _decode_token(token: str) -> dict[str, Any]:
    """Verify signature, issuer, audience, and expiry; return the claims."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise _credentials_error("Malformed token header") from exc

    key = await _jwks_cache.find_key(header.get("kid"))
    if key is None:
        raise _credentials_error("Signing key not found")

    try:
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.keycloak_audience,
            issuer=settings.keycloak_issuer,
        )
    except ExpiredSignatureError as exc:
        raise _credentials_error("Token expired") from exc
    except JWTError as exc:
        raise _credentials_error(f"Invalid token: {exc}") from exc


def _role_from_claims(claims: dict[str, Any]) -> UserRole:
    # `admin` is a composite realm role that includes `employee`; take the highest.
    roles = claims.get("realm_access", {}).get("roles", [])
    return UserRole.admin if "admin" in roles else UserRole.employee


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Validate the Bearer token and JIT-provision / refresh the mirrored user."""
    claims = await _decode_token(credentials.credentials)

    sub = claims.get("sub")
    if not sub:
        raise _credentials_error("Token missing `sub` claim")

    email = claims.get("email") or claims.get("preferred_username") or ""
    full_name = claims.get("name")
    role = _role_from_claims(claims)

    user = (await db.execute(select(User).where(User.keycloak_sub == sub))).scalar_one_or_none()

    if user is None:
        user = User(
            keycloak_sub=sub,
            email=email,
            full_name=full_name,
            role=role,
            last_login_at=func.now(),
        )
        db.add(user)
    else:
        # Keycloak is the source of truth: re-sync on every request.
        user.email = email or user.email
        user.full_name = full_name or user.full_name
        user.role = role
        user.last_login_at = func.now()

    await db.commit()
    await db.refresh(user)
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


# Ergonomic aliases for endpoint signatures.
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
