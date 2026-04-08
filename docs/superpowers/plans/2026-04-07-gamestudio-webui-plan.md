# Game Studio Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Web UI + orchestration platform for gamestudio-subagents, enabling ticket-based game development with multi-CLI AI agents.

**Architecture:** FastAPI backend + Streamlit frontend, SQLite (WAL mode) for state, subprocess-based CLI execution with temp file prompt delivery. Tickets contain multi-step pipelines with parallel/sequential agent execution.

**Tech Stack:** Python 3.11+, FastAPI, Streamlit, SQLite, aiosqlite, Docker Compose

**Spec:** `docs/superpowers/specs/2026-04-07-gamestudio-webui-design.md`

---

## File Map

### Backend

| File | Responsibility |
|------|---------------|
| `backend/main.py` | FastAPI app init, middleware, router includes, startup (DB init) |
| `backend/config.py` | Environment config (DB path, backend URL, paths) |
| `backend/database.py` | SQLite connection, WAL mode, schema migration, busy_timeout |
| `backend/models/project.py` | Project Pydantic schemas (request/response) |
| `backend/models/ticket.py` | Ticket, TicketStep, StepAgent schemas |
| `backend/models/provider.py` | CLIProvider, CostRate schemas |
| `backend/models/document.py` | Document schemas |
| `backend/models/common.py` | PaginatedResponse, shared schemas |
| `backend/routes/projects.py` | Project CRUD + freeze/resume/startover |
| `backend/routes/tickets.py` | Ticket CRUD + assign/run/cancel/retry + from-diff |
| `backend/routes/agents.py` | Agent list/read/edit (filesystem-based) + per-agent run history |
| `backend/routes/runs.py` | Run detail + result file serving |
| `backend/routes/documents.py` | Document CRUD with diff detection |
| `backend/routes/providers.py` | CLI provider list/update |
| `backend/routes/usage.py` | Token/cost aggregation queries |
| `backend/services/cli_runner.py` | CLI abstraction, temp file prompt, subprocess exec |
| `backend/services/pipeline_executor.py` | Step-by-step execution, parallel/sequential, cancel/retry |
| `backend/services/prompt_builder.py` | Assemble prompt from agent md + config + ticket + instruction |
| `backend/services/ticket_analyzer.py` | AI-powered ticket decomposition and diff analysis |
| `backend/services/token_parser.py` | Parse CLI output for token counts, calculate costs |
| `backend/prompts/decompose_task.md` | Prompt template for natural language → ticket decomposition |
| `backend/prompts/analyze_diff.md` | Prompt template for document diff → impact analysis |
| `backend/requirements.txt` | Python dependencies |

### Frontend

| File | Responsibility |
|------|---------------|
| `frontend/app.py` | Streamlit main entry, sidebar menu, API client config |
| `frontend/api_client.py` | Wrapper for all backend API calls |
| `frontend/pages/1_dashboard.py` | Project list, status overview, create project |
| `frontend/pages/2_project_detail.py` | Single project: info, tickets, costs, results, actions |
| `frontend/pages/3_ticket_board.py` | Kanban board (open/assigned/running/completed) |
| `frontend/pages/4_ticket_create.py` | Manual + AI auto ticket creation with pipeline editor |
| `frontend/pages/5_agents.py` | Agent list + markdown editor |
| `frontend/pages/6_usage.py` | Cost monitoring dashboard |
| `frontend/pages/7_settings.py` | CLI provider settings + cost rates |
| `frontend/components/pipeline_editor.py` | Step/agent pipeline builder UI component |
| `frontend/components/result_viewer.py` | Markdown result rendering + file path display |
| `frontend/requirements.txt` | Python dependencies |

### Infrastructure

| File | Responsibility |
|------|---------------|
| `docker-compose.yml` | Backend + frontend service definitions |
| `Dockerfile.backend` | Backend image with CLI tools installed |
| `Dockerfile.frontend` | Frontend image |
| `.env.example` | API key template |

---

## Task 1: Project Scaffolding & Database

**Files:**
- Create: `backend/__init__.py`
- Create: `backend/main.py`
- Create: `backend/config.py`
- Create: `backend/database.py`
- Create: `backend/models/__init__.py`
- Create: `backend/models/common.py`
- Create: `backend/requirements.txt`
- Create: `frontend/__init__.py`
- Create: `frontend/app.py`
- Create: `frontend/api_client.py`
- Create: `frontend/requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/test_database.py`
- Create: `.env.example`

- [ ] **Step 1: Create backend requirements.txt**

```
# backend/requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
aiosqlite==0.20.0
pydantic==2.9.0
python-dotenv==1.0.1
httpx==0.27.0
```

- [ ] **Step 2: Create frontend requirements.txt**

```
# frontend/requirements.txt
streamlit==1.38.0
requests==2.32.0
```

- [ ] **Step 3: Create .env.example**

```env
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
DATABASE_PATH=./data/studio.db
BACKEND_URL=http://localhost:8000
AGENTS_DIR=./agents
PROJECTS_DIR=./projects
```

- [ ] **Step 4: Create backend/config.py**

```python
# backend/config.py
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/studio.db")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
AGENTS_DIR = os.getenv("AGENTS_DIR", "./agents")
PROJECTS_DIR = os.getenv("PROJECTS_DIR", "./projects")
```

- [ ] **Step 5: Write failing test for database init**

```python
# tests/test_database.py
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
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd /Users/ad03159868/Downloads/Claude_lab/hwire && python -m pytest tests/test_database.py -v`
Expected: FAIL (module not found)

- [ ] **Step 7: Create backend/database.py with schema + WAL**

```python
# backend/database.py
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
```

- [ ] **Step 8: Create backend/models/common.py**

```python
# backend/models/common.py
from pydantic import BaseModel
from typing import Generic, TypeVar, List

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    per_page: int
```

- [ ] **Step 9: Create backend/main.py**

