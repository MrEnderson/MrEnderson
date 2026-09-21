"""Approval workflow. Consequential actions never execute without a recorded
human decision — approval is never simulated or assumed."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Approval, ApprovalStatus, RiskLevel, TaskStatus
from app.database.repositories import ApprovalRepository
from app.security.audit import AuditEventType, record_event
from app.services.task_service import TaskService


class ApprovalService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.approvals = ApprovalRepository(session)
        self.tasks = TaskService(session)

    async def request_approval(
        self,
        *,
        workspace_id: str,
        task_id: str,
        requested_action: str,
        risk_level: RiskLevel,
        reason: str | None = None,
    ) -> Approval:
        approval = await self.approvals.create(
            workspace_id=workspace_id,
            task_id=task_id,
            requested_action=requested_action,
            risk_level=risk_level,
            reason=reason,
        )
        await self.tasks.transition(task_id, TaskStatus.NEEDS_APPROVAL, workspace_id=workspace_id)
        await record_event(
            self.session,
            workspace_id=workspace_id,
            actor_type="jarvis",
            event_type=AuditEventType.APPROVAL_REQUESTED,
            entity_type="approval",
            entity_id=approval.id,
            metadata={"task_id": task_id, "risk_level": risk_level.value},
        )
        return approval

    async def approve(self, approval_id: str, resolved_by: str, decision_reason: str | None = None) -> Approval:
        approval = await self.approvals.get(approval_id)
        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval {approval_id} already resolved as {approval.status.value}")

        resolved = await self.approvals.resolve(
            approval_id, ApprovalStatus.APPROVED, resolved_by, decision_reason
        )
        await self.tasks.transition(
            approval.task_id, TaskStatus.READY, workspace_id=approval.workspace_id
        )
        await record_event(
            self.session,
            workspace_id=approval.workspace_id,
            actor_type="human",
            actor_id=resolved_by,
            event_type=AuditEventType.APPROVAL_GRANTED,
            entity_type="approval",
            entity_id=approval_id,
            metadata={"task_id": approval.task_id, "reason": decision_reason},
        )
        return resolved  # type: ignore[return-value]

    async def reject(self, approval_id: str, resolved_by: str, decision_reason: str | None = None) -> Approval:
        approval = await self.approvals.get(approval_id)
        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")
        if approval.status != ApprovalStatus.PENDING:
            raise ValueError(f"Approval {approval_id} already resolved as {approval.status.value}")

        resolved = await self.approvals.resolve(
            approval_id, ApprovalStatus.REJECTED, resolved_by, decision_reason
        )
        await self.tasks.transition(
            approval.task_id,
            TaskStatus.FAILED,
            workspace_id=approval.workspace_id,
            error=f"Approval rejected: {decision_reason or 'no reason given'}",
        )
        await record_event(
            self.session,
            workspace_id=approval.workspace_id,
            actor_type="human",
            actor_id=resolved_by,
            event_type=AuditEventType.APPROVAL_REJECTED,
            entity_type="approval",
            entity_id=approval_id,
            metadata={"task_id": approval.task_id, "reason": decision_reason},
        )
        return resolved  # type: ignore[return-value]

    async def get(self, approval_id: str) -> Approval | None:
        return await self.approvals.get(approval_id)

    async def list_for_workspace(self, workspace_id: str, status: ApprovalStatus | None = None):
        return await self.approvals.list_for_workspace(workspace_id, status=status)
