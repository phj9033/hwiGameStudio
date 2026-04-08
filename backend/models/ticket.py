from pydantic import BaseModel
from typing import Optional, List


class StepAgentCreate(BaseModel):
    agent_name: str
    cli_provider: str = "claude"
    instruction: str = ""
    context_refs: List[str] = []


class StepCreate(BaseModel):
    step_order: int
    agents: List[StepAgentCreate] = []


class TicketCreate(BaseModel):
    project_id: int
    title: str
    description: str = ""
    source: str = "manual"
    created_by: str = ""
    steps: List[StepCreate] = []


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


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


class TicketResponse(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    status: str
    source: str
    created_by: str
    created_at: str
    updated_at: str
    steps: List[StepResponse] = []


class TicketSummary(BaseModel):
    id: int
    project_id: int
    title: str
    status: str
    source: str
    created_at: str
