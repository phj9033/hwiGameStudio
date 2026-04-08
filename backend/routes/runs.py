from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
import backend.config
from backend.database import get_db
from backend.models.ticket import StepAgentResponse
import os

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{agent_run_id}", response_model=StepAgentResponse)
async def get_agent_run(agent_run_id: int):
    """Get step_agent detail by ID"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, agent_name, cli_provider, instruction, context_refs, status,
                   input_tokens, output_tokens, estimated_cost, result_summary,
                   result_path, started_at, completed_at, retry_count
            FROM step_agents
            WHERE id = ?
            """,
            (agent_run_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Agent run not found")

        return StepAgentResponse(
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


@router.get("/{agent_run_id}/result", response_class=PlainTextResponse)
async def get_agent_result_file(agent_run_id: int):
    """Read and return result file content from result_path"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT result_path FROM step_agents WHERE id = ?",
            (agent_run_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Agent run not found")

        result_path = row[0]
        if not result_path:
            raise HTTPException(status_code=404, detail="No result file available")

        if not os.path.exists(result_path):
            raise HTTPException(status_code=404, detail="Result file not found")

        with open(result_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return content
