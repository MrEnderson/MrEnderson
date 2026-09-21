"""Explicit Action state machine (spec section 6). Same shape as
app/orchestration/state_machine.py: an explicit transition table plus a
typed error, no implicit/derived transitions, no arbitrary jumps.

    PLANNED -> VALIDATED -> PERMISSION_CHECKED -> (WAITING_FOR_APPROVAL ->
    APPROVED | EXECUTING) -> EXECUTING -> EXECUTION_SUCCEEDED -> VERIFYING
    -> (VERIFIED -> COMPLETED | VERIFICATION_FAILED)

FAILED/REJECTED/CANCELLED/BLOCKED are reachable from most non-terminal
states as fail-closed escape hatches, but nothing may skip forward past
approval or verification. Retry/replan execution (re-entering PLANNED from
a terminal failure state) is explicitly NOT implemented yet — see
retry_policy.py, which only classifies whether a failure *could* be
retried, and docs/decision_intelligence.md's "Not implemented yet" list.
"""
from __future__ import annotations

from app.decision_intelligence.schemas import ActionStatus

_VALID_TRANSITIONS: dict[ActionStatus, set[ActionStatus]] = {
    ActionStatus.PLANNED: {
        ActionStatus.VALIDATED,
        ActionStatus.REJECTED,
        ActionStatus.CANCELLED,
        ActionStatus.BLOCKED,
        ActionStatus.FAILED,
    },
    ActionStatus.VALIDATED: {
        ActionStatus.PERMISSION_CHECKED,
        ActionStatus.REJECTED,
        ActionStatus.CANCELLED,
        ActionStatus.BLOCKED,
        ActionStatus.FAILED,
    },
    ActionStatus.PERMISSION_CHECKED: {
        ActionStatus.WAITING_FOR_APPROVAL,
        ActionStatus.EXECUTING,
        ActionStatus.REJECTED,
        ActionStatus.CANCELLED,
        ActionStatus.BLOCKED,
        ActionStatus.FAILED,
    },
    ActionStatus.WAITING_FOR_APPROVAL: {
        ActionStatus.APPROVED,
        ActionStatus.REJECTED,
        ActionStatus.CANCELLED,
    },
    ActionStatus.APPROVED: {
        ActionStatus.EXECUTING,
        ActionStatus.CANCELLED,
    },
    ActionStatus.EXECUTING: {
        ActionStatus.EXECUTION_SUCCEEDED,
        ActionStatus.FAILED,
        ActionStatus.CANCELLED,
    },
    ActionStatus.EXECUTION_SUCCEEDED: {
        ActionStatus.VERIFYING,
    },
    ActionStatus.VERIFYING: {
        ActionStatus.VERIFIED,
        ActionStatus.VERIFICATION_FAILED,
    },
    ActionStatus.VERIFIED: {
        ActionStatus.COMPLETED,
    },
    ActionStatus.VERIFICATION_FAILED: {
        ActionStatus.FAILED,
        ActionStatus.BLOCKED,
    },
    ActionStatus.BLOCKED: {
        ActionStatus.CANCELLED,
    },
    ActionStatus.COMPLETED: set(),
    ActionStatus.FAILED: set(),
    ActionStatus.REJECTED: set(),
    ActionStatus.CANCELLED: set(),
}


class ActionTransitionError(Exception):
    def __init__(self, current: ActionStatus, target: ActionStatus):
        super().__init__(f"Invalid action transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: ActionStatus, target: ActionStatus) -> bool:
    return target in _VALID_TRANSITIONS.get(current, set())


def assert_transition(current: ActionStatus, target: ActionStatus) -> None:
    if not can_transition(current, target):
        raise ActionTransitionError(current, target)
