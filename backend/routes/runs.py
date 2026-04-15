from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
import backend.config
from backend.database import get_db
from backend.models.session import SessionResponse
import os

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/{agent_run_id}", response_model=SessionResponse)
async def get_agent_run(agent_run_id: int):
    """Get agent session detail by ID"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, ticket_id, agent_name, cli_provider, instruction, depends_on, produces,
                   status, error_message, input_tokens, output_tokens, estimated_cost,
                   session_log_path, pid, started_at, completed_at, retry_count, created_at
            FROM agent_sessions
            WHERE id = ?
            """,
            (agent_run_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Agent run not found")

        import json
        return SessionResponse(
            id=row[0],
            ticket_id=row[1],
            agent_name=row[2],
            cli_provider=row[3],
            instruction=row[4],
            depends_on=json.loads(row[5]) if row[5] else [],
            produces=json.loads(row[6]) if row[6] else [],
            status=row[7],
            error_message=row[8],
            input_tokens=row[9],
            output_tokens=row[10],
            estimated_cost=row[11],
            session_log_path=row[12],
            pid=row[13],
            started_at=row[14],
            completed_at=row[15],
            retry_count=row[16],
            created_at=row[17]
        )


@router.get("/{agent_run_id}/result", response_class=PlainTextResponse)
async def get_agent_result_file(agent_run_id: int):
    """Read and return result file content from session_log_path"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT session_log_path FROM agent_sessions WHERE id = ?",
            (agent_run_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Agent run not found")

        result_path = row[0]
        if not result_path:
            raise HTTPException(status_code=404, detail="No session log file available")

        # Validate result_path stays within allowed directories
        from backend.config import PROJECTS_DIR
        real_path = os.path.realpath(result_path)
        allowed_dir = os.path.realpath(PROJECTS_DIR)
        if not real_path.startswith(allowed_dir):
            raise HTTPException(status_code=403, detail="Access denied: result path outside allowed directory")

        if not os.path.exists(result_path):
            raise HTTPException(status_code=404, detail="Result file not found")

        with open(result_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return content