```python
# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.config import DATABASE_PATH
from backend.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DATABASE_PATH)
    yield

app = FastAPI(title="Game Studio Sub-Agents", version="0.1.0", lifespan=lifespan)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 10: Create minimal frontend/app.py**

```python
# frontend/app.py
import streamlit as st

st.set_page_config(page_title="Game Studio", page_icon="🎮", layout="wide")
st.title("Game Studio Sub-Agents")
st.sidebar.success("Select a page above.")
```

- [ ] **Step 11: Create frontend/api_client.py**

```python
# frontend/api_client.py
import requests
import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

def get(path: str, params: dict = None):
    resp = requests.get(f"{BACKEND_URL}{path}", params=params)
    resp.raise_for_status()
    return resp.json()

def post(path: str, json: dict = None):
    resp = requests.post(f"{BACKEND_URL}{path}", json=json)
    resp.raise_for_status()
    return resp.json()

def put(path: str, json: dict = None):
    resp = requests.put(f"{BACKEND_URL}{path}", json=json)
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `cd /Users/ad03159868/Downloads/Claude_lab/hwire && python -m pytest tests/test_database.py -v`
Expected: All 3 tests PASS

- [ ] **Step 13: Create __init__.py files**

Create empty `__init__.py` files for all Python packages:
- `backend/__init__.py`
- `backend/models/__init__.py`
- `backend/routes/__init__.py`
- `backend/services/__init__.py`
- `frontend/__init__.py`
- `frontend/pages/__init__.py`
- `frontend/components/__init__.py`
- `tests/__init__.py`

- [ ] **Step 14: Commit**

```bash
git add backend/ frontend/ tests/ .env.example
git commit -m "feat: project scaffolding with database schema and basic FastAPI/Streamlit setup"
```

---

## Task 2: Project CRUD API + Frontend Dashboard

**Files:**
- Create: `backend/models/project.py`
- Create: `backend/routes/projects.py`
- Create: `tests/test_projects.py`
- Create: `frontend/pages/1_dashboard.py`
- Create: `frontend/pages/2_project_detail.py`
- Modify: `backend/main.py` (add router)

- [ ] **Step 1: Write failing tests for project API**

```python
# tests/test_projects.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
import tempfile, os

@pytest.fixture(autouse=True)
async def setup_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    await init_db(db_path)
    yield
    os.unlink(db_path)

@pytest.mark.asyncio
async def test_create_project():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/projects", json={
            "name": "my-rpg",
            "display_name": "My RPG Game",
            "engine": "godot",
            "mode": "development"
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "my-rpg"
    assert data["status"] == "active"

@pytest.mark.asyncio
async def test_list_projects():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/projects", json={
            "name": "game1", "display_name": "Game 1", "engine": "godot", "mode": "design"
        })
        resp = await client.get("/api/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1

@pytest.mark.asyncio
async def test_freeze_and_resume_project():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post("/api/projects", json={
            "name": "freezetest", "display_name": "Freeze Test", "engine": "unity", "mode": "prototype"
        })
        pid = create.json()["id"]
        freeze = await client.post(f"/api/projects/{pid}/freeze")
        assert freeze.json()["status"] == "frozen"
        resume = await client.post(f"/api/projects/{pid}/resume")
        assert resume.json()["status"] == "active"

@pytest.mark.asyncio
async def test_startover_project_cancels_active_tickets():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post("/api/projects", json={
            "name": "startovertest", "display_name": "Startover Test", "engine": "godot", "mode": "development"
        })
        pid = create.json()["id"]
        await client.post("/api/tickets", json={
            "project_id": pid, "title": "Active ticket", "steps": []
        })
        result = await client.post(f"/api/projects/{pid}/startover")
        assert result.json()["status"] == "active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_projects.py -v`
Expected: FAIL

- [ ] **Step 3: Create backend/models/project.py**

```python
# backend/models/project.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str
    display_name: str
    engine: str = "godot"
    mode: str = "development"
    config_json: str = "{}"

class ProjectUpdate(BaseModel):
    display_name: Optional[str] = None
    engine: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    config_json: Optional[str] = None

class ProjectResponse(BaseModel):
    id: int
    name: str
    display_name: str
    engine: str
    mode: str
    status: str
    config_json: str
    created_at: str
    updated_at: str
```

- [ ] **Step 4: Create backend/routes/projects.py**

```python
# backend/routes/projects.py
from fastapi import APIRouter, HTTPException, Query
from backend.database import get_db
from backend.models.project import ProjectCreate, ProjectUpdate, ProjectResponse
from backend.models.common import PaginatedResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=100)):
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM projects")
        total = (await cursor.fetchone())[0]
        offset = (page - 1) * per_page
        cursor = await db.execute(
            "SELECT * FROM projects ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        )
        rows = await cursor.fetchall()
    items = [ProjectResponse(**dict(r)) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)

@router.post("", response_model=ProjectResponse)
async def create_project(project: ProjectCreate):
    async with get_db() as db:
        try:
            cursor = await db.execute(
                "INSERT INTO projects (name, display_name, engine, mode, config_json) VALUES (?, ?, ?, ?, ?)",
                (project.name, project.display_name, project.engine, project.mode, project.config_json)
            )
            await db.commit()
            project_id = cursor.lastrowid
        except Exception:
            raise HTTPException(400, "Project name already exists")
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
    return ProjectResponse(**dict(row))

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return ProjectResponse(**dict(row))

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: int, update: ProjectUpdate):
    async with get_db() as db:
        fields = {k: v for k, v in update.model_dump().items() if v is not None}
        if not fields:
            raise HTTPException(400, "No fields to update")
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [project_id]
        await db.execute(
            f"UPDATE projects SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "Project not found")
    return ProjectResponse(**dict(row))

@router.post("/{project_id}/freeze", response_model=ProjectResponse)
async def freeze_project(project_id: int):
    async with get_db() as db:
        await db.execute(
            "UPDATE projects SET status = 'frozen', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
    return ProjectResponse(**dict(row))

@router.post("/{project_id}/resume", response_model=ProjectResponse)
async def resume_project(project_id: int):
    async with get_db() as db:
        await db.execute(
            "UPDATE projects SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
    return ProjectResponse(**dict(row))

@router.post("/{project_id}/startover", response_model=ProjectResponse)
async def startover_project(project_id: int):
    async with get_db() as db:
        # Archive existing tickets
        await db.execute(
            "UPDATE tickets SET status = 'cancelled' WHERE project_id = ? AND status NOT IN ('completed', 'cancelled')",
            (project_id,)
        )
        await db.execute(
            "UPDATE projects SET status = 'active', mode = 'development', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
        await db.commit()
        cursor = await db.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = await cursor.fetchone()
    return ProjectResponse(**dict(row))
```

