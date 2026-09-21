"""Task lifecycle service. The ONLY path by which task state may change.

No agent or route touches TaskRepository status fields directly — everything
routes through here so the state machine and audit trail stay authoritative.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Task, TaskPriority, TaskStatus
from app.database.repositories import TaskRepository
from app.orchestration.state_machine import assert_transition
from app.security.audit import AuditEventType, record_event


class TaskService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.tasks = TaskRepository(session)

    async def create_task(
        self,
        *,
        workspace_id: str,
        project_id: str,
        title: str,
        agent_type: str,
        description: str | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        requires_approval: bool = False,
        parent_task_id: str | None = None,
        input_data: dict | None = None,
        success_criteria: str | None = None,
        depends_on_task_ids: list[str] | None = None,
    ) -> Task:
        task = await self.tasks.create(
            project_id=project_id,
            title=title,
            agent_type=agent_type,
            description=description,
            priority=priority,
            requires_approval=requires_approval,
            parent_task_id=parent_task_id,
            input_data=input_data,
            success_criteria=success_criteria,
        )
        for dep_id in depends_on_task_ids or []:
            await self.tasks.add_dependency(task.id, dep_id)

        await record_event(
            self.session,
            workspace_id=workspace_id,
            actor_type="jarvis",
            event_type=AuditEventType.TASK_CREATED,
            entity_type="task",
            entity_id=task.id,
            metadata={"title": title, "agent_type": agent_type},
        )

        # A task enters the plan already PLANNED; readiness is computed separately.
        await self.transition(task.id, TaskStatus.PLANNED, workspace_id=workspace_id)
        return task

    async def transition(
        self,
        task_id: str,
        new_status: TaskStatus,
        *,
        workspace_id: str,
        output_data: dict | None = None,
        error: str | None = None,
    ) -> Task:
        task = await self.tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        assert_transition(task.status, new_status)

        now = datetime.now(timezone.utc)
        started_at = now if new_status == TaskStatus.RUNNING and task.started_at is None else None
        completed_at = (
            now if new_status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED) else None
        )

        await self.tasks.update_status(
            task_id,
            new_status,
            output_data=output_data,
            error=error,
            started_at=started_at,
            completed_at=completed_at,
        )

        event_map = {
            TaskStatus.RUNNING: AuditEventType.TASK_STARTED,
            TaskStatus.COMPLETED: AuditEventType.TASK_COMPLETED,
            TaskStatus.FAILED: AuditEventType.TASK_FAILED,
            TaskStatus.CANCELLED: AuditEventType.TASK_CANCELLED,
        }
        if new_status in event_map:
            await record_event(
                self.session,
                workspace_id=workspace_id,
                actor_type="system",
                event_type=event_map[new_status],
                entity_type="task",
                entity_id=task_id,
                metadata={"error": error} if error else None,
            )

        return await self.tasks.get(task_id)  # type: ignore[return-value]

    async def dependencies_met(self, task_id: str) -> bool:
        deps = await self.tasks.get_dependencies(task_id)
        for dep in deps:
            dep_task = await self.tasks.get(dep.depends_on_task_id)
            if dep_task is None or dep_task.status != TaskStatus.COMPLETED:
                return False
        return True

    async def get(self, task_id: str) -> Task | None:
        return await self.tasks.get(task_id)

    async def list_for_project(self, project_id: str) -> list[Task]:
        return await self.tasks.list_for_project(project_id)

    @staticmethod
    def parse_output(task: Task) -> dict | None:
        return json.loads(task.output_data) if task.output_data else None

    @staticmethod
    def parse_input(task: Task) -> dict | None:
        return json.loads(task.input_data) if task.input_data else None
