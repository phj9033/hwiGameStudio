from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from backend.models.session import SessionCreate, SessionResponse


# Legacy models for backward compatibility (to be removed in Task 9)
class StepAgentCreate(BaseModel):
    agent_name: str
    cli_provider: str = "claude"
    instruction: str = ""
    context_refs: List[str] = []


class StepCreate(BaseModel):
    step_order: int
    agents: List[StepAgentCreate] = []


class StepAgentResponse(BaseModel):
    id: int
    agent_name: str
    cli_provider: str
    instruction: str
    context_refs: str
    status: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost: Optional[float] = None
    result_summary: Optional[str] = None
    result_path: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0


class StepResponse(BaseModel):
    id: int
    step_order: int
    status: str
    agents: List[StepAgentResponse] = []


# Current models
class TicketCreate(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    source: str = "manual"
    created_by: str = "user"
    sessions: list[SessionCreate] = []
    # Legacy field for backward compatibility
    steps: List[StepCreate] = []


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
