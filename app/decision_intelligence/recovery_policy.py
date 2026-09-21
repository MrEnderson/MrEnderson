"""Deterministic Recovery Policy (v0.1.3.7, spec sections 7/8/12). NO LLM
ever decides whether a failure is safe to retry/replan — this is a pure
function over typed inputs, same shape as permission_engine.py's
evaluate_permission()/PermissionDecision: never a bare enum, always
structured reason codes.

FAILURE DOES NOT IMPLY RETRY (spec section 4) — the default posture for
every category is fail-closed; only TRANSIENT/TOOL failures with a known-
absent side effect, remaining retry budget, and no approval requirement
are ever candidates for RETRY.
"""
from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from app.decision_intelligence.schemas import FailureCategory


class RecoveryDecision(str, enum.Enum):
    RETRY = "RETRY"
    REPLAN = "REPLAN"
    WAIT_FOR_APPROVAL = "WAIT_FOR_APPROVAL"
    RECONCILE = "RECONCILE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    STOP = "STOP"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"
    NO_ACTION = "NO_ACTION"


class RecoveryEvaluation(BaseModel):
    """Structured, non-raising result of evaluate_recovery() — mirrors
    PermissionDecision/PlanReadinessResult's "never a bare bool/enum"
    convention. `retry_permitted`/`replan_permitted` are exposed
    separately from `decision` so a caller (retry_controller.py/replan.py)
    can double-check the SPECIFIC permission it's about to act on, rather
    than re-deriving it from `decision` alone."""

    decision: RecoveryDecision
    reason_codes: list[str] = Field(default_factory=list)
    retry_permitted: bool = False
    replan_permitted: bool = False
    explanation: str = ""


# spec section 12's policy table. Deliberately data, not nested if/elif —
# every category's DEFAULT decision when none of the finer-grained
# overrides below apply.
_DEFAULT_DECISION_BY_CATEGORY: dict[FailureCategory, RecoveryDecision] = {
    FailureCategory.TRANSIENT: RecoveryDecision.RECONCILE,
    FailureCategory.TOOL: RecoveryDecision.RECONCILE,
    FailureCategory.VALIDATION: RecoveryDecision.REPLAN,
    FailureCategory.PERMISSION: RecoveryDecision.STOP,
    FailureCategory.APPROVAL: RecoveryDecision.STOP,
    FailureCategory.VERIFICATION: RecoveryDecision.RECONCILE,
    FailureCategory.BUDGET: RecoveryDecision.BUDGET_EXHAUSTED,
    FailureCategory.SECURITY: RecoveryDecision.SECURITY_BLOCKED,
    FailureCategory.UNKNOWN: RecoveryDecision.RECONCILE,
}

# Categories where automatic RETRY is even conceivable, PROVIDED every
# other precondition below also holds (spec section 8's retryable/not-
# retryable split; retry_policy.py's is_potentially_retryable() covers a
# similar but coarser question for a different, older caller — this table
# is deliberately not a call into that module, since v0.1.3.7 needs the
# finer-grained TRANSIENT/TOOL split plus side-effect/budget/approval
# awareness retry_policy.py never had reason to model).
_RETRY_CANDIDATE_CATEGORIES = frozenset({FailureCategory.TRANSIENT, FailureCategory.TOOL})


