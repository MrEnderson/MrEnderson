"""Usage and evidence accounting must survive a task failure — the exact bug
from the live benchmark: two fully successful research attempts' Anthropic +
Tavily usage vanished entirely when a third attempt's structured-output
parsing failed. Offline only — stub agents raise synthetically; no real
Anthropic or Tavily call anywhere in this file."""
from __future__ import annotations

from app.agents.usage import ModelUsage, record_usage
from app.orchestration.evaluator import WorkerExecutionError, run_worker_with_qa
from app.schemas.agents import QAVerdict, ResearchOutput
from app.schemas.evidence import EvidenceItem


class _AlwaysPassQA:
    async def run(self, **kwargs):
        return QAVerdict(verdict="PASS", score=0.9, feedback="ok")


class _SucceedThenRaiseWorker:
    """Two fully successful attempts (each recording real usage and gathering
    real evidence), then a third attempt whose own provider call raises after
    already recording some usage (mirrors AnthropicProvider recording usage
    for a call that then fails to parse)."""

    def __init__(self):
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        if self.calls <= 2:
            record_usage(ModelUsage(provider="anthropic", model="claude-x", input_tokens=100, output_tokens=50))
            record_usage(ModelUsage(provider="tavily", model="search"))
            return ResearchOutput(
                question=title,
                findings=[],
                evidence=[
                    EvidenceItem(
                        claim=f"c{self.calls}", source_url=f"https://example.com/{self.calls}"
                    )
                ],
                insufficient_evidence=True,
                unsupported_claims=[f"still missing something (attempt {self.calls})"],
                summary="s",
            )
        # Third attempt: a real provider call happens (usage recorded) and
        # THEN parsing fails — exactly ModelOutputParsingError's contract.
        record_usage(ModelUsage(provider="anthropic", model="claude-x", input_tokens=None, output_tokens=None))
        raise ValueError("Structured output could not be parsed: Invalid JSON: EOF while parsing a string")


class _AlwaysFailFirstAttemptQA:
    async def run(self, **kwargs):
        return QAVerdict(verdict="NEEDS_REVIEW", score=0.4, feedback="needs more evidence")


async def test_worker_execution_error_carries_prior_successful_attempts_usage():
    worker = _SucceedThenRaiseWorker()
    try:
        await run_worker_with_qa(
            worker_agent=worker, qa_agent=_AlwaysFailFirstAttemptQA(), title="t", description="",
            input_data={}, success_criteria=None, max_retries=5,
        )
        assert False, "expected WorkerExecutionError"
    except WorkerExecutionError as exc:
        providers = [e.provider for e in exc.usage_events]
        # Two successful attempts x (anthropic + tavily) + the failing
        # attempt's own anthropic call = 5 events, none lost.
        assert providers.count("anthropic") == 3
        assert providers.count("tavily") == 2


async def test_worker_execution_error_carries_accumulated_evidence_from_prior_attempts():
    worker = _SucceedThenRaiseWorker()
    try:
        await run_worker_with_qa(
            worker_agent=worker, qa_agent=_AlwaysFailFirstAttemptQA(), title="t", description="",
            input_data={}, success_criteria=None, max_retries=5,
        )
        assert False, "expected WorkerExecutionError"
    except WorkerExecutionError as exc:
        urls = {e.source_url for e in exc.accumulated_evidence}
        assert urls == {"https://example.com/1", "https://example.com/2"}


async def test_worker_execution_error_preserves_attempts_used():
    worker = _SucceedThenRaiseWorker()
    try:
        await run_worker_with_qa(
            worker_agent=worker, qa_agent=_AlwaysFailFirstAttemptQA(), title="t", description="",
            input_data={}, success_criteria=None, max_retries=5,
        )
        assert False, "expected WorkerExecutionError"
    except WorkerExecutionError as exc:
        assert exc.attempts_used == 2  # two retries happened before the third (failing) attempt


async def test_tavily_search_and_extract_usage_both_survive_a_later_failure():
    """Item 16/17: search AND extract usage each individually survive a
    later attempt's hard failure, distinguishable from each other."""

    class _Worker:
        def __init__(self):
            self.calls = 0

        async def run(self, *, title, description, input_data, context):
            self.calls += 1
            if self.calls == 1:
                record_usage(ModelUsage(provider="tavily", model="search"))
                return ResearchOutput(
                    question=title, findings=[], evidence=[], insufficient_evidence=True, summary="s",
                )
            if self.calls == 2:
                record_usage(ModelUsage(provider="tavily", model="extract"))
                raise ValueError("Structured output could not be parsed: EOF while parsing")
            raise AssertionError("should not be called a third time")

    worker = _Worker()
    try:
        await run_worker_with_qa(
            worker_agent=worker, qa_agent=_AlwaysFailFirstAttemptQA(), title="t", description="",
            input_data={}, success_criteria=None, max_retries=1,
        )
        assert False, "expected WorkerExecutionError"
    except WorkerExecutionError as exc:
        models = [e.model for e in exc.usage_events if e.provider == "tavily"]
        assert "search" in models
        assert "extract" in models


async def test_immediate_first_attempt_failure_still_reports_zero_lost_usage_gracefully():
    class _AlwaysRaiseWorker:
        async def run(self, **kwargs):
            record_usage(ModelUsage(provider="anthropic", model="claude-x"))
            raise ValueError("boom")

    try:
        await run_worker_with_qa(
            worker_agent=_AlwaysRaiseWorker(), qa_agent=_AlwaysPassQA(), title="t", description="",
            input_data={}, success_criteria=None, max_retries=2,
        )
        assert False, "expected WorkerExecutionError"
    except WorkerExecutionError as exc:
        assert len(exc.usage_events) == 1
        assert exc.attempts_used == 0


# --- End-to-end through AgentExecutor: usage/evidence persisted on failure --


async def test_failed_research_task_still_persists_prior_usage_and_evidence(session_factory):
    from app.agents.registry import RegisteredAgent, build_default_registry
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration import dispatcher
    from app.orchestration.executor import AgentExecutor
    from app.services.evidence_service import EvidenceService
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService
    from app.services.usage_service import UsageService

    class _StubResearchAgent:
        def __init__(self, descriptor, provider=None):
            self.descriptor = descriptor
            self._worker = _SucceedThenRaiseWorker()

        async def run(self, **kwargs):
            return await self._worker.run(**kwargs)

    class _StubQAAgent:
        def __init__(self, descriptor, provider=None):
            self.descriptor = descriptor

        async def run(self, **kwargs):
            return QAVerdict(verdict="NEEDS_REVIEW", score=0.4, feedback="needs more evidence")

    registry = build_default_registry()
    registry.register(registry.get_descriptor("research"), _StubResearchAgent)
    registry.register(registry.get_descriptor("qa"), _StubQAAgent)

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("failure@example.com")
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
    from app.config.settings import get_settings
    settings = get_settings()
    settings_with_retries = settings.model_copy(update={"max_agent_retries": 5})
    executor.settings = settings_with_retries
    completed = await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)

    assert len(completed) == 1
    assert completed[0].status.value == "FAILED"

    async with session_factory() as session:
        totals = await UsageService(session).totals_for_project(project_id)
        # Two successful attempts' usage (anthropic x2 + tavily x2) plus the
        # third attempt's own anthropic call = 5 API calls, not 0.
        assert totals.api_calls == 5

        stored_evidence = await EvidenceService(session).list_for_project(project_id)
        assert len(stored_evidence) == 2
        assert {e.source_url for e in stored_evidence} == {
            "https://example.com/1",
            "https://example.com/2",
        }