- [ ] **Step 5: Add router to main.py**

Add to `backend/main.py`:
```python
from backend.routes.projects import router as projects_router
app.include_router(projects_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_projects.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Create frontend/pages/1_dashboard.py**

```python
# frontend/pages/1_dashboard.py
import streamlit as st
from frontend.api_client import get, post

st.set_page_config(page_title="Dashboard", page_icon="📁", layout="wide")
st.title("📁 프로젝트 대시보드")

# Create project form
with st.expander("+ 새 프로젝트"):
    with st.form("create_project"):
        name = st.text_input("프로젝트 슬러그", placeholder="my-rpg-game")
        display_name = st.text_input("표시 이름", placeholder="My RPG Game")
        engine = st.selectbox("엔진", ["godot", "unity", "unreal"])
        mode = st.selectbox("모드", ["design", "prototype", "development"])
        if st.form_submit_button("생성"):
            try:
                result = post("/api/projects", json={
                    "name": name, "display_name": display_name,
                    "engine": engine, "mode": mode
                })
                st.success(f"프로젝트 '{display_name}' 생성됨!")
                st.rerun()
            except Exception as e:
                st.error(f"생성 실패: {e}")

# Project list
STATUS_ICONS = {
    "active": "🟢", "paused": "🟡", "frozen": "🔵",
    "completed": "✅", "cancelled": "❌"
}

try:
    data = get("/api/projects")
    projects = data.get("items", [])
    if not projects:
        st.info("프로젝트가 없습니다. 위에서 새 프로젝트를 생성하세요.")
    for p in projects:
        icon = STATUS_ICONS.get(p["status"], "⚪")
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        col1.markdown(f"**{icon} {p['display_name']}** (`{p['name']}`)")
        col2.text(p["engine"])
        col3.text(p["mode"])
        col4.text(p["status"])
except Exception as e:
    st.error(f"백엔드 연결 실패: {e}")
```

- [ ] **Step 8: Create frontend/pages/2_project_detail.py**

```python
# frontend/pages/2_project_detail.py
import streamlit as st
from frontend.api_client import get, post

st.set_page_config(page_title="Project Detail", page_icon="📁", layout="wide")
st.title("📁 프로젝트 상세")

# Project selector
try:
    data = get("/api/projects")
    projects = data.get("items", [])
    if not projects:
        st.warning("프로젝트가 없습니다.")
        st.stop()
    
    options = {p["id"]: f"{p['display_name']} ({p['name']})" for p in projects}
    selected_id = st.selectbox("프로젝트 선택", options.keys(), format_func=lambda x: options[x])
    
    project = get(f"/api/projects/{selected_id}")
    
    st.subheader("정보")
    col1, col2, col3 = st.columns(3)
    col1.metric("엔진", project["engine"])
    col2.metric("모드", project["mode"])
    col3.metric("상태", project["status"])
    
    # Actions
    st.subheader("조작")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("▶️ 재개"):
            post(f"/api/projects/{selected_id}/resume")
            st.rerun()
    with col2:
        if st.button("⏸️ 동결"):
            post(f"/api/projects/{selected_id}/freeze")
            st.rerun()
    with col3:
        if st.button("🔄 리셋"):
            post(f"/api/projects/{selected_id}/startover")
            st.rerun()
            
except Exception as e:
    st.error(f"오류: {e}")
```

- [ ] **Step 9: Commit**

```bash
git add backend/ frontend/ tests/
git commit -m "feat: project CRUD API with FastAPI + Streamlit dashboard and detail pages"
```

---

## Task 3: Ticket CRUD API + Ticket Board UI

**Files:**
- Create: `backend/models/ticket.py`
- Create: `backend/routes/tickets.py`
- Create: `tests/test_tickets.py`
- Create: `frontend/pages/3_ticket_board.py`
- Create: `frontend/pages/4_ticket_create.py`
- Create: `frontend/components/__init__.py`
- Create: `frontend/components/pipeline_editor.py`
- Modify: `backend/main.py` (add router)

- [ ] **Step 1: Write failing tests for ticket API**

```python
# tests/test_tickets.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
import tempfile, os

