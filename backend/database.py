import aiosqlite
import os
from contextlib import asynccontextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    engine TEXT NOT NULL DEFAULT 'godot',
    mode TEXT NOT NULL DEFAULT 'development',
    status TEXT NOT NULL DEFAULT 'active',
    config_json TEXT DEFAULT '{}',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    source TEXT NOT NULL DEFAULT 'manual',
    created_by TEXT DEFAULT '',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticket_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    step_order INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS step_agents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    step_id INTEGER NOT NULL REFERENCES ticket_steps(id),
    agent_name TEXT NOT NULL,
    cli_provider TEXT NOT NULL DEFAULT 'claude',
    instruction TEXT DEFAULT '',
    context_refs TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'pending',
    input_tokens INTEGER,
    output_tokens INTEGER,
    estimated_cost REAL,
    result_summary TEXT,
    result_path TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    retry_count INTEGER DEFAULT 0,
    pid INTEGER
);

CREATE TABLE IF NOT EXISTS cost_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_rate REAL NOT NULL,
    output_rate REAL NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cli_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    command TEXT NOT NULL,
    api_key_env TEXT NOT NULL,
    enabled BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    file_path TEXT NOT NULL,
    content TEXT DEFAULT '',
    previous_content TEXT DEFAULT '',
    updated_by TEXT DEFAULT '',
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""

SEED_PROVIDERS = """
INSERT OR IGNORE INTO cli_providers (name, command, api_key_env, enabled)
VALUES ('claude', 'claude --print', 'ANTHROPIC_API_KEY', 1);

INSERT OR IGNORE INTO cli_providers (name, command, api_key_env, enabled)
VALUES ('codex', 'codex --quiet', 'OPENAI_API_KEY', 1);
"""

SEED_COST_RATES = """
INSERT OR IGNORE INTO cost_rates (provider, model, input_rate, output_rate)
VALUES ('claude', 'opus-4', 0.015, 0.075);

INSERT OR IGNORE INTO cost_rates (provider, model, input_rate, output_rate)
VALUES ('codex', 'codex', 0.003, 0.015);
"""


async def init_db(db_path: str):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(SCHEMA)
        await db.executescript(SEED_PROVIDERS)
        await db.executescript(SEED_COST_RATES)
        await db.commit()


@asynccontextmanager
async def get_db(db_path: str = None):
    from backend.config import DATABASE_PATH
    path = db_path or DATABASE_PATH
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA busy_timeout=5000")
    try:
        yield db
    finally:
        await db.close()
