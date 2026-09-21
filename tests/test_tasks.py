"""Task creation, the explicit state machine, and dependency enforcement."""
from __future__ import annotations

import pytest

from app.database.models import TaskStatus
from app.orchestration.state_machine import InvalidTransitionError, assert_transition, can_transition
from app.services.project_service import ProjectService
from app.services.task_service import TaskService


async def _make_project(session, name="Test Project"):
    from app.database.repositories import UserRepository, WorkspaceRepository

    user = await UserRepository(session).get_or_create_by_email("t@example.com")
    workspace = await WorkspaceRepository(session).create(user.id, "Test Workspace")
    project = await ProjectService(session).create_project(workspace.id, name)
    await session.commit()
    return workspace.id, project.id


async def test_create_task_starts_planned(session):
    workspace_id, project_id = await _make_project(session)
    service = TaskService(session)
    task = await service.create_task(
        workspace_id=workspace_id,
        project_id=project_id,
        title="Do research",
        agent_type="research",
    )
    assert task.status == TaskStatus.PLANNED


def test_state_machine_allows_documented_paths():
    assert can_transition(TaskStatus.PENDING, TaskStatus.PLANNED)
    assert can_transition(TaskStatus.PLANNED, TaskStatus.READY)
    assert can_transition(TaskStatus.READY, TaskStatus.RUNNING)
    assert can_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)
    assert can_transition(TaskStatus.RUNNING, TaskStatus.NEEDS_APPROVAL)
    assert can_transition(TaskStatus.NEEDS_APPROVAL, TaskStatus.READY)
    assert can_transition(TaskStatus.RUNNING, TaskStatus.FAILED)


def test_state_machine_rejects_invalid_paths():
    assert not can_transition(TaskStatus.PENDING, TaskStatus.COMPLETED)
    assert not can_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)
    assert not can_transition(TaskStatus.CANCELLED, TaskStatus.READY)
    with pytest.raises(InvalidTransitionError):
        assert_transition(TaskStatus.PENDING, TaskStatus.COMPLETED)


async def test_task_service_transition_enforces_state_machine(session):
    workspace_id, project_id = await _make_project(session)
    service = TaskService(session)
    task = await service.create_task(
        workspace_id=workspace_id, project_id=project_id, title="Do research", agent_type="research"
    )
    # task is PLANNED; jumping straight to COMPLETED is invalid.
    with pytest.raises(InvalidTransitionError):
        await service.transition(task.id, TaskStatus.COMPLETED, workspace_id=workspace_id)


async def test_dependencies_enforced(session):
    workspace_id, project_id = await _make_project(session)
    service = TaskService(session)
    upstream = await service.create_task(
        workspace_id=workspace_id, project_id=project_id, title="Research", agent_type="research"
    )
    downstream = await service.create_task(
        workspace_id=workspace_id,
        project_id=project_id,
        title="Strategy",
        agent_type="strategy",
        depends_on_task_ids=[upstream.id],
    )

    assert await service.dependencies_met(downstream.id) is False

    await service.transition(upstream.id, TaskStatus.READY, workspace_id=workspace_id)
    await service.transition(upstream.id, TaskStatus.RUNNING, workspace_id=workspace_id)
    await service.transition(upstream.id, TaskStatus.COMPLETED, workspace_id=workspace_id)

    assert await service.dependencies_met(downstream.id) is True


async def test_dispatcher_promotes_only_when_dependencies_met(session):
    from app.orchestration import dispatcher

    workspace_id, project_id = await _make_project(session)
    service = TaskService(session)
    upstream = await service.create_task(
        workspace_id=workspace_id, project_id=project_id, title="Research", agent_type="research"
    )
    downstream = await service.create_task(
        workspace_id=workspace_id,
        project_id=project_id,
        title="Strategy",
        agent_type="strategy",
        depends_on_task_ids=[upstream.id],
    )

    promoted = await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
    promoted_ids = {t.id for t in promoted}
    assert upstream.id in promoted_ids
    assert downstream.id not in promoted_ids