@pytest.fixture(autouse=True)
async def setup_db(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    monkeypatch.setenv("DATABASE_PATH", db_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    await init_db(db_path)
    yield
    os.unlink(db_path)

@pytest.fixture
async def project_id(setup_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/projects", json={
            "name": "test-proj", "display_name": "Test", "engine": "godot", "mode": "development"
        })
    return resp.json()["id"]

@pytest.mark.asyncio
async def test_create_ticket_with_steps(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/tickets", json={
            "project_id": project_id,
            "title": "Build combat system",
            "description": "Implement full combat",
            "steps": [
                {
                    "step_order": 1,
                    "agents": [
                        {"agent_name": "sr_game_designer", "cli_provider": "claude", "instruction": "Design combat"},
                        {"agent_name": "market_analyst", "cli_provider": "claude", "instruction": "Analyze competitors"}
                    ]
                },
                {
                    "step_order": 2,
                    "agents": [
                        {"agent_name": "mechanics_developer", "cli_provider": "codex", "instruction": "Implement combat logic"}
                    ]
                }
            ]
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Build combat system"
    assert data["status"] == "open"

@pytest.mark.asyncio
async def test_list_tickets_by_project(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/tickets", json={
            "project_id": project_id, "title": "Task 1", "steps": []
        })
        resp = await client.get(f"/api/tickets/?project_id={project_id}")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1

@pytest.mark.asyncio
async def test_get_ticket_detail(project_id):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create = await client.post("/api/tickets", json={
            "project_id": project_id, "title": "Detail test",
            "steps": [{"step_order": 1, "agents": [
                {"agent_name": "qa_agent", "cli_provider": "claude", "instruction": "Test"}
            ]}]
        })
        ticket_id = create.json()["id"]
        resp = await client.get(f"/api/tickets/{ticket_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps"]) == 1
    assert len(data["steps"][0]["agents"]) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tickets.py -v`
Expected: FAIL

- [ ] **Step 3: Create backend/models/ticket.py**

```python
# backend/models/ticket.py
from pydantic import BaseModel
from typing import Optional, List

class StepAgentCreate(BaseModel):
    agent_name: str
    cli_provider: str = "claude"
    instruction: str = ""
    context_refs: List[str] = []  # Serialized to JSON string for DB storage via json.dumps()

class StepCreate(BaseModel):
    step_order: int
    agents: List[StepAgentCreate] = []

class TicketCreate(BaseModel):
    project_id: int
    title: str
    description: str = ""
    source: str = "manual"
    created_by: str = ""
    steps: List[StepCreate] = []

class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None

class StepAgentResponse(BaseModel):
    id: int
    agent_name: str
    cli_provider: str
    instruction: str
    context_refs: str
    status: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    result_summary: Optional[str] = None
    result_path: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0

class StepResponse(BaseModel):
    id: int
    step_order: int
    status: str
    agents: List[StepAgentResponse] = []

class TicketResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    status: str
    source: str
    created_by: str
    created_at: str
    updated_at: str
    steps: List[StepResponse] = []

class TicketSummary(BaseModel):
    id: int
    project_id: int
    title: str
    status: str
    source: str
    created_at: str
```

- [ ] **Step 4: Create backend/routes/tickets.py with CRUD**

```python
# backend/routes/tickets.py
import json
from fastapi import APIRouter, HTTPException, Query
from backend.database import get_db
from backend.models.ticket import (
    TicketCreate, TicketUpdate, TicketResponse, TicketSummary,
    StepResponse, StepAgentResponse
)
from backend.models.common import PaginatedResponse

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

@router.get("", response_model=PaginatedResponse[TicketSummary])
async def list_tickets(
    project_id: int = None, page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=100)
):
    async with get_db() as db:
        where = "WHERE project_id = ?" if project_id else ""
        params = (project_id,) if project_id else ()
        cursor = await db.execute(f"SELECT COUNT(*) FROM tickets {where}", params)
        total = (await cursor.fetchone())[0]
        offset = (page - 1) * per_page
        cursor = await db.execute(
            f"SELECT * FROM tickets {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, per_page, offset)
        )
        rows = await cursor.fetchall()
    items = [TicketSummary(**dict(r)) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)

@router.post("", response_model=TicketResponse)
async def create_ticket(ticket: TicketCreate):
    async with get_db() as db:
        cursor = await db.execute(
            "INSERT INTO tickets (project_id, title, description, source, created_by) VALUES (?, ?, ?, ?, ?)",
            (ticket.project_id, ticket.title, ticket.description, ticket.source, ticket.created_by)
        )
        ticket_id = cursor.lastrowid

        for step in ticket.steps:
            step_cursor = await db.execute(
                "INSERT INTO ticket_steps (ticket_id, step_order) VALUES (?, ?)",
                (ticket_id, step.step_order)
            )
            step_id = step_cursor.lastrowid
            for agent in step.agents:
                await db.execute(
                    """INSERT INTO step_agents
                    (step_id, agent_name, cli_provider, instruction, context_refs)
                    VALUES (?, ?, ?, ?, ?)""",
                    (step_id, agent.agent_name, agent.cli_provider,
                     agent.instruction, json.dumps(agent.context_refs))
                )

        if ticket.steps:
            await db.execute(
                "UPDATE tickets SET status = 'assigned' WHERE id = ?", (ticket_id,)
            )
        await db.commit()
    return await _get_ticket_detail(ticket_id)

@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: int):
    return await _get_ticket_detail(ticket_id)

@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: int, update: TicketUpdate):
    async with get_db() as db:
        fields = {k: v for k, v in update.model_dump().items() if v is not None}
        if not fields:
            raise HTTPException(400, "No fields to update")
        sets = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [ticket_id]
        await db.execute(
            f"UPDATE tickets SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", values
        )
        await db.commit()
    return await _get_ticket_detail(ticket_id)

@router.post("/{ticket_id}/assign")
async def assign_ticket(ticket_id: int, steps: list[dict]):
    """Manual agent assignment. Expects list of steps with agents."""
    async with get_db() as db:
        # Clear existing steps
        cursor = await db.execute(
            "SELECT id FROM ticket_steps WHERE ticket_id = ?", (ticket_id,)
        )
        old_steps = await cursor.fetchall()
        for old_step in old_steps:
            await db.execute("DELETE FROM step_agents WHERE step_id = ?", (old_step[0],))
        await db.execute("DELETE FROM ticket_steps WHERE ticket_id = ?", (ticket_id,))

        # Insert new steps and agents
        for step_data in steps:
            step_cursor = await db.execute(
                "INSERT INTO ticket_steps (ticket_id, step_order) VALUES (?, ?)",
                (ticket_id, step_data["step_order"])
            )
            step_id = step_cursor.lastrowid
            for agent in step_data.get("agents", []):
                await db.execute(
                    """INSERT INTO step_agents
                    (step_id, agent_name, cli_provider, instruction, context_refs)
                    VALUES (?, ?, ?, ?, ?)""",
                    (step_id, agent["agent_name"], agent.get("cli_provider", "claude"),
                     agent.get("instruction", ""), json.dumps(agent.get("context_refs", [])))
                )

        await db.execute(
            "UPDATE tickets SET status = 'assigned', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (ticket_id,)
        )
        await db.commit()
    return await _get_ticket_detail(ticket_id)


