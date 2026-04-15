import pytest
import asyncio
import os
import tempfile
from backend.database import init_db, get_db

@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    os.unlink(path)

@pytest.mark.asyncio
async def test_init_db_creates_tables(db_path):
    await init_db(db_path)
    async with get_db(db_path) as db:
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
async def test_init_db_enables_wal(db_path):
    await init_db(db_path)
    async with get_db(db_path) as db:
        cursor = await db.execute("PRAGMA journal_mode")
        mode = (await cursor.fetchone())[0]
    assert mode == "wal"

@pytest.mark.asyncio
async def test_init_db_seeds_default_providers(db_path):
    await init_db(db_path)
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT name FROM cli_providers")
        providers = [row[0] for row in await cursor.fetchall()]
    assert "claude" in providers
    assert "codex" in providers

@pytest.mark.asyncio
async def test_agent_sessions_table_schema(db_path):
    await init_db(db_path)
    async with get_db(db_path) as db:
        cursor = await db.execute("PRAGMA table_info(agent_sessions)")
        columns = {row[1]: row for row in await cursor.fetchall()}

    # Check all expected columns exist
    expected_columns = [
        'id', 'ticket_id', 'agent_name', 'cli_provider', 'instruction',
        'depends_on', 'produces', 'status', 'error_message',
        'input_tokens', 'output_tokens', 'estimated_cost',
        'session_log_path', 'pid', 'started_at', 'completed_at',
        'retry_count', 'created_at'
    ]
    for col in expected_columns:
        assert col in columns, f"Column {col} missing from agent_sessions"

    # Verify key column properties
    assert columns['id'][5] == 1  # Primary key
    assert columns['ticket_id'][3] == 1  # NOT NULL
    assert columns['agent_name'][3] == 1  # NOT NULL
    assert columns['cli_provider'][3] == 1  # NOT NULL
    assert columns['instruction'][3] == 1  # NOT NULL

@pytest.mark.asyncio
async def test_agent_sessions_default_values(db_path):
    await init_db(db_path)
    async with get_db(db_path) as db:
        # Create a test project and ticket first
        await db.execute(
            "INSERT INTO projects (name, display_name) VALUES ('test', 'Test Project')"
        )
        await db.execute(
            "INSERT INTO tickets (project_id, title) VALUES (1, 'Test Ticket')"
        )
        # Insert agent_session with only required fields
        await db.execute("""
            INSERT INTO agent_sessions (ticket_id, agent_name, cli_provider, instruction)
            VALUES (1, 'test_agent', 'claude', 'test instruction')
        """)
        await db.commit()

        cursor = await db.execute("""
            SELECT depends_on, produces, status, input_tokens, output_tokens,
                   estimated_cost, retry_count, created_at
            FROM agent_sessions WHERE id=1
        """)
        row = await cursor.fetchone()

        # Verify defaults
        assert row[0] == '[]'  # depends_on
        assert row[1] == '[]'  # produces
        assert row[2] == 'pending'  # status
        assert row[3] == 0  # input_tokens
        assert row[4] == 0  # output_tokens
        assert row[5] == 0  # estimated_cost
        assert row[6] == 0  # retry_count
        assert row[7] is not None  # created_at should be set
