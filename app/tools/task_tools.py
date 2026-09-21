"""Task tool — the safe, permission-checked interface onto TaskService.

These are the callable "tools" available to the orchestration layer (and, in a
future version with LLM function-calling, directly to agents). Every call is
permission-checked against the Agent Registry before it touches the database.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentRegistry
from app.database.models import PermissionLevel, Task, TaskPriority, TaskStatus
from app.security.permissions import check_permission
from app.services.task_service import TaskService


async def create_task(
    session: AsyncSession,
    registry: AgentRegistry,
    *,
    acting_agent_type: str,
    workspace_id: str,
    project_id: str,
    title: str,
    agent_type: str,
    description: str | None = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    requires_approval: bool = False,
    input_data: dict | None = None,
    success_criteria: str | None = None,
    depends_on_task_ids: list[str] | None = None,
) -> Task:
    check_permission(registry, acting_agent_type, PermissionLevel.WRITE)
    service = TaskService(session)
    return await service.create_task(
        workspace_id=workspace_id,
        project_id=project_id,
        title=title,
        agent_type=agent_type,
        description=description,
        priority=priority,
        requires_approval=requires_approval,
        input_data=input_data,
        success_criteria=success_criteria,
        depends_on_task_ids=depends_on_task_ids,
    )


async def update_task_status(
    session: AsyncSession,
    registry: AgentRegistry,
    *,
    acting_agent_type: str,
    workspace_id: str,
    task_id: str,
    status: TaskStatus,
    output_data: dict | None = None,
    error: str | None = None,
) -> Task:
    check_permission(registry, acting_agent_type, PermissionLevel.WRITE)
    service = TaskService(session)
    return await service.transition(
        task_id, status, workspace_id=workspace_id, output_data=output_data, error=error
    )


async def get_task(
    session: AsyncSession, registry: AgentRegistry, *, acting_agent_type: str, task_id: str
) -> Task | None:
    check_permission(registry, acting_agent_type, PermissionLevel.READ)
    return await TaskService(session).get(task_id)


async def list_tasks(
    session: AsyncSession, registry: AgentRegistry, *, acting_agent_type: str, project_id: str
) -> list[Task]:
    check_permission(registry, acting_agent_type, PermissionLevel.READ)
    return await TaskService(session).list_for_project(project_id)