async def _get_ticket_detail(ticket_id: int) -> TicketResponse:
    """Helper: fetch ticket with all steps and agents joined."""
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        ticket_row = await cursor.fetchone()
        if not ticket_row:
            raise HTTPException(404, "Ticket not found")

        cursor = await db.execute(
            "SELECT * FROM ticket_steps WHERE ticket_id = ? ORDER BY step_order", (ticket_id,)
        )
        step_rows = await cursor.fetchall()

        steps = []
        for step_row in step_rows:
            cursor = await db.execute(
                "SELECT * FROM step_agents WHERE step_id = ?", (step_row["id"],)
            )
            agent_rows = await cursor.fetchall()
            agents = [StepAgentResponse(**dict(a)) for a in agent_rows]
            steps.append(StepResponse(**dict(step_row), agents=agents))

    return TicketResponse(**dict(ticket_row), steps=steps)
```

- [ ] **Step 5: Add tickets router to main.py**

```python
from backend.routes.tickets import router as tickets_router
app.include_router(tickets_router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_tickets.py -v`
Expected: All 3 tests PASS

- [ ] **Step 7: Create frontend/components/pipeline_editor.py**

```python
# frontend/components/pipeline_editor.py
import streamlit as st
from frontend.api_client import get

def render_pipeline_editor():
    """Renders a step/agent pipeline builder. Returns list of steps with agents."""
    # Fetch available agents
    try:
        agents = get("/api/agents")
        agent_names = [a["name"] for a in agents]
    except Exception:
        agent_names = []

    providers = ["claude", "codex"]

    if "pipeline_steps" not in st.session_state:
        st.session_state.pipeline_steps = [{"agents": [{}]}]

    steps = st.session_state.pipeline_steps

    for i, step in enumerate(steps):
        st.markdown(f"**Step {i + 1}** {'(병렬)' if len(step['agents']) > 1 else '(순차)'}")
        for j, agent in enumerate(step["agents"]):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                agent["agent_name"] = st.selectbox(
                    "에이전트", agent_names, key=f"agent_{i}_{j}"
                ) if agent_names else st.text_input("에이전트 이름", key=f"agent_{i}_{j}")
            with col2:
                agent["cli_provider"] = st.selectbox(
                    "CLI", providers, key=f"cli_{i}_{j}"
                )
            with col3:
                if st.button("❌", key=f"del_agent_{i}_{j}"):
                    step["agents"].pop(j)
                    st.rerun()
            agent["instruction"] = st.text_area(
                "지시 사항", key=f"instr_{i}_{j}", height=80
            )

        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"+ 에이전트 추가 (Step {i + 1})", key=f"add_agent_{i}"):
                step["agents"].append({})
                st.rerun()
        with col2:
            if len(steps) > 1 and st.button(f"Step {i + 1} 삭제", key=f"del_step_{i}"):
                steps.pop(i)
                st.rerun()
        st.divider()

    if st.button("+ Step 추가"):
        steps.append({"agents": [{}]})
        st.rerun()

    return steps
```

- [ ] **Step 8: Create frontend/pages/4_ticket_create.py**

```python
# frontend/pages/4_ticket_create.py
import streamlit as st
from frontend.api_client import get, post
from frontend.components.pipeline_editor import render_pipeline_editor

st.set_page_config(page_title="Create Ticket", page_icon="🎫", layout="wide")
st.title("🎫 티켓 생성")

try:
    projects = get("/api/projects")["items"]
    if not projects:
        st.warning("먼저 프로젝트를 생성하세요.")
        st.stop()

    project_options = {p["id"]: p["display_name"] for p in projects}
    project_id = st.selectbox("프로젝트", project_options.keys(), format_func=lambda x: project_options[x])

    tab1, tab2 = st.tabs(["✏️ 직접 입력", "🤖 AI 자동 생성"])

    with tab1:
        title = st.text_input("티켓 제목")
        description = st.text_area("설명")
        st.subheader("파이프라인 구성")
        steps = render_pipeline_editor()

        if st.button("🎫 티켓 생성"):
            formatted_steps = []
            for i, step in enumerate(steps):
                formatted_agents = []
                for agent in step["agents"]:
                    if agent.get("agent_name"):
                        formatted_agents.append({
                            "agent_name": agent["agent_name"],
                            "cli_provider": agent.get("cli_provider", "claude"),
                            "instruction": agent.get("instruction", ""),
                            "context_refs": []
                        })
                if formatted_agents:
                    formatted_steps.append({"step_order": i + 1, "agents": formatted_agents})

            result = post("/api/tickets", json={
                "project_id": project_id,
                "title": title,
                "description": description,
                "steps": formatted_steps
            })
            st.success(f"티켓 #{result['id']} 생성됨!")

    with tab2:
        st.info("AI 자동 생성 기능은 Task 7에서 구현됩니다.")
        ai_input = st.text_area("자연어로 지시하세요", placeholder="전투 시스템 구현해줘")
        st.button("🔍 분석", disabled=True)

except Exception as e:
    st.error(f"오류: {e}")
```

- [ ] **Step 9: Create frontend/pages/3_ticket_board.py**

```python
# frontend/pages/3_ticket_board.py
import streamlit as st
from frontend.api_client import get

st.set_page_config(page_title="Ticket Board", page_icon="🎫", layout="wide")
st.title("🎫 티켓 보드")

