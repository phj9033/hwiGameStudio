from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from backend.models.ticket import (
    TicketCreate,
    TicketUpdate,
    TicketResponse,
    TicketSummary,
)
from backend.models.session import SessionResponse
from backend.models.common import PaginatedResponse
from backend.database import get_db
from backend.services.dependency_graph import validate_dependency_graph, CyclicDependencyError
import backend.config
import json
import asyncio
import uuid
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/tickets", tags=["tickets"])

# In-memory store for async decompose jobs
_decompose_jobs: Dict[str, Dict[str, Any]] = {}


# Request models for new endpoints
class DiffAnalysisRequest(BaseModel):
    file_path: str
    diff_content: str
    agent_list: List[str]


class DecomposeRequest(BaseModel):
    description: str
    agent_list: List[str]


async def _get_ticket_detail(ticket_id: int, db) -> TicketResponse:
    """Helper to fetch ticket with full session detail"""
    # Fetch ticket
    ticket_row = await db.execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    )
    ticket = await ticket_row.fetchone()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Fetch sessions
    sessions_rows = await db.execute(
        "SELECT * FROM agent_sessions WHERE ticket_id = ? ORDER BY id",
        (ticket_id,)
    )
    sessions_data = await sessions_rows.fetchall()

    sessions = [
        SessionResponse(
            id=row["id"],
            ticket_id=row["ticket_id"],
            agent_name=row["agent_name"],
            cli_provider=row["cli_provider"],
            instruction=row["instruction"],
            depends_on=json.loads(row["depends_on"]) if row["depends_on"] else [],
            produces=json.loads(row["produces"]) if row["produces"] else [],
            status=row["status"],
            error_message=row["error_message"],
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            estimated_cost=row["estimated_cost"],
            session_log_path=row["session_log_path"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            retry_count=row["retry_count"],
        )
        for row in sessions_data
    ]

    return TicketResponse(
        id=ticket["id"],
        project_id=ticket["project_id"],
        title=ticket["title"],
        description=ticket["description"],
        status=ticket["status"],
        source=ticket["source"],
        created_by=ticket["created_by"],
        created_at=ticket["created_at"],
        updated_at=ticket["updated_at"],
        sessions=sessions,
    )


@router.get("/", response_model=PaginatedResponse[TicketSummary])
async def list_tickets(project_id: int = None, page: int = 1, per_page: int = 50):
    """List tickets with optional project filter"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Build query
        if project_id:
            count_row = await db.execute(
                "SELECT COUNT(*) as count FROM tickets WHERE project_id = ?",
                (project_id,)
            )
            rows = await db.execute(
                """SELECT id, project_id, title, status, source, created_at
                   FROM tickets WHERE project_id = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (project_id, per_page, (page - 1) * per_page)
            )
        else:
            count_row = await db.execute("SELECT COUNT(*) as count FROM tickets")
            rows = await db.execute(
                """SELECT id, project_id, title, status, source, created_at
                   FROM tickets
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (per_page, (page - 1) * per_page)
            )

        total = (await count_row.fetchone())["count"]
        tickets_data = await rows.fetchall()

        items = [
            TicketSummary(
                id=row["id"],
                project_id=row["project_id"],
                title=row["title"],
                status=row["status"],
                source=row["source"],
                created_at=row["created_at"],
            )
            for row in tickets_data
        ]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
        )


@router.post("/from-diff")
async def create_tickets_from_diff(request: DiffAnalysisRequest):
    """Analyze document diff and recommend tickets"""
    from backend.services.ticket_analyzer import TicketAnalyzer

    analyzer = TicketAnalyzer()
    try:
        result = await analyzer.analyze_diff(
            request.file_path,
            request.diff_content,
            request.agent_list
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


async def _run_decompose(job_id: str, description: str, agent_list: List[str]):
    """Background task for decompose"""
    from backend.services.ticket_analyzer import TicketAnalyzer
    analyzer = TicketAnalyzer()
    try:
        result = await analyzer.decompose_task(description, agent_list)
        _decompose_jobs[job_id] = {"status": "completed", "result": result}
    except Exception as e:
        _decompose_jobs[job_id] = {"status": "failed", "error": str(e)}


@router.post("/decompose")
async def decompose_task(request: DecomposeRequest):
    """Start async decompose job and return job_id"""
    job_id = str(uuid.uuid4())
    _decompose_jobs[job_id] = {"status": "running"}
    asyncio.create_task(_run_decompose(job_id, request.description, request.agent_list))
    return {"job_id": job_id, "status": "running"}


@router.get("/decompose/{job_id}")
async def get_decompose_status(job_id: str):
    """Check status of a decompose job"""
    job = _decompose_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/", response_model=TicketResponse)
async def create_ticket(ticket: TicketCreate):
    """Create a ticket with optional agent sessions"""
    # Validate dependency graph if sessions are provided
    if ticket.sessions:
        session_dicts = [s.model_dump() for s in ticket.sessions]
        try:
            validate_dependency_graph(session_dicts)
        except CyclicDependencyError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    async with get_db(backend.config.DATABASE_PATH) as db:
        # Determine status based on whether sessions are provided
        status = "assigned" if ticket.sessions else "open"

        # Insert ticket
        cursor = await db.execute(
            """INSERT INTO tickets (project_id, title, description, status, source, created_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                ticket.project_id,
                ticket.title,
                ticket.description,
                status,
                ticket.source,
                ticket.created_by,
            )
        )
        ticket_id = cursor.lastrowid

        # Insert sessions
        for session in ticket.sessions:
            depends_on_json = json.dumps(session.depends_on)
            produces_json = json.dumps(session.produces)
            await db.execute(
                """INSERT INTO agent_sessions
                   (ticket_id, agent_name, cli_provider, instruction, depends_on, produces, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    ticket_id,
                    session.agent_name,
                    session.cli_provider,
                    session.instruction,
                    depends_on_json,
                    produces_json,
                    "pending",
                )
            )

        await db.commit()

        # Return full ticket detail
        return await _get_ticket_detail(ticket_id, db)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: int):
    """Get ticket with full session detail"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        return await _get_ticket_detail(ticket_id, db)


@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: int, ticket: TicketUpdate):
    """Update ticket title and/or description"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Check ticket exists
        check = await db.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if not await check.fetchone():
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Build update query
        updates = []
        params = []
        if ticket.title is not None:
            updates.append("title = ?")
            params.append(ticket.title)
        if ticket.description is not None:
            updates.append("description = ?")
            params.append(ticket.description)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(ticket_id)
            await db.execute(
                f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?",
                tuple(params)
            )
            await db.commit()

        return await _get_ticket_detail(ticket_id, db)


@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: int):
    """Delete a ticket and its sessions"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        check = await db.execute("SELECT id, status FROM tickets WHERE id = ?", (ticket_id,))
        row = await check.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if row["status"] == "running":
            raise HTTPException(status_code=400, detail="Cannot delete a running ticket. Cancel it first.")

        # Delete sessions, then ticket
        await db.execute("DELETE FROM agent_sessions WHERE ticket_id = ?", (ticket_id,))
        await db.execute("DELETE FROM tickets WHERE id = ?", (ticket_id,))
        await db.commit()

    return {"message": "Ticket deleted", "ticket_id": ticket_id}


