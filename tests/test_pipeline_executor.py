import pytest
import pytest_asyncio
from backend.services.pipeline_executor import PipelineExecutor
from backend.database import init_db, get_db
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch
import signal


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
async def sample_ticket(setup_db):
    """Create a sample ticket with steps and agents"""
    async with get_db(setup_db) as db:
        # Create project
        proj_cursor = await db.execute(
            """INSERT INTO projects (name, display_name, engine, mode)
               VALUES (?, ?, ?, ?)""",
            ("test-proj", "Test Project", "godot", "development")
        )
        project_id = proj_cursor.lastrowid

        # Create ticket
        ticket_cursor = await db.execute(
            """INSERT INTO tickets (project_id, title, description, status)
               VALUES (?, ?, ?, ?)""",
            (project_id, "Test Ticket", "Test description", "assigned")
        )
        ticket_id = ticket_cursor.lastrowid

        # Create step 1 with 2 agents
        step1_cursor = await db.execute(
            """INSERT INTO ticket_steps (ticket_id, step_order, status)
               VALUES (?, ?, ?)""",
            (ticket_id, 1, "pending")
        )
        step1_id = step1_cursor.lastrowid

        await db.execute(
            """INSERT INTO step_agents (step_id, agent_name, cli_provider, instruction, status)
               VALUES (?, ?, ?, ?, ?)""",
            (step1_id, "agent1", "claude", "Do task 1", "pending")
        )
        await db.execute(
            """INSERT INTO step_agents (step_id, agent_name, cli_provider, instruction, status)
               VALUES (?, ?, ?, ?, ?)""",
            (step1_id, "agent2", "codex", "Do task 2", "pending")
        )

        # Create step 2 with 1 agent
        step2_cursor = await db.execute(
            """INSERT INTO ticket_steps (ticket_id, step_order, status)
               VALUES (?, ?, ?)""",
            (ticket_id, 2, "pending")
        )
        step2_id = step2_cursor.lastrowid

        await db.execute(
            """INSERT INTO step_agents (step_id, agent_name, cli_provider, instruction, status)
               VALUES (?, ?, ?, ?, ?)""",
            (step2_id, "agent3", "claude", "Do task 3", "pending")
        )

        await db.commit()

        return ticket_id


@pytest.mark.asyncio
async def test_run_ticket_success(sample_ticket, setup_db, monkeypatch, tmp_path):
    """Test successful ticket execution"""
    # Mock the agents directory
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "agent1.md").write_text("# Agent 1 instructions")
    (agents_dir / "agent2.md").write_text("# Agent 2 instructions")
    (agents_dir / "agent3.md").write_text("# Agent 3 instructions")

    monkeypatch.setattr("backend.config.AGENTS_DIR", str(agents_dir))
    monkeypatch.setattr("backend.config.PROJECTS_DIR", str(tmp_path))

    # Mock CLIRunner
    mock_result = {
        "stdout": "Success! Tokens: input=1000, output=500",
        "stderr": "",
        "return_code": 0,
        "input_tokens": 1000,
        "output_tokens": 500,
        "pid": 12345
    }

    with patch('backend.services.pipeline_executor.CLIRunner') as MockCLIRunner:
        mock_runner = MockCLIRunner.return_value
        mock_runner.run = AsyncMock(return_value=mock_result)

        executor = PipelineExecutor()
        await executor.run_ticket(sample_ticket)

    # Verify ticket status
    async with get_db(setup_db) as db:
        ticket_row = await db.execute("SELECT status FROM tickets WHERE id = ?", (sample_ticket,))
        ticket = await ticket_row.fetchone()
        assert ticket["status"] == "completed"

        # Verify all steps completed
        steps_rows = await db.execute(
            "SELECT status FROM ticket_steps WHERE ticket_id = ? ORDER BY step_order",
            (sample_ticket,)
        )
        steps = await steps_rows.fetchall()
        assert all(step["status"] == "completed" for step in steps)

        # Verify all agents completed
        agents_rows = await db.execute(
            """SELECT sa.status, sa.input_tokens, sa.output_tokens
               FROM step_agents sa
               JOIN ticket_steps ts ON sa.step_id = ts.id
               WHERE ts.ticket_id = ?""",
            (sample_ticket,)
        )
        agents = await agents_rows.fetchall()
        assert all(agent["status"] == "completed" for agent in agents)
        assert all(agent["input_tokens"] == 1000 for agent in agents)
        assert all(agent["output_tokens"] == 500 for agent in agents)


