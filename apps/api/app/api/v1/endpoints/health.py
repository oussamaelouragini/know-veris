import httpx
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.schemas.health import DependencyStatus, HealthRead

router = APIRouter()


async def _check_postgres() -> DependencyStatus:
    """Liveness + proof that pgvector is actually installed, not just requested."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
            version = result.scalar_one_or_none()
        if version is None:
            return DependencyStatus(ok=False, detail="pgvector extension missing")
        return DependencyStatus(ok=True, detail=f"pgvector {version}")
    except Exception as exc:  # noqa: BLE001 - health must never raise
        return DependencyStatus(ok=False, detail=str(exc)[:200])
    finally:
        await engine.dispose()


async def _check_ollama() -> DependencyStatus:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.ollama_url}/api/tags")
            response.raise_for_status()
            models = [m["name"] for m in response.json().get("models", [])]
        return DependencyStatus(ok=True, detail=f"{len(models)} model(s): {', '.join(models)}")
    except Exception as exc:  # noqa: BLE001
        return DependencyStatus(ok=False, detail=str(exc)[:200])


@router.get("/health", response_model=HealthRead)
async def health() -> HealthRead:
    postgres = await _check_postgres()
    ollama = await _check_ollama()
    return HealthRead(
        status="ok" if postgres.ok and ollama.ok else "degraded",
        postgres=postgres,
        ollama=ollama,
    )
