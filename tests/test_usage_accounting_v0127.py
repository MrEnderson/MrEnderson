"""v0.1.2.7 Phase 8: worker_model_calls/qa_model_calls accounting defect.

The v0.1.2.6 live benchmark reported implausibly high worker call counts
(e.g. "worker model calls: 16" for a Validation task) with no matching
Anthropic request volume in the live log.

Root cause: app/tools/research_tools.py::TavilyResearchProvider._post calls
the SAME app.agents.usage.record_usage() side-channel every real LLM
provider call goes through, and that call happens INSIDE
app/orchestration/evaluator.py::run_worker_with_qa's `with collect_usage()
as worker_events:` block (because the worker's own agent.run() is what
issues the Tavily searches). Every worker_events entry — Tavily search,
Tavily extract, AND the one real Anthropic completion — was then blanket
tagged `role="worker"`, and app/orchestration/executor.py summed ALL of
them as worker_model_calls. `role` answers WHO issued a call (worker vs QA)
but never WHAT was called — Tavily's retrieval calls were being counted as
LLM completion calls just because they happened to be issued by the worker.

Fix: ModelUsage gained `is_model_call: bool = True` (see app/agents/
usage.py) — true for every existing model-provider call site (Anthropic/
OpenAI/Mock, unchanged), explicitly False only for Tavily's record_usage()
call. executor.py's worker_model_calls/qa_model_calls sums now require
`role == <role> AND is_model_call` — Tavily calls are excluded regardless
of which role's collect_usage() block they were issued inside.

No mission-level usage accounting changed (UsageService/totals_for_project
still sum everything, unchanged) and no database migration — `role`/
`is_model_call` are JSON-carried Task.output_data fields, never persisted
columns. Offline only — fake providers, no network call.
"""
from __future__ import annotations

from app.agents.usage import ModelUsage, record_usage
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, ResearchOutput


class _AlwaysPassQA:
    async def run(self, **kwargs):
        return QAVerdict(verdict="PASS", score=0.9, feedback="ok")


def _tavily_event(model: str) -> ModelUsage:
    """Exactly what app/tools/research_tools.py's real Tavily provider now
    records — is_model_call explicitly False."""
    return ModelUsage(provider="tavily", model=model, is_model_call=False)


def _anthropic_event(**kwargs) -> ModelUsage:
    return ModelUsage(provider="anthropic", model="claude-x", **kwargs)


# --- Tavily search/extract are never counted as worker model calls ---------


async def test_tavily_search_is_not_counted_as_a_worker_model_call():
    class _Worker:
        async def run(self, *, title, description, input_data, context):
            record_usage(_tavily_event("search"))
            record_usage(_anthropic_event())
            return ResearchOutput(question=title, findings=[], insufficient_evidence=False, summary="s")

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    worker_model_calls = sum(
        e.api_calls for e in result.usage_events if e.role == "worker" and e.is_model_call
    )
    assert worker_model_calls == 1  # only the real Anthropic call


async def test_tavily_extract_is_not_counted_as_a_worker_model_call():
    class _Worker:
        async def run(self, *, title, description, input_data, context):
            record_usage(_tavily_event("search"))
            record_usage(_tavily_event("search"))
            record_usage(_tavily_event("extract"))
            record_usage(_tavily_event("extract"))
            record_usage(_anthropic_event())
            return ResearchOutput(question=title, findings=[], insufficient_evidence=False, summary="s")

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    worker_model_calls = sum(
        e.api_calls for e in result.usage_events if e.role == "worker" and e.is_model_call
    )
    assert worker_model_calls == 1
    tavily_events = [e for e in result.usage_events if e.provider == "tavily"]
    assert len(tavily_events) == 4
    assert all(not e.is_model_call for e in tavily_events)


