"""Phase 5 pre-call budget enforcement: a conservative reservation (committed
+ in-flight + a flat, non-predictive reservation for the next attempt) is
checked BEFORE a retry attempt is allowed to start, not only after usage is
already committed. All offline, deterministic — no network, no live API key.
See app/orchestration/budget.py::reserved_totals and
app/orchestration/evaluator.py::run_worker_with_qa."""
from __future__ import annotations

from app.agents.usage import ModelUsage, record_usage
from app.config.settings import Settings, get_settings
from app.database.repositories import UsageTotals
from app.orchestration.budget import check_budget, reserved_totals
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import ExecutionOutput, QAVerdict


def _settings(**overrides) -> Settings:
    base = dict(
        max_api_calls_per_mission=40,
        max_tokens_per_mission=200_000,
        budget_reserved_output_tokens=4096,
        budget_reservation_safety_margin_tokens=2000,
    )
    base.update(overrides)
    return Settings(**base)


# --- reserved_totals / check_budget combination (unit) -----------------------


def test_reservation_exactly_under_budget_is_allowed():
    committed = UsageTotals(api_calls=1, total_tokens=100_000)
    settings = _settings(max_tokens_per_mission=200_000)
    projected = reserved_totals(committed, in_flight_calls=0, in_flight_tokens=0, settings=settings)
    assert check_budget(totals=projected, daily_cost_usd=None, settings=settings) is None


def test_reservation_predicted_to_exceed_budget_is_blocked():
    committed = UsageTotals(api_calls=1, total_tokens=195_000)
    settings = _settings(max_tokens_per_mission=200_000)
    projected = reserved_totals(committed, in_flight_calls=0, in_flight_tokens=0, settings=settings)
    # 195_000 + 4096 + 2000 > 200_000 — blocked BEFORE the call, even though
    # committed usage alone is still comfortably under the limit.
    reason = check_budget(totals=projected, daily_cost_usd=None, settings=settings)
    assert reason is not None
    assert "MAX_TOKENS_PER_MISSION" in reason


def test_reservation_includes_in_flight_usage_from_this_task():
    committed = UsageTotals(api_calls=1, total_tokens=100_000)
    settings = _settings(max_tokens_per_mission=105_000)
    # This task's own prior attempts already used 3000 tokens, not yet committed.
    projected = reserved_totals(committed, in_flight_calls=1, in_flight_tokens=3_000, settings=settings)
    reason = check_budget(totals=projected, daily_cost_usd=None, settings=settings)
    assert reason is not None


def test_reservation_counts_api_call_limit_before_the_call():
    committed = UsageTotals(api_calls=38, total_tokens=100)
    settings = _settings(max_api_calls_per_mission=40)
    # Reserves 2 calls (worker + qa) for the next attempt: 38 + 2 = 40 >= 40.
    projected = reserved_totals(committed, in_flight_calls=0, in_flight_tokens=0, settings=settings)
    reason = check_budget(totals=projected, daily_cost_usd=None, settings=settings)
    assert reason is not None
    assert "MAX_API_CALLS_PER_MISSION" in reason


# --- run_worker_with_qa integration: attempt blocked before it starts --------


class _CountingWorker:
    def __init__(self):
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        record_usage(ModelUsage(provider="mock", model="m", input_tokens=10, output_tokens=10, total_tokens=20))
        return ExecutionOutput(actions_performed=[f"attempt {self.calls}"])


class _AlwaysNeedsReviewQA:
    async def run(self, **kwargs):
        return QAVerdict(verdict="NEEDS_REVIEW", score=0.4, feedback="try again")


async def test_second_attempt_blocked_before_execution_when_mission_near_budget(monkeypatch):
    monkeypatch.setenv("MAX_TOKENS_PER_MISSION", "1000")
    get_settings.cache_clear()

    worker = _CountingWorker()
    # Mission already has 995 tokens committed — the first attempt alone is
    # allowed to run (it was already gated at task-start in AgentExecutor,
    # outside this function), but the SECOND attempt's reservation
    # (4096 + 2000 flat) pushes it over, so the retry never starts.
    mission_usage = UsageTotals(api_calls=1, total_tokens=995)

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysNeedsReviewQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=5, mission_usage=mission_usage,
    )

    get_settings.cache_clear()

    assert worker.calls == 1  # the second Anthropic call never happened
    assert result.attempts_used == 0
    assert result.verdict.verdict == "NEEDS_REVIEW"  # last REAL verdict preserved, not discarded
    assert result.budget_stopped_reason is not None
    assert "MAX_TOKENS_PER_MISSION" in result.budget_stopped_reason


async def test_unused_reservation_is_never_recorded_as_real_usage(monkeypatch):
    """The reservation is only ever used to DECIDE whether to proceed — it
    must never show up in usage_events as if a call happened."""
    monkeypatch.setenv("MAX_TOKENS_PER_MISSION", "1000")
    get_settings.cache_clear()

    worker = _CountingWorker()
    mission_usage = UsageTotals(api_calls=1, total_tokens=995)

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysNeedsReviewQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=5, mission_usage=mission_usage,
    )

    get_settings.cache_clear()

    # Exactly one real usage event (the one attempt that actually ran) —
    # nothing phantom for the blocked second attempt.
    assert len(result.usage_events) == 1
    assert result.usage_events[0].total_tokens == 20


# --- End-to-end: mission stops with STOPPED_BUDGET_LIMIT --------------------


async def test_run_objective_stops_cleanly_with_pre_call_gate(
    session_factory, registry, provider, monkeypatch
):
    """A budget tight enough to cut the mission off mid-run (not just before
    the very first call, unlike tests/test_budget.py's MAX_API_CALLS_PER_MISSION=1
    case) still stops cleanly with a correct final report — some work
    completed, the rest deferred/never started, never a crash or a task
    stuck in RUNNING."""
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import run_objective
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    monkeypatch.setenv("MAX_API_CALLS_PER_MISSION", "5")
    get_settings.cache_clear()

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("budget2@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
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

    get_settings.cache_clear()

    assert report.status == "STOPPED_BUDGET_LIMIT"
    assert report.usage.budget_stopped_reason
    # No task is left stuck in RUNNING — every task is in a terminal-ish,
    # resumable, or still-pending state, never orphaned mid-flight.
    async with session_factory() as session:
        tasks = await TaskService(session).list_for_project(project_id)
    assert all(t.status != TaskStatus.RUNNING for t in tasks)


async def test_no_mission_usage_means_no_budget_gating_applied():
    """Backward compatible: callers that don't pass mission_usage (e.g. most
    existing unit tests) get the exact pre-patch behavior — retries proceed
    up to max_retries with no budget interference."""
    worker = _CountingWorker()
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysNeedsReviewQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=2,
    )
    assert worker.calls == 3
    assert result.budget_stopped_reason is None
