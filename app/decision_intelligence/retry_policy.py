"""Deterministic retry/error-category classification (spec section 7).
Metadata and classification ONLY — nothing here performs a retry. A future
checkpoint's Retry/Replan Engine decides how to use these helpers.
"""
from __future__ import annotations

from app.decision_intelligence.schemas import FailureCategory

# TRANSIENT: worth retrying outright (network blip, rate limit, timeout).
# TOOL: potentially retryable, but only under a future BOUNDED policy (a
# tool call that failed once is not automatically safe to repeat forever —
# see docs/decision_intelligence.md).
# VERIFICATION: a failed verification means the action's effect couldn't be
# confirmed, not that it's unsafe to try again/replan — potentially
# retryable/replannable.
_POTENTIALLY_RETRYABLE = frozenset(
    {FailureCategory.TRANSIENT, FailureCategory.TOOL, FailureCategory.VERIFICATION}
)

# APPROVAL/PERMISSION/BUDGET: the failure reflects a deliberate boundary
# (a human said no, the agent isn't allowed to, a budget ran out) — retrying
# the same action automatically would defeat the boundary.
# SECURITY: never auto-retryable, full stop — see security invariant 6.
# VALIDATION/UNKNOWN: conservative fail-closed default — not retryable
# until something more specific is known.
_NEVER_RETRYABLE = frozenset(
    {
        FailureCategory.APPROVAL,
        FailureCategory.PERMISSION,
        FailureCategory.BUDGET,
        FailureCategory.SECURITY,
        FailureCategory.VALIDATION,
        FailureCategory.UNKNOWN,
    }
)


def is_potentially_retryable(category: FailureCategory) -> bool:
    """Fail-closed: only the explicitly whitelisted categories return True."""
    return category in _POTENTIALLY_RETRYABLE


def is_replannable(category: FailureCategory) -> bool:
    """Whether a failure of this category is a reasonable candidate for a
    future replanning step, as distinct from a same-action retry. Today
    this is VERIFICATION only (spec section 7); no replanning is
    implemented yet."""
    return category == FailureCategory.VERIFICATION
