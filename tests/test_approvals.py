"""Approval creation and resolution, including audit trail side effects."""
from __future__ import annotations

import pytest

from app.database.models import ApprovalStatus, RiskLevel, TaskStatus
from app.database.repositories import AuditRepository, UserRepository, WorkspaceRepository
from app.security.audit import AuditEventType
from app.services.approval_service import ApprovalService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService


async def _make_task(session):
    user = await UserRepository(session).get_or_create_by_email("a@example.com")
    workspace = await WorkspaceRepository(session).create(user.id, "Approval Workspace")
    project = await ProjectService(session).create_project(workspace.id, "Approval Project")
    service = TaskService(session)
    task = await service.create_task(
        workspace_id=workspace.id,
        project_id=project.id,
        title="Purchase ad credits",
        agent_type="execution",
    )
    # Approval requests originate from RUNNING in the real executor (see
    # app.orchestration.executor); mirror that here so the state machine allows it.
    await service.transition(task.id, TaskStatus.READY, workspace_id=workspace.id)
    await service.transition(task.id, TaskStatus.RUNNING, workspace_id=workspace.id)
    await session.commit()
    return workspace.id, task.id


async def test_request_approval_moves_task_to_needs_approval(session):
    workspace_id, task_id = await _make_task(session)
    service = ApprovalService(session)

    approval = await service.request_approval(
        workspace_id=workspace_id,
        task_id=task_id,
        requested_action="Purchase ad credits",
        risk_level=RiskLevel.HIGH,
    )
    await session.commit()

    assert approval.status == ApprovalStatus.PENDING
    task = await TaskService(session).get(task_id)
    assert task.status == TaskStatus.NEEDS_APPROVAL


async def test_approve_returns_task_to_ready_and_records_audit(session):
    workspace_id, task_id = await _make_task(session)
    service = ApprovalService(session)
    approval = await service.request_approval(
        workspace_id=workspace_id,
        task_id=task_id,
        requested_action="Purchase ad credits",
        risk_level=RiskLevel.HIGH,
    )
    await session.commit()

    resolved = await service.approve(approval.id, "owner@example.com", "Approved for Q1 budget")
    await session.commit()

    assert resolved.status == ApprovalStatus.APPROVED
    task = await TaskService(session).get(task_id)
    assert task.status == TaskStatus.READY

    events = await AuditRepository(session).list_for_workspace(workspace_id)
    assert any(e.event_type == AuditEventType.APPROVAL_GRANTED for e in events)


async def test_reject_marks_task_failed_and_records_audit(session):
    workspace_id, task_id = await _make_task(session)
    service = ApprovalService(session)
    approval = await service.request_approval(
        workspace_id=workspace_id,
        task_id=task_id,
        requested_action="Purchase ad credits",
        risk_level=RiskLevel.HIGH,
    )
    await session.commit()

    resolved = await service.reject(approval.id, "owner@example.com", "Not in budget")
    await session.commit()

    assert resolved.status == ApprovalStatus.REJECTED
    task = await TaskService(session).get(task_id)
    assert task.status == TaskStatus.FAILED
    assert "Not in budget" in (task.error or "")

    events = await AuditRepository(session).list_for_workspace(workspace_id)
    assert any(e.event_type == AuditEventType.APPROVAL_REJECTED for e in events)


async def test_cannot_resolve_approval_twice(session):
    workspace_id, task_id = await _make_task(session)
    service = ApprovalService(session)
    approval = await service.request_approval(
        workspace_id=workspace_id,
        task_id=task_id,
        requested_action="Purchase ad credits",
        risk_level=RiskLevel.HIGH,
    )
    await session.commit()

    await service.approve(approval.id, "owner@example.com")
    await session.commit()

    with pytest.raises(ValueError):
        await service.approve(approval.id, "owner@example.com")
