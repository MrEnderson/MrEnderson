"""FastAPI routes. Thin controllers — all real logic lives in services/orchestration."""
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.providers import get_default_provider
from app.agents.registry import build_default_registry
from app.config.settings import get_settings
from app.database.connection import get_session_factory
from app.database.repositories import UserRepository, WorkspaceRepository
from app.orchestration.executor import run_objective
from app.schemas.approvals import ApprovalDecision
from app.schemas.projects import (
    ChatRequest,
    ChatResponse,
    ObjectiveCreate,
    ProjectCreate,
    ProjectOut,
    WorkspaceCreate,
    WorkspaceOut,
)
from app.schemas.tasks import TaskOut
from app.services.approval_service import ApprovalService
from app.services.project_service import ProjectService

router = APIRouter()

_registry = build_default_registry()
_provider = get_default_provider()


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@router.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "environment": settings.jarvis_env,
        "model_provider": _provider.name,
        "agents": [a.name for a in _registry.list_agents()],
    }


@router.post("/workspaces", response_model=WorkspaceOut)
async def create_workspace(payload: WorkspaceCreate, session: AsyncSession = Depends(get_db)):
    user = await UserRepository(session).get_or_create_by_email(payload.user_email)
    workspace = await WorkspaceRepository(session).create(user.id, payload.name, payload.description)
    return workspace


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceOut)
async def get_workspace(workspace_id: str, session: AsyncSession = Depends(get_db)):
    workspace = await WorkspaceRepository(session).get(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.post("/projects", response_model=ProjectOut)
async def create_project(payload: ProjectCreate, session: AsyncSession = Depends(get_db)):
    project = await ProjectService(session).create_project(
        payload.workspace_id, payload.name, payload.description
    )
    return project


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, session: AsyncSession = Depends(get_db)):
    project = await ProjectService(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects/{project_id}/objectives", response_model=ProjectOut)
async def set_objective(project_id: str, payload: ObjectiveCreate, session: AsyncSession = Depends(get_db)):
    project = await ProjectService(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return await ProjectService(session).set_objective(project.workspace_id, project_id, payload.objective)


@router.get("/projects/{project_id}/tasks", response_model=list[TaskOut])
async def list_tasks(project_id: str, session: AsyncSession = Depends(get_db)):
    from app.services.task_service import TaskService

    tasks = await TaskService(session).list_for_project(project_id)
    return [_task_to_out(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, session: AsyncSession = Depends(get_db)):
    from app.services.task_service import TaskService

    task = await TaskService(session).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_out(task)


@router.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str, payload: ApprovalDecision, session: AsyncSession = Depends(get_db)):
    approval_service = ApprovalService(session)
    approval = await approval_service.approvals.get_for_task(task_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="No approval request found for this task")
    approved = await approval_service.approve(approval.id, payload.resolved_by, payload.decision_reason)
    return approved


@router.post("/tasks/{task_id}/reject")
async def reject_task(task_id: str, payload: ApprovalDecision, session: AsyncSession = Depends(get_db)):
    approval_service = ApprovalService(session)
    approval = await approval_service.approvals.get_for_task(task_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="No approval request found for this task")
    rejected = await approval_service.reject(approval.id, payload.resolved_by, payload.decision_reason)
    return rejected


@router.get("/projects/{project_id}/audit")
async def get_audit(project_id: str, session: AsyncSession = Depends(get_db)):
    events = await ProjectService(session).get_audit_trail(project_id)
    return [
        {
            "id": e.id,
            "actor_type": e.actor_type,
            "actor_id": e.actor_id,
            "event_type": e.event_type,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, session: AsyncSession = Depends(get_db)):
    user = await UserRepository(session).get_or_create_by_email(payload.user_email)

    if payload.workspace_id:
        workspace = await WorkspaceRepository(session).get(payload.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
    else:
        workspace = await WorkspaceRepository(session).create(
            user.id, payload.workspace_name or "Default Workspace"
        )

    project_service = ProjectService(session)
    if payload.project_id:
        project = await project_service.get(payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
    else:
        project = await project_service.create_project(
            workspace.id, payload.project_name or payload.objective[:80]
        )
    workspace_id, project_id = workspace.id, project.id
    await project_service.set_objective(workspace_id, project_id, payload.objective)

    report = await run_objective(
        session,
        _registry,
        _provider,
        workspace_id=workspace_id,
        project_id=project_id,
        objective=payload.objective,
    )

    from app.services.task_service import TaskService

    tasks = await TaskService(session).list_for_project(project_id)

    return ChatResponse(
        run_id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        project_id=project_id,
        objective=payload.objective,
        status=report.status,
        message=report.to_text(),
        tasks=[_task_to_out(t).model_dump(mode="json") for t in tasks],
        approvals_required=report.approvals_required,
    )


def _task_to_out(task) -> TaskOut:
    import json

    return TaskOut(
        id=task.id,
        project_id=task.project_id,
        parent_task_id=task.parent_task_id,
        assigned_agent_id=task.assigned_agent_id,
        agent_type=task.agent_type,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        output_data=json.loads(task.output_data) if task.output_data else None,
        error=task.error,
        requires_approval=task.requires_approval,
        retry_count=task.retry_count,
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
    )
