import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
import json
import signal
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from backend.database import init_db, get_db


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def workspace_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest_asyncio.fixture
async def setup_db(db_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    await init_db(db_path)
    yield db_path


async def _create_project_and_ticket(db_path, title="Test Ticket", desc="Test description"):
    """Helper to create a project and ticket, returns (project_id, ticket_id)."""
    async with get_db(db_path) as db:
        cur = await db.execute(
            "INSERT INTO projects (name, display_name, engine, mode) VALUES (?, ?, ?, ?)",
            ("test-proj", "Test Project", "godot", "development"),
        )
        project_id = cur.lastrowid
        cur2 = await db.execute(
            "INSERT INTO tickets (project_id, title, description, status) VALUES (?, ?, ?, ?)",
            (project_id, title, desc, "assigned"),
        )
        ticket_id = cur2.lastrowid
        await db.commit()
        return project_id, ticket_id


async def _create_session(db_path, ticket_id, agent_name, instruction="Do work",
                          depends_on=None, produces=None, cli_provider="claude"):
    """Helper to create an agent_session, returns session_id."""
    async with get_db(db_path) as db:
        cur = await db.execute(
            """INSERT INTO agent_sessions
               (ticket_id, agent_name, cli_provider, instruction, depends_on, produces, status)
               VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
            (
                ticket_id,
                agent_name,
                cli_provider,
                instruction,
                json.dumps(depends_on or []),
                json.dumps(produces or []),
            ),
        )
        session_id = cur.lastrowid
        await db.commit()
        return session_id


def _make_executor(workspace_dir, agents_dir, monkeypatch, max_parallel=5, poll_interval=0.1):
    """Create a SessionExecutor with mocked config."""
    monkeypatch.setattr("backend.config.AGENTS_DIR", str(agents_dir))
    monkeypatch.setattr("backend.config.PROJECTS_DIR", str(workspace_dir))

    from backend.services.session_executor import SessionExecutor
    return SessionExecutor(
        max_parallel=max_parallel,
        projects_dir=str(workspace_dir),
        poll_interval=poll_interval,
    )


def _setup_agents_dir(workspace_dir, agent_names):
    """Create minimal agent markdown files."""
    agents_dir = Path(workspace_dir) / "agents"
    agents_dir.mkdir(exist_ok=True)
    for name in agent_names:
        (agents_dir / f"{name}.md").write_text(f"# {name} instructions\nDo things.")
    return agents_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_independent_sessions_run_in_parallel(setup_db, workspace_dir, monkeypatch):
    """Two sessions with no dependencies start simultaneously."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    await _create_session(setup_db, ticket_id, "artist", produces=["art.png"])
    await _create_session(setup_db, ticket_id, "coder", produces=["code.py"])

    agents_dir = _setup_agents_dir(workspace_dir, ["artist", "coder"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    started_times = []

    original_run_cli = executor._run_cli

    async def mock_run_cli(prompt, provider, **kwargs):
        started_times.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.05)  # Simulate brief work
        return {
            "stdout": "Done. input_tokens=100 output_tokens=50",
            "stderr": "",
            "return_code": 0,
            "input_tokens": 100,
            "output_tokens": 50,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.execute_ticket(ticket_id)

    # Both should have started within a very small window (nearly simultaneous)
    assert len(started_times) == 2
    assert abs(started_times[0] - started_times[1]) < 0.5

    # Verify ticket completed
    async with get_db(setup_db) as db:
        row = await db.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        ticket = await row.fetchone()
        assert ticket["status"] == "completed"


@pytest.mark.asyncio
async def test_dependent_session_waits(setup_db, workspace_dir, monkeypatch):
    """Session B depends on A's output file and waits for it."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    await _create_session(setup_db, ticket_id, "artist", produces=["design.md"])
    await _create_session(setup_db, ticket_id, "coder", depends_on=["design.md"], produces=["impl.py"])

    agents_dir = _setup_agents_dir(workspace_dir, ["artist", "coder"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    call_order = []

    async def mock_run_cli(prompt, provider, **kwargs):
        # Determine which agent by checking prompt content
        if "artist" in prompt.lower():
            call_order.append("artist")
        else:
            call_order.append("coder")
        await asyncio.sleep(0.02)
        return {
            "stdout": "Done", "stderr": "",
            "return_code": 0, "input_tokens": 100, "output_tokens": 50,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.execute_ticket(ticket_id)

    # artist must run before coder
    assert call_order.index("artist") < call_order.index("coder")

    # Ticket should be completed
    async with get_db(setup_db) as db:
        row = await db.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        ticket = await row.fetchone()
        assert ticket["status"] == "completed"


@pytest.mark.asyncio
async def test_failed_session_does_not_block_independent(setup_db, workspace_dir, monkeypatch):
    """Failure of A doesn't stop unrelated C from completing."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    await _create_session(setup_db, ticket_id, "artist", produces=["art.png"])
    await _create_session(setup_db, ticket_id, "coder", depends_on=["art.png"], produces=["code.py"])
    await _create_session(setup_db, ticket_id, "writer", produces=["story.md"])  # independent

    agents_dir = _setup_agents_dir(workspace_dir, ["artist", "coder", "writer"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    async def mock_run_cli(prompt, provider, **kwargs):
        if "artist" in prompt.lower():
            return {
                "stdout": "", "stderr": "Crashed",
                "return_code": 1, "input_tokens": 10, "output_tokens": 5,
                "pid": os.getpid(),
            }
        return {
            "stdout": "Done", "stderr": "",
            "return_code": 0, "input_tokens": 100, "output_tokens": 50,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.execute_ticket(ticket_id)

    async with get_db(setup_db) as db:
        rows = await db.execute(
            "SELECT agent_name, status FROM agent_sessions WHERE ticket_id = ?", (ticket_id,)
        )
        sessions = {r["agent_name"]: r["status"] for r in await rows.fetchall()}

    assert sessions["artist"] == "failed"
    assert sessions["coder"] == "cancelled"  # upstream failed
    assert sessions["writer"] == "completed"  # independent, should finish

    # Ticket should be failed (at least one session failed)
    async with get_db(setup_db) as db:
        row = await db.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        ticket = await row.fetchone()
        assert ticket["status"] == "failed"


@pytest.mark.asyncio
async def test_cancel_kills_running_sessions(setup_db, workspace_dir, monkeypatch):
    """cancel_ticket sets status to cancelled and attempts SIGTERM."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    s1 = await _create_session(setup_db, ticket_id, "artist", produces=["art.png"])
    s2 = await _create_session(setup_db, ticket_id, "coder", produces=["code.py"])

    # Simulate running state with fake PIDs
    async with get_db(setup_db) as db:
        await db.execute(
            "UPDATE agent_sessions SET status='running', pid=99998 WHERE id=?", (s1,)
        )
        await db.execute(
            "UPDATE agent_sessions SET status='waiting', pid=NULL WHERE id=?", (s2,)
        )
        await db.execute(
            "UPDATE tickets SET status='running' WHERE id=?", (ticket_id,)
        )
        await db.commit()

    # Create workspace with .writing files
    ws = Path(workspace_dir) / f"workspace/ticket_{ticket_id}"
    ws.mkdir(parents=True, exist_ok=True)
    writing_file = ws / "art.png.writing"
    writing_file.write_text("partial")

    agents_dir = _setup_agents_dir(workspace_dir, ["artist", "coder"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    with patch("os.kill") as mock_kill:
        await executor.cancel_ticket(ticket_id)
        mock_kill.assert_called()

    # .writing files should be cleaned up
    assert not writing_file.exists()

    async with get_db(setup_db) as db:
        row = await db.execute("SELECT status FROM tickets WHERE id=?", (ticket_id,))
        assert (await row.fetchone())["status"] == "cancelled"

        rows = await db.execute(
            "SELECT status FROM agent_sessions WHERE ticket_id=?", (ticket_id,)
        )
        for s in await rows.fetchall():
            assert s["status"] == "cancelled"


@pytest.mark.asyncio
async def test_max_parallel_respected(setup_db, workspace_dir, monkeypatch):
    """max_parallel=2 means at most 2 concurrent sessions."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    for name in ["a1", "a2", "a3", "a4"]:
        await _create_session(setup_db, ticket_id, name, produces=[f"{name}.txt"])

    agents_dir = _setup_agents_dir(workspace_dir, ["a1", "a2", "a3", "a4"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch, max_parallel=2)

    concurrent_count = 0
    max_concurrent = 0
    lock = asyncio.Lock()

    async def mock_run_cli(prompt, provider, **kwargs):
        nonlocal concurrent_count, max_concurrent
        async with lock:
            concurrent_count += 1
            if concurrent_count > max_concurrent:
                max_concurrent = concurrent_count
        await asyncio.sleep(0.05)
        async with lock:
            concurrent_count -= 1
        return {
            "stdout": "Done", "stderr": "",
            "return_code": 0, "input_tokens": 10, "output_tokens": 5,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.execute_ticket(ticket_id)

    assert max_concurrent <= 2


@pytest.mark.asyncio
async def test_writing_files_renamed_on_success(setup_db, workspace_dir, monkeypatch):
    """.writing files are renamed to final names on success."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    await _create_session(setup_db, ticket_id, "artist", produces=["output.md"])

    agents_dir = _setup_agents_dir(workspace_dir, ["artist"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    ws = Path(workspace_dir) / f"workspace/ticket_{ticket_id}"

    async def mock_run_cli(prompt, provider, **kwargs):
        # Simulate the CLI creating the .writing file
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "output.md.writing").write_text("result content")
        return {
            "stdout": "Done", "stderr": "",
            "return_code": 0, "input_tokens": 100, "output_tokens": 50,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.execute_ticket(ticket_id)

    # .writing should be gone, final file should exist
    assert not (ws / "output.md.writing").exists()
    assert (ws / "output.md").exists()
    assert (ws / "output.md").read_text() == "result content"


@pytest.mark.asyncio
async def test_writing_files_cleaned_on_failure(setup_db, workspace_dir, monkeypatch):
    """.writing files are deleted on failure."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    await _create_session(setup_db, ticket_id, "artist", produces=["output.md"])

    agents_dir = _setup_agents_dir(workspace_dir, ["artist"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    ws = Path(workspace_dir) / f"workspace/ticket_{ticket_id}"

    async def mock_run_cli(prompt, provider, **kwargs):
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "output.md.writing").write_text("partial content")
        return {
            "stdout": "", "stderr": "Error",
            "return_code": 1, "input_tokens": 10, "output_tokens": 5,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.execute_ticket(ticket_id)

    # .writing should be cleaned up
    assert not (ws / "output.md.writing").exists()
    # Final file should NOT exist either
    assert not (ws / "output.md").exists()


@pytest.mark.asyncio
async def test_retry_session(setup_db, workspace_dir, monkeypatch):
    """retry_session resets a failed session and its downstream dependents."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    s1 = await _create_session(setup_db, ticket_id, "artist", produces=["art.png"])
    s2 = await _create_session(setup_db, ticket_id, "coder", depends_on=["art.png"], produces=["code.py"])

    # Simulate: artist failed, coder cancelled
    async with get_db(setup_db) as db:
        await db.execute(
            "UPDATE agent_sessions SET status='failed', error_message='boom' WHERE id=?", (s1,)
        )
        await db.execute(
            "UPDATE agent_sessions SET status='cancelled' WHERE id=?", (s2,)
        )
        await db.execute(
            "UPDATE tickets SET status='failed' WHERE id=?", (ticket_id,)
        )
        await db.commit()

    agents_dir = _setup_agents_dir(workspace_dir, ["artist", "coder"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    call_count = 0

    async def mock_run_cli(prompt, provider, **kwargs):
        nonlocal call_count
        call_count += 1
        return {
            "stdout": "Done", "stderr": "",
            "return_code": 0, "input_tokens": 100, "output_tokens": 50,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.retry_session(s1)

    # Both sessions should now be completed (artist retried, coder re-ran because downstream)
    async with get_db(setup_db) as db:
        rows = await db.execute(
            "SELECT agent_name, status, retry_count FROM agent_sessions WHERE ticket_id=?",
            (ticket_id,),
        )
        sessions = {r["agent_name"]: dict(r) for r in await rows.fetchall()}

    assert sessions["artist"]["status"] == "completed"
    assert sessions["artist"]["retry_count"] == 1
    assert sessions["coder"]["status"] == "completed"


@pytest.mark.asyncio
async def test_session_log_saved(setup_db, workspace_dir, monkeypatch):
    """Session log is saved to sessions directory."""
    _, ticket_id = await _create_project_and_ticket(setup_db)
    s1 = await _create_session(setup_db, ticket_id, "artist", produces=["art.png"])

    agents_dir = _setup_agents_dir(workspace_dir, ["artist"])
    executor = _make_executor(workspace_dir, agents_dir, monkeypatch)

    async def mock_run_cli(prompt, provider, **kwargs):
        return {
            "stdout": "Agent output here", "stderr": "",
            "return_code": 0, "input_tokens": 100, "output_tokens": 50,
            "pid": os.getpid(),
        }

    executor._run_cli = mock_run_cli
    await executor.execute_ticket(ticket_id)

    # Check log file exists
    async with get_db(setup_db) as db:
        row = await db.execute(
            "SELECT session_log_path FROM agent_sessions WHERE id=?", (s1,)
        )
        session = await row.fetchone()
        assert session["session_log_path"] is not None
        assert os.path.exists(session["session_log_path"])
