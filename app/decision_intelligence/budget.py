"""Deterministic Budget Enforcement (v0.1.3.7, spec sections 23-33). Budget
is broader than money — this module enforces ACTION_ATTEMPTS/RETRIES/
REPLANS/MODEL_CALLS/ESTIMATED_COST at ACTION or PLAN scope, all through one
small, atomic, restart-safe primitive: `reserve_and_consume()`.

DESIGN, stated up front because it deliberately diverges from the letter of
spec section 25's Decimal suggestion (documented, not silently ignored):
every value here is a plain `float`, matching `Action.estimated_cost`/
`ActionPlan.estimated_cost` (both float since v0.1.3.1 — frozen contracts
this checkpoint does not change) and `UsageRecord.estimated_cost_usd`
elsewhere in this codebase. No REAL money ever moves anywhere in this
checkpoint (nor in any checkpoint so far) — introducing `Decimal` here
would create a THIRD numeric representation for "cost" alongside the two
existing float ones without closing any real precision gap, which is the
premature-abstraction problem this codebase's own conventions warn
against. If a future checkpoint ever wires a real payment/billing
integration, that is the appropriate point to migrate every cost-bearing
field (including these) to Decimal together, not this one in isolation.

ATOMICITY (spec sections 27/53): modeled on ExecutionAttemptRepository's
existing claim-by-UNIQUE-INSERT pattern. Every consumption attempt first
tries to INSERT a BudgetEventRecord keyed by a caller-supplied
`idempotency_key`; the UNIQUE constraint on that column is what makes two
concurrent (or a crash-and-retried) callers resolve to exactly one applied
outcome. Only after that claim succeeds does this module attempt the
account's own version-guarded conditional UPDATE — if that fails (budget
would be exceeded, or a version race), the ledger already recorded
`applied=False`/the race is retried, so a restart or duplicate caller
replays the SAME recorded outcome rather than re-evaluating and possibly
double-consuming (spec sections 43/54).

Jarvis may observe/consume/report a budget. It may never increase its own
limit (spec section 30) — `ensure_account()` is the only way an account's
`limit_value` is ever set, and only at first creation; nothing in this
module, `retry_controller.py`, or `replan.py` ever calls anything else.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from app.database.models import BudgetAccountStatus, BudgetScope, BudgetType
from app.database.repositories import BudgetAccountRepository, BudgetEventRepository

_MAX_CAS_ATTEMPTS = 5


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class BudgetConsumeResult(BaseModel):
    """Structured, non-raising result — same "never a bare bool" convention
    as PermissionDecision/RecoveryEvaluation."""

    granted: bool
    scope_type: BudgetScope
    scope_id: str
    budget_type: BudgetType
    limit: float
    consumed: float
    remaining: float
    status: BudgetAccountStatus
    replayed: bool = False
    reason: str = ""


class BudgetConcurrencyError(Exception):
    """Raised only when the bounded CAS retry loop genuinely cannot
    converge (spec section 27) — a real anomaly, not routine contention;
    every routine race resolves within the retry loop, same shape as
    durable_action_executor.py's StaleActionVersionError."""

    def __init__(self, account_id: str):
        super().__init__(f"BudgetAccountRecord '{account_id}' could not be updated after {_MAX_CAS_ATTEMPTS} attempts")
        self.account_id = account_id


async def ensure_account(
    account_repo: BudgetAccountRepository,
    *,
    scope_type: BudgetScope,
    scope_id: str,
    budget_type: BudgetType,
    limit_value: float,
):
    """Get-or-create. NEVER changes `limit_value` on an already-existing
    account (spec section 30) — a caller asking for a different limit on an
    existing account silently gets back the ORIGINAL account unchanged."""
    return await account_repo.ensure(
        scope_type=scope_type, scope_id=scope_id, budget_type=budget_type, limit_value=limit_value
    )


async def get_remaining(
    account_repo: BudgetAccountRepository, *, scope_type: BudgetScope, scope_id: str, budget_type: BudgetType
) -> float | None:
    """None means "no budget account configured for this scope" — treated
    as UNLIMITED by every caller in this codebase (spec section 24 does not
    require every plan to configure every budget type; an unconfigured
    budget never blocks orchestration that v0.1.3.6 already proved safe
    without one)."""
    account = await account_repo.get_by_scope(scope_type=scope_type, scope_id=scope_id, budget_type=budget_type)
    if account is None:
        return None
    return account.limit_value - account.consumed_value


