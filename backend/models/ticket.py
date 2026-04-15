from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.models.session import SessionCreate, SessionResponse


class TicketCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    source: str = "manual"
    created_by: str = "user"
    sessions: list[SessionCreate] = []


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class TicketResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: Optional[str]
    status: str
    source: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    sessions: list[SessionResponse] = []


class TicketSummary(BaseModel):
    id: int
    project_id: int
    title: str
    status: str
    source: str
    created_at: datetime