async def test_many_tavily_calls_do_not_inflate_worker_model_calls_reproducing_the_live_benchmark():
    """Reproduces the exact live-benchmark shape: many Tavily searches (one
    per candidate-scoped query across several retry attempts) but only a
    small, real number of Anthropic worker calls."""

    class _Worker:
        async def run(self, *, title, description, input_data, context):
            for _ in range(5):  # e.g. 3 candidates + 2 gap-retry queries this attempt
                record_usage(_tavily_event("search"))
            record_usage(_anthropic_event())
            return ResearchOutput(
                question=title, findings=[], insufficient_evidence=True, summary="s", evidence_gaps=[],
            )

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    worker_model_calls = sum(
        e.api_calls for e in result.usage_events if e.role == "worker" and e.is_model_call
    )
    tavily_calls = sum(1 for e in result.usage_events if e.provider == "tavily")
    assert tavily_calls == 5
    assert worker_model_calls == 1, "worker_model_calls must reflect ONLY the real Anthropic call, never the 5 Tavily searches"


# --- One Anthropic worker call = 1, one QA call = 1 -------------------------


async def test_one_anthropic_worker_call_counts_as_one_worker_model_call():
    class _Worker:
        async def run(self, *, title, description, input_data, context):
            record_usage(_anthropic_event())
            return ResearchOutput(question=title, findings=[], insufficient_evidence=False, summary="s")

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    worker_model_calls = sum(
        e.api_calls for e in result.usage_events if e.role == "worker" and e.is_model_call
    )
    assert worker_model_calls == 1


async def test_one_qa_call_counts_as_one_qa_model_call():
    class _Worker:
        async def run(self, *, title, description, input_data, context):
            record_usage(_anthropic_event())
            return ResearchOutput(question=title, findings=[], insufficient_evidence=False, summary="s")

    class _QA:
        async def run(self, **kwargs):
            record_usage(_anthropic_event())
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_QA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    qa_model_calls = sum(e.api_calls for e in result.usage_events if e.role == "qa" and e.is_model_call)
    assert qa_model_calls == 1


# --- A structured-output repair call increments worker_model_calls ---------


async def test_repair_anthropic_call_increments_worker_model_call_count():
    """A worker whose provider needed a repair attempt records TWO real
    Anthropic events for the same logical attempt — both must count."""

    class _Worker:
        async def run(self, *, title, description, input_data, context):
            record_usage(_anthropic_event())  # original call: malformed response
            record_usage(_anthropic_event())  # repair call
            return ResearchOutput(question=title, findings=[], insufficient_evidence=False, summary="s")

    result = await run_worker_with_qa(
        worker_agent=_Worker(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    worker_model_calls = sum(
        e.api_calls for e in result.usage_events if e.role == "worker" and e.is_model_call
    )
    assert worker_model_calls == 2


# --- End-to-end through AgentExecutor: output_data carries the corrected ---
#     counts


async def test_task_output_worker_model_calls_excludes_tavily_end_to_end(session_factory):
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
            record_usage(_tavily_event("search"))
            record_usage(_tavily_event("search"))
            record_usage(_tavily_event("extract"))
            record_usage(_anthropic_event())
            return ResearchOutput(question="q", findings=[], insufficient_evidence=False, summary="s")

    class _StubQAAgent:
        def __init__(self, descriptor, provider=None):
            pass

        async def run(self, **kwargs):
            record_usage(_anthropic_event())
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    registry = build_default_registry()
    registry.register(registry.get_descriptor("research"), _StubResearchAgent)
    registry.register(registry.get_descriptor("qa"), _StubQAAgent)

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("usageacct@example.com")
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
        from app.services.usage_service import UsageService

        task = await TS(session).get(completed[0].id)
        output = TS(session).parse_output(task)
        assert output.get("worker_model_calls") == 1  # NOT 3 (the two Tavily calls excluded)
        assert output.get("qa_model_calls") == 1

        # Mission-level accounting is UNCHANGED: all 5 real API calls
        # (3 tavily + 1 worker anthropic + 1 qa anthropic) are still there.
        totals = await UsageService(session).totals_for_project(project_id)
        assert totals.api_calls == 5
