from fastapi import APIRouter, HTTPException
from backend.models.project import ProjectCreate, ProjectUpdate, ProjectResponse
from backend.models.common import PaginatedResponse
from backend.database import get_db
import backend.config
from typing import Optional

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(page: int = 1, per_page: int = 20, status: Optional[str] = None):
    """List all projects with pagination"""
    offset = (page - 1) * per_page

    async with get_db(backend.config.DATABASE_PATH) as db:
        # Build query with optional status filter
        params = []
        where_clause = ""
        if status:
            where_clause = "WHERE status = ?"
            params.append(status)

        # Get total count
        count_query = f"SELECT COUNT(*) FROM projects {where_clause}"
        cursor = await db.execute(count_query, tuple(params))
        total = (await cursor.fetchone())[0]

        # Get paginated results
        query = f"""
            SELECT id, name, display_name, engine, mode, status, config_json, created_at, updated_at
            FROM projects
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([per_page, offset])
        cursor = await db.execute(query, tuple(params))
        rows = await cursor.fetchall()

        items = [
            ProjectResponse(
                id=row[0],
                name=row[1],
                display_name=row[2],
                engine=row[3],
                mode=row[4],
                status=row[5],
                config_json=row[6],
                created_at=row[7],
                updated_at=row[8]
            )
            for row in rows
        ]

        return PaginatedResponse(items=items, total=total, page=page, per_page=per_page)


@router.post("", response_model=ProjectResponse)
async def create_project(project: ProjectCreate):
    """Create a new project"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Check if project name already exists
        cursor = await db.execute("SELECT id FROM projects WHERE name = ?", (project.name,))
        if await cursor.fetchone():
            raise HTTPException(status_code=400, detail=f"Project '{project.name}' already exists")

        # Insert new project
        cursor = await db.execute(
            """
            INSERT INTO projects (name, display_name, engine, mode, config_json, status)
            VALUES (?, ?, ?, ?, ?, 'active')
            """,
            (project.name, project.display_name, project.engine, project.mode, project.config_json)
        )
        await db.commit()
        project_id = cursor.lastrowid

        # Fetch and return the created project
        cursor = await db.execute(
            "SELECT id, name, display_name, engine, mode, status, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,)
        )
        row = await cursor.fetchone()

        return ProjectResponse(
            id=row[0],
            name=row[1],
            display_name=row[2],
            engine=row[3],
            mode=row[4],
            status=row[5],
            config_json=row[6],
            created_at=row[7],
            updated_at=row[8]
        )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int):
    """Get a single project by ID"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            "SELECT id, name, display_name, engine, mode, status, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,)
        )
        row = await cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Project not found")

        return ProjectResponse(
            id=row[0],
            name=row[1],
            display_name=row[2],
            engine=row[3],
            mode=row[4],
            status=row[5],
            config_json=row[6],
            created_at=row[7],
            updated_at=row[8]
        )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: int, updates: ProjectUpdate):
    """Update a project"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Check if project exists
        cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")

        # Build update query dynamically based on provided fields
        update_fields = []
        update_values = []

        if updates.display_name is not None:
            update_fields.append("display_name = ?")
            update_values.append(updates.display_name)
        if updates.engine is not None:
            update_fields.append("engine = ?")
            update_values.append(updates.engine)
        if updates.mode is not None:
            update_fields.append("mode = ?")
            update_values.append(updates.mode)
        if updates.status is not None:
            update_fields.append("status = ?")
            update_values.append(updates.status)
        if updates.config_json is not None:
            update_fields.append("config_json = ?")
            update_values.append(updates.config_json)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        update_values.append(project_id)

        query = f"UPDATE projects SET {', '.join(update_fields)} WHERE id = ?"
        await db.execute(query, tuple(update_values))
        await db.commit()

        # Fetch and return updated project
        cursor = await db.execute(
            "SELECT id, name, display_name, engine, mode, status, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,)
        )
        row = await cursor.fetchone()

        return ProjectResponse(
            id=row[0],
            name=row[1],
            display_name=row[2],
            engine=row[3],
            mode=row[4],
            status=row[5],
            config_json=row[6],
            created_at=row[7],
            updated_at=row[8]
        )


@router.post("/{project_id}/freeze", response_model=ProjectResponse)
async def freeze_project(project_id: int):
    """Freeze a project (set status to 'frozen')"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")

        await db.execute(
            "UPDATE projects SET status = 'frozen', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
        await db.commit()

        # Fetch and return updated project
        cursor = await db.execute(
            "SELECT id, name, display_name, engine, mode, status, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,)
        )
        row = await cursor.fetchone()

        return ProjectResponse(
            id=row[0],
            name=row[1],
            display_name=row[2],
            engine=row[3],
            mode=row[4],
            status=row[5],
            config_json=row[6],
            created_at=row[7],
            updated_at=row[8]
        )


@router.post("/{project_id}/resume", response_model=ProjectResponse)
async def resume_project(project_id: int):
    """Resume a project (set status to 'active')"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")

        await db.execute(
            "UPDATE projects SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
        await db.commit()

        # Fetch and return updated project
        cursor = await db.execute(
            "SELECT id, name, display_name, engine, mode, status, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,)
        )
        row = await cursor.fetchone()

        return ProjectResponse(
            id=row[0],
            name=row[1],
            display_name=row[2],
            engine=row[3],
            mode=row[4],
            status=row[5],
            config_json=row[6],
            created_at=row[7],
            updated_at=row[8]
        )


@router.post("/{project_id}/startover", response_model=ProjectResponse)
async def startover_project(project_id: int):
    """Start over a project - reset to active status and cancel all active tickets"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute("SELECT id FROM projects WHERE id = ?", (project_id,))
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Project not found")

        # Cancel all active tickets for this project
        await db.execute(
            "UPDATE tickets SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE project_id = ? AND status NOT IN ('completed', 'cancelled')",
            (project_id,)
        )

        # Reset project status to active
        await db.execute(
            "UPDATE projects SET status = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,)
        )
        await db.commit()

        # Fetch and return updated project
        cursor = await db.execute(
            "SELECT id, name, display_name, engine, mode, status, config_json, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,)
        )
        row = await cursor.fetchone()

        return ProjectResponse(
            id=row[0],
            name=row[1],
            display_name=row[2],
            engine=row[3],
            mode=row[4],
            status=row[5],
            config_json=row[6],
            created_at=row[7],
            updated_at=row[8]
        )
