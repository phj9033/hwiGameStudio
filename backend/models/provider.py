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


