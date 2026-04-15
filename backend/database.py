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
VALUES ('claude', 'claude --dangerously-skip-permissions -p', 'ANTHROPIC_API_KEY', 1);

INSERT OR IGNORE INTO cli_providers (name, command, api_key_env, enabled)
VALUES ('codex', 'codex exec --skip-git-repo-check --full-auto', 'OPENAI_API_KEY', 1);

UPDATE cli_providers SET command = 'claude --dangerously-skip-permissions -p' WHERE name = 'claude';
UPDATE cli_providers SET command = 'codex exec --skip-git-repo-check --full-auto' WHERE name = 'codex';
"""

async def init_db(db_path: str):
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
        await db.executescript(SCHEMA)
        await db.executescript(SEED_PROVIDERS)
        # Fix orphaned running states from previous container restart
        await db.execute("""
            UPDATE agent_sessions SET status='failed',
                error_message='Process lost (server restart)',
                completed_at=CURRENT_TIMESTAMP
            WHERE status='running'
        """)
        await db.execute("UPDATE tickets SET status='failed', updated_at=CURRENT_TIMESTAMP WHERE status='running'")
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
