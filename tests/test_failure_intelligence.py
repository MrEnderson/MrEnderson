"""Deterministic Failure Intelligence (v0.1.3.7, spec sections 5/6/34/36)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.database.repositories import FailureRecordRepository
from app.decision_intelligence.failure_intelligence import (
    build_failure_record,
    classify_failure,
    persist_failure_record,
    row_to_failure_record,
)
from app.decision_intelligence.schemas import Action, ExecutionResult, ExecutorFailureCode, FailureCategory


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="sandbox_create", tool_name="file.create_sandboxed", title="A",
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    fields.update(overrides)
    return Action(**fields)


def _execution_result(action_id: str, **overrides) -> ExecutionResult:
    now = datetime.now(timezone.utc)
    fields = dict(action_id=action_id, started_at=now, completed_at=now, success=False)
    fields.update(overrides)
    return ExecutionResult(**fields)


class TestClassifyFailure:
    def test_error_code_maps_through_executor_failure_category(self):
        result = _execution_result("a1", error_code=ExecutorFailureCode.SANDBOX_VIOLATION.value)
        assert classify_failure(execution_result=result) == FailureCategory.SECURITY

    def test_error_code_tool_execution_failure_maps_to_tool(self):
        result = _execution_result("a1", error_code=ExecutorFailureCode.TOOL_EXECUTION_FAILURE.value)
        assert classify_failure(execution_result=result) == FailureCategory.TOOL

    def test_error_type_used_when_code_absent(self):
        result = _execution_result("a1", error_type=FailureCategory.VERIFICATION)
        assert classify_failure(execution_result=result) == FailureCategory.VERIFICATION

    def test_error_code_takes_priority_over_error_type(self):
        result = _execution_result(
            "a1", error_code=ExecutorFailureCode.PERMISSION_FAILURE.value, error_type=FailureCategory.UNKNOWN
        )
        assert classify_failure(execution_result=result) == FailureCategory.PERMISSION

    def test_unrecognized_error_code_falls_back_to_error_type(self):
        result = _execution_result("a1", error_code="NOT_A_REAL_CODE", error_type=FailureCategory.TOOL)
        assert classify_failure(execution_result=result) == FailureCategory.TOOL

    def test_no_execution_result_falls_back_to_default(self):
        assert classify_failure(execution_result=None) == FailureCategory.UNKNOWN
        assert classify_failure(execution_result=None, fallback_category=FailureCategory.TRANSIENT) == FailureCategory.TRANSIENT

    def test_never_pretends_certainty_for_unmodeled_failure(self):
        result = _execution_result("a1")  # no error_code, no error_type
        assert classify_failure(execution_result=result) == FailureCategory.UNKNOWN


class TestBuildFailureRecord:
    def test_captures_action_and_result_fields(self):
        action = _action(retry_count=1, max_retries=3)
        result = _execution_result(
            action.id, error_code=ExecutorFailureCode.TOOL_EXECUTION_FAILURE.value, error_message="boom",
            side_effect_occurred=False, execution_attempt_id="attempt-1",
        )
        record = build_failure_record(action, plan_id="plan-1", execution_result=result, retry_safe=True)
        assert record.action_id == action.id
        assert record.plan_id == "plan-1"
        assert record.category == FailureCategory.TOOL
        assert record.code == ExecutorFailureCode.TOOL_EXECUTION_FAILURE.value
        assert record.message == "boom"
        assert record.side_effect_occurred is False
        assert record.retry_safe is True
        assert record.retry_count_at_failure == 1
        assert record.execution_attempt_id == "attempt-1"

    def test_no_execution_result_uses_action_error(self):
        action = _action(error="internal reasoning failure")
        record = build_failure_record(action, plan_id="plan-1", execution_result=None, retry_safe=False)
        assert record.message == "internal reasoning failure"
        assert record.category == FailureCategory.UNKNOWN
        assert record.side_effect_occurred is False


class TestFailureRecordPersistence:
    async def test_persist_and_round_trip(self, session):
        action = _action()
        result = _execution_result(action.id, error_code=ExecutorFailureCode.TOOL_EXECUTION_FAILURE.value, error_message="x")
        record = build_failure_record(action, plan_id="plan-1", execution_result=result, retry_safe=True)
        repo = FailureRecordRepository(session)
        row = await persist_failure_record(repo, record)
        assert row.id == record.id
        loaded = row_to_failure_record(row)
        assert loaded.category == FailureCategory.TOOL
        assert loaded.retry_safe is True

    async def test_failure_history_is_append_only_not_a_single_mutable_field(self, session):
        """Distinct from ActionRecord.last_error (spec section 34) — a
        plan that fails three times keeps all three FailureRecords, not
        just the last one."""
        action = _action()
        repo = FailureRecordRepository(session)
        for i in range(3):
            result = _execution_result(action.id, error_code=ExecutorFailureCode.TOOL_EXECUTION_FAILURE.value)
            record = build_failure_record(
                action.model_copy(update={"retry_count": i}), plan_id="plan-1", execution_result=result, retry_safe=True
            )
            await persist_failure_record(repo, record)
        history = await repo.list_for_action(action.id)
        assert len(history) == 3
        assert [h.retry_count_at_failure for h in history] == [0, 1, 2]

    async def test_list_for_plan_scopes_correctly(self, session):
        repo = FailureRecordRepository(session)
        a1, a2 = _action(action_plan_id="plan-A"), _action(action_plan_id="plan-B")
        for action in (a1, a2):
            result = _execution_result(action.id, error_code=ExecutorFailureCode.TOOL_EXECUTION_FAILURE.value)
            record = build_failure_record(action, plan_id=action.action_plan_id, execution_result=result, retry_safe=False)
            await persist_failure_record(repo, record)
        plan_a_failures = await repo.list_for_plan("plan-A")
        assert len(plan_a_failures) == 1
        assert plan_a_failures[0].action_id == a1.id
