"""v0.1.2.6 Phase 10: usage attribution clarity. The live benchmark's
"Research (Anthropic/Haiku): 8 calls" bucket includes BOTH ResearchAgent's
own generation calls AND the QA evaluator calls that happen inside the
SAME research task — traced to app/orchestration/evaluator.py::
run_worker_with_qa, which used to collect worker and QA usage into one
shared list with no marker of which role made each call.

Task-level attribution (UsageService.record_many's agent_type=
task.agent_type) is UNCHANGED and intentional — a Research task's usage
rows are still recorded under agent_type="research". This checkpoint adds
an ADDITIONAL, finer-grained dimension (ModelUsage.role) without touching
that existing semantics, and surfaces both task attribution and the
worker-vs-QA split via Task.output_data (no migration — same JSON-carried
provenance pattern used throughout this project).

Offline — fake providers, no network call.
"""
from __future__ import annotations

from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, ResearchOutput


class _Worker:
    async def run(self, *, title, description, input_data, context):
        from app.agents.usage import ModelUsage, record_usage

        record_usage(ModelUsage(provider="anthropic", model="claude-haiku"))
        return ResearchOutput(question=title, findings=[], insufficient_evidence=False, summary="s")


class _QA:
    async def run(self, **kwargs):
        from app.agents.usage import ModelUsage, record_usage

        record_usage(ModelUsage(provider="anthropic", model="claude-haiku"))
        return QAVerdict(verdict="PASS", score=0.9, feedback="ok")


async def test_worker_and_qa_usage_events_are_tagged_with_their_actual_role():
    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_QA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    roles = sorted(e.role for e in result.usage_events)
    assert roles == ["qa", "worker"]


async def test_task_level_attribution_is_unchanged_by_role_tagging():
    """Both events still carry the SAME provider/model — task-level
    accounting (which sums ALL events regardless of role, attributed to
    the parent task's agent_type in executor.py) is unaffected; role is
    purely additive."""
    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_QA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    assert len(result.usage_events) == 2
    assert all(e.provider == "anthropic" and e.model == "claude-haiku" for e in result.usage_events)


async def test_multiple_retries_each_tag_worker_and_qa_events_independently():
    class _NeedsReviewThenPassQA:
        def __init__(self):
            self.calls = 0

        async def run(self, **kwargs):
            from app.agents.usage import ModelUsage, record_usage

            record_usage(ModelUsage(provider="anthropic", model="claude-haiku"))
            self.calls += 1
            passed = self.calls >= 2
            return QAVerdict(verdict="PASS" if passed else "NEEDS_REVIEW", score=0.9 if passed else 0.3, feedback="ok")

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_NeedsReviewThenPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=2,
    )
    worker_count = sum(1 for e in result.usage_events if e.role == "worker")
    qa_count = sum(1 for e in result.usage_events if e.role == "qa")
    assert worker_count == 2  # attempt 0 + retry 1
    assert qa_count == 2


async def test_worker_failure_still_tags_whatever_usage_was_recorded_before_it_raised():
    """A worker that records usage then raises must still surface that
    usage, correctly tagged 'worker' (never lost — see
    WorkerExecutionError), with qa_events correctly empty since QA was
    never reached."""
    from app.orchestration.evaluator import WorkerExecutionError

    class _RecordsThenRaises:
        async def run(self, *, title, description, input_data, context):
            from app.agents.usage import ModelUsage, record_usage

            record_usage(ModelUsage(provider="anthropic", model="claude-haiku"))
            raise ValueError("boom")

    try:
        await run_worker_with_qa(
            worker_agent=_RecordsThenRaises(), qa_agent=_QA(), title="t", description="",
            input_data={}, success_criteria=None, max_retries=0,
        )
        assert False, "expected WorkerExecutionError"
    except WorkerExecutionError as exc:
        assert len(exc.usage_events) == 1
        assert exc.usage_events[0].role == "worker"


async def test_task_output_carries_worker_vs_qa_call_counts_no_migration(session_factory):
    """End-to-end through app/orchestration/executor.py: the completed
    task's own output_data carries worker_model_calls/qa_model_calls —
    plain JSON fields, no new database column."""
    from app.agents.registry import build_default_registry
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration import dispatcher
    from app.orchestration.executor import AgentExecutor
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    class _StubResearchAgent:
        def __init__(self, descriptor, provider=None):
            pass

        async def run(self, **kwargs):
            return await _Worker().run(**kwargs)

    class _StubQAAgent:
        def __init__(self, descriptor, provider=None):
            pass

        async def run(self, **kwargs):
            return await _QA().run(**kwargs)

    registry = build_default_registry()
    registry.register(registry.get_descriptor("research"), _StubResearchAgent)
    registry.register(registry.get_descriptor("qa"), _StubQAAgent)

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("roleattr@example.com")
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
    completed = await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)
    assert len(completed) == 1

    async with session_factory() as session:
        from app.services.task_service import TaskService as TS

        task = await TS(session).get(completed[0].id)
        output = TS(session).parse_output(task)
        assert output.get("worker_model_calls") == 1
        assert output.get("qa_model_calls") == 1
