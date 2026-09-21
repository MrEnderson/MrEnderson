"""Mission budget guardrails (v0.1.1). A mission is one project/objective run.

Checked once per dispatch iteration in app/orchestration/executor.py::run_objective,
before a new batch of tasks is started — never mid-batch, since in-flight API
calls cannot be safely cancelled. Reaching a limit stops the run cleanly:
already-completed work is preserved, the reason is recorded on the audit
trail, and a partial executive report is still produced.
"""
from __future__ import annotations

from app.config.settings import Settings
from app.database.repositories import UsageTotals


def check_budget(
    *, totals: UsageTotals, daily_cost_usd: float | None, settings: Settings
) -> str | None:
    """Returns a human-readable reason if a configured limit has been reached, else None."""
    if settings.max_api_calls_per_mission and totals.api_calls >= settings.max_api_calls_per_mission:
        return f"MAX_API_CALLS_PER_MISSION ({settings.max_api_calls_per_mission}) reached"

    if settings.max_tokens_per_mission and totals.total_tokens >= settings.max_tokens_per_mission:
        return f"MAX_TOKENS_PER_MISSION ({settings.max_tokens_per_mission}) reached"

    if (
        settings.max_estimated_cost_per_mission_usd is not None
        and totals.estimated_cost_usd is not None
        and totals.estimated_cost_usd >= settings.max_estimated_cost_per_mission_usd
    ):
        return (
            f"MAX_ESTIMATED_COST_PER_MISSION_USD (${settings.max_estimated_cost_per_mission_usd}) reached"
        )

    if (
        settings.daily_cost_limit_usd is not None
        and daily_cost_usd is not None
        and daily_cost_usd >= settings.daily_cost_limit_usd
    ):
        return f"DAILY_COST_LIMIT_USD (${settings.daily_cost_limit_usd}) reached for this workspace"

    return None


def reserved_totals(
    committed: UsageTotals, *, in_flight_calls: int, in_flight_tokens: int, settings: Settings
) -> UsageTotals:
    """Projects what mission usage would look like if the next attempt (a
    worker call plus its QA call) is allowed to proceed: already-committed
    (persisted) usage, plus this task's own not-yet-persisted usage so far
    this run, plus a conservative FLAT reservation for the upcoming attempt.

    Deliberately not a token-count prediction from prompt size — the
    provider API doesn't make that reliable ahead of a call (see
    app/agents/providers.py's own comments on this). `budget_reserved_output_tokens`
    covers the provider's configured max output allowance,
    `budget_reservation_safety_margin_tokens` is an explicit buffer on top.
    Never persisted as real usage — see app/orchestration/evaluator.py,
    which only ever calls check_budget() against this to DECIDE whether to
    proceed; actual recorded usage after a real call replaces/resolves it.
    """
    return UsageTotals(
        api_calls=committed.api_calls + in_flight_calls + 2,  # worker call + its QA call
        total_tokens=(
            committed.total_tokens
            + in_flight_tokens
            + settings.budget_reserved_output_tokens
            + settings.budget_reservation_safety_margin_tokens
        ),
        estimated_cost_usd=committed.estimated_cost_usd,
    )
