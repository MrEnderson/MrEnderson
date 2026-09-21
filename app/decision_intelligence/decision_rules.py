"""Deterministic Decision lifecycle: valid transitions, readiness
invariants, and the Decision -> ActionPlan boundary. Mirrors
app/orchestration/state_machine.py's shape (explicit transition table +
typed error), extended with the invariant checks v0.1.3.1 requires: no
prompt-instruction is ever the enforcement mechanism here, only this code.
"""
from __future__ import annotations

from app.decision_intelligence.schemas import Decision, DecisionStatus

_VALID_TRANSITIONS: dict[DecisionStatus, set[DecisionStatus]] = {
    DecisionStatus.PROPOSED: {
        DecisionStatus.INSUFFICIENT_EVIDENCE,
        DecisionStatus.READY_FOR_ACTION,
        DecisionStatus.REJECTED,
        DecisionStatus.SUPERSEDED,
    },
    DecisionStatus.INSUFFICIENT_EVIDENCE: {
        DecisionStatus.PROPOSED,
        DecisionStatus.REJECTED,
        DecisionStatus.SUPERSEDED,
    },
    DecisionStatus.READY_FOR_ACTION: {
        DecisionStatus.APPROVAL_REQUIRED,
        DecisionStatus.APPROVED,
        DecisionStatus.REJECTED,
        DecisionStatus.SUPERSEDED,
    },
    DecisionStatus.APPROVAL_REQUIRED: {
        DecisionStatus.APPROVED,
        DecisionStatus.REJECTED,
        DecisionStatus.SUPERSEDED,
    },
    DecisionStatus.APPROVED: {
        DecisionStatus.SUPERSEDED,
    },
    DecisionStatus.REJECTED: set(),
    DecisionStatus.SUPERSEDED: set(),
}


class DecisionTransitionError(Exception):
    def __init__(self, current: DecisionStatus, target: DecisionStatus):
        super().__init__(f"Invalid decision transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


class DecisionInvariantViolation(Exception):
    """Raised when a transition is structurally valid but a deterministic
    readiness invariant blocks it (e.g. comparison_ready is False)."""


class DecisionPlanBoundaryError(Exception):
    """Raised when a Decision may not be used to produce a consequential,
    executable ActionPlan yet."""


def can_transition(current: DecisionStatus, target: DecisionStatus) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


def assert_transition(current: DecisionStatus, target: DecisionStatus) -> None:
    if not can_transition(current, target):
        raise DecisionTransitionError(current, target)


def apply_decision_transition(decision: Decision, target: DecisionStatus) -> Decision:
    """Returns a NEW Decision with `status` updated to `target`, never
    mutating the input. Fails closed: an invalid state-machine transition
    raises DecisionTransitionError; a structurally valid transition that
    still violates a deterministic readiness invariant raises
    DecisionInvariantViolation. Neither error depends on, or can be
    suppressed by, `decision.actionable`.
    """
    assert_transition(decision.status, target)

    # Core invariant (spec section 3): a Decision MUST NOT become
    # READY_FOR_ACTION when comparison_ready is False, no matter what
    # status/actionable an upstream LLM call already set on the object.
    if target == DecisionStatus.READY_FOR_ACTION and not decision.comparison_ready:
        raise DecisionInvariantViolation(
            "Decision cannot become READY_FOR_ACTION while comparison_ready is False"
        )

    return decision.model_copy(update={"status": target})


def compute_actionable(decision: Decision) -> bool:
    """The ONLY deterministic source of truth for whether a Decision is
    actionable. `decision.actionable` (settable by an LLM-driven
    decision-writer agent) is deliberately never read here — actionability
    is derived purely from deterministic, code-checked state, so an LLM
    setting actionable=True cannot bypass Decision readiness (spec section
    3 / security invariant 1)."""
    return decision.status == DecisionStatus.READY_FOR_ACTION and decision.comparison_ready


def enforce_actionable_flag(decision: Decision) -> Decision:
    """Returns a NEW Decision whose `actionable` field has been overwritten
    with the deterministic value from compute_actionable(), discarding
    whatever value was previously set. Use this before ever exposing/acting
    on a Decision that came from an LLM-driven writer."""
    return decision.model_copy(update={"actionable": compute_actionable(decision)})


def assert_can_produce_plan(decision: Decision) -> None:
    """The Decision -> ActionPlan boundary (spec section 14). Raises
    DecisionPlanBoundaryError, fail-closed, unless every rule below holds.
    Does not build a plan or invoke an LLM planner — that is future work;
    this only decides whether it is even permissible to try.
    """
    if decision.status == DecisionStatus.INSUFFICIENT_EVIDENCE:
        raise DecisionPlanBoundaryError(
            "Decision has INSUFFICIENT_EVIDENCE status; cannot produce an ActionPlan"
        )
    if not decision.comparison_ready:
        raise DecisionPlanBoundaryError(
            "Decision.comparison_ready is False; cannot produce a consequential, executable ActionPlan"
        )
    if decision.status in (DecisionStatus.REJECTED, DecisionStatus.SUPERSEDED):
        raise DecisionPlanBoundaryError(
            f"Decision status {decision.status.value} cannot produce a new executable plan "
            "without being explicitly reopened first (not implemented yet)"
        )


def can_produce_plan(decision: Decision) -> bool:
    """Non-raising convenience wrapper around assert_can_produce_plan."""
    try:
        assert_can_produce_plan(decision)
    except DecisionPlanBoundaryError:
        return False
    return True
