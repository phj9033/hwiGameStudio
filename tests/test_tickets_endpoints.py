import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
import tempfile
import os
from unittest.mock import AsyncMock, patch


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

    # Mock agents and projects dirs
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "test_agent.md").write_text("# Test Agent")

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
async def test_run_ticket_endpoint(project_id):
    """Test /run endpoint starts ticket execution"""
    transport = ASGITransport(app=app)

    # Mock PipelineExecutor
    mock_result = {
        "stdout": "Success",
        "stderr": "",
        "return_code": 0,
        "input_tokens": 1000,
        "output_tokens": 500,
        "pid": 12345
    }

    with patch('backend.services.pipeline_executor.CLIRunner') as MockCLIRunner:
        mock_runner = MockCLIRunner.return_value
        mock_runner.run = AsyncMock(return_value=mock_result)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create ticket
            create_resp = await client.post("/api/tickets/", json={
                "project_id": project_id,
                "title": "Test ticket",
                "steps": [
                    {
                        "step_order": 1,
                        "agents": [
                            {"agent_name": "test_agent", "cli_provider": "claude", "instruction": "Test"}
                        ]
                    }
                ]
            })
            ticket_id = create_resp.json()["id"]

            # Run ticket
            run_resp = await client.post(f"/api/tickets/{ticket_id}/run")
            assert run_resp.status_code == 200
            assert run_resp.json()["message"] == "Ticket execution started"

            # Wait a bit for background task
            import asyncio
            await asyncio.sleep(0.1)

            # Check ticket status (should be completed or running depending on timing)
            get_resp = await client.get(f"/api/tickets/{ticket_id}")
            assert get_resp.status_code == 200
            status = get_resp.json()["status"]
            assert status in ("running", "completed")


@pytest.mark.asyncio
async def test_run_ticket_invalid_status(project_id):
    """Test /run endpoint rejects invalid status"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create and immediately run a ticket
        create_resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Test ticket",
            "steps": [{"step_order": 1, "agents": [
                {"agent_name": "test_agent", "cli_provider": "claude", "instruction": "Test"}
            ]}]
        })
        ticket_id = create_resp.json()["id"]

        # Manually set status to running
        from backend.database import get_db
        import backend.config
        async with get_db(backend.config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                ("running", ticket_id)
            )
            await db.commit()

        # Try to run again - should fail
        run_resp = await client.post(f"/api/tickets/{ticket_id}/run")
        assert run_resp.status_code == 400
        assert "Cannot run ticket" in run_resp.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_ticket_endpoint(project_id):
    """Test /cancel endpoint"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create ticket
        create_resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Test ticket",
            "steps": [{"step_order": 1, "agents": [
                {"agent_name": "test_agent", "cli_provider": "claude", "instruction": "Test"}
            ]}]
        })
        ticket_id = create_resp.json()["id"]

        # Set to running with a fake PID
        from backend.database import get_db
        import backend.config
        async with get_db(backend.config.DATABASE_PATH) as db:
            await db.execute(
                "UPDATE tickets SET status = ? WHERE id = ?",
                ("running", ticket_id)
            )
            await db.execute(
                """UPDATE step_agents SET status = ?, pid = ?
                   WHERE step_id IN (SELECT id FROM ticket_steps WHERE ticket_id = ?)""",
                ("running", 99999, ticket_id)
            )
            await db.commit()

        # Cancel with mocked os.kill
        with patch('os.kill'):
            cancel_resp = await client.post(f"/api/tickets/{ticket_id}/cancel")
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["message"] == "Ticket cancelled"

        # Verify status
        get_resp = await client.get(f"/api/tickets/{ticket_id}")
        assert get_resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_retry_ticket_endpoint(project_id):
    """Test /retry endpoint"""
    transport = ASGITransport(app=app)

    mock_result = {
        "stdout": "Success",
        "stderr": "",
        "return_code": 0,
        "input_tokens": 1000,
        "output_tokens": 500,
        "pid": 12345
    }

    with patch('backend.services.pipeline_executor.CLIRunner') as MockCLIRunner:
        mock_runner = MockCLIRunner.return_value
        mock_runner.run = AsyncMock(return_value=mock_result)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create ticket
            create_resp = await client.post("/api/tickets/", json={
                "project_id": project_id,
                "title": "Test ticket",
                "steps": [{"step_order": 1, "agents": [
                    {"agent_name": "test_agent", "cli_provider": "claude", "instruction": "Test"}
                ]}]
            })
            ticket_id = create_resp.json()["id"]

            # Set to failed
            from backend.database import get_db
            import backend.config
            async with get_db(backend.config.DATABASE_PATH) as db:
                await db.execute(
                    "UPDATE tickets SET status = ? WHERE id = ?",
                    ("failed", ticket_id)
                )
                await db.execute(
                    "UPDATE ticket_steps SET status = ? WHERE ticket_id = ?",
                    ("failed", ticket_id)
                )
                await db.execute(
                    """UPDATE step_agents SET status = ?
                       WHERE step_id IN (SELECT id FROM ticket_steps WHERE ticket_id = ?)""",
                    ("failed", ticket_id)
                )
                await db.commit()

            # Retry
            retry_resp = await client.post(f"/api/tickets/{ticket_id}/retry")
            assert retry_resp.status_code == 200
            assert retry_resp.json()["message"] == "Ticket retry started"

            # Wait for background task
            import asyncio
            await asyncio.sleep(0.1)

            # Check status
            get_resp = await client.get(f"/api/tickets/{ticket_id}")
            status = get_resp.json()["status"]
            assert status in ("assigned", "running", "completed")


@pytest.mark.asyncio
async def test_run_nonexistent_ticket(setup_db):
    """Test running nonexistent ticket returns 404"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tickets/99999/run")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cancel_nonrunning_ticket(project_id):
    """Test cancelling non-running ticket returns 400"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create ticket with 'open' status
        create_resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Test ticket",
            "steps": []
        })
        ticket_id = create_resp.json()["id"]

        # Try to cancel
        cancel_resp = await client.post(f"/api/tickets/{ticket_id}/cancel")
        assert cancel_resp.status_code == 400
        assert "Cannot cancel" in cancel_resp.json()["detail"]


@pytest.mark.asyncio
async def test_retry_nonfailed_ticket(project_id):
    """Test retrying non-failed ticket returns 400"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create ticket with 'open' status
        create_resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Test ticket",
            "steps": []
        })
        ticket_id = create_resp.json()["id"]

        # Try to retry
        retry_resp = await client.post(f"/api/tickets/{ticket_id}/retry")
        assert retry_resp.status_code == 400
        assert "Cannot retry" in retry_resp.json()["detail"]
