import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
import tempfile
import os


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest_asyncio.fixture
async def setup_db(db_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    await init_db(db_path)
    yield db_path


@pytest_asyncio.fixture
async def project_id(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/projects", json={
            "name": "test-proj",
            "display_name": "Test Project",
            "engine": "godot",
            "mode": "development"
        })
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_document(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/documents", json={
            "project_id": project_id,
            "file_path": "design/combat.md",
            "content": "# Combat Design\nInitial design",
            "updated_by": "Alice"
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["file_path"] == "design/combat.md"
    assert data["content"] == "# Combat Design\nInitial design"
    assert data["updated_by"] == "Alice"
    assert data["previous_content"] == ""


@pytest.mark.asyncio
async def test_list_documents_by_project(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/documents", json={
            "project_id": project_id,
            "file_path": "design/doc1.md",
            "content": "Doc 1"
        })
        await client.post("/api/documents", json={
            "project_id": project_id,
            "file_path": "design/doc2.md",
            "content": "Doc 2"
        })
        resp = await client.get(f"/api/documents?project_id={project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_get_document(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/documents", json={
            "project_id": project_id,
            "file_path": "design/test.md",
            "content": "Test content"
        })
        doc_id = create_resp.json()["id"]
        resp = await client.get(f"/api/documents/{doc_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == doc_id
    assert data["content"] == "Test content"


@pytest.mark.asyncio
async def test_update_document_saves_previous(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create document
        create_resp = await client.post("/api/documents", json={
            "project_id": project_id,
            "file_path": "design/evolving.md",
            "content": "Version 1",
            "updated_by": "Alice"
        })
        doc_id = create_resp.json()["id"]

        # Update document
        update_resp = await client.put(f"/api/documents/{doc_id}", json={
            "content": "Version 2",
            "updated_by": "Bob"
        })

    assert update_resp.status_code == 200
    data = update_resp.json()
    assert data["content"] == "Version 2"
    assert data["previous_content"] == "Version 1"
    assert data["updated_by"] == "Bob"


@pytest.mark.asyncio
async def test_get_document_diff(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create and update document
        create_resp = await client.post("/api/documents", json={
            "project_id": project_id,
            "file_path": "design/changes.md",
            "content": "Line 1\nLine 2\nLine 3"
        })
        doc_id = create_resp.json()["id"]

        await client.put(f"/api/documents/{doc_id}", json={
            "content": "Line 1\nLine 2 Modified\nLine 3\nLine 4",
            "updated_by": "Charlie"
        })

        # Get diff
        resp = await client.get(f"/api/documents/{doc_id}/diff")

    assert resp.status_code == 200
    data = resp.json()
    assert "diff" in data
    # Diff should contain some indication of changes
    assert len(data["diff"]) > 0
