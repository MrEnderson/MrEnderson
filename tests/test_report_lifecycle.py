"""Mission status/next-action lifecycle: the stale "Connect a live
ResearchProvider" message when live research demonstrably ran, the new
COMPLETED_WITH_REVIEW status for unresolved QA quality, and that the final
QA verdict shown is always the latest attempt's. Offline only."""
from __future__ import annotations

from app.database.models import TaskStatus
from app.schemas.agents import QAVerdict


# --- Stale next-action fix for structured-output failures / auth failures ---


async def test_structured_output_failure_next_action_not_stale_research_message(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.schemas.evidence import EvidenceItem
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("s@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        # Live evidence WAS gathered before the failure (persisted, exactly
        # as AgentExecutor now does even on task failure).
        item = EvidenceItem(claim="c", source_url="https://example.com/a")
        await EvidenceService(session).store_many(
            workspace_id=workspace_id, project_id=project_id, task_id=task_id, items=[item]
        )
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.FAILED,
            workspace_id=workspace_id,
            error="Structured output could not be parsed: Invalid JSON: EOF while parsing a string",
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    assert not any("Connect a live ResearchProvider" in a for a in report.next_actions)
    assert any("structured-output" in a.lower() or "structured output" in a.lower() for a in report.next_actions)
    assert report.status == "COMPLETED_WITH_FAILURES"


async def test_authentication_failure_next_action(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("auth@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.FAILED,
            workspace_id=workspace_id,
            error="Authentication failed: Anthropic rejected the API key (HTTP 401).",
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    assert any("authentication" in a.lower() for a in report.next_actions)
    assert not any("Connect a live ResearchProvider" in a for a in report.next_actions)


# --- COMPLETED_WITH_REVIEW status -------------------------------------------


async def test_completed_with_review_when_final_verdict_is_needs_review(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("rev@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "question": "X", "findings": [], "evidence": [], "assumptions": [],
                "unsupported_claims": [], "open_questions": [], "evidence_gaps": [],
                "insufficient_evidence": True, "summary": "s",
                "qa_verdict": "NEEDS_REVIEW", "qa_score": 0.4, "qa_feedback": "needs more",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )
    assert report.status == "COMPLETED_WITH_REVIEW"


async def test_plain_completed_when_all_verdicts_pass(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("pass@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research X", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "question": "X", "findings": [], "evidence": [], "assumptions": [],
                "unsupported_claims": [], "open_questions": [], "evidence_gaps": [],
                "insufficient_evidence": False, "summary": "s",
                "qa_verdict": "PASS", "qa_score": 0.9, "qa_feedback": "fine",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )
    assert report.status == "COMPLETED"


async def test_failed_task_takes_priority_over_needs_review_status(session_factory):
    """COMPLETED_WITH_FAILURES must still win over COMPLETED_WITH_REVIEW when
    both a hard failure and a non-passing verdict are present."""
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("mix@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        t1 = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research A", agent_type="research"
        )
        t2 = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Research B", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id = workspace.id, project.id
        t1_id, t2_id = t1.id, t2.id

    async with session_factory() as session:
        ts = TaskService(session)
        for tid in (t1_id, t2_id):
            await ts.transition(tid, TaskStatus.READY, workspace_id=workspace_id)
            await ts.transition(tid, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            t1_id, TaskStatus.COMPLETED, workspace_id=workspace_id,
            output_data={
                "question": "A", "findings": [], "evidence": [], "assumptions": [],
                "unsupported_claims": [], "open_questions": [], "evidence_gaps": [],
                "insufficient_evidence": False, "summary": "s",
                "qa_verdict": "NEEDS_REVIEW", "qa_score": 0.4, "qa_feedback": "x",
            },
        )
        await ts.transition(t2_id, TaskStatus.FAILED, workspace_id=workspace_id, error="boom")
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )
    assert report.status == "COMPLETED_WITH_FAILURES"


# --- Phase 8: report quality when budget stops before final QA -------------


async def test_recommendation_labeled_preliminary_when_budget_stops_before_final_qa(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("prelim@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        strategy_task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Strategy", agent_type="strategy"
        )
        # A task that never even started — the mission stopped before it could run.
        await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Final QA review", agent_type="qa"
        )
        await session.commit()
        workspace_id, project_id, strategy_id = workspace.id, project.id, strategy_task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(strategy_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(strategy_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            strategy_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "options_considered": [], "recommendation": "Launch product X",
                "reasoning": "r", "assumptions": ["a"], "evidence_used": [],
                "unsupported_claims": [], "confidence": 0.6,
                "qa_verdict": "NEEDS_REVIEW", "qa_score": 0.55, "qa_feedback": "needs more evidence",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj",
            budget_stopped_reason="MAX_TOKENS_PER_MISSION (200000) reached",
        )

    assert report.status == "STOPPED_BUDGET_LIMIT"
    assert report.recommendation.startswith("PRELIMINARY")
    assert "Launch product X" in report.recommendation
    assert not report.recommendation.startswith("Launch product X")  # never an unqualified launch instruction
    assert any("NOT STARTED" in item for item in report.what_was_done)
    assert any("Final QA review" in item for item in report.what_was_done)


async def test_recommendation_not_labeled_preliminary_when_fully_passed_before_budget_note(session_factory):
    """If everything that mattered actually completed and passed, a
    budget_stopped_reason noted afterward must not falsely downgrade a
    clean recommendation to 'preliminary'."""
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("clean@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        strategy_task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Strategy", agent_type="strategy"
        )
        await session.commit()
        workspace_id, project_id, strategy_id = workspace.id, project.id, strategy_task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(strategy_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(strategy_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            strategy_id,
            TaskStatus.COMPLETED,
            workspace_id=workspace_id,
            output_data={
                "options_considered": [], "recommendation": "Launch product X",
                "reasoning": "r", "assumptions": ["a"], "evidence_used": [],
                "unsupported_claims": [], "confidence": 0.9,
                "qa_verdict": "PASS", "qa_score": 0.9, "qa_feedback": "fine",
            },
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj",
            budget_stopped_reason="MAX_TOKENS_PER_MISSION (200000) reached",
        )

    assert report.recommendation == "Launch product X"
    assert not report.recommendation.startswith("PRELIMINARY")


# --- Final QA verdict is the latest attempt's, not stale ---------------------


async def test_final_verdict_is_latest_attempt_not_first():
    from app.orchestration.evaluator import run_worker_with_qa
    from app.schemas.agents import ExecutionOutput

    class _Worker:
        async def run(self, **kwargs):
            return ExecutionOutput(actions_performed=["did a thing"])

    class _QASequence:
        def __init__(self, verdicts):
            self.verdicts = verdicts
            self.calls = 0

        async def run(self, **kwargs):
            v = self.verdicts[self.calls]
            self.calls += 1
            return QAVerdict(verdict=v, score=0.9 if v == "PASS" else 0.3, feedback=f"attempt {self.calls}")

    qa = _QASequence(["FAIL", "NEEDS_REVIEW", "PASS"])
    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=qa, title="t", description="",
        input_data={}, success_criteria=None, max_retries=3,
    )
    assert result.verdict.verdict == "PASS"
    assert result.verdict.feedback == "attempt 3"


async def test_final_verdict_reflects_retry_exhaustion_not_first_failure():
    from app.orchestration.evaluator import run_worker_with_qa
    from app.schemas.agents import ExecutionOutput

    class _Worker:
        async def run(self, **kwargs):
            return ExecutionOutput(actions_performed=["did a thing"])

    class _QASequence:
        def __init__(self, verdicts):
            self.verdicts = verdicts
            self.calls = 0

        async def run(self, **kwargs):
            v = self.verdicts[min(self.calls, len(self.verdicts) - 1)]
            self.calls += 1
            return QAVerdict(verdict=v, score=0.3, feedback=f"attempt {self.calls}")

    qa = _QASequence(["FAIL", "NEEDS_REVIEW"])
    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=qa, title="t", description="",
        input_data={}, success_criteria=None, max_retries=1,
    )
    # Must reflect the LATEST (2nd) attempt's verdict, not the stale first one.
    assert result.verdict.verdict == "NEEDS_REVIEW"
    assert result.verdict.feedback == "attempt 2"
