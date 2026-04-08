from pydantic import BaseModel
from typing import Optional


class CLIProviderResponse(BaseModel):
    id: int
    name: str
    command: str
    api_key_env: str
    enabled: bool


class CLIProviderUpdate(BaseModel):
    command: Optional[str] = None
    api_key_env: Optional[str] = None
    enabled: Optional[bool] = None


class CostRateResponse(BaseModel):
    id: int
    provider: str
    model: str
    input_rate: float
    output_rate: float
    updated_at: str


class CostRateUpdate(BaseModel):
    input_rate: Optional[float] = None
    output_rate: Optional[float] = None
