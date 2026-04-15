import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db, get_db
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
async def setup_db(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "designer.md").write_text("# Designer Agent")
    (agents_dir / "artist.md").write_text("# Artist Agent")

    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    (projects_dir / "test-proj").mkdir()

    monkeypatch.setattr("backend.config.AGENTS_DIR", str(agents_dir))
    monkeypatch.setattr("backend.config.PROJECTS_DIR", str(projects_dir))

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
async def test_create_ticket_with_sessions_status_assigned(project_id, setup_db):
    """Create ticket with sessions -> status 'assigned', sessions returned"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Test ticket with sessions",
            "sessions": [
                {
                    "agent_name": "designer",
                    "cli_provider": "claude",
                    "instruction": "Design the UI",
                    "depends_on": [],
                    "produces": ["ui_spec.md"]
                },
                {
                    "agent_name": "artist",
                    "cli_provider": "claude",
                    "instruction": "Create art assets",
                    "depends_on": ["ui_spec.md"],
                    "produces": ["art_assets.zip"]
                }
            ]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "assigned"
        assert len(data["sessions"]) == 2

        # Verify session fields
        s0 = data["sessions"][0]
        assert s0["agent_name"] == "designer"
        assert s0["instruction"] == "Design the UI"
        assert s0["depends_on"] == []
        assert s0["produces"] == ["ui_spec.md"]
        assert s0["status"] == "pending"

        s1 = data["sessions"][1]
        assert s1["agent_name"] == "artist"
        assert s1["depends_on"] == ["ui_spec.md"]
        assert s1["produces"] == ["art_assets.zip"]


@pytest.mark.asyncio
async def test_create_ticket_with_cyclic_dependency_returns_400(project_id, setup_db):
    """Create ticket with cyclic dependency -> 400 error"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Cycle: A depends on B's output, B depends on A's output
        resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Cyclic ticket",
            "sessions": [
                {
                    "agent_name": "designer",
                    "cli_provider": "claude",
                    "instruction": "Design",
                    "depends_on": ["art.png"],
                    "produces": ["spec.md"]
                },
                {
                    "agent_name": "artist",
                    "cli_provider": "claude",
                    "instruction": "Draw",
                    "depends_on": ["spec.md"],
                    "produces": ["art.png"]
                }
            ]
        })
        assert resp.status_code == 400
        assert "yclic" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_ticket_with_unresolved_dependency_returns_400(project_id, setup_db):
    """Create ticket with unresolved dependency -> 400 error"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Unresolved dep ticket",
            "sessions": [
                {
                    "agent_name": "designer",
                    "cli_provider": "claude",
                    "instruction": "Design",
                    "depends_on": ["nonexistent_file.md"],
                    "produces": ["spec.md"]
                }
            ]
        })
        assert resp.status_code == 400
        assert "Unresolved" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_ticket_without_sessions_status_open(project_id, setup_db):
    """Create ticket without sessions -> status 'open'"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Empty ticket"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "open"
        assert data["sessions"] == []


@pytest.mark.asyncio
async def test_get_ticket_detail_includes_sessions(project_id, setup_db):
    """Get ticket detail -> sessions included with parsed JSON fields"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create
        create_resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Detail ticket",
            "sessions": [
                {
                    "agent_name": "designer",
                    "cli_provider": "claude",
                    "instruction": "Design the game",
                    "depends_on": [],
                    "produces": ["design.md"]
                }
            ]
        })
        ticket_id = create_resp.json()["id"]

        # Get
        get_resp = await client.get(f"/api/tickets/{ticket_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert len(data["sessions"]) == 1

        session = data["sessions"][0]
        assert session["agent_name"] == "designer"
        assert session["instruction"] == "Design the game"
        assert session["depends_on"] == []
        assert session["produces"] == ["design.md"]
        assert session["ticket_id"] == ticket_id
        assert session["status"] == "pending"


@pytest.mark.asyncio
async def test_delete_ticket_cascades_to_sessions(project_id, setup_db):
    """Delete ticket -> cascades to sessions"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create ticket with sessions
        create_resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Delete me",
            "sessions": [
                {
                    "agent_name": "designer",
                    "cli_provider": "claude",
                    "instruction": "Work",
                    "depends_on": [],
                    "produces": []
                }
            ]
        })
        ticket_id = create_resp.json()["id"]

        # Delete
        del_resp = await client.delete(f"/api/tickets/{ticket_id}")
        assert del_resp.status_code == 200

        # Verify ticket is gone
        get_resp = await client.get(f"/api/tickets/{ticket_id}")
        assert get_resp.status_code == 404

        # Verify sessions are gone
        import backend.config
        async with get_db(backend.config.DATABASE_PATH) as db:
            rows = await db.execute(
                "SELECT COUNT(*) as cnt FROM agent_sessions WHERE ticket_id = ?",
                (ticket_id,)
            )
            row = await rows.fetchone()
            assert row["cnt"] == 0
