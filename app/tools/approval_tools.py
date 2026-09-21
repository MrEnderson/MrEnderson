"""Approval tool — permission-checked interface onto ApprovalService.

Only WRITE-permission agents (Jarvis, Execution) may request approval. Resolving
an approval is a human action and is intentionally NOT exposed here — it goes
through app.services.approval_service directly from the API/CLI layer, never
from an agent.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentRegistry
from app.database.models import Approval, PermissionLevel, RiskLevel
from app.security.permissions import check_permission
from app.services.approval_service import ApprovalService


async def request_approval(
    session: AsyncSession,
    registry: AgentRegistry,
    *,
    acting_agent_type: str,
    workspace_id: str,
    task_id: str,
    requested_action: str,
    risk_level: RiskLevel,
    reason: str | None = None,
) -> Approval:
    check_permission(registry, acting_agent_type, PermissionLevel.WRITE)
    return await ApprovalService(session).request_approval(
        workspace_id=workspace_id,
        task_id=task_id,
        requested_action=requested_action,
        risk_level=risk_level,
        reason=reason,
    )


async def get_approval(session: AsyncSession, *, approval_id: str) -> Approval | None:
    return await ApprovalService(session).get(approval_id)
