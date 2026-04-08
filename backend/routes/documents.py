from fastapi import APIRouter, HTTPException
from backend.models.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
)
from backend.database import get_db
import backend.config
import difflib
from typing import List

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("", response_model=List[DocumentResponse])
async def list_documents(project_id: int):
    """List documents by project"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        rows = await db.execute(
            """SELECT id, project_id, file_path, content, previous_content, updated_by, updated_at
               FROM documents WHERE project_id = ?
               ORDER BY updated_at DESC""",
            (project_id,)
        )
        documents_data = await rows.fetchall()

        return [
            DocumentResponse(
                id=row["id"],
                project_id=row["project_id"],
                file_path=row["file_path"],
                content=row["content"],
                previous_content=row["previous_content"],
                updated_by=row["updated_by"],
                updated_at=row["updated_at"],
            )
            for row in documents_data
        ]


@router.post("", response_model=DocumentResponse)
async def create_document(document: DocumentCreate):
    """Create a new document"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO documents (project_id, file_path, content, previous_content, updated_by)
               VALUES (?, ?, ?, ?, ?)""",
            (
                document.project_id,
                document.file_path,
                document.content,
                "",  # New documents have no previous content
                document.updated_by,
            )
        )
        document_id = cursor.lastrowid
        await db.commit()

        # Fetch and return the created document
        row = await db.execute(
            "SELECT * FROM documents WHERE id = ?",
            (document_id,)
        )
        doc = await row.fetchone()

        return DocumentResponse(
            id=doc["id"],
            project_id=doc["project_id"],
            file_path=doc["file_path"],
            content=doc["content"],
            previous_content=doc["previous_content"],
            updated_by=doc["updated_by"],
            updated_at=doc["updated_at"],
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: int):
    """Get a specific document"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        row = await db.execute(
            "SELECT * FROM documents WHERE id = ?",
            (document_id,)
        )
        doc = await row.fetchone()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        return DocumentResponse(
            id=doc["id"],
            project_id=doc["project_id"],
            file_path=doc["file_path"],
            content=doc["content"],
            previous_content=doc["previous_content"],
            updated_by=doc["updated_by"],
            updated_at=doc["updated_at"],
        )


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(document_id: int, document: DocumentUpdate):
    """Update document content, saving previous content"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        # Get current document
        row = await db.execute(
            "SELECT content FROM documents WHERE id = ?",
            (document_id,)
        )
        current_doc = await row.fetchone()

        if not current_doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Update document, saving current content as previous
        await db.execute(
            """UPDATE documents
               SET content = ?, previous_content = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                document.content,
                current_doc["content"],  # Save current as previous
                document.updated_by,
                document_id,
            )
        )
        await db.commit()

        # Fetch and return updated document
        row = await db.execute(
            "SELECT * FROM documents WHERE id = ?",
            (document_id,)
        )
        doc = await row.fetchone()

        return DocumentResponse(
            id=doc["id"],
            project_id=doc["project_id"],
            file_path=doc["file_path"],
            content=doc["content"],
            previous_content=doc["previous_content"],
            updated_by=doc["updated_by"],
            updated_at=doc["updated_at"],
        )


@router.get("/{document_id}/diff")
async def get_document_diff(document_id: int):
    """Get diff between current and previous content"""
    async with get_db(backend.config.DATABASE_PATH) as db:
        row = await db.execute(
            "SELECT content, previous_content, file_path FROM documents WHERE id = ?",
            (document_id,)
        )
        doc = await row.fetchone()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Generate unified diff
        previous_lines = doc["previous_content"].splitlines(keepends=True)
        current_lines = doc["content"].splitlines(keepends=True)

        diff = difflib.unified_diff(
            previous_lines,
            current_lines,
            fromfile=f"{doc['file_path']} (previous)",
            tofile=f"{doc['file_path']} (current)",
            lineterm=""
        )

        diff_text = "\n".join(diff)

        return {
            "document_id": document_id,
            "file_path": doc["file_path"],
            "diff": diff_text
        }
