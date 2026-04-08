import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
from unittest.mock import patch, AsyncMock
import tempfile
import os
import json


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
async def test_decompose_endpoint(project_id):
    """Test the /api/tickets/decompose endpoint"""
    mock_response = {
        "stdout": json.dumps({
            "tickets": [
                {
                    "title": "Design combat",
                    "description": "Create design doc",
                    "steps": [
                        {
                            "step_order": 1,
                            "agents": [
                                {
                                    "agent_name": "sr_game_designer",
                                    "cli_provider": "claude",
                                    "instruction": "Design mechanics"
                                }
                            ]
                        }
                    ]
                }
            ]
        }),
        "stderr": "",
        "return_code": 0,
        "input_tokens": 100,
        "output_tokens": 200,
        "pid": 12345
    }

    with patch('backend.services.cli_runner.CLIRunner.run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_response

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/tickets/decompose", json={
                "description": "Build a combat system",
                "agent_list": ["sr_game_designer", "mechanics_developer"]
            })

    assert resp.status_code == 200
    data = resp.json()
    assert "tickets" in data
    assert len(data["tickets"]) == 1
    assert data["tickets"][0]["title"] == "Design combat"


@pytest.mark.asyncio
async def test_from_diff_endpoint(project_id):
    """Test the /api/tickets/from-diff endpoint"""
    mock_response = {
        "stdout": json.dumps({
            "tickets": [
                {
                    "title": "Implement feature",
                    "description": "Based on diff",
                    "steps": [
                        {
                            "step_order": 1,
                            "agents": [
                                {
                                    "agent_name": "mechanics_developer",
                                    "cli_provider": "codex",
                                    "instruction": "Implement"
                                }
                            ]
                        }
                    ]
                }
            ]
        }),
        "stderr": "",
        "return_code": 0,
        "input_tokens": 150,
        "output_tokens": 250,
        "pid": 12346
    }

    with patch('backend.services.cli_runner.CLIRunner.run', new_callable=AsyncMock) as mock_run:
        mock_run.return_value = mock_response

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/tickets/from-diff", json={
                "file_path": "design/combat.md",
                "diff_content": "+New feature\n-Old feature",
                "agent_list": ["mechanics_developer"]
            })

    assert resp.status_code == 200
    data = resp.json()
    assert "tickets" in data
    assert len(data["tickets"]) == 1
    assert data["tickets"][0]["title"] == "Implement feature"


@pytest.mark.asyncio
async def test_auto_assign_endpoint(project_id):
    """Test the /api/tickets/{id}/auto-assign endpoint"""
    # Create a ticket first
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_resp = await client.post("/api/tickets/", json={
            "project_id": project_id,
            "title": "Build feature",
            "description": "Need to build a combat system",
            "steps": []
        })
        ticket_id = create_resp.json()["id"]

        mock_response = {
            "stdout": json.dumps({
                "tickets": [
                    {
                        "title": "Recommended ticket",
                        "description": "AI recommendation",
                        "steps": [
                            {
                                "step_order": 1,
                                "agents": [
                                    {
                                        "agent_name": "sr_game_designer",
                                        "cli_provider": "claude",
                                        "instruction": "Design"
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }),
            "stderr": "",
            "return_code": 0,
            "input_tokens": 120,
            "output_tokens": 180,
            "pid": 12347
        }

        with patch('backend.services.cli_runner.CLIRunner.run', new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_response

            resp = await client.post(f"/api/tickets/{ticket_id}/auto-assign")

    assert resp.status_code == 200
    data = resp.json()
    assert "tickets" in data
