"""Persists a validated ExecutionPlan as real Task rows and promotes tasks whose
dependencies are satisfied from PLANNED to READY. Dependency enforcement lives
in Python here, never left to the model to "remember"."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TaskStatus
from app.schemas.tasks import ExecutionPlan
from app.security.approvals import requires_human_approval
from app.security.audit import AuditEventType, record_event
from app.services.task_service import TaskService


async def persist_plan(
    session: AsyncSession, *, workspace_id: str, project_id: str, plan: ExecutionPlan
) -> dict[str, Task]:
    service = TaskService(session)
    key_to_task: dict[str, Task] = {}

    for task_plan in plan.tasks:
        requires_approval = task_plan.requires_approval or requires_human_approval(
            f"{task_plan.title} {task_plan.description}"
        )
        # research_mode is explicit, structured planner intent (v0.1.2.1) —
        # stored in input_data (Task has no dedicated column for it) so
        # app/agents/research.py can read it deterministically via
        # AgentExecutor._build_input. Omitted entirely (None) when the
        # planner didn't set it, so parse_input() stays unchanged for every
        # non-research task and every GENERAL research task.
        input_data = {"research_mode": task_plan.research_mode} if task_plan.research_mode else None
        task = await service.create_task(
            workspace_id=workspace_id,
            project_id=project_id,
            title=task_plan.title,
            agent_type=task_plan.agent_type,
            description=task_plan.description,
            priority=task_plan.priority,
            requires_approval=requires_approval,
            input_data=input_data,
            success_criteria=task_plan.success_criteria,
        )
        key_to_task[task_plan.key] = task

    for task_plan in plan.tasks:
        task = key_to_task[task_plan.key]
        for dep_key in task_plan.dependencies:
            await service.tasks.add_dependency(task.id, key_to_task[dep_key].id)

    await record_event(
        session,
        workspace_id=workspace_id,
        actor_type="jarvis",
        event_type=AuditEventType.PLAN_CREATED,
        entity_type="project",
        entity_id=project_id,
        metadata={"task_count": len(plan.tasks), "objective": plan.objective},
    )

    return key_to_task


async def promote_ready_tasks(session: AsyncSession, *, workspace_id: str, project_id: str) -> list[Task]:
    """Move every PLANNED task whose dependencies are all COMPLETED to READY."""
    service = TaskService(session)
    tasks = await service.list_for_project(project_id)
    promoted: list[Task] = []
    for task in tasks:
        if task.status != TaskStatus.PLANNED:
            continue
        if await service.dependencies_met(task.id):
            updated = await service.transition(task.id, TaskStatus.READY, workspace_id=workspace_id)
            promoted.append(updated)
    return promoted


async def get_ready_tasks(session: AsyncSession, *, project_id: str) -> list[Task]:
    service = TaskService(session)
    tasks = await service.list_for_project(project_id)
    return [t for t in tasks if t.status == TaskStatus.READY]


async def is_project_finished(session: AsyncSession, *, project_id: str) -> bool:
    service = TaskService(session)
    tasks = await service.list_for_project(project_id)
    terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    active_or_blocked = {TaskStatus.NEEDS_APPROVAL}
    unfinished = [t for t in tasks if t.status not in terminal]
    if not unfinished:
        return True
    # Finished (for this run) if everything remaining is blocked on human approval.
    return all(t.status in active_or_blocked for t in unfinished)
