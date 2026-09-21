"""Planner validation, agent routing, parallel execution, and the QA retry loop
(including the maximum-retry ceiling). Uses stub agents where determinism matters
more than realism, and the MockProvider elsewhere."""
from __future__ import annotations

import pytest

from app.agents.usage import ModelUsage, record_usage
from app.database.models import TaskStatus
from app.orchestration.evaluator import run_worker_with_qa
from app.orchestration.executor import AgentExecutor, run_objective
from app.orchestration.planner import PlanValidationError, create_plan
from app.schemas.agents import ExecutionOutput, QAVerdict
from app.schemas.tasks import ExecutionPlan, TaskPlan


class _FakeJarvis:
    def __init__(self, plan: ExecutionPlan):
        self._plan = plan

    async def plan(self, objective: str) -> ExecutionPlan:
        return self._plan


class _StubWorker:
    def __init__(self):
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        return ExecutionOutput(actions_performed=[f"attempt {self.calls}"])


class _StubQA:
    def __init__(self, verdicts: list[str]):
        self.verdicts = verdicts
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        verdict = self.verdicts[min(self.calls, len(self.verdicts) - 1)]
        self.calls += 1
        return QAVerdict(verdict=verdict, score=0.9 if verdict == "PASS" else 0.3, feedback="feedback")


# --- Planner validation -----------------------------------------------------


async def test_planner_rejects_empty_objective():
    with pytest.raises(PlanValidationError):
        await create_plan(_FakeJarvis(None), "   ")


async def test_planner_rejects_duplicate_task_keys():
    plan = ExecutionPlan(
        objective="x",
        tasks=[
            TaskPlan(key="a", title="A", description="d", agent_type="research", success_criteria="c"),
            TaskPlan(key="a", title="A2", description="d", agent_type="research", success_criteria="c"),
        ],
        estimated_complexity="low",
        success_criteria="c",
    )
    with pytest.raises(PlanValidationError):
        await create_plan(_FakeJarvis(plan), "x")


async def test_planner_rejects_unknown_dependency():
    plan = ExecutionPlan(
        objective="x",
        tasks=[
            TaskPlan(
                key="a", title="A", description="d", agent_type="research",
                dependencies=["missing"], success_criteria="c",
            ),
        ],
        estimated_complexity="low",
        success_criteria="c",
    )
    with pytest.raises(PlanValidationError):
        await create_plan(_FakeJarvis(plan), "x")


async def test_planner_rejects_cyclic_dependencies():
    plan = ExecutionPlan(
        objective="x",
        tasks=[
            TaskPlan(key="a", title="A", description="d", agent_type="research", dependencies=["b"], success_criteria="c"),
            TaskPlan(key="b", title="B", description="d", agent_type="research", dependencies=["a"], success_criteria="c"),
        ],
        estimated_complexity="low",
        success_criteria="c",
    )
    with pytest.raises(PlanValidationError):
        await create_plan(_FakeJarvis(plan), "x")


# --- Agent routing -----------------------------------------------------------


def test_registry_creates_correct_agent_classes(registry, provider):
    from app.agents.execution import ExecutionAgent
    from app.agents.jarvis import JarvisAgent
    from app.agents.qa import QAAgent
    from app.agents.research import ResearchAgent
    from app.agents.strategy import StrategyAgent

    assert isinstance(registry.create("research", provider=provider), ResearchAgent)
    assert isinstance(registry.create("strategy", provider=provider), StrategyAgent)
    assert isinstance(registry.create("execution", provider=provider), ExecutionAgent)
    assert isinstance(registry.create("qa", provider=provider), QAAgent)
    assert isinstance(registry.create("jarvis", provider=provider), JarvisAgent)


# --- QA retry loop -------------------------------------------------------------


async def test_qa_retry_loop_succeeds_after_failures():
    worker = _StubWorker()
    qa = _StubQA(["FAIL", "FAIL", "PASS"])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=2,
    )

    assert result.verdict.verdict == "PASS"
    assert result.attempts_used == 2
    assert worker.calls == 3


async def test_qa_retry_loop_respects_max_retries():
    worker = _StubWorker()
    qa = _StubQA(["FAIL", "FAIL", "FAIL", "FAIL"])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=2,
    )

    assert result.verdict.verdict == "FAIL"
    assert result.attempts_used == 2
    assert worker.calls == 3  # initial attempt + 2 retries, never more


class _UsageEmittingWorker:
    """Simulates a worker whose ModelProvider call records real usage,
    so each retry attempt's usage can be checked for correct tagging."""

    def __init__(self):
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        record_usage(ModelUsage(provider="mock", model="m", api_calls=1))
        return ExecutionOutput(actions_performed=[f"attempt {self.calls}"])


async def test_retry_usage_events_are_tagged_with_their_attempt_number():
    worker = _UsageEmittingWorker()
    qa = _StubQA(["FAIL", "FAIL", "PASS"])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=2,
    )

    assert result.attempts_used == 2
    assert [e.retry_number for e in result.usage_events] == [0, 1, 2]


# --- Parallel execution --------------------------------------------------------


async def test_independent_tasks_execute_concurrently(session_factory, registry, provider):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration import dispatcher
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("p@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        service = TaskService(session)
        await service.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research A", agent_type="research"
        )
        await service.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research B", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
        await session.commit()

    executor = AgentExecutor(session_factory, registry, provider)
    completed = await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)

    assert len(completed) == 2
    assert all(t.status == TaskStatus.COMPLETED for t in completed)


# --- Failure handling -----------------------------------------------------------


async def test_unregistered_agent_type_fails_task_without_crashing_run(session_factory, registry, provider):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration import dispatcher
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("f@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        await TaskService(session).create_task(
            workspace_id=workspace.id,
            project_id=project.id,
            title="Unknown work",
            agent_type="marketing",  # not registered in v0.1
        )
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
        await session.commit()

    executor = AgentExecutor(session_factory, registry, provider)
    completed = await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)

    assert len(completed) == 1
    assert completed[0].status == TaskStatus.FAILED
    assert completed[0].error


# --- Full pipeline (first end-to-end demo) -------------------------------------


async def test_run_objective_end_to_end(session_factory, registry, provider):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.services.project_service import ProjectService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("demo@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "Demo WS")
        project = await ProjectService(session).create_project(workspace.id, "Demo Project")
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        report = await run_objective(
            session,
            registry,
            provider,
            workspace_id=workspace_id,
            project_id=project_id,
            objective="Find three potential digital-product opportunities and recommend the strongest one.",
        )

    # MockProvider's research output always self-labels insufficient_evidence
    # (dev/sample data), so its self-QA always ends at NEEDS_REVIEW after
    # exhausting retries — the mission must honestly reflect that rather than
    # reporting a clean COMPLETED (see app/orchestration/executor.py::build_report).
    assert report.status == "COMPLETED_WITH_REVIEW"
    assert report.what_was_done
    assert report.recommendation
    assert not report.approvals_required
