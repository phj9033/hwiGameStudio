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
async def setup_db(db_path, monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    projects_dir = str(tmp_path / "projects")
    os.makedirs(projects_dir, exist_ok=True)
    monkeypatch.setattr("backend.config.PROJECTS_DIR", projects_dir)
    await init_db(db_path)
    yield db_path


@pytest_asyncio.fixture
async def setup_test_data(setup_db):
    """Create test data: projects, tickets, agents with token/cost data"""
    from backend.database import get_db
    import backend.config

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # Create two projects
        proj1 = await client.post("/api/projects", json={
            "name": "project1",
            "display_name": "Project 1",
            "engine": "godot"
        })
        proj1_id = proj1.json()["id"]

        proj2 = await client.post("/api/projects", json={
            "name": "project2",
            "display_name": "Project 2",
            "engine": "unity"
        })
        proj2_id = proj2.json()["id"]

        # Create tickets and agent_sessions directly in database
        async with get_db(backend.config.DATABASE_PATH) as db:
            # Create ticket 1
            cursor = await db.execute(
                "INSERT INTO tickets (project_id, title, description, status) VALUES (?, ?, ?, ?)",
                (proj1_id, "Ticket 1", "", "assigned")
            )
            ticket1_id = cursor.lastrowid

            # Create agent session 1
            cursor = await db.execute(
                """INSERT INTO agent_sessions
                   (ticket_id, agent_name, cli_provider, instruction, input_tokens, output_tokens, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ticket1_id, "coder", "claude", "Write code", 1000, 2000, "completed")
            )
            agent1_id = cursor.lastrowid

            # Create ticket 2
            cursor = await db.execute(
                "INSERT INTO tickets (project_id, title, description, status) VALUES (?, ?, ?, ?)",
                (proj2_id, "Ticket 2", "", "assigned")
            )
            ticket2_id = cursor.lastrowid

            # Create agent session 2
            cursor = await db.execute(
                """INSERT INTO agent_sessions
                   (ticket_id, agent_name, cli_provider, instruction, input_tokens, output_tokens, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (ticket2_id, "designer", "codex", "Design feature", 500, 1500, "completed")
            )
            agent2_id = cursor.lastrowid

            await db.commit()

        return {
            "proj1_id": proj1_id,
            "proj2_id": proj2_id,
            "agent1_id": agent1_id,
            "agent2_id": agent2_id
        }


@pytest.mark.asyncio
async def test_usage_summary(setup_test_data):
    """Test total token/cost summary across all"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        resp = await client.get("/api/usage/summary")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_input_tokens"] == 1500
    assert data["total_output_tokens"] == 3500


@pytest.mark.asyncio
async def test_usage_by_project(setup_test_data):
    """Test usage grouped by project"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        resp = await client.get("/api/usage/by-project")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Find project1 and project2 data
    proj1_data = next(p for p in data if p["project_name"] == "project1")
    proj2_data = next(p for p in data if p["project_name"] == "project2")

    assert proj1_data["total_input_tokens"] == 1000
    assert proj1_data["total_output_tokens"] == 2000

    assert proj2_data["total_input_tokens"] == 500
    assert proj2_data["total_output_tokens"] == 1500


@pytest.mark.asyncio
async def test_usage_by_agent(setup_test_data):
    """Test usage grouped by agent_name"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        resp = await client.get("/api/usage/by-agent")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Find coder and designer data
    coder_data = next(a for a in data if a["agent_name"] == "coder")
    designer_data = next(a for a in data if a["agent_name"] == "designer")

    assert coder_data["total_input_tokens"] == 1000
    assert coder_data["total_output_tokens"] == 2000

    assert designer_data["total_input_tokens"] == 500
    assert designer_data["total_output_tokens"] == 1500


@pytest.mark.asyncio
async def test_providers_list(setup_db):
    """Test providers list returns seeded data"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        resp = await client.get("/api/providers")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2

    claude = next(p for p in data if p["name"] == "claude")
    assert claude["command"] == "claude --print"
    assert claude["api_key_env"] == "ANTHROPIC_API_KEY"
    assert claude["enabled"] is True


@pytest.mark.asyncio
async def test_provider_update(setup_db):
    """Test updating a provider"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # Get providers list
        list_resp = await client.get("/api/providers")
        providers = list_resp.json()
        claude = next(p for p in providers if p["name"] == "claude")

        # Update provider
        update_resp = await client.put(f"/api/providers/{claude['id']}", json={
            "enabled": False
        })

        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["enabled"] is False
        assert updated["command"] == "claude --print"


@pytest.mark.asyncio
async def test_runs_get_agent_detail(setup_test_data):
    """Test runs endpoint returns agent detail"""
    data = setup_test_data
    agent_id = data["agent1_id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        resp = await client.get(f"/api/runs/{agent_id}")

    assert resp.status_code == 200
    agent = resp.json()
    assert agent["id"] == agent_id
    assert agent["agent_name"] == "coder"
    assert agent["input_tokens"] == 1000
    assert agent["output_tokens"] == 2000


@pytest.mark.asyncio
async def test_runs_get_result_file(setup_test_data):
    """Test runs result file endpoint"""
    data = setup_test_data
    agent_id = data["agent1_id"]

    # First, update agent with result_path inside PROJECTS_DIR
    from backend.config import PROJECTS_DIR
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # Create a result file inside PROJECTS_DIR
        result_path = os.path.join(PROJECTS_DIR, "result.txt")
        with open(result_path, 'w') as f:
            f.write("Test result content")

        # Update agent with result_path
        await client.put(f"/api/agents/runs/{agent_id}", json={
            "result_path": result_path
        })

        # Get result file
        result_resp = await client.get(f"/api/runs/{agent_id}/result")
        assert result_resp.status_code == 200
        assert result_resp.text == "Test result content"


@pytest.mark.asyncio
async def test_runs_get_result_file_not_found(setup_test_data):
    """Test runs result file endpoint when file doesn't exist"""
    data = setup_test_data
    agent_id = data["agent1_id"]

    from backend.config import PROJECTS_DIR
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # Update agent with non-existent result_path inside PROJECTS_DIR
        await client.put(f"/api/agents/runs/{agent_id}", json={
            "result_path": os.path.join(PROJECTS_DIR, "nonexistent.txt")
        })

        # Get result file should return 404
        result_resp = await client.get(f"/api/runs/{agent_id}/result")
        assert result_resp.status_code == 404
