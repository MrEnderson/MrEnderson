"""Working memory (this run only) and long-term memory promotion policy.

Working memory lives in-process for the lifetime of one orchestration run and is
never persisted as-is. Long-term memory is written only when something is
explicitly promoted — we do not save every task result or conversation turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Approval, MemoryType, Task
from app.services.memory_service import MemoryService


@dataclass
class WorkingMemory:
    """Ephemeral per-run context: current project, objective, tasks, results, approvals."""

    project_id: str
    objective: str
    tasks: dict[str, Task] = field(default_factory=dict)
    task_results: dict[str, dict] = field(default_factory=dict)
    active_approvals: list[Approval] = field(default_factory=list)

    def record_task(self, task: Task) -> None:
        self.tasks[task.id] = task

    def record_result(self, task_id: str, result: dict) -> None:
        self.task_results[task_id] = result

    def record_approval(self, approval: Approval) -> None:
        self.active_approvals.append(approval)


class MemoryManager:
    """Decides what, from a run's working memory, is worth promoting long-term."""

    def __init__(self, session: AsyncSession):
        self.service = MemoryService(session)

    async def promote_research(
        self, workspace_id: str, question: str, summary: str, insufficient_evidence: bool
    ) -> None:
        await self.service.store(
            workspace_id=workspace_id,
            type=MemoryType.RESEARCH,
            title=f"Research: {question}",
            content=summary,
            source="research_agent",
            importance=2 if insufficient_evidence else 4,
        )

    async def promote_decision(self, workspace_id: str, title: str, content: str) -> None:
        await self.service.store(
            workspace_id=workspace_id,
            type=MemoryType.DECISION,
            title=title,
            content=content,
            source="strategy_agent",
            importance=5,
        )

    async def promote_lesson(self, workspace_id: str, title: str, content: str) -> None:
        await self.service.store(
            workspace_id=workspace_id,
            type=MemoryType.LESSON,
            title=title,
            content=content,
            source="qa_agent",
            importance=4,
        )