@router.post("/{ticket_id}/auto-assign")
async def auto_assign_ticket(ticket_id: int):
    """Analyze ticket description and recommend agent assignments"""
    from backend.services.ticket_analyzer import TicketAnalyzer

    async with get_db(backend.config.DATABASE_PATH) as db:
        # Get ticket
        ticket_row = await db.execute(
            "SELECT description FROM tickets WHERE id = ?",
            (ticket_id,)
        )
        ticket = await ticket_row.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # Get available agents (simplified - just using hardcoded list for now)
        # In production, you'd fetch from agents table
        agent_list = [
            "sr_game_designer",
            "mechanics_developer",
            "ui_ux_designer",
            "qa_tester"
        ]

        analyzer = TicketAnalyzer()
        try:
            result = await analyzer.decompose_task(
                ticket["description"],
                agent_list
            )
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(ticket_id: int):
    """Manual assignment - sets status to assigned"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Check ticket exists
        check = await db.execute("SELECT id FROM tickets WHERE id = ?", (ticket_id,))
        if not await check.fetchone():
            raise HTTPException(status_code=404, detail="Ticket not found")

        await db.execute(
            "UPDATE tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ("assigned", ticket_id)
        )
        await db.commit()

        return await _get_ticket_detail(ticket_id, db)


@router.post("/{ticket_id}/run")
async def run_ticket(ticket_id: int, background_tasks: BackgroundTasks):
    """Run ticket execution pipeline in background"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Validate ticket exists and is in runnable state
        check = await db.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        row = await check.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if row["status"] not in ("open", "assigned", "failed"):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot run ticket in status: {row['status']}"
            )

        # Update status to running
        await db.execute(
            "UPDATE tickets SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            ("running", ticket_id)
        )
        await db.commit()

    # Launch session executor in background
    from backend.services.session_executor import SessionExecutor
    executor = SessionExecutor()
    background_tasks.add_task(executor.execute_ticket, ticket_id)

    return {"message": "Ticket execution started", "ticket_id": ticket_id}


