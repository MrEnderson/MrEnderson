"""Explicit ActionPlan state machine (v0.1.3.6, spec section 12). Same
shape as action_state_machine.py: an explicit transition table plus a
typed error, no implicit/derived transitions, no arbitrary jumps.

    DRAFT -> VALIDATING -> READY -> EXECUTING -> (WAITING_FOR_APPROVAL |
    PARTIALLY_COMPLETED | COMPLETED | FAILED | CANCELLED)

`WAITING_FOR_APPROVAL`/`PARTIALLY_COMPLETED` can both return to
`EXECUTING` (resuming orchestration) or move toward a terminal state.
`COMPLETED`/`FAILED`/`CANCELLED` are dead ends — no recovery path is
defined in this checkpoint (matches v0.1.3.1's `ActionStatus`/
`DecisionStatus` precedent: reopening a terminal state is explicitly not
implemented).
"""
from __future__ import annotations

from app.decision_intelligence.schemas import ActionPlanStatus

_VALID_TRANSITIONS: dict[ActionPlanStatus, set[ActionPlanStatus]] = {
    ActionPlanStatus.DRAFT: {
        ActionPlanStatus.VALIDATING,
        ActionPlanStatus.FAILED,
        ActionPlanStatus.CANCELLED,
    },
    ActionPlanStatus.VALIDATING: {
        ActionPlanStatus.READY,
        ActionPlanStatus.FAILED,
        ActionPlanStatus.CANCELLED,
    },
    ActionPlanStatus.READY: {
        ActionPlanStatus.EXECUTING,
        ActionPlanStatus.CANCELLED,
    },
    ActionPlanStatus.EXECUTING: {
        ActionPlanStatus.WAITING_FOR_APPROVAL,
        ActionPlanStatus.PARTIALLY_COMPLETED,
        ActionPlanStatus.COMPLETED,
        ActionPlanStatus.FAILED,
        ActionPlanStatus.CANCELLED,
    },
    ActionPlanStatus.WAITING_FOR_APPROVAL: {
        ActionPlanStatus.EXECUTING,
        ActionPlanStatus.PARTIALLY_COMPLETED,
        ActionPlanStatus.FAILED,
        ActionPlanStatus.CANCELLED,
    },
    ActionPlanStatus.PARTIALLY_COMPLETED: {
        ActionPlanStatus.EXECUTING,
        ActionPlanStatus.WAITING_FOR_APPROVAL,
        ActionPlanStatus.COMPLETED,
        ActionPlanStatus.FAILED,
        ActionPlanStatus.CANCELLED,
    },
    ActionPlanStatus.COMPLETED: set(),
    ActionPlanStatus.FAILED: set(),
    ActionPlanStatus.CANCELLED: set(),
}


class ActionPlanTransitionError(Exception):
    def __init__(self, current: ActionPlanStatus, target: ActionPlanStatus):
        super().__init__(f"Invalid action plan transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: ActionPlanStatus, target: ActionPlanStatus) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


def assert_transition(current: ActionPlanStatus, target: ActionPlanStatus) -> None:
    if not can_transition(current, target):
        raise ActionPlanTransitionError(current, target)