def evaluate_recovery(
    *,
    category: FailureCategory,
    side_effect_occurred: bool,
    retry_count: int,
    max_retries: int,
    approval_required: bool,
    replan_permitted: bool = True,
) -> RecoveryEvaluation:
    """Pure, deterministic (spec section 6) — no I/O, no side effects. Never
    returns RETRY unless ALL of the following hold (spec sections 8/12/13):

      1. category is TRANSIENT or TOOL (the only two categories a failure
         boundary itself, not a deliberate authorization boundary, can
         explain — see the module docstring's category table);
      2. `side_effect_occurred` is False (spec section 8 — "side effect
         may have happened" is explicitly NOT automatically retryable; an
         UNKNOWN/ambiguous state must never reach this function as True/False
         at all — the caller resolves that via reconcile_action() FIRST,
         spec section 9, and only calls this once it has a definite bool);
      3. `retry_count < max_retries` (spec section 10's bounded-retry
         invariant, `retry_count <= max_retries` after the bump);
      4. `approval_required` is False — an approval-gated Action's ONE
         approval is already consumed and single-use (spec sections 12/13
         of v0.1.3.3.1); recovery can never manufacture a fresh one, so a
         transient/tool failure on such an Action needs a human, not an
         automatic retry.
    """
    reason_codes: list[str] = [f"CATEGORY_{category.value}"]

    if category == FailureCategory.SECURITY:
        reason_codes.append("SECURITY_NEVER_RETRIES")
        return RecoveryEvaluation(
            decision=RecoveryDecision.SECURITY_BLOCKED, reason_codes=reason_codes,
            explanation="SECURITY failures never retry, replan, or otherwise continue automatically.",
        )

    if category == FailureCategory.BUDGET:
        reason_codes.append("BUDGET_EXHAUSTED")
        return RecoveryEvaluation(
            decision=RecoveryDecision.BUDGET_EXHAUSTED, reason_codes=reason_codes,
            explanation="A budget boundary failure stops safely; nothing here increases a budget automatically.",
        )

    if category == FailureCategory.PERMISSION:
        reason_codes.append("PERMISSION_POLICY_MUST_BE_RESOLVED")
        return RecoveryEvaluation(
            decision=RecoveryDecision.STOP, reason_codes=reason_codes,
            explanation="A PERMISSION failure reflects a deliberate policy boundary; it is never retried or replanned around.",
        )

    if category == FailureCategory.APPROVAL:
        reason_codes.append("APPROVAL_CANNOT_BE_MANUFACTURED")
        return RecoveryEvaluation(
            decision=RecoveryDecision.STOP, reason_codes=reason_codes,
            explanation="An APPROVAL failure requires a fresh human decision; recovery never re-executes on the strength of an old one.",
        )

    if approval_required:
        reason_codes.append("APPROVAL_REQUIRED_NO_AUTOMATIC_RETRY")
        return RecoveryEvaluation(
            decision=RecoveryDecision.HUMAN_REVIEW, reason_codes=reason_codes,
            explanation="This Action's approval was single-use and already consumed; a human must authorize any further attempt.",
        )

    if category in _RETRY_CANDIDATE_CATEGORIES:
        if side_effect_occurred:
            reason_codes.append("SIDE_EFFECT_MAY_HAVE_OCCURRED")
            return RecoveryEvaluation(
                decision=RecoveryDecision.RECONCILE, reason_codes=reason_codes,
                explanation="A side effect occurred during a failed attempt; reconciliation must establish the true state before any retry.",
            )
        if retry_count >= max_retries:
            reason_codes.append("RETRY_BUDGET_EXHAUSTED")
            return RecoveryEvaluation(
                decision=RecoveryDecision.BUDGET_EXHAUSTED, reason_codes=reason_codes,
                explanation=f"retry_count ({retry_count}) has reached max_retries ({max_retries}); no further automatic attempt is made.",
            )
        reason_codes.append("SIDE_EFFECT_KNOWN_ABSENT")
        reason_codes.append("RETRY_BUDGET_AVAILABLE")
        return RecoveryEvaluation(
            decision=RecoveryDecision.RETRY, reason_codes=reason_codes, retry_permitted=True,
            explanation=f"{category.value} failure with no side effect and retry budget remaining ({retry_count}/{max_retries}) — bounded retry authorized.",
        )

    if category == FailureCategory.VALIDATION:
        if replan_permitted:
            reason_codes.append("VALIDATION_CANDIDATE_FOR_REPLAN")
            return RecoveryEvaluation(
                decision=RecoveryDecision.REPLAN, reason_codes=reason_codes, replan_permitted=True,
                explanation="A VALIDATION failure means the same Action cannot succeed unchanged; a caller-supplied replacement may be proposed.",
            )
        reason_codes.append("REPLAN_BUDGET_EXHAUSTED")
        return RecoveryEvaluation(
            decision=RecoveryDecision.STOP, reason_codes=reason_codes,
            explanation="A VALIDATION failure would normally be a replan candidate, but the plan's replan budget is exhausted.",
        )

    if category == FailureCategory.VERIFICATION:
        reason_codes.append("VERIFICATION_MUST_RECONCILE_FIRST")
        return RecoveryEvaluation(
            decision=RecoveryDecision.RECONCILE, reason_codes=reason_codes,
            explanation="A VERIFICATION failure never automatically re-executes; reconciliation establishes the true effect state first.",
        )

    reason_codes.append("UNKNOWN_NEVER_BLINDLY_RETRIES")
    return RecoveryEvaluation(
        decision=_DEFAULT_DECISION_BY_CATEGORY.get(category, RecoveryDecision.HUMAN_REVIEW),
        reason_codes=reason_codes,
        explanation="An UNKNOWN or unmodeled failure category is never retried blindly; reconciliation/human review decides next steps.",
    )
