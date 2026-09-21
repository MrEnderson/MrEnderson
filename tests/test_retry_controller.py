"""Bounded Retry Authorization (v0.1.3.7, spec sections 8-13)."""
from __future__ import annotations

import pytest

from app.database.models import PersistedActionStatus
from app.database.repositories import ActionRecordRepository
from app.decision_intelligence.execution_persistence import action_to_record_fields, record_to_action
from app.decision_intelligence.retry_controller import (
    RetryBudgetExhaustedError,
    RetryNotEligibleError,
    authorize_retry,
    is_retry_exhausted,
)
from app.decision_intelligence.schemas import Action, ActionStatus


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="sandbox_create", tool_name="file.create_sandboxed", title="A",
        inputs={"relative_path": "a.txt", "content": "x"}, expected_result="r", success_criteria="n/a",
        verification_method="n/a", max_retries=2,
    )
    fields.update(overrides)
    return Action(**fields)


async def _persist(session, action: Action):
    repo = ActionRecordRepository(session)
    await repo.create(**action_to_record_fields(action))
    return repo


class TestIsRetryExhausted:
    def test_false_when_below_max(self):
        assert is_retry_exhausted(_action(retry_count=0, max_retries=2)) is False

    def test_true_when_equal_to_max(self):
        assert is_retry_exhausted(_action(retry_count=2, max_retries=2)) is True

    def test_true_when_max_is_zero(self):
        assert is_retry_exhausted(_action(retry_count=0, max_retries=0)) is True


class TestAuthorizeRetryFromFailed:
    async def test_resets_to_validated_and_bumps_retry_count(self, session):
        action = _action(status=ActionStatus.FAILED, retry_count=0, max_retries=2, error="boom")
        repo = await _persist(session, action)
        row = await repo.get(action.id)

        refreshed = await authorize_retry(repo, row)
        assert refreshed.status == ActionStatus.VALIDATED
        assert refreshed.retry_count == 1
        assert refreshed.error is None

        durable = await repo.get(action.id)
        assert durable.status == PersistedActionStatus.VALIDATED
        assert durable.retry_count == 1

    async def test_second_retry_bumps_again(self, session):
        action = _action(status=ActionStatus.FAILED, retry_count=1, max_retries=2)
        repo = await _persist(session, action)
        row = await repo.get(action.id)
        refreshed = await authorize_retry(repo, row)
        assert refreshed.retry_count == 2

    async def test_exhausted_budget_raises_and_does_not_write(self, session):
        action = _action(status=ActionStatus.FAILED, retry_count=2, max_retries=2)
        repo = await _persist(session, action)
        row = await repo.get(action.id)
        with pytest.raises(RetryBudgetExhaustedError):
            await authorize_retry(repo, row)
        durable = await repo.get(action.id)
        assert durable.status == PersistedActionStatus.FAILED  # unchanged
        assert durable.retry_count == 2

    async def test_preserves_action_hash_and_inputs(self, session):
        """A retry is the SAME Action, SAME payload (spec section 13) — not
        a replan; action_hash must be byte-identical before/after."""
        action = _action(status=ActionStatus.FAILED, retry_count=0, max_retries=1)
        repo = await _persist(session, action)
        row_before = await repo.get(action.id)
        hash_before = row_before.action_hash
        await authorize_retry(repo, row_before)
        row_after = await repo.get(action.id)
        assert row_after.action_hash == hash_before
        assert row_after.inputs_json == row_before.inputs_json


class TestAuthorizeRetryFromCrashInterrupted:
    async def test_resets_from_executing(self, session):
        """spec sections 9/44/75: reconciliation confirmed EXECUTING +
        side-effect-known-absent — retry re-enters from EXECUTING, not
        FAILED (the Action was never durably marked FAILED at all)."""
        action = _action(status=ActionStatus.EXECUTING, retry_count=0, max_retries=1)
        repo = await _persist(session, action)
        row = await repo.get(action.id)
        refreshed = await authorize_retry(repo, row)
        assert refreshed.status == ActionStatus.VALIDATED
        assert refreshed.retry_count == 1

    async def test_resets_from_approved(self, session):
        action = _action(status=ActionStatus.APPROVED, retry_count=0, max_retries=1, approval_required=True)
        repo = await _persist(session, action)
        row = await repo.get(action.id)
        refreshed = await authorize_retry(repo, row)
        assert refreshed.status == ActionStatus.VALIDATED


class TestAuthorizeRetryRejectsIneligibleStatuses:
    @pytest.mark.parametrize(
        "status",
        [ActionStatus.COMPLETED, ActionStatus.REJECTED, ActionStatus.CANCELLED, ActionStatus.BLOCKED,
         ActionStatus.PLANNED, ActionStatus.VALIDATED, ActionStatus.PERMISSION_CHECKED,
         ActionStatus.WAITING_FOR_APPROVAL, ActionStatus.VERIFYING, ActionStatus.VERIFIED],
    )
    async def test_rejects_non_reentry_status(self, session, status):
        action = _action(status=status, retry_count=0, max_retries=2)
        repo = await _persist(session, action)
        row = await repo.get(action.id)
        with pytest.raises(RetryNotEligibleError):
            await authorize_retry(repo, row)


class TestRetryDoesNotDoubleIncrementOnRestart:
    async def test_retry_count_is_not_reset_by_a_fresh_repo_instance(self, session):
        """Restart must not reset retry_count (spec section 10)."""
        action = _action(status=ActionStatus.FAILED, retry_count=1, max_retries=3)
        repo = await _persist(session, action)
        row = await repo.get(action.id)
        await authorize_retry(repo, row)

        fresh_repo = ActionRecordRepository(session)
        durable = await fresh_repo.get(action.id)
        assert durable.retry_count == 2  # continued from 1, not reset to 1 again
