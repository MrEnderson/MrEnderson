"""Canonical action fingerprinting (v0.1.3.1, spec sections 9/17)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.decision_intelligence.action_hash import canonical_action_payload, compute_action_hash
from app.decision_intelligence.schemas import Action, ActionStatus, PermissionLevel, RiskLevel


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1",
        action_type="send_email",
        title="Send confirmation",
        tool_name="email_tool",
        inputs={"to": "a@example.com", "subject": "Hi"},
        expected_result="Customer receives a confirmation email",
        permission_level=PermissionLevel.EXTERNAL_ACTION,
        risk_level=RiskLevel.MEDIUM,
    )
    fields.update(overrides)
    return Action(**fields)


def test_same_semantic_action_produces_same_hash():
    a = _action(id="a1")
    b = _action(id="a1")
    assert compute_action_hash(a) == compute_action_hash(b)


def test_dictionary_key_ordering_does_not_change_hash():
    a = _action(inputs={"to": "x@example.com", "subject": "Hi", "cc": "y@example.com"})
    b = _action(inputs={"cc": "y@example.com", "subject": "Hi", "to": "x@example.com"})
    assert compute_action_hash(a) == compute_action_hash(b)


def test_security_relevant_input_change_changes_hash():
    a = _action(inputs={"to": "a@example.com"})
    b = _action(inputs={"to": "b@example.com"})
    assert compute_action_hash(a) != compute_action_hash(b)


def test_tool_change_changes_hash():
    a = _action(tool_name="email_tool")
    b = _action(tool_name="sms_tool")
    assert compute_action_hash(a) != compute_action_hash(b)


def test_expected_result_change_changes_hash():
    a = _action(expected_result="Customer receives a confirmation email")
    b = _action(expected_result="Customer receives a refund confirmation")
    assert compute_action_hash(a) != compute_action_hash(b)


def test_permission_or_risk_level_change_changes_hash():
    a = _action(permission_level=PermissionLevel.WRITE)
    b = _action(permission_level=PermissionLevel.EXTERNAL_ACTION)
    assert compute_action_hash(a) != compute_action_hash(b)


def test_lifecycle_metadata_does_not_change_hash():
    now = datetime.now(timezone.utc)
    a = _action(
        id="a1",
        status=ActionStatus.PLANNED,
        retry_count=0,
        started_at=None,
        completed_at=None,
        result=None,
        error=None,
    )
    b = _action(
        id="a2",  # different id
        status=ActionStatus.EXECUTING,
        retry_count=3,
        started_at=now,
        completed_at=now + timedelta(minutes=5),
        result={"ok": True},
        error="transient blip",
        approval_id="approval-99",
        estimated_cost=42.0,
    )
    assert compute_action_hash(a) == compute_action_hash(b)


def test_title_description_and_dependencies_do_not_change_hash():
    a = _action(title="Send it", description="", dependencies=[])
    b = _action(title="Send the confirmation email now", description="urgent", dependencies=["other-id"])
    assert compute_action_hash(a) == compute_action_hash(b)


def test_canonical_payload_contains_only_the_documented_fields():
    payload = canonical_action_payload(_action())
    assert set(payload.keys()) == {
        "action_type",
        "tool_name",
        "inputs",
        "expected_result",
        "permission_level",
        "risk_level",
    }
