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
    assert "ticket_steps" in tables
    assert "step_agents" in tables
    assert "cli_providers" in tables
    assert "cost_rates" in tables
    assert "documents" in tables

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
