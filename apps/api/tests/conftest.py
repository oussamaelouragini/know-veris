"""Shared pytest fixtures — and isolation of the test database.

Tests run against a dedicated `knowveris_test` database, never the dev database
the running app uses. This keeps the two from colliding (e.g. a live-ingested
document's hash breaking an upload-dedup test) and lets the app keep a demo
corpus indexed while the suite stays deterministic.

The redirect happens by overriding `DATABASE_URL` in the environment *before*
any `app.*` import, so the app's module-level engine binds to the test DB.
Override the target with `TEST_DATABASE_URL` if the default doesn't fit.

Schema is provisioned with `Base.metadata.create_all` (fast, self-contained) —
the perf-only HNSW/GIN indexes from the Alembic migration are intentionally
skipped; they don't affect correctness, only speed.
"""

import asyncio
import os

# --- MUST run before importing anything under app.* ---
_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://knowveris:knowveris@postgres:5432/knowveris_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

import app.models  # noqa: E402, F401  — populate Base.metadata with every table
from app.db.base import Base  # noqa: E402
from app.db.session import engine  # noqa: E402  — already bound to the test DB


async def _provision_test_database() -> None:
    """Create the test DB if missing, then (re)build extensions + schema."""
    base, _, dbname = _TEST_DB_URL.rpartition("/")

    # CREATE DATABASE cannot run inside a transaction — use an AUTOCOMMIT
    # connection to the maintenance `postgres` database.
    admin = create_async_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": dbname}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        await admin.dispose()

    # Extensions are per-database, so the fresh test DB needs its own.
    setup = create_async_engine(_TEST_DB_URL)
    try:
        async with setup.begin() as conn:
            for extension in ("vector", "pg_trgm", "uuid-ossp"):
                await conn.execute(text(f'CREATE EXTENSION IF NOT EXISTS "{extension}"'))
            # Drop + recreate so every run starts from the current schema.
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await setup.dispose()


# Runs once, at collection time, before any event loop pytest-asyncio manages.
asyncio.run(_provision_test_database())


@pytest.fixture(autouse=True)
async def _dispose_engine_after_test():
    """Dispose the module-level engine after each test.

    pytest-asyncio (auto mode) gives each test its own event loop; the shared
    engine would otherwise cache connections bound to a closed loop and fail
    with "Event loop is closed" on the next test.
    """
    yield
    await engine.dispose()
