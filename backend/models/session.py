from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SessionCreate(BaseModel):
    agent_name: str
    cli_provider: str = "claude"
    instruction: str
    depends_on: list[str] = []
    produces: list[str] = []


class SessionResponse(BaseModel):
    id: int
    ticket_id: int
    agent_name: str
    cli_provider: str
    instruction: str
    depends_on: list[str]
    produces: list[str]
    status: str
    error_message: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0
    session_log_path: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
