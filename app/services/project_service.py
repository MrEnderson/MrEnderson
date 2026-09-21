from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Project
from app.database.repositories import AuditRepository, ProjectRepository, TaskRepository
from app.security.audit import AuditEventType, record_event


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.projects = ProjectRepository(session)
        self.tasks = TaskRepository(session)
        self.audit = AuditRepository(session)

    async def create_project(
        self, workspace_id: str, name: str, description: str | None = None
    ) -> Project:
        project = await self.projects.create(workspace_id, name, description)
        await record_event(
            self.session,
            workspace_id=workspace_id,
            actor_type="human",
            event_type=AuditEventType.TASK_CREATED,
            entity_type="project",
            entity_id=project.id,
            metadata={"name": name},
        )
        return project

    async def set_objective(self, workspace_id: str, project_id: str, objective: str) -> Project:
        project = await self.projects.set_objective(project_id, objective)
        if project is None:
            raise ValueError(f"Project {project_id} not found")
        await record_event(
            self.session,
            workspace_id=workspace_id,
            actor_type="human",
            event_type=AuditEventType.OBJECTIVE_CREATED,
            entity_type="project",
            entity_id=project_id,
            metadata={"objective": objective},
        )
        return project

    async def get(self, project_id: str) -> Project | None:
        return await self.projects.get(project_id)

    async def list_for_workspace(self, workspace_id: str) -> list[Project]:
        return await self.projects.list_for_workspace(workspace_id)

    async def get_audit_trail(self, project_id: str, limit: int = 200):
        tasks = await self.tasks.list_for_project(project_id)
        task_ids = [t.id for t in tasks]
        return await self.audit.list_for_entities(
            {"project": [project_id], "task": task_ids}, limit=limit
        )