@pytest.mark.asyncio
async def test_run_ticket_agent_failure(sample_ticket, setup_db, monkeypatch, tmp_path):
    """Test ticket execution when an agent fails"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "agent1.md").write_text("# Agent 1")
    (agents_dir / "agent2.md").write_text("# Agent 2")

    monkeypatch.setattr("backend.config.AGENTS_DIR", str(agents_dir))
    monkeypatch.setattr("backend.config.PROJECTS_DIR", str(tmp_path))

    # Mock CLIRunner - first agent fails
    mock_failure = {
        "stdout": "",
        "stderr": "Error occurred",
        "return_code": 1,
        "input_tokens": 100,
        "output_tokens": 50,
        "pid": 12346
    }

    with patch('backend.services.pipeline_executor.CLIRunner') as MockCLIRunner:
        mock_runner = MockCLIRunner.return_value
        mock_runner.run = AsyncMock(return_value=mock_failure)

        executor = PipelineExecutor()
        await executor.run_ticket(sample_ticket)

    # Verify ticket and step marked as failed
    async with get_db(setup_db) as db:
        ticket_row = await db.execute("SELECT status FROM tickets WHERE id = ?", (sample_ticket,))
        ticket = await ticket_row.fetchone()
        assert ticket["status"] == "failed"

        # First step should be failed
        step_row = await db.execute(
            "SELECT status FROM ticket_steps WHERE ticket_id = ? AND step_order = 1",
            (sample_ticket,)
        )
        step = await step_row.fetchone()
        assert step["status"] == "failed"


@pytest.mark.asyncio
async def test_cancel_ticket(sample_ticket, setup_db, monkeypatch, tmp_path):
    """Test cancelling a running ticket"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "agent1.md").write_text("# Agent 1")

    monkeypatch.setattr("backend.config.AGENTS_DIR", str(agents_dir))
    monkeypatch.setattr("backend.config.PROJECTS_DIR", str(tmp_path))

    # Set up a "running" agent with a PID
    async with get_db(setup_db) as db:
        await db.execute(
            """UPDATE step_agents SET status = ?, pid = ?, started_at = CURRENT_TIMESTAMP
               WHERE step_id IN (SELECT id FROM ticket_steps WHERE ticket_id = ?)""",
            ("running", 99999, sample_ticket)
        )
        await db.execute(
            "UPDATE tickets SET status = ? WHERE id = ?",
            ("running", sample_ticket)
        )
        await db.commit()

    # Mock os.kill to prevent actual signal sending
    with patch('os.kill') as mock_kill:
        executor = PipelineExecutor()
        await executor.cancel_ticket(sample_ticket)

        # Verify os.kill was called
        assert mock_kill.called

    # Verify statuses updated to cancelled
    async with get_db(setup_db) as db:
        ticket_row = await db.execute("SELECT status FROM tickets WHERE id = ?", (sample_ticket,))
        ticket = await ticket_row.fetchone()
        assert ticket["status"] == "cancelled"

        agents_rows = await db.execute(
            """SELECT sa.status FROM step_agents sa
               JOIN ticket_steps ts ON sa.step_id = ts.id
               WHERE ts.ticket_id = ?""",
            (sample_ticket,)
        )
        agents = await agents_rows.fetchall()
        assert all(agent["status"] == "cancelled" for agent in agents)


@pytest.mark.asyncio
async def test_retry_ticket(sample_ticket, setup_db, monkeypatch, tmp_path):
    """Test retrying a failed ticket"""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "agent1.md").write_text("# Agent 1")
    (agents_dir / "agent2.md").write_text("# Agent 2")
    (agents_dir / "agent3.md").write_text("# Agent 3")

    monkeypatch.setattr("backend.config.AGENTS_DIR", str(agents_dir))
    monkeypatch.setattr("backend.config.PROJECTS_DIR", str(tmp_path))

    # Set up failed ticket - step 1 completed, step 2 failed
    async with get_db(setup_db) as db:
        await db.execute(
            "UPDATE tickets SET status = ? WHERE id = ?",
            ("failed", sample_ticket)
        )

        # Get step IDs
        steps_rows = await db.execute(
            "SELECT id, step_order FROM ticket_steps WHERE ticket_id = ? ORDER BY step_order",
            (sample_ticket,)
        )
        steps = await steps_rows.fetchall()
        step1_id, step2_id = steps[0]["id"], steps[1]["id"]

        # Mark step 1 as completed
        await db.execute("UPDATE ticket_steps SET status = ? WHERE id = ?", ("completed", step1_id))
        await db.execute("UPDATE step_agents SET status = ? WHERE step_id = ?", ("completed", step1_id))

        # Mark step 2 as failed
        await db.execute("UPDATE ticket_steps SET status = ? WHERE id = ?", ("failed", step2_id))
        await db.execute("UPDATE step_agents SET status = ? WHERE step_id = ?", ("failed", step2_id))

        await db.commit()

    # Mock successful retry
    mock_result = {
        "stdout": "Success on retry",
        "stderr": "",
        "return_code": 0,
        "input_tokens": 1000,
        "output_tokens": 500,
        "pid": 12347
    }

    with patch('backend.services.pipeline_executor.CLIRunner') as MockCLIRunner:
        mock_runner = MockCLIRunner.return_value
        mock_runner.run = AsyncMock(return_value=mock_result)

        executor = PipelineExecutor()
        await executor.retry_ticket(sample_ticket)

    # Verify ticket completed after retry
    async with get_db(setup_db) as db:
        ticket_row = await db.execute("SELECT status FROM tickets WHERE id = ?", (sample_ticket,))
        ticket = await ticket_row.fetchone()
        assert ticket["status"] == "completed"

        # Step 2 should now be completed
        step2_row = await db.execute(
            "SELECT status FROM ticket_steps WHERE ticket_id = ? AND step_order = 2",
            (sample_ticket,)
        )
        step2 = await step2_row.fetchone()
        assert step2["status"] == "completed"