try:
    projects = get("/api/projects")["items"]
    if not projects:
        st.warning("프로젝트가 없습니다.")
        st.stop()

    project_options = {p["id"]: p["display_name"] for p in projects}
    project_id = st.selectbox("프로젝트", project_options.keys(), format_func=lambda x: project_options[x])

    tickets = get(f"/api/tickets/?project_id={project_id}")["items"]

    STATUS_COLUMNS = ["open", "assigned", "running", "completed"]
    cols = st.columns(len(STATUS_COLUMNS))

    for col, status in zip(cols, STATUS_COLUMNS):
        with col:
            st.subheader(status.upper())
            filtered = [t for t in tickets if t["status"] == status]
            if not filtered:
                st.caption("없음")
            for ticket in filtered:
                with st.container(border=True):
                    st.markdown(f"**#{ticket['id']}** {ticket['title']}")
                    st.caption(f"{ticket['source']} | {ticket['created_at'][:10]}")
                    if st.button("상세", key=f"detail_{ticket['id']}"):
                        st.session_state["selected_ticket"] = ticket["id"]

    # Ticket detail expander
    if "selected_ticket" in st.session_state:
        ticket = get(f"/api/tickets/{st.session_state['selected_ticket']}")
        st.divider()
        st.subheader(f"#{ticket['id']} {ticket['title']}")
        st.write(ticket["description"])
        for step in ticket.get("steps", []):
            st.markdown(f"**Step {step['step_order']}** [{step['status']}]")
            for agent in step.get("agents", []):
                icon = {"pending": "⏳", "running": "🔄", "completed": "✅", "failed": "❌"}.get(agent["status"], "⚪")
                st.write(f"  {icon} {agent['agent_name']} ({agent['cli_provider']}) - {agent['status']}")
                if agent.get("result_summary"):
                    st.caption(agent["result_summary"])

except Exception as e:
    st.error(f"오류: {e}")
```

- [ ] **Step 10: Commit**

```bash
git add backend/ frontend/ tests/
git commit -m "feat: ticket CRUD API with step/agent pipeline + kanban board UI"
```

---

## Task 4: Agent Management API + Editor UI

**Files:**
- Create: `backend/routes/agents.py`
- Create: `tests/test_agents.py`
- Create: `frontend/pages/5_agents.py`
- Modify: `backend/main.py` (add router)

- [ ] **Step 1: Write failing tests for agent API**

Test listing agents (scans `agents/` directory), reading agent md content, writing agent md content, and per-agent run history.

```python
# tests/test_agents.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import init_db
from backend.config import AGENTS_DIR
import tempfile, os, shutil

@pytest.fixture(autouse=True)
async def setup(monkeypatch, tmp_path):
    # Temp DB
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("backend.config.DATABASE_PATH", db_path)
    await init_db(db_path)
    # Temp agents dir with a test agent
    agents_dir = str(tmp_path / "agents")
    os.makedirs(agents_dir)
    with open(os.path.join(agents_dir, "test_agent.md"), "w") as f:
        f.write("# Test Agent\nYou are a test agent.")
    monkeypatch.setattr("backend.config.AGENTS_DIR", agents_dir)
    yield

@pytest.mark.asyncio
async def test_list_agents():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert any(a["name"] == "test_agent" for a in agents)

@pytest.mark.asyncio
async def test_get_agent_content():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents/test_agent")
    assert resp.status_code == 200
    assert "Test Agent" in resp.json()["content"]

@pytest.mark.asyncio
async def test_update_agent_content():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.put("/api/agents/test_agent", json={"content": "# Updated Agent"})
    assert resp.status_code == 200
    assert "Updated Agent" in resp.json()["content"]

@pytest.mark.asyncio
async def test_get_agent_runs():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/agents/test_agent/runs")
    assert resp.status_code == 200
    assert resp.json()["items"] == []  # No runs yet
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_agents.py -v`
Expected: FAIL

- [ ] **Step 3: Create backend/routes/agents.py**

```python
# backend/routes/agents.py
import os
import glob
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.config import AGENTS_DIR
from backend.database import get_db
from backend.models.common import PaginatedResponse
from backend.models.ticket import StepAgentResponse

router = APIRouter(prefix="/api/agents", tags=["agents"])

class AgentInfo(BaseModel):
    name: str
    file_path: str

class AgentContent(BaseModel):
    name: str
    content: str

class AgentContentUpdate(BaseModel):
    content: str

@router.get("", response_model=list[AgentInfo])
async def list_agents():
    md_files = glob.glob(os.path.join(AGENTS_DIR, "*.md"))
    agents = []
    for f in sorted(md_files):
        name = os.path.splitext(os.path.basename(f))[0]
        if name.lower() == "readme":
            continue
        agents.append(AgentInfo(name=name, file_path=f))
    return agents

@router.get("/{name}", response_model=AgentContent)
async def get_agent(name: str):
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise HTTPException(404, f"Agent '{name}' not found")
    with open(path, "r") as f:
        content = f.read()
    return AgentContent(name=name, content=content)

@router.put("/{name}", response_model=AgentContent)
async def update_agent(name: str, update: AgentContentUpdate):
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise HTTPException(404, f"Agent '{name}' not found")
    with open(path, "w") as f:
        f.write(update.content)
    return AgentContent(name=name, content=update.content)

@router.get("/{name}/runs", response_model=PaginatedResponse[StepAgentResponse])
async def get_agent_runs(name: str, page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=100)):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM step_agents WHERE agent_name = ?", (name,)
        )
        total = (await cursor.fetchone())[0]
        offset = (page - 1) * per_page
        cursor = await db.execute(
            "SELECT * FROM step_agents WHERE agent_name = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (name, per_page, offset)
        )
        rows = await cursor.fetchall()
    items = [StepAgentResponse(**dict(r)) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)
