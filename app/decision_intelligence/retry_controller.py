"""Bounded, side-effect-aware Retry Authorization (v0.1.3.7, spec sections
8-13). This module owns exactly one durable operation: resetting a
FAILED-or-crash-interrupted Action back to `ActionStatus.VALIDATED` with
`retry_count` durably bumped by exactly one, so the UNMODIFIED existing
pipeline (VALIDATED -> PERMISSION_CHECKED -> execute, driven entirely by
action_plan_orchestrator.py's existing `_advance_one_action()`) re-runs the
SAME Action, SAME action_hash, SAME tool/inputs — never a modified payload
(spec section 13; a changed payload is a REPLAN, see replan.py, not a
retry).

WHY THIS BYPASSES `action_state_machine.py` RATHER THAN EXTENDING IT: that
table is a FORWARD-ONLY lifecycle (spec section 6 of v0.1.3.1) with no
notion of "authorized regression." Adding e.g. `FAILED -> VALIDATED` as an
ordinary edge would also make it a legal target for
`durable_action_executor.py::_upsert_action_record()`'s own writes — but
that function's `_HAPPY_PATH_ORDER` monotonic-progress guard would then
silently treat a genuine retry-reset (VALIDATED, rank 1) landing after an
EXECUTING/APPROVED row (rank 4-5) as a STALE write and drop it entirely,
because that guard has no way to distinguish "a late, stale write" from "a
deliberate, authorized reset." Rather than teach that frozen guard a new
concept, this module performs the reset via a direct, version-guarded
`ActionRecordRepository.update_if_version_matches()` call — bypassing
`_upsert_action_record()` (and therefore its guard) entirely, exactly
once, for exactly this one deliberate operation — and validates the
transition itself via the narrow `_RETRY_REENTRY_SOURCES` allowlist below
instead of `action_state_machine.py`. `action_state_machine.py` itself is
therefore left completely untouched by this checkpoint.

RETRY BUDGET: reuses `Action.retry_count`/`Action.max_retries` (spec
section 12: "Reuse these where appropriate") rather than a new
BudgetAccountRecord — every Action already durably carries its own bound,
and `retry_count <= max_retries` is checked BOTH by recovery_policy.py
(informationally) and again here (authoritatively, the last word before
any durable write happens).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from app.database.models import PersistedActionStatus
from app.database.repositories import ActionRecordRepository
from app.decision_intelligence.schemas import Action, ActionStatus

# The ONLY statuses a bounded, authorized retry may reset FROM:
#   FAILED     — a synchronous, in-process failure (spec sections 10/13).
#   EXECUTING  — reconciliation confirmed EXECUTION_INTERRUPTED (side effect
#                known absent) after a crash (spec sections 9/44/75); the
#                Action was never durably marked FAILED at all.
#   APPROVED   — reconciliation confirmed EXECUTION_NOT_STARTED after a
#                crash between authorization and the first execution
#                attempt (spec section 9); included for completeness even
#                though the orchestrator's automatic reconciliation call
#                site does not currently reach this branch (see
#                reconciliation.py's docstring on why it is unreachable
#                from discover_reconciliation_candidates()).
_RETRY_REENTRY_SOURCES = frozenset({ActionStatus.FAILED, ActionStatus.EXECUTING, ActionStatus.APPROVED})


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class RetryAuthorizationError(Exception):
    """Base class — never raised for a routine "retry not permitted right
    now" business outcome (that is `is_retry_exhausted()`'s job to detect
    BEFORE calling this); raised only for genuine caller misuse."""


class RetryNotEligibleError(RetryAuthorizationError):
    def __init__(self, action_id: str, status: ActionStatus):
        super().__init__(
            f"Action '{action_id}' is in status {status.value}, which is not an authorized retry re-entry point "
            f"({', '.join(s.value for s in sorted(_RETRY_REENTRY_SOURCES, key=lambda s: s.value))})"
        )
        self.action_id = action_id
        self.status = status


class RetryBudgetExhaustedError(RetryAuthorizationError):
    def __init__(self, action_id: str, retry_count: int, max_retries: int):
        super().__init__(
            f"Action '{action_id}' has retry_count={retry_count} >= max_retries={max_retries}; no further retry is authorized"
        )
        self.action_id = action_id
        self.retry_count = retry_count
        self.max_retries = max_retries


class RetryStaleVersionError(RetryAuthorizationError):
    def __init__(self, action_id: str, expected_version: int):
        super().__init__(
            f"ActionRecord '{action_id}' was not at expected version {expected_version} "
            "(a concurrent writer already advanced it) — reload and retry from scratch"
        )
        self.action_id = action_id
        self.expected_version = expected_version


def is_retry_exhausted(action: Action) -> bool:
    """Non-raising predicate (spec section 10's invariant, `retry_count <=
    max_retries`) — the FIRST thing a caller should check before ever
    attempting authorize_retry()."""
    return action.retry_count >= action.max_retries


async def authorize_retry(
    action_repo: ActionRecordRepository,
    action_row,
    *,
    now: Callable[[], datetime] | None = None,
) -> Action:
    """The one durable retry-authorization write (spec section 10: "A retry
    attempt must be durably recorded before execution"). Fails closed with
    a typed error for every precondition; never silently no-ops. Returns
    the freshly-reloaded Action, now at ActionStatus.VALIDATED with
    `retry_count` incremented by exactly one and `last_error`/`error`
    cleared (a fresh attempt gets a fresh record — the FailureRecord
    history, not this field, is where the prior error lives durably)."""
    clock = now or _default_now
    current_status = ActionStatus(action_row.status.value)
    if current_status not in _RETRY_REENTRY_SOURCES:
        raise RetryNotEligibleError(action_row.id, current_status)
    if action_row.retry_count >= action_row.max_retries:
        raise RetryBudgetExhaustedError(action_row.id, action_row.retry_count, action_row.max_retries)

    ok = await action_repo.update_if_version_matches(
        action_row.id,
        expected_version=action_row.version,
        status=PersistedActionStatus.VALIDATED,
        retry_count=action_row.retry_count + 1,
        last_error=None,
        started_at=None,
        completed_at=None,
    )
    if not ok:
        raise RetryStaleVersionError(action_row.id, action_row.version)

    from app.decision_intelligence.execution_persistence import record_to_action

    refreshed = await action_repo.get(action_row.id)
    return record_to_action(refreshed)
