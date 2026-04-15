import os
import glob
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db
from backend.models.common import PaginatedResponse
from backend.models.session import SessionResponse
import backend.config

router = APIRouter(prefix="/api/agents", tags=["agents"])


class AgentInfo(BaseModel):
    name: str


def _validate_agent_name(name: str):
    """Validate agent name to prevent path traversal attacks."""
    if '..' in name or '/' in name or '\\' in name or '\0' in name:
        raise HTTPException(400, "Invalid agent name")


class AgentContent(BaseModel):
    name: str
    content: str


class AgentContentUpdate(BaseModel):
    content: str


class AgentRunUpdate(BaseModel):
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    status: Optional[str] = None
    result_summary: Optional[str] = None
    result_path: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.get("", response_model=list[AgentInfo])
async def list_agents():
    from backend.config import AGENTS_DIR
    md_files = glob.glob(os.path.join(AGENTS_DIR, "*.md"))
    agents = []
    for f in sorted(md_files):
        name = os.path.splitext(os.path.basename(f))[0]
        if name.lower() == "readme":
            continue
        agents.append(AgentInfo(name=name))
    return agents


@router.get("/{name}", response_model=AgentContent)
async def get_agent(name: str):
    _validate_agent_name(name)
    from backend.config import AGENTS_DIR
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise HTTPException(404, f"Agent '{name}' not found")
    with open(path, "r") as f:
        content = f.read()
    return AgentContent(name=name, content=content)


@router.put("/{name}", response_model=AgentContent)
async def update_agent(name: str, update: AgentContentUpdate):
    _validate_agent_name(name)
    from backend.config import AGENTS_DIR
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise HTTPException(404, f"Agent '{name}' not found")
    with open(path, "w") as f:
        f.write(update.content)
    return AgentContent(name=name, content=update.content)


@router.get("/{name}/runs", response_model=PaginatedResponse[SessionResponse])
async def get_agent_runs(name: str, page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=100)):
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM agent_sessions WHERE agent_name = ?", (name,))
        total = (await cursor.fetchone())[0]
        offset = (page - 1) * per_page
        cursor = await db.execute(
            "SELECT * FROM agent_sessions WHERE agent_name = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (name, per_page, offset)
        )
        rows = await cursor.fetchall()
    items = [SessionResponse(**dict(r)) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)


@router.put("/runs/{agent_run_id}", response_model=SessionResponse)
async def update_agent_run(agent_run_id: int, update: AgentRunUpdate):
    """Update agent run data (tokens, cost, status, etc)"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Check if agent run exists
        cursor = await db.execute(
            "SELECT id FROM agent_sessions WHERE id = ?",
            (agent_run_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Agent run not found")

        # Build update query
        updates = []
        params = []
        if update.input_tokens is not None:
            updates.append("input_tokens = ?")
            params.append(update.input_tokens)
        if update.output_tokens is not None:
            updates.append("output_tokens = ?")
            params.append(update.output_tokens)
        if update.estimated_cost is not None:
            updates.append("estimated_cost = ?")
            params.append(update.estimated_cost)
        if update.status is not None:
            updates.append("status = ?")
            params.append(update.status)
        if update.result_summary is not None:
            updates.append("result_summary = ?")
            params.append(update.result_summary)
        if update.result_path is not None:
            updates.append("result_path = ?")
            params.append(update.result_path)
        if update.started_at is not None:
            updates.append("started_at = ?")
            params.append(update.started_at)
        if update.completed_at is not None:
            updates.append("completed_at = ?")
            params.append(update.completed_at)

        if updates:
            params.append(agent_run_id)
            await db.execute(
                f"UPDATE agent_sessions SET {', '.join(updates)} WHERE id = ?",
                params
            )
            await db.commit()

        # Fetch updated record
        cursor = await db.execute(
            """
            SELECT id, agent_name, cli_provider, instruction, context_refs, status,
                   input_tokens, output_tokens, estimated_cost, result_summary,
                   result_path, started_at, completed_at, retry_count
            FROM agent_sessions
            WHERE id = ?
            """,
            (agent_run_id,)
        )
        row = await cursor.fetchone()

        return SessionResponse(
            id=row[0],
            agent_name=row[1],
            cli_provider=row[2],
            instruction=row[3],
            context_refs=row[4],
            status=row[5],
            input_tokens=row[6],
            output_tokens=row[7],
            estimated_cost=row[8],
            result_summary=row[9],
            result_path=row[10],
            started_at=row[11],
            completed_at=row[12],
            retry_count=row[13]
        )
