import os
import glob
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
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
    from backend.config import AGENTS_DIR
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
    from backend.config import AGENTS_DIR
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise HTTPException(404, f"Agent '{name}' not found")
    with open(path, "r") as f:
        content = f.read()
    return AgentContent(name=name, content=content)


@router.put("/{name}", response_model=AgentContent)
async def update_agent(name: str, update: AgentContentUpdate):
    from backend.config import AGENTS_DIR
    path = os.path.join(AGENTS_DIR, f"{name}.md")
    if not os.path.exists(path):
        raise HTTPException(404, f"Agent '{name}' not found")
    with open(path, "w") as f:
        f.write(update.content)
    return AgentContent(name=name, content=update.content)


@router.get("/{name}/runs", response_model=PaginatedResponse[StepAgentResponse])
async def get_agent_runs(name: str, page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=100)):
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM step_agents WHERE agent_name = ?", (name,))
        total = (await cursor.fetchone())[0]
        offset = (page - 1) * per_page
        cursor = await db.execute(
            "SELECT * FROM step_agents WHERE agent_name = ? ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (name, per_page, offset)
        )
        rows = await cursor.fetchall()
    items = [StepAgentResponse(**dict(r)) for r in rows]
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)
