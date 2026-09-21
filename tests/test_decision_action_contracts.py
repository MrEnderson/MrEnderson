"""ApprovalRequest / ExecutionResult / VerificationResult / PlanReadinessResult
contracts: construction, serialization, fail-closed unknown values, and that
this checkpoint reused rather than duplicated existing enums (v0.1.3.1, spec
sections 8/10/11/17/18)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.database.models import ApprovalStatus as ExistingTaskApprovalStatus
from app.database.models import PermissionLevel, RiskLevel
from app.decision_intelligence.action_hash import compute_action_hash
from app.decision_intelligence.schemas import (
    Action,
    ActionStatus,
    ApprovalRequest,
    ApprovalRequestStatus,
    ExecutionResult,
    FailureCategory,
    PlanReadinessResult,
    VerificationResult,
)


def _approval_request(**overrides) -> ApprovalRequest:
    action = Action(action_plan_id="plan-1", action_type="send_email", title="Send it")
    fields = dict(
        action_id=action.id,
        permission_level=PermissionLevel.EXTERNAL_ACTION,
        action_hash=compute_action_hash(action),
    )
    fields.update(overrides)
    return ApprovalRequest(**fields)


def test_approval_request_defaults_to_pending():
    request = _approval_request()
    assert request.status == ApprovalRequestStatus.PENDING
    assert request.decided_at is None
    assert request.decided_by is None


def test_approval_request_serialization_round_trips():
    request = _approval_request(reason="Sends money to a vendor")
    dumped = request.model_dump(mode="json")
    restored = ApprovalRequest.model_validate(dumped)
    assert restored == request


def test_approval_request_status_is_distinct_from_existing_task_approval_status():
    # Existing app.database.models.ApprovalStatus is Task-scoped and lacks
    # EXPIRED/CANCELLED — this checkpoint's ApprovalRequestStatus is a
    # deliberately separate, Action-scoped enum, not a silent duplicate.
    existing_values = {member.value for member in ExistingTaskApprovalStatus}
    new_values = {member.value for member in ApprovalRequestStatus}
    assert existing_values == {"PENDING", "APPROVED", "REJECTED"}
    assert new_values == {"PENDING", "APPROVED", "REJECTED", "EXPIRED", "CANCELLED"}


def test_execution_result_construction_and_serialization():
    now = datetime.now(timezone.utc)
    result = ExecutionResult(
        action_id="a1",
        tool_name="email_tool",
        started_at=now,
        completed_at=now,
        success=False,
        error_type=FailureCategory.TOOL,
        error_message="provider timeout",
    )
    dumped = result.model_dump(mode="json")
    assert ExecutionResult.model_validate(dumped) == result


def test_verification_result_confidence_is_bounded():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        VerificationResult(action_id="a1", method="manual_check", passed=True, confidence=1.5, verified_at=now)


def test_verification_result_serialization():
    result = VerificationResult(action_id="a1", method="manual_check", passed=True, confidence=0.9)
    dumped = result.model_dump(mode="json")
    assert VerificationResult.model_validate(dumped) == result


def test_plan_readiness_result_defaults_to_not_ready():
    result = PlanReadinessResult()
    assert result.ready is False
    assert result.blockers == []
    assert result.warnings == []


# --- Fail closed on unknown/invalid values --------------------------------


def test_unknown_action_status_string_is_rejected():
    with pytest.raises(ValidationError):
        Action(action_plan_id="plan-1", action_type="send_email", title="x", status="NOT_A_REAL_STATUS")


def test_unknown_permission_level_string_is_rejected():
    with pytest.raises(ValidationError):
        Action(
            action_plan_id="plan-1",
            action_type="send_email",
            title="x",
            permission_level="SUPERUSER",
        )


def test_action_status_enum_matches_exactly_the_documented_set():
    assert {member.value for member in ActionStatus} == {
        "PLANNED",
        "VALIDATED",
        "PERMISSION_CHECKED",
        "WAITING_FOR_APPROVAL",
        "APPROVED",
        "EXECUTING",
        "EXECUTION_SUCCEEDED",
        "VERIFYING",
        "VERIFIED",
        "VERIFICATION_FAILED",
        "COMPLETED",
        "FAILED",
        "REJECTED",
        "CANCELLED",
        "BLOCKED",
    }


# --- Reuse, not duplication, of existing abstractions ---------------------


def test_action_reuses_existing_permission_and_risk_level_enums():
    action = Action(action_plan_id="plan-1", action_type="send_email", title="x")
    assert isinstance(action.permission_level, PermissionLevel)
    assert isinstance(action.risk_level, RiskLevel)
