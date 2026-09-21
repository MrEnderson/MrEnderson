"""ActionPlan structural validation and deterministic readiness evaluation
(v0.1.3.1, spec sections 4/12/13/17)."""
from __future__ import annotations

import pytest

from app.decision_intelligence.plan_validation import (
    ActionPlanValidationError,
    detect_dependency_cycle,
    evaluate_plan_readiness,
    validate_dependencies,
)
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus, RiskLevel


def _well_formed_action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1",
        action_type="send_email",
        title="Send confirmation email",
        tool_name="email_tool",
        expected_result="Customer receives a confirmation email",
        success_criteria="Email delivered without bounce",
        verification_method="Check provider delivery webhook",
    )
    fields.update(overrides)
    return Action(**fields)


def _plan(actions: list[Action], **overrides) -> ActionPlan:
    fields = dict(decision_id="dec-1", title="Notify customers")
    fields.update(overrides)
    return ActionPlan(actions=actions, **fields)


# --- Readiness: empty / malformed plans ----------------------------------


def test_empty_plan_is_not_ready():
    result = evaluate_plan_readiness(_plan([]))
    assert result.ready is False
    assert any("no actions" in b for b in result.blockers)


def test_well_formed_single_action_plan_is_ready():
    result = evaluate_plan_readiness(_plan([_well_formed_action(id="a1")]))
    assert result.ready is True
    assert result.blockers == []


def test_duplicate_action_ids_block_readiness():
    plan = _plan([_well_formed_action(id="a1"), _well_formed_action(id="a1")])
    result = evaluate_plan_readiness(plan)
    assert result.ready is False
    assert any("Duplicate action ids" in b for b in result.blockers)


def test_self_dependency_blocks_readiness():
    plan = _plan([_well_formed_action(id="a1", dependencies=["a1"])])
    result = evaluate_plan_readiness(plan)
    assert result.ready is False
    assert any("depend on themselves" in b for b in result.blockers)


def test_unknown_dependency_blocks_readiness():
    plan = _plan([_well_formed_action(id="a1", dependencies=["ghost"])])
    result = evaluate_plan_readiness(plan)
    assert result.ready is False
    assert any("unknown action ids" in b for b in result.blockers)


def test_cyclic_dependency_blocks_readiness():
    a = _well_formed_action(id="a1", dependencies=["a3"], sequence=1)
    b = _well_formed_action(id="a2", dependencies=["a1"], sequence=2)
    c = _well_formed_action(id="a3", dependencies=["a2"], sequence=3)
    plan = _plan([a, b, c])
    result = evaluate_plan_readiness(plan)
    assert result.ready is False
    assert any("Cyclic dependency" in b for b in result.blockers)


def test_detect_dependency_cycle_returns_none_for_acyclic_graph():
    a = _well_formed_action(id="a1", sequence=1)
    b = _well_formed_action(id="a2", dependencies=["a1"], sequence=2)
    assert detect_dependency_cycle([a, b]) is None


def test_forward_only_dependency_violation_blocks_readiness():
    early = _well_formed_action(id="a1", sequence=1, dependencies=["a2"])
    later = _well_formed_action(id="a2", sequence=2)
    result = evaluate_plan_readiness(_plan([early, later]))
    assert result.ready is False
    assert any("later-sequenced action" in b for b in result.blockers)


def test_missing_expected_result_blocks_readiness():
    action = _well_formed_action(id="a1", expected_result="")
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is False
    assert any("expected_result" in b for b in result.blockers)


def test_missing_success_criteria_blocks_readiness():
    action = _well_formed_action(id="a1", success_criteria="")
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is False
    assert any("success_criteria" in b for b in result.blockers)


def test_missing_verification_method_blocks_readiness():
    action = _well_formed_action(id="a1", verification_method="")
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is False
    assert any("verification_method" in b for b in result.blockers)


def test_tool_required_action_without_tool_name_blocks_readiness():
    action = _well_formed_action(id="a1", tool_name=None)
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is False
    assert any("declared tool_name" in b for b in result.blockers)


def test_no_tool_action_type_does_not_require_a_tool():
    action = _well_formed_action(id="a1", action_type="internal", tool_name=None)
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is True


@pytest.mark.parametrize(
    "status",
    [
        ActionStatus.FAILED,
        ActionStatus.CANCELLED,
        ActionStatus.REJECTED,
        ActionStatus.BLOCKED,
        ActionStatus.VERIFICATION_FAILED,
    ],
)
def test_impossible_action_status_blocks_readiness(status):
    action = _well_formed_action(id="a1", status=status)
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is False
    assert any("impossible state" in b for b in result.blockers)


def test_retry_count_exceeding_max_retries_is_a_warning_not_a_blocker():
    action = _well_formed_action(id="a1", retry_count=3, max_retries=1)
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is True
    assert any("exceeding max_retries" in w for w in result.warnings)


def test_low_risk_approval_required_is_a_warning():
    action = _well_formed_action(id="a1", approval_required=True, risk_level=RiskLevel.LOW)
    result = evaluate_plan_readiness(_plan([action]))
    assert result.ready is True
    assert any("approval_required" in w for w in result.warnings)


# --- Strict raising variant (validate_dependencies) ----------------------


def test_validate_dependencies_raises_for_cycle():
    a = _well_formed_action(id="a1", dependencies=["a2"])
    b = _well_formed_action(id="a2", dependencies=["a1"])
    with pytest.raises(ActionPlanValidationError):
        validate_dependencies([a, b])


def test_validate_dependencies_passes_for_valid_graph():
    a = _well_formed_action(id="a1")
    b = _well_formed_action(id="a2", dependencies=["a1"])
    validate_dependencies([a, b])  # must not raise
