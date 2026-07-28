"""Fixtures for the golden-set eval: a freshly indexed bootstrap corpus.

The eval needs the 5 bootstrap documents indexed with **real** bge-m3 embeddings
(retrieval quality can't be measured on mocks). This ingests them into the
isolated test DB once per session, and skips the whole eval if Ollama is
unreachable — the eval is a live measurement, not a unit test.
"""

import asyncio
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.models import Document, DocumentStatus, User, UserRole
from app.services.ingestion.indexer import ingest_document
from app.services.ingestion.parsers import DOCX_MIME, PDF_MIME
from app.services.ingestion.uploader import DuplicateDocument, register_upload

settings = get_settings()

BOOTSTRAP = Path(__file__).parents[1] / "data" / "bootstrap"
MIME = {".pdf": PDF_MIME, ".docx": DOCX_MIME}


def _ollama_reachable() -> bool:
    try:
        httpx.get(f"{settings.ollama_url}/api/tags", timeout=3.0).raise_for_status()
        return True
    except Exception:
        return False


async def _ingest_bootstrap() -> int:
    async with SessionLocal() as db:
        loader = User(keycloak_sub="eval-loader", email="eval@local", role=UserRole.admin)
        db.add(loader)
        await db.commit()
        await db.refresh(loader)

    for path in sorted(BOOTSTRAP.iterdir()):
        if path.suffix not in MIME:
            continue
        async with SessionLocal() as db:
            try:
                document, saved = await register_upload(
                    db,
                    filename=path.name,
                    mime_type=MIME[path.suffix],
                    contents=path.read_bytes(),
                    uploaded_by=loader.id,
                )
            except DuplicateDocument:
                continue
        async with SessionLocal() as db:
            await ingest_document(document.id, saved, db)

    async with SessionLocal() as db:
        indexed = (
            await db.execute(
                Document.__table__.select().where(Document.status == DocumentStatus.INDEXED)
            )
        ).all()

    # This ran in its own asyncio.run loop; dispose the shared engine so no
    # pooled connection leaks into the test loop ("attached to a different loop").
    await engine.dispose()
    return len(indexed)


@pytest.fixture(scope="session")
def indexed_corpus() -> int:
    """Ingest the bootstrap corpus once (real embeddings). Skip if no Ollama."""
    if not _ollama_reachable():
        pytest.skip("Ollama not reachable — golden-set eval requires live models")
    count = asyncio.run(_ingest_bootstrap())
    assert count == 5, f"expected 5 indexed bootstrap docs, got {count}"
    return count
