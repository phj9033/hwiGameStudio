from fastapi import APIRouter
from typing import List, Dict, Any
import backend.config
from backend.database import get_db

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/summary")
async def get_usage_summary() -> Dict[str, Any]:
    """Total token/cost summary across all"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output,
                COALESCE(SUM(estimated_cost), 0.0) as total_cost
            FROM step_agents
            """
        )
        row = await cursor.fetchone()

        return {
            "total_input_tokens": row[0],
            "total_output_tokens": row[1],
            "total_cost": row[2]
        }


@router.get("/by-project")
async def get_usage_by_project() -> List[Dict[str, Any]]:
    """Token/cost grouped by project"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                p.id as project_id,
                p.name as project_name,
                p.display_name as project_display_name,
                COALESCE(SUM(sa.input_tokens), 0) as total_input,
                COALESCE(SUM(sa.output_tokens), 0) as total_output,
                COALESCE(SUM(sa.estimated_cost), 0.0) as total_cost
            FROM projects p
            LEFT JOIN tickets t ON t.project_id = p.id
            LEFT JOIN ticket_steps ts ON ts.ticket_id = t.id
            LEFT JOIN step_agents sa ON sa.step_id = ts.id
            GROUP BY p.id, p.name, p.display_name
            HAVING total_input > 0 OR total_output > 0 OR total_cost > 0
            ORDER BY total_cost DESC
            """
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            result.append({
                "project_id": row[0],
                "project_name": row[1],
                "project_display_name": row[2],
                "total_input_tokens": row[3],
                "total_output_tokens": row[4],
                "total_cost": row[5]
            })

        return result


@router.get("/by-agent")
async def get_usage_by_agent() -> List[Dict[str, Any]]:
    """Token/cost grouped by agent_name"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT
                agent_name,
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output,
                COALESCE(SUM(estimated_cost), 0.0) as total_cost
            FROM step_agents
            GROUP BY agent_name
            HAVING total_input > 0 OR total_output > 0 OR total_cost > 0
            ORDER BY total_cost DESC
            """
        )
        rows = await cursor.fetchall()

        result = []
        for row in rows:
            result.append({
                "agent_name": row[0],
                "total_input_tokens": row[1],
                "total_output_tokens": row[2],
                "total_cost": row[3]
            })

        return result
