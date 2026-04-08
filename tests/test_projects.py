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


@pytest.mark.asyncio
async def test_create_project(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/projects", json={
            "name": "my-rpg",
            "display_name": "My RPG Game",
            "engine": "godot",
            "mode": "development"
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "my-rpg"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_list_projects(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/projects", json={
            "name": "game1", "display_name": "Game 1", "engine": "godot", "mode": "design"
        })
        resp = await client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_freeze_and_resume_project(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post("/api/projects", json={
            "name": "freezetest", "display_name": "Freeze Test", "engine": "unity", "mode": "prototype"
        })
        pid = create.json()["id"]
        freeze = await client.post(f"/api/projects/{pid}/freeze")
        assert freeze.json()["status"] == "frozen"
        resume = await client.post(f"/api/projects/{pid}/resume")
        assert resume.json()["status"] == "active"


@pytest.mark.asyncio
async def test_startover_project(setup_db):
    """Test that startover resets project status to active"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post("/api/projects", json={
            "name": "startovertest", "display_name": "Startover Test", "engine": "godot", "mode": "development"
        })
        pid = create.json()["id"]
        # Freeze the project first
        await client.post(f"/api/projects/{pid}/freeze")
        # Now startover should reset it to active
        result = await client.post(f"/api/projects/{pid}/startover")
        assert result.json()["status"] == "active"
