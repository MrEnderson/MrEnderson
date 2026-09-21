from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.database.models import MemoryType


class MemoryCreate(BaseModel):
    workspace_id: str
    type: MemoryType
    title: str
    content: str
    source: str | None = None
    importance: int = Field(default=3, ge=1, le=5)


class MemoryOut(BaseModel):
    id: str
    workspace_id: str
    type: MemoryType
    title: str
    content: str
    source: str | None
    importance: int
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryQuery(BaseModel):
    workspace_id: str
    type: MemoryType | None = None
    keyword: str | None = None
    min_importance: int | None = None
