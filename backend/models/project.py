from pydantic import BaseModel
from typing import Optional


class ProjectCreate(BaseModel):
    name: str
    display_name: str
    engine: str = "godot"
    mode: str = "development"
    config_json: str = "{}"


class ProjectUpdate(BaseModel):
    display_name: Optional[str] = None
    engine: Optional[str] = None
    mode: Optional[str] = None
    status: Optional[str] = None
    config_json: Optional[str] = None


class ProjectResponse(BaseModel):
    id: int
    name: str
    display_name: str
    engine: str
    mode: str
    status: str
    config_json: str
    created_at: str
    updated_at: str
