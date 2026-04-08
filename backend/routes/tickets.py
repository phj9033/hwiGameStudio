from fastapi import APIRouter, HTTPException
from backend.models.ticket import (
    TicketCreate,
    TicketUpdate,
    TicketResponse,
    TicketSummary,
    StepResponse,
    StepAgentResponse,
)
from backend.models.common import PaginatedResponse
from backend.database import get_db
import backend.config
import json
from datetime import datetime

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


async def _get_ticket_detail(ticket_id: int, db) -> TicketResponse:
    """Helper to fetch ticket with full step and agent detail"""
    # Fetch ticket
    ticket_row = await db.execute(
        "SELECT * FROM tickets WHERE id = ?", (ticket_id,)
    )
    ticket = await ticket_row.fetchone()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Fetch steps
    steps_rows = await db.execute(
        "SELECT * FROM ticket_steps WHERE ticket_id = ? ORDER BY step_order",
        (ticket_id,)
    )
    steps_data = await steps_rows.fetchall()

    steps = []
    for step_row in steps_data:
        # Fetch agents for this step
        agents_rows = await db.execute(
            "SELECT * FROM step_agents WHERE step_id = ?",
            (step_row["id"],)
        )
        agents_data = await agents_rows.fetchall()

        agents = [
            StepAgentResponse(
                id=agent["id"],
                agent_name=agent["agent_name"],
                cli_provider=agent["cli_provider"],
                instruction=agent["instruction"],
                context_refs=agent["context_refs"],
                status=agent["status"],
                input_tokens=agent["input_tokens"],
                output_tokens=agent["output_tokens"],
                estimated_cost=agent["estimated_cost"],
                result_summary=agent["result_summary"],
                result_path=agent["result_path"],
                started_at=agent["started_at"],
                completed_at=agent["completed_at"],
                retry_count=agent["retry_count"],
            )
            for agent in agents_data
        ]

        steps.append(
            StepResponse(
                id=step_row["id"],
                step_order=step_row["step_order"],
                status=step_row["status"],
                agents=agents,
            )
        )

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
        steps=steps,
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


@router.post("/", response_model=TicketResponse)
async def create_ticket(ticket: TicketCreate):
    """Create a ticket with nested steps and agents"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Determine status based on whether steps are provided
        status = "assigned" if ticket.steps else "open"

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

        # Insert steps and agents
        for step in ticket.steps:
            step_cursor = await db.execute(
                """INSERT INTO ticket_steps (ticket_id, step_order, status)
                   VALUES (?, ?, ?)""",
                (ticket_id, step.step_order, "pending")
            )
            step_id = step_cursor.lastrowid

            # Insert agents for this step
            for agent in step.agents:
                context_refs_json = json.dumps(agent.context_refs)
                await db.execute(
                    """INSERT INTO step_agents
                       (step_id, agent_name, cli_provider, instruction, context_refs, status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        step_id,
                        agent.agent_name,
                        agent.cli_provider,
                        agent.instruction,
                        context_refs_json,
                        "pending",
                    )
                )

        await db.commit()

        # Return full ticket detail
        return await _get_ticket_detail(ticket_id, db)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: int):
    """Get ticket with full step and agent detail"""
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
