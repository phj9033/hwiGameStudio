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
async def test_create_ticket_with_steps(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Build combat system",
            "description": "Implement full combat",
            "steps": [
                {
                    "step_order": 1,
                    "agents": [
                        {"agent_name": "sr_game_designer", "cli_provider": "claude", "instruction": "Design combat"},
                        {"agent_name": "market_analyst", "cli_provider": "claude", "instruction": "Analyze competitors"}
                    ]
                },
                {
                    "step_order": 2,
                    "agents": [
                        {"agent_name": "mechanics_developer", "cli_provider": "codex", "instruction": "Implement combat logic"}
                    ]
                }
            ]
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Build combat system"
    assert data["status"] in ["open", "assigned"]


@pytest.mark.asyncio
async def test_list_tickets_by_project(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/tickets/", json={
            "project_id": project_id, "title": "Task 1", "steps": []
        })
        resp = await client.get(f"/api/tickets/?project_id={project_id}")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_get_ticket_detail(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post("/api/tickets/", json={
            "project_id": project_id, "title": "Detail test",
            "steps": [{"step_order": 1, "agents": [
                {"agent_name": "qa_agent", "cli_provider": "claude", "instruction": "Test"}
            ]}]
        })
        ticket_id = create.json()["id"]
        resp = await client.get(f"/api/tickets/{ticket_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps"]) == 1
    assert len(data["steps"][0]["agents"]) == 1


@pytest.mark.asyncio
async def test_update_ticket(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post("/api/tickets/", json={
            "project_id": project_id, "title": "Original title", "steps": []
        })
        ticket_id = create.json()["id"]
        resp = await client.put(f"/api/tickets/{ticket_id}", json={
            "title": "Updated title",
            "description": "Updated description"
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Updated title"
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_create_ticket_without_steps(project_id):
    """Test creating a ticket without steps should have status 'open'"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "No steps ticket",
            "steps": []
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "open"


@pytest.mark.asyncio
async def test_list_all_tickets(project_id):
    """Test listing tickets without project filter"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/tickets/", json={
            "project_id": project_id, "title": "Task A", "steps": []
        })
        resp = await client.get("/api/tickets/")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1
