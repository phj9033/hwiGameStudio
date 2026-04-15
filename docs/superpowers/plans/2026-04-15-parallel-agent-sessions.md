# Parallel Agent Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the step-based sequential pipeline with flat, dependency-driven parallel agent sessions using file-based shared context.

**Architecture:** Remove `ticket_steps`/`step_agents` tables, add `agent_sessions` table. Each session runs independently as a CLI subprocess. Sessions declare `depends_on`/`produces` files; the orchestrator polls `workspace/` for completed files and launches waiting sessions when dependencies are met. Results are stored as files in `workspace/` (shared documents) and `sessions/` (execution logs).

**Tech Stack:** Python 3.11+, FastAPI, aiosqlite, asyncio, Streamlit

**Spec:** `docs/superpowers/specs/2026-04-15-parallel-agent-sessions-design.md`

---

## File Structure

### New Files
- `backend/models/session.py` — Pydantic models for agent sessions
- `backend/routes/sessions.py` — Session API endpoints
- `backend/services/session_executor.py` — New parallel execution engine
- `backend/services/dependency_graph.py` — DAG validation (cycle detection)
- `tests/test_session_executor.py` — Executor tests
- `tests/test_dependency_graph.py` — DAG validation tests
- `tests/test_sessions_endpoints.py` — Session API tests

### Modified Files
- `backend/database.py` — Drop old tables, add `agent_sessions`. Refactor `init_db` to accept optional connection.
- `backend/models/ticket.py` — Replace step models with session models
- `backend/routes/tickets.py` — Remove step logic, use sessions
- `backend/routes/runs.py` — Update queries from `step_agents` to `agent_sessions`
- `backend/routes/agents.py` — Update queries from `step_agents` to `agent_sessions`, use `SessionResponse`
- `backend/main.py` — Register sessions router
- `backend/services/prompt_builder.py` — Add workspace context to prompts
- `backend/routes/usage.py` — Update queries for `agent_sessions`
- `frontend/pages/3_ticket_board.py` — Session-based UI (board + ticket creation form)
- `frontend/pages/5_agents.py` — Update run history to use sessions
- `frontend/pages/6_usage.py` — Update if referencing step-based data
- `frontend/components/result_viewer.py` — Session log viewer
- `tests/test_database.py` — Update schema tests
- `tests/test_usage.py` — Update for new table
- `tests/test_tickets.py` — Update for sessions
- `tests/test_tickets_endpoints.py` — Update for sessions
- `tests/test_pipeline_executor.py` — Replace with session executor tests

### Deleted Files
- `backend/services/pipeline_executor.py` — Replaced by `session_executor.py`

### Notes
- `backend/routes/ccusage.py` — Review for any `step_agents` references
- Preserve existing column defaults in `projects` table (e.g., `mode DEFAULT 'development'`)
- `estimated_cost` computation deferred — field exists but not calculated yet (same as current system)

---

### Task 1: Dependency Graph Validator

**Files:**
- Create: `backend/services/dependency_graph.py`
- Create: `tests/test_dependency_graph.py`

- [ ] **Step 1: Write the failing test for cycle detection**

```python
# tests/test_dependency_graph.py
import pytest
from backend.services.dependency_graph import validate_dependency_graph, CyclicDependencyError


def test_valid_linear_graph():
    sessions = [
        {"agent_name": "designer", "depends_on": [], "produces": ["gdd.md"]},
        {"agent_name": "developer", "depends_on": ["gdd.md"], "produces": ["spec.md"]},
    ]
    assert validate_dependency_graph(sessions) is True


def test_valid_parallel_graph():
    sessions = [
        {"agent_name": "designer", "depends_on": [], "produces": ["gdd.md"]},
        {"agent_name": "artist", "depends_on": [], "produces": ["art.md"]},
        {"agent_name": "developer", "depends_on": ["gdd.md", "art.md"], "produces": ["spec.md"]},
    ]
    assert validate_dependency_graph(sessions) is True


def test_cyclic_dependency_raises():
    sessions = [
        {"agent_name": "a", "depends_on": ["b.md"], "produces": ["a.md"]},
        {"agent_name": "b", "depends_on": ["a.md"], "produces": ["b.md"]},
    ]
    with pytest.raises(CyclicDependencyError):
        validate_dependency_graph(sessions)


def test_self_dependency_raises():
    sessions = [
        {"agent_name": "a", "depends_on": ["a.md"], "produces": ["a.md"]},
    ]
    with pytest.raises(CyclicDependencyError):
        validate_dependency_graph(sessions)


def test_unresolved_dependency_raises():
    sessions = [
        {"agent_name": "a", "depends_on": ["nonexistent.md"], "produces": ["a.md"]},
    ]
    with pytest.raises(ValueError, match="unresolved"):
        validate_dependency_graph(sessions)


def test_empty_sessions():
    assert validate_dependency_graph([]) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_dependency_graph.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement dependency graph validator**

```python
# backend/services/dependency_graph.py
from collections import deque
from typing import Any


