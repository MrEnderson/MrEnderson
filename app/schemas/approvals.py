from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.database.models import ApprovalStatus, RiskLevel


class ApprovalCreate(BaseModel):
    workspace_id: str
    task_id: str
    requested_action: str
    risk_level: RiskLevel
    reason: str | None = None


class ApprovalDecision(BaseModel):
    resolved_by: str
    decision_reason: str | None = None


class ApprovalOut(BaseModel):
    id: str
    workspace_id: str
    task_id: str
    requested_action: str
    risk_level: RiskLevel
    status: ApprovalStatus
    reason: str | None
    requested_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    decision_reason: str | None

    model_config = {"from_attributes": True}
