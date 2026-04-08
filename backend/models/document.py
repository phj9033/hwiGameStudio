from pydantic import BaseModel
from typing import Optional


class DocumentCreate(BaseModel):
    project_id: int
    file_path: str
    content: str = ""
    updated_by: str = ""


class DocumentUpdate(BaseModel):
    content: str
    updated_by: str = ""


class DocumentResponse(BaseModel):
    id: int
    project_id: int
    file_path: str
    content: str
    previous_content: str
    updated_by: str
    updated_at: str