class CyclicDependencyError(Exception):
    pass


def validate_dependency_graph(sessions: list[dict[str, Any]]) -> bool:
    """Validate that session dependencies form a DAG (no cycles).

    Each session has depends_on (list of filenames) and produces (list of filenames).
    Build a graph: file -> producing session, session -> depends_on files.
    Run topological sort to detect cycles.
    """
    if not sessions:
        return True

    # Map: filename -> session index that produces it
    producers: dict[str, int] = {}
    for i, s in enumerate(sessions):
        for f in s.get("produces", []):
            producers[f] = i

    # Check for unresolved dependencies
    all_produced = set(producers.keys())
    for s in sessions:
        for dep in s.get("depends_on", []):
            if dep not in all_produced:
                raise ValueError(f"Unresolved dependency: '{dep}' is not produced by any session")

    # Build adjacency list: session i -> [sessions that i depends on]
    n = len(sessions)
    adj: list[list[int]] = [[] for _ in range(n)]
    in_degree = [0] * n

    for i, s in enumerate(sessions):
        for dep in s.get("depends_on", []):
            if dep in producers:
                parent = producers[dep]
                if parent == i:
                    raise CyclicDependencyError(
                        f"Self-dependency: session '{s['agent_name']}' depends on file it produces"
                    )
                adj[parent].append(i)
                in_degree[i] += 1

    # Kahn's algorithm for topological sort
    queue = deque(i for i in range(n) if in_degree[i] == 0)
    visited = 0

    while queue:
        node = queue.popleft()
        visited += 1
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if visited != n:
        raise CyclicDependencyError("Cyclic dependency detected among sessions")

    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_dependency_graph.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/dependency_graph.py tests/test_dependency_graph.py
git commit -m "feat: add dependency graph validator with cycle detection"
```

---

### Task 2: Database Schema Migration

**Files:**
- Modify: `backend/database.py`
- Modify: `tests/test_database.py`

- [ ] **Step 1: Write the failing test for new schema**

Note: The current `init_db()` takes a `db_path: str` and creates its own connection. Refactor it to also accept an optional connection parameter, or use a temp file in tests. Use the temp file approach to avoid breaking the existing API:

```python
# tests/test_database.py — replace existing tests
import os
import tempfile
import pytest
import aiosqlite
from backend.database import init_db

