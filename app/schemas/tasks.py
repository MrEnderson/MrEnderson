"""Task and execution-plan schemas. The planner MUST produce these, never free text."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.database.models import TaskPriority, TaskStatus
from app.schemas.evidence import ResearchMode


class TaskPlan(BaseModel):
    """One task within a structured execution plan, as produced by the planner."""

    key: str = Field(description="Unique short reference key within the plan, e.g. 'research_1'")
    title: str
    description: str
    agent_type: str
    dependencies: list[str] = Field(
        default_factory=list, description="Keys of other TaskPlans this task depends on"
    )
    priority: TaskPriority = TaskPriority.NORMAL
    requires_approval: bool = False
    success_criteria: str
    research_mode: ResearchMode | None = Field(
        default=None,
        description=(
            "Only meaningful for agent_type='research'. DISCOVERY for a task that must first "
            "identify candidate opportunities; VALIDATION for a task that depends on a DISCOVERY "
            "task and gathers candidate-specific evidence against common requirements. Omit "
            "(None) for ordinary single-topic research — app/agents/research.py then defaults to "
            "GENERAL, the unchanged v0.1.1/v0.1.2 behavior. See docs/research_intelligence.md."
        ),
    )


class ExecutionPlan(BaseModel):
    """Structured output of the planner. Never accept raw free-text as a plan."""

    objective: str
    tasks: list[TaskPlan]
    estimated_complexity: str = Field(description="low | medium | high")
    requires_approval: bool = False
    success_criteria: str


class TaskOut(BaseModel):
    id: str
    project_id: str
    parent_task_id: str | None
    assigned_agent_id: str | None
    agent_type: str
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    output_data: dict | None
    error: str | None
    requires_approval: bool
    retry_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}
