import os
import json
from fastapi import APIRouter, HTTPException
from backend.database import get_db
from backend.models.session import SessionResponse
import backend.config

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "projects")


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: int):
    """Get session details by ID"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Query agent_sessions by id
        session_row = await db.execute(
            "SELECT * FROM agent_sessions WHERE id = ?",
            (session_id,)
        )
        session = await session_row.fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Parse JSON fields and return dict
        return SessionResponse(
            id=session["id"],
            ticket_id=session["ticket_id"],
            agent_name=session["agent_name"],
            cli_provider=session["cli_provider"],
            instruction=session["instruction"],
            depends_on=json.loads(session["depends_on"]) if session["depends_on"] else [],
            produces=json.loads(session["produces"]) if session["produces"] else [],
            status=session["status"],
            error_message=session["error_message"],
            input_tokens=session["input_tokens"],
            output_tokens=session["output_tokens"],
            estimated_cost=session["estimated_cost"],
            session_log_path=session["session_log_path"],
            started_at=session["started_at"],
            completed_at=session["completed_at"],
            retry_count=session["retry_count"],
        )


@router.get("/{session_id}/log")
async def get_session_log(session_id: int):
    """Get session log file content"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Query session to get log path
        session_row = await db.execute(
            "SELECT session_log_path FROM agent_sessions WHERE id = ?",
            (session_id,)
        )
        session = await session_row.fetchone()

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        log_path = session["session_log_path"]
        if not log_path or not os.path.exists(log_path):
            raise HTTPException(status_code=404, detail="Log file not found")

        # Read and return log content
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"content": content}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading log file: {str(e)}")
