"""Budget guardrails: the check_budget() function directly, and an end-to-end
run_objective that hits MAX_API_CALLS_PER_MISSION and stops cleanly with a
partial report. All offline against MockProvider/MockResearchProvider."""
from __future__ import annotations

from app.config.settings import Settings, get_settings
from app.database.repositories import UsageTotals
from app.orchestration.budget import check_budget


def _settings(**overrides) -> Settings:
    base = dict(
        max_api_calls_per_mission=40,
        max_tokens_per_mission=200_000,
        max_estimated_cost_per_mission_usd=None,
        daily_cost_limit_usd=None,
    )
    base.update(overrides)
    return Settings(**base)


def test_check_budget_none_when_under_all_limits():
    totals = UsageTotals(api_calls=1, total_tokens=100)
    assert check_budget(totals=totals, daily_cost_usd=None, settings=_settings()) is None


def test_check_budget_flags_api_call_limit():
    totals = UsageTotals(api_calls=40, total_tokens=100)
    reason = check_budget(totals=totals, daily_cost_usd=None, settings=_settings(max_api_calls_per_mission=40))
    assert reason is not None
    assert "MAX_API_CALLS_PER_MISSION" in reason


def test_check_budget_flags_token_limit():
    totals = UsageTotals(api_calls=1, total_tokens=200_000)
    reason = check_budget(totals=totals, daily_cost_usd=None, settings=_settings(max_tokens_per_mission=200_000))
    assert reason is not None
    assert "MAX_TOKENS_PER_MISSION" in reason


def test_check_budget_flags_mission_cost_limit():
    totals = UsageTotals(api_calls=1, total_tokens=100, estimated_cost_usd=10.0)
    reason = check_budget(
        totals=totals, daily_cost_usd=None, settings=_settings(max_estimated_cost_per_mission_usd=5.0)
    )
    assert reason is not None
    assert "MAX_ESTIMATED_COST_PER_MISSION_USD" in reason


def test_check_budget_ignores_cost_limit_when_cost_unknown():
    totals = UsageTotals(api_calls=1, total_tokens=100, estimated_cost_usd=None)
    reason = check_budget(
        totals=totals, daily_cost_usd=None, settings=_settings(max_estimated_cost_per_mission_usd=5.0)
    )
    assert reason is None


def test_check_budget_flags_daily_cost_limit():
    totals = UsageTotals(api_calls=1, total_tokens=100)
    reason = check_budget(
        totals=totals, daily_cost_usd=30.0, settings=_settings(daily_cost_limit_usd=25.0)
    )
    assert reason is not None
    assert "DAILY_COST_LIMIT_USD" in reason


# --- End-to-end: a mission that hits the budget stops cleanly --------------


async def test_run_objective_stops_cleanly_when_api_call_budget_exhausted(
    session_factory, registry, provider, monkeypatch
):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import run_objective
    from app.services.project_service import ProjectService

    monkeypatch.setenv("MAX_API_CALLS_PER_MISSION", "1")
    get_settings.cache_clear()

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("budget@example.com")
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
    assert report.usage is not None
    assert report.usage.budget_stopped_reason
    assert "MAX_API_CALLS_PER_MISSION" in report.usage.budget_stopped_reason
    # Planning at minimum must have gone through and been preserved.
    assert report.what_was_done or report.usage.total_api_calls >= 1