@pytest.fixture
async def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        await init_db(db_path)
        conn = await aiosqlite.connect(db_path)
        yield conn
        await conn.close()
    finally:
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_init_db_creates_tables(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    assert "projects" in tables
    assert "tickets" in tables
    assert "agent_sessions" in tables
    assert "cli_providers" in tables
    assert "documents" in tables
    # Old tables should NOT exist
    assert "ticket_steps" not in tables
    assert "step_agents" not in tables


@pytest.mark.asyncio
async def test_agent_sessions_columns(db):
    cursor = await db.execute("PRAGMA table_info(agent_sessions)")
    columns = {row[1] for row in await cursor.fetchall()}
    expected = {
        "id", "ticket_id", "agent_name", "cli_provider", "instruction",
        "depends_on", "produces", "status", "error_message",
        "input_tokens", "output_tokens", "estimated_cost",
        "session_log_path", "pid", "started_at", "completed_at",
        "retry_count", "created_at",
    }
    assert expected.issubset(columns)


@pytest.mark.asyncio
async def test_init_db_enables_wal(db):
    cursor = await db.execute("PRAGMA journal_mode")
    mode = (await cursor.fetchone())[0]
    assert mode == "wal"


@pytest.mark.asyncio
async def test_init_db_seeds_default_providers(db):
    cursor = await db.execute("SELECT name FROM cli_providers ORDER BY name")
    names = [row[0] for row in await cursor.fetchall()]
    assert "claude" in names
    assert "codex" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_database.py -v`
Expected: FAIL (old tables still exist, agent_sessions missing)

- [ ] **Step 3: Update database.py schema**

Replace the SCHEMA in `backend/database.py`:
- Remove `ticket_steps` and `step_agents` table definitions
- Add `agent_sessions` table per spec
- Keep `projects`, `tickets`, `cli_providers`, `documents` tables unchanged

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    engine TEXT NOT NULL DEFAULT 'godot',
    mode TEXT NOT NULL DEFAULT 'development',
    status TEXT NOT NULL DEFAULT 'active',
    config_json TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    source TEXT DEFAULT 'manual',
    created_by TEXT DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    agent_name TEXT NOT NULL,
    cli_provider TEXT NOT NULL DEFAULT 'claude',
    instruction TEXT NOT NULL,
    depends_on TEXT DEFAULT '[]',
    produces TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost REAL DEFAULT 0,
    session_log_path TEXT,
    pid INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cli_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    command TEXT NOT NULL,
    api_key_env TEXT,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL,
    content TEXT,
    previous_content TEXT,
    updated_by TEXT DEFAULT 'user',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_database.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/database.py tests/test_database.py
git commit -m "feat: replace ticket_steps/step_agents with agent_sessions table"
```

---

### Task 3: Pydantic Models for Sessions

**Files:**
- Create: `backend/models/session.py`
- Modify: `backend/models/ticket.py`

- [ ] **Step 1: Create session models**

```python
# backend/models/session.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SessionCreate(BaseModel):
    agent_name: str
    cli_provider: str = "claude"
    instruction: str
    depends_on: list[str] = []
    produces: list[str] = []


class SessionResponse(BaseModel):
    id: int
    ticket_id: int
    agent_name: str
    cli_provider: str
    instruction: str
    depends_on: list[str]
    produces: list[str]
    status: str
    error_message: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0
    session_log_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
```

- [ ] **Step 2: Update ticket models**

Replace step-based models in `backend/models/ticket.py`:
- Remove `StepAgentCreate`, `StepCreate`, `StepAgentResponse`, `StepResponse`
- Update `TicketCreate` to use `sessions: list[SessionCreate]` instead of `steps: list[StepCreate]`
- Update `TicketResponse` to use `sessions: list[SessionResponse]` instead of `steps: list[StepResponse]`

```python
# backend/models/ticket.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.models.session import SessionCreate, SessionResponse


class TicketCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    source: str = "manual"
    created_by: str = "user"
    sessions: list[SessionCreate] = []


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class TicketResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: Optional[str]
    status: str
    source: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    sessions: list[SessionResponse] = []


class TicketSummary(BaseModel):
    id: int
    project_id: int
    title: str
    status: str
    source: str
    created_at: datetime
```

- [ ] **Step 3: Commit**

```bash
git add backend/models/session.py backend/models/ticket.py
git commit -m "feat: add session pydantic models, replace step models"
```

---

### Task 4: Session Executor — Core Parallel Engine

**Important:** This task MUST come before ticket routes, since routes depend on `SessionExecutor`.

**Files:**
- Create: `backend/services/session_executor.py`
- Create: `tests/test_session_executor.py`
- Delete: `backend/services/pipeline_executor.py`

- [ ] **Step 1: Write failing tests for session executor**

```python
# tests/test_session_executor.py
import pytest
import os
import json
import asyncio
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock
import aiosqlite
from backend.database import init_db
from backend.services.session_executor import SessionExecutor


@pytest.fixture
async def db_and_dir():
    """Provide a real DB and temp workspace directory."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test.db")
    await init_db(db_path)
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    yield conn, tmpdir
    await conn.close()


async def insert_ticket_with_sessions(db, sessions_data):
    await db.execute(
        "INSERT INTO projects (name, display_name) VALUES ('proj', 'Proj')"
    )
    await db.execute(
        "INSERT INTO tickets (project_id, title, status) VALUES (1, 'Test', 'assigned')"
    )
    for s in sessions_data:
        await db.execute(
            """INSERT INTO agent_sessions
               (ticket_id, agent_name, instruction, depends_on, produces, status)
               VALUES (1, ?, ?, ?, ?, 'pending')""",
            (s["agent_name"], s["instruction"],
             json.dumps(s.get("depends_on", [])),
             json.dumps(s.get("produces", [])))
        )
    await db.commit()
    return 1


@pytest.mark.asyncio
async def test_independent_sessions_run_in_parallel(db_and_dir):
    """Two sessions with no dependencies should both start immediately."""
    db, tmpdir = db_and_dir
    await insert_ticket_with_sessions(db, [
        {"agent_name": "a", "instruction": "Do A", "produces": ["a.md"]},
        {"agent_name": "b", "instruction": "Do B", "produces": ["b.md"]},
    ])

    started = []

    async def mock_cli_run(prompt, provider, **kwargs):
        started.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.1)
        return MagicMock(success=True, stdout="done", stderr="")

    executor = SessionExecutor(max_parallel=5, projects_dir=tmpdir)
    with patch.object(executor, '_run_cli', side_effect=mock_cli_run):
        await executor.execute_ticket(1)

    # Both should have started nearly simultaneously (within 0.5s of each other)
    assert len(started) == 2
    assert abs(started[0] - started[1]) < 0.5

    # Both sessions should be completed
    cursor = await db.execute(
        "SELECT status FROM agent_sessions WHERE ticket_id = 1"
    )
    statuses = [row[0] for row in await cursor.fetchall()]
    assert all(s == "completed" for s in statuses)


@pytest.mark.asyncio
async def test_dependent_session_waits(db_and_dir):
    """Session B depends on file from Session A. B should not start until A completes."""
    db, tmpdir = db_and_dir
    await insert_ticket_with_sessions(db, [
        {"agent_name": "a", "instruction": "Do A", "produces": ["a.md"]},
        {"agent_name": "b", "instruction": "Do B", "depends_on": ["a.md"], "produces": ["b.md"]},
    ])

    execution_order = []
    workspace = os.path.join(tmpdir, "workspace", "ticket_1")
    os.makedirs(workspace, exist_ok=True)

    async def mock_cli_run(prompt, provider, **kwargs):
        # Determine which agent from prompt
        if "Do A" in prompt:
            execution_order.append("a_start")
            # Simulate writing output
            with open(os.path.join(workspace, "a.md.writing"), "w") as f:
                f.write("Result A")
            await asyncio.sleep(0.1)
            execution_order.append("a_done")
        else:
            execution_order.append("b_start")
            await asyncio.sleep(0.1)
            execution_order.append("b_done")
        return MagicMock(success=True, stdout="done", stderr="")

    executor = SessionExecutor(max_parallel=5, projects_dir=tmpdir, poll_interval=0.2)
    with patch.object(executor, '_run_cli', side_effect=mock_cli_run):
        await executor.execute_ticket(1)

    # A must complete before B starts
    assert execution_order.index("a_done") < execution_order.index("b_start")


@pytest.mark.asyncio
async def test_failed_session_does_not_block_independent(db_and_dir):
    """If session A fails, unrelated session C should still complete."""
    db, tmpdir = db_and_dir
    await insert_ticket_with_sessions(db, [
        {"agent_name": "a", "instruction": "Fail", "produces": ["a.md"]},
        {"agent_name": "c", "instruction": "Succeed", "produces": ["c.md"]},
    ])

    async def mock_cli_run(prompt, provider, **kwargs):
        if "Fail" in prompt:
            return MagicMock(success=False, stdout="", stderr="error")
        return MagicMock(success=True, stdout="done", stderr="")

    executor = SessionExecutor(max_parallel=5, projects_dir=tmpdir)
    with patch.object(executor, '_run_cli', side_effect=mock_cli_run):
        await executor.execute_ticket(1)

    cursor = await db.execute(
        "SELECT agent_name, status FROM agent_sessions WHERE ticket_id = 1 ORDER BY agent_name"
    )
    results = {row[0]: row[1] for row in await cursor.fetchall()}
    assert results["a"] == "failed"
    assert results["c"] == "completed"


@pytest.mark.asyncio
async def test_cancel_kills_running_sessions(db_and_dir):
    """Cancel should set running/waiting sessions to cancelled."""
    db, tmpdir = db_and_dir
    await insert_ticket_with_sessions(db, [
        {"agent_name": "a", "instruction": "Long task", "produces": ["a.md"]},
    ])
    # Manually set session to running with a fake PID
    await db.execute(
        "UPDATE agent_sessions SET status = 'running', pid = 99999 WHERE id = 1"
    )
    await db.commit()

    executor = SessionExecutor(max_parallel=5, projects_dir=tmpdir)
    with patch("os.kill") as mock_kill:
        await executor.cancel_ticket(1)

    cursor = await db.execute(
        "SELECT status FROM agent_sessions WHERE ticket_id = 1"
    )
    status = (await cursor.fetchone())[0]
    assert status == "cancelled"


@pytest.mark.asyncio
async def test_max_parallel_respected(db_and_dir):
    """Only max_parallel sessions should run concurrently."""
    db, tmpdir = db_and_dir
    await insert_ticket_with_sessions(db, [
        {"agent_name": f"agent_{i}", "instruction": f"Task {i}", "produces": [f"{i}.md"]}
        for i in range(5)
    ])

    concurrent_count = []
    running = 0
    lock = asyncio.Lock()

    async def mock_cli_run(prompt, provider, **kwargs):
        nonlocal running
        async with lock:
            running += 1
            concurrent_count.append(running)
        await asyncio.sleep(0.1)
        async with lock:
            running -= 1
        return MagicMock(success=True, stdout="done", stderr="")

    executor = SessionExecutor(max_parallel=2, projects_dir=tmpdir, poll_interval=0.2)
    with patch.object(executor, '_run_cli', side_effect=mock_cli_run):
        await executor.execute_ticket(1)

    # Max concurrent should never exceed 2
    assert max(concurrent_count) <= 2


@pytest.mark.asyncio
async def test_writing_files_renamed_on_success(db_and_dir):
    """On success, .writing files should be renamed to final names."""
    db, tmpdir = db_and_dir
    await insert_ticket_with_sessions(db, [
        {"agent_name": "a", "instruction": "Do A", "produces": ["result.md"]},
    ])
    workspace = os.path.join(tmpdir, "workspace", "ticket_1")
    os.makedirs(workspace, exist_ok=True)

    async def mock_cli_run(prompt, provider, **kwargs):
        with open(os.path.join(workspace, "result.md.writing"), "w") as f:
            f.write("Output content")
        return MagicMock(success=True, stdout="done", stderr="")

    executor = SessionExecutor(max_parallel=5, projects_dir=tmpdir)
    with patch.object(executor, '_run_cli', side_effect=mock_cli_run):
        await executor.execute_ticket(1)

    assert os.path.exists(os.path.join(workspace, "result.md"))
    assert not os.path.exists(os.path.join(workspace, "result.md.writing"))


@pytest.mark.asyncio
async def test_writing_files_cleaned_on_failure(db_and_dir):
    """On failure, .writing files should be deleted."""
    db, tmpdir = db_and_dir
    await insert_ticket_with_sessions(db, [
        {"agent_name": "a", "instruction": "Fail", "produces": ["result.md"]},
    ])
    workspace = os.path.join(tmpdir, "workspace", "ticket_1")
    os.makedirs(workspace, exist_ok=True)

    async def mock_cli_run(prompt, provider, **kwargs):
        with open(os.path.join(workspace, "result.md.writing"), "w") as f:
            f.write("Partial output")
        return MagicMock(success=False, stdout="", stderr="crash")

    executor = SessionExecutor(max_parallel=5, projects_dir=tmpdir)
    with patch.object(executor, '_run_cli', side_effect=mock_cli_run):
        await executor.execute_ticket(1)

    assert not os.path.exists(os.path.join(workspace, "result.md"))
    assert not os.path.exists(os.path.join(workspace, "result.md.writing"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_session_executor.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement SessionExecutor**

Create `backend/services/session_executor.py` implementing:
- `__init__(max_parallel, projects_dir, poll_interval)` — configurable params
- `execute_ticket(ticket_id)` — main entry point
  - Query all `agent_sessions` for ticket
  - Set no-dependency sessions to "running", launch tasks
  - Set dependency sessions to "waiting"
  - Poll loop checking workspace for completed files
  - Respect `max_parallel_sessions` limit via semaphore
  - Update ticket status when all done (completed if all done, failed if any failed)
- `_run_single_session(session_id)` — run one agent
  - Build prompt with workspace context
  - Call `_run_cli()` (extracted for testability)
  - Save session log to `sessions/ticket_{id}/{agent}.md`
  - On success: rename `.writing` files
  - On failure: cleanup `.writing` files, set error_message
- `_run_cli(prompt, provider)` — thin wrapper around CLIRunner (mockable)
- `cancel_ticket(ticket_id)` — SIGTERM running PIDs, set all non-completed to cancelled
- `retry_session(session_id)` — reset single failed session + downstream waiting sessions

Key implementation details:
- Set status to "running" synchronously BEFORE `create_task` to prevent race conditions
- Wait timeout: 30 min for dependencies, 60 min for execution
- Create workspace/sessions directories on ticket run
- Use `asyncio.Semaphore(max_parallel)` for concurrency limit

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_session_executor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Delete old pipeline_executor.py**

```bash
rm backend/services/pipeline_executor.py
rm tests/test_pipeline_executor.py
```

- [ ] **Step 6: Commit**

```bash
git add backend/services/session_executor.py tests/test_session_executor.py
git add -u  # stages deletions
git commit -m "feat: parallel session executor replaces sequential pipeline"
```

---

### Task 5: Ticket Routes — Remove Steps, Add Sessions

**Depends on:** Task 4 (SessionExecutor must exist)

**Files:**
- Modify: `backend/routes/tickets.py`
- Create: `tests/test_sessions_endpoints.py`

- [ ] **Step 1: Write failing tests for session-based ticket creation**

```python
# tests/test_sessions_endpoints.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db, get_db

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        async with get_db() as db:
            await init_db(db)
        yield c


@pytest.fixture
async def project(client):
    resp = await client.post("/api/projects/", json={
        "name": "test_proj", "display_name": "Test", "engine": "godot"
    })
    return resp.json()


@pytest.mark.asyncio
async def test_create_ticket_with_sessions(client, project):
    resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "Test ticket",
        "sessions": [
            {"agent_name": "designer", "instruction": "Design GDD", "produces": ["gdd.md"]},
            {"agent_name": "developer", "instruction": "Implement", "depends_on": ["gdd.md"], "produces": ["spec.md"]},
        ]
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "assigned"
    assert len(data["sessions"]) == 2
    assert data["sessions"][0]["agent_name"] == "designer"
    assert data["sessions"][1]["depends_on"] == ["gdd.md"]


@pytest.mark.asyncio
async def test_create_ticket_cyclic_dependency_rejected(client, project):
    resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "Cyclic",
        "sessions": [
            {"agent_name": "a", "instruction": "Do A", "depends_on": ["b.md"], "produces": ["a.md"]},
            {"agent_name": "b", "instruction": "Do B", "depends_on": ["a.md"], "produces": ["b.md"]},
        ]
    })
    assert resp.status_code == 400
    assert "cyclic" in resp.json()["detail"].lower() or "Cyclic" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_ticket_without_sessions(client, project):
    resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "No sessions",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"
    assert resp.json()["sessions"] == []


