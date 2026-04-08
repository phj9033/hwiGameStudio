"""
Full workflow integration test:
1. Create project
2. Create ticket with pipeline
3. Verify ticket structure
4. Create document
5. Update document (triggers diff)
6. Verify usage endpoints
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
import tempfile, os

@pytest_asyncio.fixture
async def setup_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "integration.db")
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    agents_dir = str(tmp_path / "agents")
    os.makedirs(agents_dir)
    with open(os.path.join(agents_dir, "test_agent.md"), "w") as f:
        f.write("# Test Agent\nYou are a test agent.")
    monkeypatch.setattr("backend.config.AGENTS_DIR", agents_dir)
    await init_db(db_path)
    yield

@pytest.mark.asyncio
async def test_full_workflow(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        health = await client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        # 2. Create project
        project = await client.post("/api/projects", json={
            "name": "integration-test",
            "display_name": "Integration Test Game",
            "engine": "godot",
            "mode": "development"
        })
        assert project.status_code == 200
        project_id = project.json()["id"]

        # 3. Create ticket with steps
        ticket = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Build player movement",
            "description": "Implement WASD movement",
            "steps": [
                {
                    "step_order": 1,
                    "agents": [
                        {"agent_name": "test_agent", "cli_provider": "claude", "instruction": "Design movement system"}
                    ]
                },
                {
                    "step_order": 2,
                    "agents": [
                        {"agent_name": "test_agent", "cli_provider": "codex", "instruction": "Implement movement"}
                    ]
                }
            ]
        })
        assert ticket.status_code == 200
        ticket_data = ticket.json()
        assert len(ticket_data["steps"]) == 2
        assert len(ticket_data["steps"][0]["agents"]) == 1

        # 4. Verify ticket appears in list
        tickets_list = await client.get(f"/api/tickets/?project_id={project_id}")
        assert tickets_list.status_code == 200
        assert tickets_list.json()["total"] >= 1

        # 5. Get ticket detail
        ticket_detail = await client.get(f"/api/tickets/{ticket_data['id']}")
        assert ticket_detail.status_code == 200

        # 6. Create document
        doc = await client.post("/api/documents", json={
            "project_id": project_id,
            "file_path": "docs/gdd.md",
            "content": "# Game Design\nOriginal content",
            "updated_by": "developer"
        })
        assert doc.status_code == 200
        doc_id = doc.json()["id"]

        # 7. Update document (triggers diff save)
        updated_doc = await client.put(f"/api/documents/{doc_id}", json={
            "content": "# Game Design\nUpdated content with new features",
            "updated_by": "designer"
        })
        assert updated_doc.status_code == 200
        assert "Original content" in updated_doc.json()["previous_content"]

        # 8. Verify agents list
        agents = await client.get("/api/agents")
        assert agents.status_code == 200
        assert len(agents.json()) >= 1

        # 9. Check providers
        providers = await client.get("/api/providers")
        assert providers.status_code == 200
        assert len(providers.json()) >= 2  # claude and codex seeded

        # 10. Check usage summary
        usage = await client.get("/api/usage/summary")
        assert usage.status_code == 200

        # 11. Freeze and resume project
        freeze = await client.post(f"/api/projects/{project_id}/freeze")
        assert freeze.json()["status"] == "frozen"
        resume = await client.post(f"/api/projects/{project_id}/resume")
        assert resume.json()["status"] == "active"