async def reserve_and_consume(
    account_repo: BudgetAccountRepository,
    event_repo: BudgetEventRepository,
    *,
    scope_type: BudgetScope,
    scope_id: str,
    budget_type: BudgetType,
    amount: float,
    idempotency_key: str,
    reason: str = "",
    default_limit: float | None = None,
    now: Callable[[], datetime] | None = None,
) -> BudgetConsumeResult:
    """The single atomic consumption primitive every recovery module routes
    through. If no account exists for this scope AND `default_limit` is
    None, the budget is treated as unconfigured/unlimited — `granted=True`
    is returned WITHOUT creating any durable row (spec section 24: budgets
    are opt-in; an unconfigured plan behaves exactly as v0.1.3.6 already
    tested). Passing `default_limit` establishes the account (once) with
    that ceiling."""
    clock = now or _default_now

    existing_event = await event_repo.get_by_idempotency_key(idempotency_key)
    if existing_event is not None:
        account = await account_repo.get(existing_event.budget_account_id)
        return BudgetConsumeResult(
            granted=existing_event.applied,
            scope_type=scope_type, scope_id=scope_id, budget_type=budget_type,
            limit=account.limit_value, consumed=account.consumed_value,
            remaining=account.limit_value - account.consumed_value,
            status=account.status, replayed=True,
            reason="replayed a previously-recorded outcome for this idempotency_key",
        )

    account = await account_repo.get_by_scope(scope_type=scope_type, scope_id=scope_id, budget_type=budget_type)
    if account is None:
        if default_limit is None:
            return BudgetConsumeResult(
                granted=True, scope_type=scope_type, scope_id=scope_id, budget_type=budget_type,
                limit=float("inf"), consumed=0.0, remaining=float("inf"), status=BudgetAccountStatus.ACTIVE,
                reason="no budget account configured for this scope — treated as unlimited",
            )
        account = await ensure_account(
            account_repo, scope_type=scope_type, scope_id=scope_id, budget_type=budget_type, limit_value=default_limit
        )

    for _ in range(_MAX_CAS_ATTEMPTS):
        fresh = await account_repo.get(account.id)
        would_exceed = (fresh.consumed_value + amount) > fresh.limit_value
        if would_exceed:
            await event_repo.claim(
                budget_account_id=fresh.id, idempotency_key=idempotency_key, delta=amount, applied=False, reason=reason,
                created_at=clock(),
            )
            return BudgetConsumeResult(
                granted=False, scope_type=scope_type, scope_id=scope_id, budget_type=budget_type,
                limit=fresh.limit_value, consumed=fresh.consumed_value, remaining=fresh.limit_value - fresh.consumed_value,
                status=BudgetAccountStatus.EXHAUSTED, reason=f"consuming {amount} would exceed limit {fresh.limit_value}",
            )

        new_consumed = fresh.consumed_value + amount
        new_status = BudgetAccountStatus.EXHAUSTED if new_consumed >= fresh.limit_value else BudgetAccountStatus.ACTIVE
        ok = await account_repo.update_if_version_matches(
            fresh.id, expected_version=fresh.version, consumed_value=new_consumed, status=new_status
        )
        if not ok:
            continue  # lost the CAS race — re-read and retry, same shape as _upsert_action_record()

        event = await event_repo.claim(
            budget_account_id=fresh.id, idempotency_key=idempotency_key, delta=amount, applied=True, reason=reason,
            created_at=clock(),
        )
        if event is None:
            # Another caller already recorded THIS exact idempotency_key
            # between our first check and now (a genuine race on a
            # logically-duplicate call) — the account was already
            # incremented once for real work; back out our own increment
            # rather than double-charge it, then replay the winner's result.
            await account_repo.update_if_version_matches(
                fresh.id, expected_version=fresh.version + 1, consumed_value=fresh.consumed_value, status=fresh.status
            )
            winner = await event_repo.get_by_idempotency_key(idempotency_key)
            refreshed = await account_repo.get(fresh.id)
            return BudgetConsumeResult(
                granted=winner.applied, scope_type=scope_type, scope_id=scope_id, budget_type=budget_type,
                limit=refreshed.limit_value, consumed=refreshed.consumed_value,
                remaining=refreshed.limit_value - refreshed.consumed_value, status=refreshed.status,
                replayed=True, reason="replayed a concurrently-recorded outcome for this idempotency_key",
            )

        return BudgetConsumeResult(
            granted=True, scope_type=scope_type, scope_id=scope_id, budget_type=budget_type,
            limit=fresh.limit_value, consumed=new_consumed, remaining=fresh.limit_value - new_consumed,
            status=new_status, reason=reason,
        )

    raise BudgetConcurrencyError(account.id)
