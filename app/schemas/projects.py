from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.database.models import ProjectStatus


class ProjectCreate(BaseModel):
    workspace_id: str
    name: str
    description: str | None = None


class ObjectiveCreate(BaseModel):
    objective: str


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str | None
    status: ProjectStatus
    objective: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceCreate(BaseModel):
    user_email: str
    name: str
    description: str | None = None


class WorkspaceOut(BaseModel):
    id: str
    user_id: str
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    user_email: str
    objective: str
    workspace_id: str | None = None
    workspace_name: str | None = None
    project_id: str | None = None
    project_name: str | None = None


class ChatResponse(BaseModel):
    run_id: str
    workspace_id: str
    project_id: str
    objective: str
    status: str
    message: str
    tasks: list[dict]
    approvals_required: list[str]