@router.post("/{ticket_id}/cancel")
async def cancel_ticket(ticket_id: int):
    """Cancel running ticket execution"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Validate ticket exists
        check = await db.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        row = await check.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if row["status"] != "running":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel ticket in status: {row['status']}"
            )

    # Delegate to SessionExecutor
    from backend.services.session_executor import SessionExecutor
    executor = SessionExecutor()
    await executor.cancel_ticket(ticket_id)

    return {"message": "Ticket cancelled", "ticket_id": ticket_id}


@router.post("/{ticket_id}/retry")
async def retry_ticket(
    ticket_id: int,
    background_tasks: BackgroundTasks,
    session_id: Optional[int] = Query(None, description="Retry a specific session"),
):
    """Retry failed ticket. Optionally retry a specific session."""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Validate ticket exists and is in failed state
        check = await db.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,))
        row = await check.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if row["status"] != "failed":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot retry ticket in status: {row['status']}"
            )

    from backend.services.session_executor import SessionExecutor
    executor = SessionExecutor()

    if session_id is not None:
        # Retry a specific session
        background_tasks.add_task(executor.retry_session, session_id)
        return {"message": "Session retry started", "ticket_id": ticket_id, "session_id": session_id}
    else:
        # Retry the whole ticket
        background_tasks.add_task(executor.execute_ticket, ticket_id)
        return {"message": "Ticket retry started", "ticket_id": ticket_id}


@router.get("/{ticket_id}/workspace")
async def get_workspace(ticket_id: int):
    """List files in ticket workspace directory"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Find project for ticket
        ticket_row = await db.execute(
            """SELECT t.id, p.name as project_name
               FROM tickets t
               JOIN projects p ON t.project_id = p.id
               WHERE t.id = ?""",
            (ticket_id,)
        )
        ticket = await ticket_row.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        project_name = ticket["project_name"]
        workspace_path = os.path.join(
            backend.config.PROJECTS_DIR,
            project_name,
            "workspace",
            f"ticket_{ticket_id}"
        )

        # Return empty list if directory doesn't exist
        if not os.path.exists(workspace_path):
            return []

        # List files with metadata
        files = []
        try:
            for filename in os.listdir(workspace_path):
                file_path = os.path.join(workspace_path, filename)
                if os.path.isfile(file_path):
                    stat = os.stat(file_path)
                    files.append({
                        "filename": filename,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "is_writing": False  # TODO: Track actual writing status if needed
                    })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error listing workspace: {str(e)}")

        return files


@router.get("/{ticket_id}/workspace/{filename:path}")
async def get_workspace_file(ticket_id: int, filename: str):
    """Read a file from ticket workspace"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Find project for ticket
        ticket_row = await db.execute(
            """SELECT t.id, p.name as project_name
               FROM tickets t
               JOIN projects p ON t.project_id = p.id
               WHERE t.id = ?""",
            (ticket_id,)
        )
        ticket = await ticket_row.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")

        project_name = ticket["project_name"]
        file_path = os.path.join(
            backend.config.PROJECTS_DIR,
            project_name,
            "workspace",
            f"ticket_{ticket_id}",
            filename
        )

        # Security check: ensure path is within workspace
        workspace_dir = os.path.join(
            backend.config.PROJECTS_DIR,
            project_name,
            "workspace",
            f"ticket_{ticket_id}"
        )
        abs_file_path = os.path.abspath(file_path)
        abs_workspace_dir = os.path.abspath(workspace_dir)
        if not abs_file_path.startswith(abs_workspace_dir):
            raise HTTPException(status_code=403, detail="Access denied")

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="File not found")

        # Read and return file content
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return {"content": content, "filename": filename}
        except UnicodeDecodeError:
            # Handle binary files
            raise HTTPException(status_code=400, detail="Cannot read binary file")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
