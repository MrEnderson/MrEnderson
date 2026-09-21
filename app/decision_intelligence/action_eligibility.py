"""Deterministic Action eligibility evaluation within an ActionPlan
(v0.1.3.6, spec sections 10/11). Pure functions only — no I/O, no LLM, no
database access. The orchestrator supplies durable truth; this module only
reasons about it.
"""
from __future__ import annotations

import enum

from app.decision_intelligence.schemas import Action, ActionStatus


class ActionEligibility(str, enum.Enum):
    READY = "READY"
    ALREADY_COMPLETED = "ALREADY_COMPLETED"
    WAITING_FOR_DEPENDENCIES = "WAITING_FOR_DEPENDENCIES"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    BLOCKED_BY_FAILED_DEPENDENCY = "BLOCKED_BY_FAILED_DEPENDENCY"
    BLOCKED_BY_REJECTED_DEPENDENCY = "BLOCKED_BY_REJECTED_DEPENDENCY"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    CURRENTLY_EXECUTING = "CURRENTLY_EXECUTING"
    TERMINAL_FAILED = "TERMINAL_FAILED"
    CANCELLED = "CANCELLED"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"


# spec section 11: a dependency is satisfied ONLY when its prerequisite is
# durably COMPLETED — explicitly NOT EXECUTION_SUCCEEDED/VERIFYING/VERIFIED
# (verification is part of successful completion, not a separate
# lesser-sufficient state) and NOT any failure/waiting/ambiguous state.
_DEPENDENCY_SATISFYING_STATUS = ActionStatus.COMPLETED

_IN_PROGRESS_STATUSES = frozenset(
    {
        ActionStatus.EXECUTING,
        ActionStatus.EXECUTION_SUCCEEDED,
        ActionStatus.VERIFYING,
        ActionStatus.VERIFIED,
    }
)


def evaluate_action_eligibility(action: Action, actions_by_id: dict[str, Action]) -> ActionEligibility:
    """`actions_by_id` must contain every Action in the plan (including
    `action` itself), keyed by id, so dependency status can be looked up.
    An in-progress Action's uncertainty (spec section 27 item 4) is
    resolved by the caller via v0.1.3.5's `reconcile_action()` BEFORE
    calling this function again with the refreshed status — this module
    does not duplicate that reconciliation logic; see
    action_plan_orchestrator.py.
    """
    if action.status == ActionStatus.COMPLETED:
        return ActionEligibility.ALREADY_COMPLETED
    if action.status == ActionStatus.FAILED:
        return ActionEligibility.TERMINAL_FAILED
    if action.status == ActionStatus.REJECTED:
        return ActionEligibility.TERMINAL_FAILED
    if action.status == ActionStatus.CANCELLED:
        return ActionEligibility.CANCELLED
    if action.status == ActionStatus.BLOCKED:
        return ActionEligibility.SECURITY_BLOCKED
    if action.status == ActionStatus.WAITING_FOR_APPROVAL:
        return ActionEligibility.WAITING_FOR_APPROVAL
    if action.status in _IN_PROGRESS_STATUSES:
        return ActionEligibility.CURRENTLY_EXECUTING

    # PLANNED / VALIDATED / PERMISSION_CHECKED / APPROVED: gate on dependencies.
    for dep_id in action.dependencies:
        dep = actions_by_id.get(dep_id)
        if dep is None:
            # Should never happen once plan_validation.py's structural
            # checks have passed — fail closed rather than silently
            # treating an unresolvable dependency as satisfied.
            return ActionEligibility.RECONCILIATION_REQUIRED
        if dep.status == ActionStatus.REJECTED:
            return ActionEligibility.BLOCKED_BY_REJECTED_DEPENDENCY
        if dep.status in (ActionStatus.FAILED, ActionStatus.CANCELLED, ActionStatus.BLOCKED):
            return ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY
        if dep.status != _DEPENDENCY_SATISFYING_STATUS:
            return ActionEligibility.WAITING_FOR_DEPENDENCIES

    return ActionEligibility.READY