@pytest.mark.asyncio
async def test_get_ticket_detail_with_sessions(client, project):
    create_resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "Detail test",
        "sessions": [
            {"agent_name": "designer", "instruction": "Design", "produces": ["gdd.md"]},
        ]
    })
    ticket_id = create_resp.json()["id"]
    resp = await client.get(f"/api/tickets/{ticket_id}")
    assert resp.status_code == 200
    assert len(resp.json()["sessions"]) == 1


@pytest.mark.asyncio
async def test_delete_ticket_cascades_sessions(client, project):
    create_resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "Delete test",
        "sessions": [
            {"agent_name": "designer", "instruction": "Design", "produces": ["gdd.md"]},
        ]
    })
    ticket_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/tickets/{ticket_id}")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_sessions_endpoints.py -v`
Expected: FAIL

- [ ] **Step 3: Update tickets.py routes**

Rewrite `backend/routes/tickets.py`:
- `_get_ticket_detail()`: Query `agent_sessions` instead of `ticket_steps` + `step_agents`
- `create_ticket()`: Insert into `agent_sessions` instead of steps/agents. Call `validate_dependency_graph()` before insert. Set status to "assigned" if sessions provided.
- `delete_ticket()`: CASCADE delete `agent_sessions` instead of steps/agents
- `run_ticket()`: Use `SessionExecutor` (from Task 4)
- `cancel_ticket()`: Delegate to `SessionExecutor.cancel_ticket()`
- `retry_ticket()`: Accept optional `session_id` query param for per-session retry. Delegate to `SessionExecutor.retry_session()`.
- Add `POST /api/sessions/{session_id}/retry` endpoint for per-session retry
- Remove step-related logic entirely
- Keep decompose/diff/auto-assign endpoints but update return format

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_sessions_endpoints.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/tickets.py tests/test_sessions_endpoints.py
git commit -m "feat: ticket routes use sessions instead of steps"
```

---

### Task 6: Session API Endpoints

**Files:**
- Create: `backend/routes/sessions.py`
- Modify: `backend/main.py`

- [ ] **Step 1: Write failing tests for session endpoints**

Add to `tests/test_sessions_endpoints.py`:

```python
@pytest.mark.asyncio
async def test_get_session_detail(client, project):
    # Create ticket with session, then GET /api/sessions/{id}
    create_resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "Session detail",
        "sessions": [{"agent_name": "designer", "instruction": "Design", "produces": ["gdd.md"]}]
    })
    session_id = create_resp.json()["sessions"][0]["id"]
    resp = await client.get(f"/api/sessions/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["agent_name"] == "designer"


@pytest.mark.asyncio
async def test_get_session_log_not_found(client, project):
    create_resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "Log test",
        "sessions": [{"agent_name": "designer", "instruction": "Design"}]
    })
    session_id = create_resp.json()["sessions"][0]["id"]
    resp = await client.get(f"/api/sessions/{session_id}/log")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_workspace_empty(client, project):
    create_resp = await client.post("/api/tickets/", json={
        "project_id": project["id"],
        "title": "Workspace test",
        "sessions": [{"agent_name": "designer", "instruction": "Design"}]
    })
    ticket_id = create_resp.json()["id"]
    resp = await client.get(f"/api/tickets/{ticket_id}/workspace")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_sessions_endpoints.py::test_get_session_detail -v`
Expected: FAIL (404)

- [ ] **Step 3: Implement session routes**

```python
# backend/routes/sessions.py
import os
import json
from fastapi import APIRouter, HTTPException
from backend.database import get_db

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "projects")


