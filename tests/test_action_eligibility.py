"""Deterministic Action eligibility evaluation (v0.1.3.6, spec sections
10/11/47/48). Pure functions — no I/O, no database, no LLM."""
from __future__ import annotations

from app.decision_intelligence.action_eligibility import ActionEligibility, evaluate_action_eligibility
from app.decision_intelligence.schemas import Action, ActionStatus


def _action(**overrides) -> Action:
    fields = dict(action_plan_id="plan-1", action_type="internal", title="A", status=ActionStatus.VALIDATED)
    fields.update(overrides)
    return Action(**fields)


def _by_id(*actions: Action) -> dict[str, Action]:
    return {a.id: a for a in actions}


# --- Basic self-status classifications -----------------------------------------


def test_completed_action_is_already_completed():
    a = _action(status=ActionStatus.COMPLETED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.ALREADY_COMPLETED


def test_failed_action_is_terminal_failed():
    a = _action(status=ActionStatus.FAILED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.TERMINAL_FAILED


def test_rejected_action_is_terminal_failed():
    a = _action(status=ActionStatus.REJECTED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.TERMINAL_FAILED


def test_cancelled_action_is_cancelled():
    a = _action(status=ActionStatus.CANCELLED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.CANCELLED


def test_blocked_action_is_security_blocked():
    a = _action(status=ActionStatus.BLOCKED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.SECURITY_BLOCKED


def test_waiting_for_approval_action_is_waiting_for_approval():
    a = _action(status=ActionStatus.WAITING_FOR_APPROVAL)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.WAITING_FOR_APPROVAL


import pytest


@pytest.mark.parametrize(
    "status",
    [ActionStatus.EXECUTING, ActionStatus.EXECUTION_SUCCEEDED, ActionStatus.VERIFYING, ActionStatus.VERIFIED],
)
def test_in_progress_statuses_are_currently_executing(status):
    a = _action(status=status)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.CURRENTLY_EXECUTING


# --- No dependencies -------------------------------------------------------------


def test_no_dependencies_and_validated_is_ready():
    a = _action(status=ActionStatus.VALIDATED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.READY


def test_no_dependencies_and_permission_checked_is_ready():
    a = _action(status=ActionStatus.PERMISSION_CHECKED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.READY


def test_no_dependencies_and_approved_is_ready():
    a = _action(status=ActionStatus.APPROVED)
    assert evaluate_action_eligibility(a, _by_id(a)) == ActionEligibility.READY


# --- Dependency satisfaction rule (spec section 11: ONLY COMPLETED) -----------


@pytest.mark.parametrize(
    "dep_status",
    [
        ActionStatus.EXECUTION_SUCCEEDED,
        ActionStatus.VERIFYING,
        ActionStatus.VERIFIED,
        ActionStatus.WAITING_FOR_APPROVAL,
        ActionStatus.PLANNED,
        ActionStatus.VALIDATED,
        ActionStatus.PERMISSION_CHECKED,
        ActionStatus.APPROVED,
    ],
)
def test_dependency_not_yet_completed_is_waiting_for_dependencies(dep_status):
    dep = _action(status=dep_status)
    child = _action(dependencies=[dep.id])
    assert evaluate_action_eligibility(child, _by_id(dep, child)) == ActionEligibility.WAITING_FOR_DEPENDENCIES


def test_dependency_completed_makes_child_ready():
    dep = _action(status=ActionStatus.COMPLETED)
    child = _action(dependencies=[dep.id])
    assert evaluate_action_eligibility(child, _by_id(dep, child)) == ActionEligibility.READY


def test_dependency_failed_blocks_child():
    dep = _action(status=ActionStatus.FAILED)
    child = _action(dependencies=[dep.id])
    assert evaluate_action_eligibility(child, _by_id(dep, child)) == ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY


def test_dependency_cancelled_blocks_child():
    dep = _action(status=ActionStatus.CANCELLED)
    child = _action(dependencies=[dep.id])
    assert evaluate_action_eligibility(child, _by_id(dep, child)) == ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY


def test_dependency_blocked_blocks_child():
    dep = _action(status=ActionStatus.BLOCKED)
    child = _action(dependencies=[dep.id])
    assert evaluate_action_eligibility(child, _by_id(dep, child)) == ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY


def test_dependency_rejected_blocks_child_distinctly():
    dep = _action(status=ActionStatus.REJECTED)
    child = _action(dependencies=[dep.id])
    assert evaluate_action_eligibility(child, _by_id(dep, child)) == ActionEligibility.BLOCKED_BY_REJECTED_DEPENDENCY


def test_unknown_dependency_id_fails_closed_to_reconciliation_required():
    child = _action(dependencies=["nonexistent-action-id"])
    assert evaluate_action_eligibility(child, _by_id(child)) == ActionEligibility.RECONCILIATION_REQUIRED


# --- Fan-in (spec section 47) ----------------------------------------------------


def test_fan_in_waits_for_all_dependencies():
    a = _action(title="A", status=ActionStatus.COMPLETED)
    b = _action(title="B", status=ActionStatus.VALIDATED)
    d = _action(title="D", dependencies=[a.id, b.id])
    # A completed, B not yet -> D still waiting.
    assert evaluate_action_eligibility(d, _by_id(a, b, d)) == ActionEligibility.WAITING_FOR_DEPENDENCIES


def test_fan_in_becomes_ready_only_once_all_complete():
    a = _action(title="A", status=ActionStatus.COMPLETED)
    b = _action(title="B", status=ActionStatus.COMPLETED)
    d = _action(title="D", dependencies=[a.id, b.id])
    assert evaluate_action_eligibility(d, _by_id(a, b, d)) == ActionEligibility.READY


# --- Fan-out (spec section 48) ---------------------------------------------------


def test_fan_out_all_children_independently_ready_after_parent_completes():
    a = _action(title="A", status=ActionStatus.COMPLETED)
    b = _action(title="B", dependencies=[a.id])
    c = _action(title="C", dependencies=[a.id])
    d = _action(title="D", dependencies=[a.id])
    by_id = _by_id(a, b, c, d)
    assert evaluate_action_eligibility(b, by_id) == ActionEligibility.READY
    assert evaluate_action_eligibility(c, by_id) == ActionEligibility.READY
    assert evaluate_action_eligibility(d, by_id) == ActionEligibility.READY


def test_fan_out_children_not_ready_before_parent_completes():
    a = _action(title="A", status=ActionStatus.VALIDATED)
    b = _action(title="B", dependencies=[a.id])
    c = _action(title="C", dependencies=[a.id])
    by_id = _by_id(a, b, c)
    assert evaluate_action_eligibility(b, by_id) == ActionEligibility.WAITING_FOR_DEPENDENCIES
    assert evaluate_action_eligibility(c, by_id) == ActionEligibility.WAITING_FOR_DEPENDENCIES


# --- Chained dependency failure propagation (spec section 21) ---------------


def test_transitive_block_through_chain():
    a = _action(title="A", status=ActionStatus.FAILED)
    b = _action(title="B", dependencies=[a.id])
    by_id_ab = _by_id(a, b)
    assert evaluate_action_eligibility(b, by_id_ab) == ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY
    # B itself never executed — it's not FAILED, it's blocked; C depending
    # on B (still VALIDATED, not FAILED) is WAITING_FOR_DEPENDENCIES, not
    # yet transitively blocked, since eligibility is computed fresh from
    # durable truth each time (the orchestrator would need another pass
    # once B is finalized) — this test documents that distinction.
    c = _action(title="C", dependencies=[b.id])
    by_id_abc = _by_id(a, b, c)
    assert evaluate_action_eligibility(c, by_id_abc) == ActionEligibility.WAITING_FOR_DEPENDENCIES
