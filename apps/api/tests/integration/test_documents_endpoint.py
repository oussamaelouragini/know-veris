"""Document admin endpoints: upload (202 + dedup + type check), list, status.

The ingestion BackgroundTask is stubbed, so no Ollama call happens; storage is
redirected to a tmp dir. Auth is exercised via FastAPI dependency overrides
rather than real Keycloak tokens.
"""

import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.security import get_current_user, require_admin
from app.db.session import SessionLocal
from app.main import app
from app.models import AuditLog, Document, DocumentChunk, DocumentStatus, User, UserRole
from app.services.ingestion.uploader import document_path

BOOTSTRAP = Path(__file__).parents[1] / "data" / "bootstrap"
PDF_BYTES = (BOOTSTRAP / "fr-obligations-vigilance.pdf").read_bytes()
PDF_MIME = "application/pdf"


@pytest.fixture
async def admin_user(tmp_path, monkeypatch):
    """A real admin row (FK target), auth override, tmp storage, stubbed task."""
    monkeypatch.setattr(get_settings(), "storage_path", str(tmp_path))
    calls: list[tuple] = []

    async def _fake_process(document_id, file_path):
        calls.append((document_id, file_path))

    monkeypatch.setattr("app.api.v1.endpoints.documents.process_document", _fake_process)

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
    yield user, calls
    app.dependency_overrides.clear()

    async with SessionLocal() as db:
        await db.execute(delete(Document).where(Document.uploaded_by == user.id))
        await db.execute(delete(User).where(User.id == user.id))
        await db.commit()


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_upload_returns_202_and_schedules_ingestion(admin_user):
    user, calls = admin_user
    async with _client() as client:
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("doc.pdf", PDF_BYTES, PDF_MIME)},
        )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["filename"] == "doc.pdf"

    # Background ingestion was scheduled with the new id and a real saved path.
    assert len(calls) == 1
    scheduled_id, path = calls[0]
    assert str(scheduled_id) == body["id"]
    assert Path(path).exists()


async def test_duplicate_upload_is_rejected_409(admin_user):
    async with _client() as client:
        first = await client.post(
            "/api/v1/documents", files={"file": ("a.pdf", PDF_BYTES, PDF_MIME)}
        )
        assert first.status_code == 202
        second = await client.post(
            "/api/v1/documents", files={"file": ("b.pdf", PDF_BYTES, PDF_MIME)}
        )
    assert second.status_code == 409


async def test_unsupported_type_is_rejected_415(admin_user):
    async with _client() as client:
        resp = await client.post(
            "/api/v1/documents",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
    assert resp.status_code == 415


async def test_list_and_get_document_status(admin_user):
    async with _client() as client:
        created = (
            await client.post("/api/v1/documents", files={"file": ("c.pdf", PDF_BYTES, PDF_MIME)})
        ).json()

        listing = await client.get("/api/v1/documents")
        assert listing.status_code == 200
        assert any(d["id"] == created["id"] for d in listing.json())

        one = await client.get(f"/api/v1/documents/{created['id']}")
        assert one.status_code == 200
        assert one.json()["status"] == "PENDING"

        missing = await client.get(f"/api/v1/documents/{uuid.uuid4()}")
        assert missing.status_code == 404


async def test_non_admin_is_forbidden(admin_user):
    # Swap the admin override for an employee -> real require_admin should 403.
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides[get_current_user] = lambda: User(
        keycloak_sub="pytest-employee", email="e@example.com", role=UserRole.employee
    )
    async with _client() as client:
        resp = await client.get("/api/v1/documents")
    assert resp.status_code == 403


async def test_delete_document_cascades_chunks_and_audits(admin_user):
    user, _ = admin_user
    async with SessionLocal() as db:
        doc = Document(
            filename="del.pdf",
            mime_type=PDF_MIME,
            file_hash=uuid.uuid4().hex,
            status=DocumentStatus.INDEXED,
            uploaded_by=user.id,
        )
        db.add(doc)
        await db.flush()
        db.add(
            DocumentChunk(
                document_id=doc.id,
                chunk_index=0,
                content="chunk",
                page_number=1,
                language="en",
            )
        )
        await db.commit()
        doc_id = doc.id

    # A stored file at the expected path must be removed by the delete.
    stored = document_path(doc)
    stored.write_bytes(b"pdf-bytes")

    async with _client() as client:
        resp = await client.delete(f"/api/v1/documents/{doc_id}")
    assert resp.status_code == 204

    async with SessionLocal() as db:
        assert await db.get(Document, doc_id) is None
        chunks = (
            (await db.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id)))
            .scalars()
            .all()
        )
        assert chunks == []  # cascaded away
        audits = (
            (
                await db.execute(
                    select(AuditLog).where(
                        AuditLog.action == "document.deleted",
                        AuditLog.resource_id == str(doc_id),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(audits) == 1
    assert not stored.exists()  # file removed


async def test_delete_missing_document_is_404(admin_user):
    async with _client() as client:
        resp = await client.delete(f"/api/v1/documents/{uuid.uuid4()}")
    assert resp.status_code == 404
