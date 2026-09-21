"""Action domain contract and its state machine (v0.1.3.1, spec sections
5/6/17). Illegal transitions must fail closed with a typed error."""
from __future__ import annotations

import pytest

from app.decision_intelligence.action_state_machine import (
    ActionTransitionError,
    assert_transition,
    can_transition,
)
from app.decision_intelligence.schemas import Action, ActionStatus


def _action(**overrides) -> Action:
    fields = dict(action_plan_id="plan-1", action_type="send_email", title="Do it")
    fields.update(overrides)
    return Action(**fields)


def test_action_defaults_to_planned():
    action = _action()
    assert action.status == ActionStatus.PLANNED
    assert action.retry_count == 0
    assert action.approval_required is False


# --- Legal path: approval required --------------------------------------


def test_full_lifecycle_with_approval_required():
    path = [
        ActionStatus.PLANNED,
        ActionStatus.VALIDATED,
        ActionStatus.PERMISSION_CHECKED,
        ActionStatus.WAITING_FOR_APPROVAL,
        ActionStatus.APPROVED,
        ActionStatus.EXECUTING,
        ActionStatus.EXECUTION_SUCCEEDED,
        ActionStatus.VERIFYING,
        ActionStatus.VERIFIED,
        ActionStatus.COMPLETED,
    ]
    for current, target in zip(path, path[1:]):
        assert_transition(current, target)  # must not raise


# --- Legal path: no approval required ------------------------------------


def test_full_lifecycle_without_approval_required():
    path = [
        ActionStatus.PLANNED,
        ActionStatus.VALIDATED,
        ActionStatus.PERMISSION_CHECKED,
        ActionStatus.EXECUTING,
        ActionStatus.EXECUTION_SUCCEEDED,
        ActionStatus.VERIFYING,
        ActionStatus.VERIFIED,
        ActionStatus.COMPLETED,
    ]
    for current, target in zip(path, path[1:]):
        assert_transition(current, target)


def test_verification_failure_path_reaches_failed():
    assert_transition(ActionStatus.VERIFYING, ActionStatus.VERIFICATION_FAILED)
    assert_transition(ActionStatus.VERIFICATION_FAILED, ActionStatus.FAILED)


# --- Illegal transitions (security invariant 2/3/4/5) --------------------


def test_planned_cannot_jump_to_completed():
    assert can_transition(ActionStatus.PLANNED, ActionStatus.COMPLETED) is False
    with pytest.raises(ActionTransitionError):
        assert_transition(ActionStatus.PLANNED, ActionStatus.COMPLETED)


def test_planned_cannot_jump_to_executing():
    assert can_transition(ActionStatus.PLANNED, ActionStatus.EXECUTING) is False
    with pytest.raises(ActionTransitionError):
        assert_transition(ActionStatus.PLANNED, ActionStatus.EXECUTING)


def test_waiting_for_approval_cannot_reach_executing_without_approved():
    assert can_transition(ActionStatus.WAITING_FOR_APPROVAL, ActionStatus.EXECUTING) is False
    with pytest.raises(ActionTransitionError):
        assert_transition(ActionStatus.WAITING_FOR_APPROVAL, ActionStatus.EXECUTING)


def test_execution_succeeded_cannot_reach_completed_without_verification():
    assert can_transition(ActionStatus.EXECUTION_SUCCEEDED, ActionStatus.COMPLETED) is False
    with pytest.raises(ActionTransitionError):
        assert_transition(ActionStatus.EXECUTION_SUCCEEDED, ActionStatus.COMPLETED)


def test_verification_failed_cannot_reach_completed():
    assert can_transition(ActionStatus.VERIFICATION_FAILED, ActionStatus.COMPLETED) is False
    with pytest.raises(ActionTransitionError):
        assert_transition(ActionStatus.VERIFICATION_FAILED, ActionStatus.COMPLETED)


def test_verified_cannot_skip_back_to_executing():
    assert can_transition(ActionStatus.VERIFIED, ActionStatus.EXECUTING) is False


@pytest.mark.parametrize(
    "terminal",
    [ActionStatus.COMPLETED, ActionStatus.FAILED, ActionStatus.REJECTED, ActionStatus.CANCELLED],
)
def test_terminal_states_accept_no_further_transitions(terminal):
    for target in ActionStatus:
        if target == terminal:
            continue
        assert can_transition(terminal, target) is False


def test_transition_error_carries_current_and_target():
    with pytest.raises(ActionTransitionError) as exc_info:
        assert_transition(ActionStatus.PLANNED, ActionStatus.COMPLETED)
    assert exc_info.value.current == ActionStatus.PLANNED
    assert exc_info.value.target == ActionStatus.COMPLETED


def test_blocked_action_can_only_be_cancelled():
    assert can_transition(ActionStatus.BLOCKED, ActionStatus.CANCELLED) is True
    assert can_transition(ActionStatus.BLOCKED, ActionStatus.EXECUTING) is False
