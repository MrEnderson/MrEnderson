"""Defect 1 regression tests (v0.1.1 reliability patch): the FINAL executed
attempt's verdict/output must always be what gets returned from
run_worker_with_qa, persisted onto the Task row, and surfaced in the
executive report — never an earlier attempt's. Traced end to end through
AgentExecutor and build_report, not just the evaluator in isolation
(app/orchestration/evaluator.py already had this invariant correct — see
tests/test_qa_pass_termination.py for the unit-level proof — these tests
additionally cover the full persistence/report path). All offline,
deterministic stub agents — no network, no live API key."""
from __future__ import annotations

from app.agents.registry import build_default_registry
from app.database.models import TaskStatus
from app.database.repositories import UserRepository, WorkspaceRepository
from app.orchestration import dispatcher
from app.orchestration.executor import AgentExecutor, build_report
from app.schemas.agents import ExecutionOutput, QAVerdict
from app.services.project_service import ProjectService
from app.services.task_service import TaskService


class _ScriptedWorker:
    def __init__(self, descriptor, provider=None):
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        return ExecutionOutput(actions_performed=[f"attempt {self.calls}"])


def _scripted_qa_factory(script: list[tuple[str, float]]):
    class _ScriptedQA:
        def __init__(self, descriptor, provider=None):
            self.calls = 0

        async def run(self, **kwargs):
            assert self.calls < len(script), "QA called more times than the script provides"
            verdict, score = script[self.calls]
            self.calls += 1
            return QAVerdict(verdict=verdict, score=score, feedback=f"feedback:{verdict}:{self.calls}")

    return _ScriptedQA


async def _run_single_task_mission(session_factory, script: list[tuple[str, float]], *, max_agent_retries: int = 5):
    registry = build_default_registry()
    worker_cls = _ScriptedWorker
    qa_cls = _scripted_qa_factory(script)
    registry.register(registry.get_descriptor("research"), worker_cls)
    registry.register(registry.get_descriptor("qa"), qa_cls)

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("verdict@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        await TaskService(session).create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
        await session.commit()

    executor = AgentExecutor(session_factory, registry, provider=None)
    executor.settings = executor.settings.model_copy(update={"max_agent_retries": max_agent_retries})
    completed = await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    return completed[0], report, workspace_id, project_id


async def test_fail_needs_review_pass_persists_the_final_pass_verdict(session_factory):
    task, report, workspace_id, project_id = await _run_single_task_mission(
        session_factory, [("FAIL", 0.15), ("NEEDS_REVIEW", 0.72), ("PASS", 0.78)]
    )

    assert task.status == TaskStatus.COMPLETED
    output = TaskService.parse_output(task)
    assert output["qa_verdict"] == "PASS"
    assert output["qa_score"] == 0.78
    assert output["qa_feedback"] == "feedback:PASS:3"
    assert task.retry_count == 2  # 2 retries -> 3 total attempts

    # Report must not resurrect the earlier NEEDS_REVIEW feedback for a task
    # whose FINAL verdict is PASS.
    assert not any("NEEDS_REVIEW" in q for q in report.open_questions)
    assert not any("feedback:NEEDS_REVIEW" in q for q in report.open_questions)
    assert report.status == "COMPLETED"


async def test_fail_needs_review_pass_reaches_worker_and_qa_exactly_three_times(session_factory):
    registry = build_default_registry()
    worker_cls = _ScriptedWorker
    qa_cls = _scripted_qa_factory([("FAIL", 0.15), ("NEEDS_REVIEW", 0.72), ("PASS", 0.78)])
    registry.register(registry.get_descriptor("research"), worker_cls)
    registry.register(registry.get_descriptor("qa"), qa_cls)

    from app.orchestration.evaluator import run_worker_with_qa

    worker = worker_cls(None)
    qa = qa_cls(None)
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=5,
    )

    assert worker.calls == 3
    assert qa.calls == 3
    assert result.verdict.verdict == "PASS"
    assert result.attempts_used == 2
    # No fourth call happened — nothing executes after PASS.
    assert worker.calls == qa.calls == 3


async def test_fail_then_pass_persists_pass(session_factory):
    task, report, *_ = await _run_single_task_mission(session_factory, [("FAIL", 0.2), ("PASS", 0.85)])
    output = TaskService.parse_output(task)
    assert output["qa_verdict"] == "PASS"
    assert output["qa_score"] == 0.85
    assert task.retry_count == 1


async def test_needs_review_then_pass_persists_pass(session_factory):
    task, report, *_ = await _run_single_task_mission(session_factory, [("NEEDS_REVIEW", 0.5), ("PASS", 0.9)])
    output = TaskService.parse_output(task)
    assert output["qa_verdict"] == "PASS"
    assert output["qa_score"] == 0.9
    assert task.retry_count == 1


async def test_fail_needs_review_needs_review_persists_final_needs_review_on_exhaustion(session_factory):
    """Retry exhaustion (max_agent_retries=2 -> 3 total attempts) with no
    PASS ever reached: the LAST attempt's verdict (the second NEEDS_REVIEW,
    not the first FAIL) is what must be persisted."""
    task, report, *_ = await _run_single_task_mission(
        session_factory,
        [("FAIL", 0.3), ("NEEDS_REVIEW", 0.55), ("NEEDS_REVIEW", 0.6)],
        max_agent_retries=2,
    )
    output = TaskService.parse_output(task)
    assert output["qa_verdict"] == "NEEDS_REVIEW"
    assert output["qa_score"] == 0.6  # the LAST attempt's score, not the first FAIL's 0.3
    assert output["qa_feedback"] == "feedback:NEEDS_REVIEW:3"
    assert task.retry_count == 2
    assert report.status == "COMPLETED_WITH_REVIEW"