@router.get("/{session_id}")
async def get_session(session_id: int):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM agent_sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        columns = [desc[0] for desc in cursor.description]
        session = dict(zip(columns, row))
        session["depends_on"] = json.loads(session["depends_on"])
        session["produces"] = json.loads(session["produces"])
        return session


@router.get("/{session_id}/log")
async def get_session_log(session_id: int):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT session_log_path FROM agent_sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Session not found")
        log_path = row[0]
        if not log_path or not os.path.exists(log_path):
            raise HTTPException(404, "Session log not found")
        with open(log_path, "r") as f:
            return {"content": f.read()}
```

Add workspace endpoints to `backend/routes/tickets.py`:

```python
@router.get("/{ticket_id}/workspace")
async def get_workspace(ticket_id: int):
    # Find project for ticket, list files in workspace/ticket_{id}/
    # Return [{filename, size, modified, is_writing}]

@router.get("/{ticket_id}/workspace/{filename}")
async def get_workspace_file(ticket_id: int, filename: str):
    # Read and return file content
```

- [ ] **Step 4: Register router in main.py**

Add to `backend/main.py`:
```python
from backend.routes.sessions import router as sessions_router
app.include_router(sessions_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_sessions_endpoints.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/sessions.py backend/main.py tests/test_sessions_endpoints.py
git commit -m "feat: add session and workspace API endpoints"
```

---

### Task 7: Update Prompt Builder for Workspace Context

**Files:**
- Modify: `backend/services/prompt_builder.py`
- Modify: `tests/test_prompt_builder.py`

- [ ] **Step 1: Write failing test**

```python
def test_build_prompt_with_workspace_context():
    prompt = builder.build_prompt(
        agent_name="developer",
        instruction="Implement mechanics",
        workspace_path="/tmp/workspace/ticket_1/",
        produces=["mechanics_spec.md"],
    )
    assert "workspace" in prompt.lower()
    assert ".writing" in prompt
    assert "mechanics_spec.md" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_prompt_builder.py::test_build_prompt_with_workspace_context -v`
Expected: FAIL

- [ ] **Step 3: Update prompt builder**

Add workspace context section to the built prompt:
- Workspace path and convention explanation
- List of `.writing` convention rules
- Which files this agent should produce
- Instruction to write to `{filename}.writing` and the orchestrator will rename on completion

- [ ] **Step 4: Run all prompt builder tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_prompt_builder.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/prompt_builder.py tests/test_prompt_builder.py
git commit -m "feat: prompt builder includes workspace context and .writing convention"
```

---

### Task 8: Update Usage Routes

**Files:**
- Modify: `backend/routes/usage.py`
- Modify: `tests/test_usage.py`

- [ ] **Step 1: Write failing test**

```python
@pytest.mark.asyncio
async def test_usage_summary_from_sessions(client):
    # Insert agent_sessions with token data, verify /api/usage/summary returns correct totals
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_usage.py -v`
Expected: FAIL (old table references)

- [ ] **Step 3: Update usage queries**

Replace all `step_agents` → `agent_sessions` and `ticket_steps` → direct join in:
- `get_usage_summary()`: `SELECT SUM(input_tokens), SUM(output_tokens) FROM agent_sessions`
- `get_usage_by_project()`: Join `agent_sessions` → `tickets` → `projects`
- `get_usage_by_agent()`: Group by `agent_sessions.agent_name`

- [ ] **Step 4: Run tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_usage.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routes/usage.py tests/test_usage.py
git commit -m "feat: usage routes query agent_sessions instead of step_agents"
```

---

### Task 9: Update Runs/Agents Routes

**Files:**
- Modify: `backend/routes/runs.py` — queries `step_agents` for `GET /api/runs/{id}` and `GET /api/runs/{id}/result`
- Modify: `backend/routes/agents.py` — queries `step_agents` at lines ~84, 88, 104, 148 for `GET /api/agents/{name}/runs`
- Modify: `tests/test_agents.py`

- [ ] **Step 1: Update runs.py**

Replace all `step_agents` references with `agent_sessions`:
- `GET /api/runs/{id}` → `SELECT * FROM agent_sessions WHERE id = ?`
- `GET /api/runs/{id}/result` → read `session_log_path` from `agent_sessions`
- Update response model imports: replace `StepAgentResponse` with `SessionResponse`

- [ ] **Step 2: Update agents.py**

Replace `step_agents` joins with `agent_sessions`:
- `GET /api/agents/{name}/runs` → `SELECT * FROM agent_sessions WHERE agent_name = ?`
- Remove `ticket_steps` join (no longer exists)
- Update response model to `SessionResponse`

- [ ] **Step 3: Update frontend pages/5_agents.py**

Update run history display to use session fields instead of step_agent fields.

- [ ] **Step 4: Check ccusage.py for step_agents references**

Review `backend/routes/ccusage.py` and update if needed.

- [ ] **Step 5: Run all tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routes/runs.py backend/routes/agents.py backend/routes/ccusage.py frontend/pages/5_agents.py tests/test_agents.py
git commit -m "fix: update runs, agents, ccusage routes from step_agents to agent_sessions"
```

---

### Task 10: Frontend — Ticket Board with Sessions

**Files:**
- Modify: `frontend/pages/3_ticket_board.py`

- [ ] **Step 1: Rewrite ticket detail view**

Replace step tree view with flat session list:
- Each session card shows: agent_name, status badge, depends_on info
- Status badges: `pending` (gray), `waiting` (yellow + "waiting for X"), `running` (blue spinner), `completed` (green), `failed` (red), `cancelled` (gray strikethrough)
- Show elapsed time for running/completed sessions
- Show error_message for failed sessions

- [ ] **Step 2: Update ticket creation form**

Replace step-based form with session-based:
- Add agent selector (dropdown from `/api/agents/`)
- Per-session fields: `instruction`, `depends_on` (multi-select from other sessions' produces), `produces` (text input)
- Add/remove sessions dynamically
- "AI Decompose" button fills sessions automatically

- [ ] **Step 3: Update action buttons**

- Run button: calls `POST /api/tickets/{id}/run`
- Cancel button: calls `POST /api/tickets/{id}/cancel`
- Per-session retry: calls `POST /api/sessions/{id}/retry`

- [ ] **Step 4: Test manually**

Run: `cd /Users/user/hwiGameStudio && docker compose up --build`
Verify: Ticket board shows sessions instead of steps, creation form works

- [ ] **Step 5: Commit**

```bash
git add frontend/pages/3_ticket_board.py
git commit -m "feat: ticket board displays sessions instead of steps"
```

---

### Task 11: Frontend — Session Viewer

**Files:**
- Modify: `frontend/components/result_viewer.py`

- [ ] **Step 1: Update result viewer for sessions**

Replace `render_result_viewer(agent_run_id)` with `render_session_viewer(session_id)`:
- Fetch session metadata from `GET /api/sessions/{id}`
- Display session log from `GET /api/sessions/{id}/log` as markdown
- Show workspace documents produced by this session
- Show token usage, duration, status

- [ ] **Step 2: Test manually**

Verify session viewer renders correctly in the browser.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/result_viewer.py
git commit -m "feat: session viewer replaces agent run viewer"
```

---

### Task 12: Update Ticket Analyzer for Session Format

**Files:**
- Modify: `backend/services/ticket_analyzer.py`
- Modify: `backend/prompts/decompose_task.md` (if exists)

- [ ] **Step 1: Update decompose output format**

Change `TicketAnalyzer.decompose_task()` to return sessions instead of steps:
- Each session has `agent_name`, `instruction`, `depends_on`, `produces`
- Update the prompt template to instruct Claude to output session format

- [ ] **Step 2: Update auto-assign endpoint**

`auto_assign_ticket` should work with sessions instead of steps.

- [ ] **Step 3: Run ticket analyzer tests**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/test_ticket_analyzer.py tests/test_ticket_ai_endpoints.py -v`
Expected: ALL PASS (may need test updates)

- [ ] **Step 4: Commit**

```bash
git add backend/services/ticket_analyzer.py backend/prompts/
git commit -m "feat: ticket analyzer outputs sessions format instead of steps"
```

---

### Task 13: Update Remaining Tests

**Files:**
- Modify: `tests/test_tickets.py`
- Modify: `tests/test_tickets_endpoints.py`
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Update test_tickets.py**

Replace step-based test data with session-based. Update assertions.

- [ ] **Step 2: Update test_tickets_endpoints.py**

Update run/cancel/retry endpoint tests to work with sessions instead of steps.

- [ ] **Step 3: Update test_integration.py**

Update full workflow test to create sessions instead of steps.

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/user/hwiGameStudio && python -m pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: update all tests for session-based architecture"
```

---

### Task 14: Cleanup and Final Verification

**Files:**
- Remove any dead code referencing steps/step_agents
- Verify docker-compose build works

- [ ] **Step 1: Search for remaining step_agents/ticket_steps references**

```bash
grep -r "step_agents\|ticket_steps\|StepCreate\|StepResponse\|StepAgentCreate\|StepAgentResponse" backend/ frontend/ tests/ --include="*.py"
```

Fix any remaining references.

- [ ] **Step 2: Build and run with Docker**

```bash
cd /Users/user/hwiGameStudio && docker compose build && docker compose up -d
```

- [ ] **Step 3: Manual smoke test**

1. Create a project
2. Create a ticket with sessions (some parallel, some with dependencies)
3. Run the ticket
4. Verify sessions execute in parallel
5. Verify dependent sessions wait and start when file appears
6. Check workspace files
7. Check session logs in viewer

- [ ] **Step 4: Commit any final fixes**

```bash
git add -A
git commit -m "chore: cleanup old step references, final verification"
```