```

- [ ] **Step 4: Add router to main.py**

```python
from backend.routes.agents import router as agents_router
app.include_router(agents_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_agents.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Create frontend/pages/5_agents.py**

```python
# frontend/pages/5_agents.py
import streamlit as st
from frontend.api_client import get, put

st.set_page_config(page_title="Agents", page_icon="🤖", layout="wide")
st.title("🤖 에이전트 관리")

try:
    agents = get("/api/agents")
    if not agents:
        st.info("에이전트가 없습니다.")
        st.stop()

    agent_names = [a["name"] for a in agents]
    selected = st.selectbox("에이전트 선택", agent_names)

    agent = get(f"/api/agents/{selected}")

    st.subheader(f"📝 {selected}.md")
    content = st.text_area("내용", value=agent["content"], height=400)

    if st.button("💾 저장"):
        result = put(f"/api/agents/{selected}", json={"content": content})
        st.success("저장됨!")

    # Run history
    st.subheader("실행 이력")
    runs = get(f"/api/agents/{selected}/runs")
    if runs["items"]:
        for run in runs["items"]:
            st.write(f"- [{run['status']}] {run.get('started_at', 'N/A')} | 토큰: {run.get('input_tokens', '?')}/{run.get('output_tokens', '?')}")
    else:
        st.caption("아직 실행 이력이 없습니다.")

except Exception as e:
    st.error(f"오류: {e}")
```

- [ ] **Step 7: Commit**

```bash
git add backend/ frontend/ tests/
git commit -m "feat: agent management API with filesystem-based md editor"
```

---

## Task 5: CLI Runner + Pipeline Executor + Token Parser

**Files:**
- Create: `backend/services/cli_runner.py`
- Create: `backend/services/prompt_builder.py`
- Create: `backend/services/pipeline_executor.py`
- Create: `backend/services/token_parser.py`
- Create: `tests/test_cli_runner.py`
- Create: `tests/test_token_parser.py`
- Create: `tests/test_pipeline_executor.py`
- Modify: `backend/routes/tickets.py` (add run/cancel/retry endpoints)

- [ ] **Step 1: Write failing tests for token_parser**

```python
# tests/test_token_parser.py
from backend.services.token_parser import parse_claude_output, parse_codex_output, calculate_cost

def test_parse_claude_output():
    output = "... Total tokens: input=8230, output=3120 ..."
    result = parse_claude_output(output)
    assert result["input_tokens"] == 8230
    assert result["output_tokens"] == 3120

def test_parse_claude_output_failure():
    result = parse_claude_output("no token info here")
    assert result["input_tokens"] is None

def test_calculate_cost():
    cost = calculate_cost(8230, 3120, input_rate=0.015, output_rate=0.075)
    # (8230/1000 * 0.015) + (3120/1000 * 0.075) = 0.12345 + 0.234 = 0.35745
    assert abs(cost - 0.35745) < 0.0001
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement token_parser.py**

Regex-based parsing for Claude and Codex output formats. `calculate_cost()` function.

- [ ] **Step 4: Run token_parser tests to verify they pass**

- [ ] **Step 5: Write failing tests for prompt_builder**

Test that prompt is assembled correctly from agent md + project config + ticket + instruction + context refs.

- [ ] **Step 6: Implement prompt_builder.py**

Reads agent md file, reads project-config.json, assembles full prompt string.

- [ ] **Step 7: Run prompt_builder tests to verify they pass**

- [ ] **Step 8: Write failing tests for cli_runner**

Test with a mock subprocess (don't actually call Claude/Codex). Verify temp file creation/cleanup, PID capture.

- [ ] **Step 9: Implement cli_runner.py**

`CLIRunner.run()`: write prompt to temp file, subprocess exec, capture stdout/stderr, parse tokens, cleanup.

- [ ] **Step 10: Run cli_runner tests to verify they pass**

- [ ] **Step 11: Write failing tests for pipeline_executor**

Test sequential steps, parallel agents within a step, failure propagation, cancellation.

- [ ] **Step 12: Implement pipeline_executor.py**

`PipelineExecutor.run_ticket()`: iterate steps in order, `asyncio.gather` for parallel agents in same step, update DB status, handle failure/cancel.

- [ ] **Step 13: Run pipeline_executor tests to verify they pass**

- [ ] **Step 14: Add run/cancel/retry endpoints to tickets.py**

```python
@router.post("/{ticket_id}/run")
async def run_ticket(ticket_id: int, background_tasks: BackgroundTasks):
    # Validate ticket exists and is in assignable state
    # Launch PipelineExecutor.run_ticket in background
    ...

@router.post("/{ticket_id}/cancel")
async def cancel_ticket(ticket_id: int):
    # Find running step_agents, send SIGTERM to PIDs
    ...

@router.post("/{ticket_id}/retry")
async def retry_ticket(ticket_id: int, background_tasks: BackgroundTasks):
    # Find failed step, reset status, re-run from there
    ...
```

- [ ] **Step 15: Commit**

```bash
git add backend/ tests/
git commit -m "feat: CLI runner, pipeline executor, token parser with run/cancel/retry endpoints"
```

---

## Task 6: Runs, Usage, Provider APIs + Frontend Pages

**Files:**
- Create: `backend/routes/runs.py`
- Create: `backend/routes/usage.py`
- Create: `backend/routes/providers.py`
- Create: `backend/models/provider.py`
- Create: `tests/test_usage.py`
- Create: `frontend/pages/6_usage.py`
- Create: `frontend/pages/7_settings.py`
- Create: `frontend/components/result_viewer.py`
- Modify: `backend/main.py` (add routers)

- [ ] **Step 1: Write failing tests for usage aggregation**

Test: total summary, per-project aggregation from step_agents data.

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Create backend/models/provider.py**

Pydantic schemas for CLIProvider and CostRate.

- [ ] **Step 4: Create backend/routes/runs.py**

GET /{id} returns step_agent detail. GET /{id}/result reads result files from result_path.

- [ ] **Step 5: Create backend/routes/usage.py**

Aggregation queries: SUM tokens/cost grouped by project, by agent.

- [ ] **Step 6: Create backend/routes/providers.py**

CRUD for cli_providers and cost_rates tables.

- [ ] **Step 7: Add routers to main.py**

- [ ] **Step 8: Run tests to verify they pass**

- [ ] **Step 9: Create frontend/components/result_viewer.py**

Renders summary.md as markdown, displays files_changed.json as file list with paths.

- [ ] **Step 10: Create frontend/pages/6_usage.py**

Cost monitoring: table with project/agent breakdown, token counts, estimated costs.

- [ ] **Step 11: Create frontend/pages/7_settings.py**

CLI provider list with enable/disable toggle. Cost rate editor.

- [ ] **Step 12: Commit**

```bash
git add backend/ frontend/ tests/
git commit -m "feat: runs/usage/provider APIs + cost monitoring and settings UI"
```

---

## Task 7: AI Ticket Analyzer + Document Management

**Files:**
- Create: `backend/services/ticket_analyzer.py`
- Create: `backend/routes/documents.py`
- Create: `backend/models/document.py`
- Create: `backend/prompts/decompose_task.md`
- Create: `backend/prompts/analyze_diff.md`
- Create: `tests/test_ticket_analyzer.py`
- Create: `tests/test_documents.py`
- Modify: `backend/routes/tickets.py` (add from-diff, auto-assign endpoints)
- Modify: `backend/main.py` (add router)
- Modify: `frontend/pages/4_ticket_create.py` (wire up AI tab)

- [ ] **Step 1: Create prompt templates**

`backend/prompts/decompose_task.md`:
```markdown
You are a game development project manager. Analyze the following task request and decompose it into specific tickets.

Task: {task_description}

Available agents: {agent_list}

Respond in JSON format:
{json_schema}
```

`backend/prompts/analyze_diff.md`:
```markdown
You are a game development project manager. A design document has been modified. Analyze the changes and recommend tickets.

Document: {file_path}
Diff:
{diff_content}

Available agents: {agent_list}

Respond in JSON format:
{json_schema}
```

- [ ] **Step 2: Write failing tests for ticket_analyzer**

Test prompt assembly, JSON response parsing (mock CLI call).

- [ ] **Step 3: Implement ticket_analyzer.py**

Uses CLIRunner with default provider. Builds prompt from template + user input. Parses JSON response into ticket recommendation structures.

- [ ] **Step 4: Run ticket_analyzer tests to verify they pass**

- [ ] **Step 5: Write failing tests for documents API**

Test: list documents by project, get document, update document (triggers diff).

- [ ] **Step 6: Create backend/models/document.py and backend/routes/documents.py**

CRUD with diff detection on PUT: saves previous_content before updating content.

- [ ] **Step 7: Add from-diff and auto-assign endpoints to tickets.py**

`POST /api/tickets/from-diff`: receives document diff, calls ticket_analyzer, returns recommendations.
`POST /api/tickets/{id}/auto-assign`: analyzes ticket description, recommends agents.

- [ ] **Step 8: Add documents router to main.py**

- [ ] **Step 9: Run all tests to verify they pass**

- [ ] **Step 10: Wire up AI auto-generate tab in frontend/pages/4_ticket_create.py**

Natural language input → call auto-decompose → display recommended tickets → confirm → create.

- [ ] **Step 11: Commit**

```bash
git add backend/ frontend/ tests/
git commit -m "feat: AI ticket analyzer with document change detection and auto-decompose"
```

---

## Task 8: Docker Configuration + Integration Test

**Files:**
- Create: `docker-compose.yml`
- Create: `Dockerfile.backend`
- Create: `Dockerfile.frontend`
- Create: `tests/test_integration.py`
- Create: `data/.gitkeep`
- Create: `.gitignore`

- [ ] **Step 1: Create Dockerfile.backend**

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl nodejs npm git && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code@latest
RUN npm install -g @openai/codex@latest

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY scripts/ ./scripts/

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create Dockerfile.frontend**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY frontend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/ ./frontend/

EXPOSE 8501
CMD ["streamlit", "run", "frontend/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

- [ ] **Step 3: Create docker-compose.yml**

As specified in the spec, with all volume mounts including scripts/.

- [ ] **Step 4: Create data/.gitkeep**

- [ ] **Step 4.5: Create .gitignore**

```gitignore
# .gitignore
__pycache__/
*.pyc
.env
data/studio.db
data/*.db
*.egg-info/
dist/
build/
.venv/
venv/
```

- [ ] **Step 5: Write integration test**

```python
# tests/test_integration.py
"""
Full workflow integration test:
1. Create project
2. Create ticket with pipeline
3. Verify ticket structure
4. (CLI execution is mocked)
"""
```

- [ ] **Step 6: Run integration test**

Run: `python -m pytest tests/test_integration.py -v`
Expected: PASS

- [ ] **Step 7: Test local dev startup**

```bash
# Terminal 1
cd backend && uvicorn backend.main:app --reload --port 8000
# Verify: curl http://localhost:8000/api/health → {"status": "ok"}

# Terminal 2
cd frontend && streamlit run frontend/app.py
# Verify: browser opens at localhost:8501
```

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml Dockerfile.backend Dockerfile.frontend data/ tests/ .gitignore
git commit -m "feat: Docker configuration + integration test for full workflow"
```

---

## Task Summary

| Task | Description | Dependencies |
|------|-------------|-------------|
| 1 | Project scaffolding + DB | None |
| 2 | Project CRUD + dashboard UI | Task 1 |
| 3 | Ticket CRUD + board UI | Task 2 |
| 4 | Agent management + editor | Task 1 |
| 5 | CLI runner + pipeline executor | Task 3 |
| 6 | Runs/usage/provider APIs + UI | Task 5 |
| 7 | AI ticket analyzer + documents | Task 5 |
| 8 | Docker + integration test | All |

**Parallel opportunities:** Tasks 2 and 4 can run in parallel (both depend only on Task 1). Tasks 6 and 7 can run in parallel (both depend on Task 5).
