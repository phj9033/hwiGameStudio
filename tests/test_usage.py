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
async def setup_test_data(setup_db):
    """Create test data: projects, tickets, agents with token/cost data"""
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

        # Create tickets with agents
        ticket1 = await client.post("/api/tickets", json={
            "project_id": proj1_id,
            "title": "Ticket 1",
            "steps": [
                {
                    "step_order": 1,
                    "agents": [
                        {
                            "agent_name": "coder",
                            "cli_provider": "claude",
                            "instruction": "Write code"
                        }
                    ]
                }
            ]
        })
        assert ticket1.status_code == 200, f"Ticket creation failed: {ticket1.status_code} - {ticket1.text}"
        t1_data = ticket1.json()
        agent1_id = t1_data["steps"][0]["agents"][0]["id"]

        ticket2 = await client.post("/api/tickets", json={
            "project_id": proj2_id,
            "title": "Ticket 2",
            "steps": [
                {
                    "step_order": 1,
                    "agents": [
                        {
                            "agent_name": "designer",
                            "cli_provider": "codex",
                            "instruction": "Design feature"
                        }
                    ]
                }
            ]
        })
        t2_data = ticket2.json()
        agent2_id = t2_data["steps"][0]["agents"][0]["id"]

        # Update agents with token/cost data
        await client.put(f"/api/agents/runs/{agent1_id}", json={
            "input_tokens": 1000,
            "output_tokens": 2000,
            "estimated_cost": 0.15,
            "status": "completed"
        })

        await client.put(f"/api/agents/runs/{agent2_id}", json={
            "input_tokens": 500,
            "output_tokens": 1500,
            "estimated_cost": 0.05,
            "status": "completed"
        })

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
    assert abs(data["total_cost"] - 0.20) < 0.001


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
    assert abs(proj1_data["total_cost"] - 0.15) < 0.001

    assert proj2_data["total_input_tokens"] == 500
    assert proj2_data["total_output_tokens"] == 1500
    assert abs(proj2_data["total_cost"] - 0.05) < 0.001


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
    assert abs(coder_data["total_cost"] - 0.15) < 0.001

    assert designer_data["total_input_tokens"] == 500
    assert designer_data["total_output_tokens"] == 1500
    assert abs(designer_data["total_cost"] - 0.05) < 0.001


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
async def test_cost_rates_list(setup_db):
    """Test cost rates list returns seeded data"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        resp = await client.get("/api/providers/rates")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2

    opus = next(r for r in data if r["provider"] == "claude" and r["model"] == "opus-4")
    assert opus["input_rate"] == 0.015
    assert opus["output_rate"] == 0.075


@pytest.mark.asyncio
async def test_cost_rate_update(setup_db):
    """Test updating a cost rate"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # Get rates list
        list_resp = await client.get("/api/providers/rates")
        rates = list_resp.json()
        opus = next(r for r in rates if r["provider"] == "claude" and r["model"] == "opus-4")

        # Update rate
        update_resp = await client.put(f"/api/providers/rates/{opus['id']}", json={
            "input_rate": 0.020
        })

        assert update_resp.status_code == 200
        updated = update_resp.json()
        assert updated["input_rate"] == 0.020
        assert updated["output_rate"] == 0.075


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

    # First, update agent with result_path
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # Create a temporary result file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Test result content")
            result_path = f.name

        try:
            # Update agent with result_path
            await client.put(f"/api/agents/runs/{agent_id}", json={
                "result_path": result_path
            })

            # Get result file
            result_resp = await client.get(f"/api/runs/{agent_id}/result")
            assert result_resp.status_code == 200
            assert result_resp.text == "Test result content"
        finally:
            if os.path.exists(result_path):
                os.unlink(result_path)


@pytest.mark.asyncio
async def test_runs_get_result_file_not_found(setup_test_data):
    """Test runs result file endpoint when file doesn't exist"""
    data = setup_test_data
    agent_id = data["agent1_id"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        # Update agent with non-existent result_path
        await client.put(f"/api/agents/runs/{agent_id}", json={
            "result_path": "/nonexistent/file.txt"
        })

        # Get result file should return 404
        result_resp = await client.get(f"/api/runs/{agent_id}/result")
        assert result_resp.status_code == 404
