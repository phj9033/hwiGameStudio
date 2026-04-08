import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
import os


@pytest_asyncio.fixture(autouse=True)
async def setup(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    await init_db(db_path)
    agents_dir = str(tmp_path / "agents")
    os.makedirs(agents_dir)
    with open(os.path.join(agents_dir, "test_agent.md"), "w") as f:
        f.write("# Test Agent\nYou are a test agent.")
    monkeypatch.setattr("backend.config.AGENTS_DIR", agents_dir)
    yield


@pytest.mark.asyncio
async def test_list_agents():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert any(a["name"] == "test_agent" for a in agents)


@pytest.mark.asyncio
async def test_get_agent_content():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents/test_agent")
    assert resp.status_code == 200
    assert "Test Agent" in resp.json()["content"]


@pytest.mark.asyncio
async def test_update_agent_content():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/api/agents/test_agent", json={"content": "# Updated Agent"})
    assert resp.status_code == 200
    assert "Updated Agent" in resp.json()["content"]


@pytest.mark.asyncio
async def test_get_agent_runs():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents/test_agent/runs")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
