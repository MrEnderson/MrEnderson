"""The deterministic Reconciliation Engine — classification, recovery,
crash-window simulations, candidate discovery, and security invariants
(v0.1.3.5, spec sections 14-21/26-28/36-38). NO LLM, NO re-invocation of
adapter.execute() anywhere in this suite — recovery is inspect -> classify
-> (safely) verify/advance, never a blind retry."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import (
    ActionApprovalStatus,
    ExecutionAttemptStatus,
    PersistedActionStatus,
    ResultProvenance,
)
from app.database.repositories import (
    ActionRecordRepository,
    ExecutionAttemptRepository,
    ExecutionResultRepository,
    VerificationResultRepository,
)
from app.decision_intelligence.execution_persistence import (
    action_to_record_fields,
    compute_idempotency_key,
    execution_result_to_record_fields,
    verification_result_to_record_fields,
)
from app.decision_intelligence.reconciliation import (
    ReconciliationClassification,
    discover_reconciliation_candidates,
    reconcile_action,
)
from app.decision_intelligence.schemas import Action, ActionStatus, ExecutionResult, VerificationResult
from app.decision_intelligence.tool_adapters import ToolAdapterRegistry, build_default_adapter_registry


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="sandbox_create", tool_name="file.create_sandboxed",
        title="Recovery test", inputs={"relative_path": "note.txt", "content": "recovered content"},
        expected_result="a sandbox file is created", status=ActionStatus.PERMISSION_CHECKED,
    )
    fields.update(overrides)
    return Action(**fields)


async def _persist_action(session, action: Action, *, status: PersistedActionStatus | None = None, approval_required: bool = False):
    fields = action_to_record_fields(action)
    if status is not None:
        fields["status"] = status
    fields["approval_required"] = approval_required
    row = await ActionRecordRepository(session).create(**fields)
    await session.commit()
    return row


async def _claim_attempt(session, action, action_hash, *, tool_name="file.create_sandboxed", adapter_name="file.create_sandboxed", now=None):
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    effective_now = now or datetime.now(timezone.utc)
    attempt = await repo.claim(
        action_id=action.id, idempotency_key=key, tool_name=tool_name, adapter_name=adapter_name,
        adapter_version="1.0.0", claimed_by="worker-1", now=effective_now,
    )
    return attempt


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


# --- discover_reconciliation_candidates (spec section 28) --------------------


async def test_discover_finds_non_terminal_executing_action(session):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    candidates = await discover_reconciliation_candidates(session)
    assert action.id in candidates


async def test_discover_finds_verifying_and_verified(session):
    a1 = _action()
    a2 = _action(action_plan_id="plan-2")
    await _persist_action(session, a1, status=PersistedActionStatus.VERIFYING)
    await _persist_action(session, a2, status=PersistedActionStatus.VERIFIED)
    candidates = await discover_reconciliation_candidates(session)
    assert a1.id in candidates
    assert a2.id in candidates


async def test_discover_does_not_flag_completed(session):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.COMPLETED)
    candidates = await discover_reconciliation_candidates(session)
    assert action.id not in candidates


async def test_discover_does_not_flag_permission_checked(session):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.PERMISSION_CHECKED)
    candidates = await discover_reconciliation_candidates(session)
    assert action.id not in candidates


async def test_discover_finds_stale_started_attempt(session):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    attempt = await _claim_attempt(session, action, row.action_hash)
    now = datetime.now(timezone.utc)
    await ExecutionAttemptRepository(session).update_fields(
        attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now - timedelta(hours=1),
        lease_expires_at=now - timedelta(minutes=30),
    )
    candidates = await discover_reconciliation_candidates(session, now=lambda: now)
    assert action.id in candidates


async def test_discover_is_read_only(session):
    action = _action()
    row_before = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await discover_reconciliation_candidates(session)
    row_after = await ActionRecordRepository(session).get(action.id)
    assert row_after.version == row_before.version  # nothing mutated


# --- Basic classifications ----------------------------------------------------


async def test_unknown_action_id_is_ambiguous(session, sandbox_root):
    result = await reconcile_action("nonexistent-id", session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.AMBIGUOUS_STATE
    assert result.human_review_required is True


async def test_completed_action_is_consistent_completed(session, sandbox_root):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.COMPLETED)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_COMPLETED
    assert result.recovered is False
    assert result.safe_to_retry is False


@pytest.mark.parametrize("status", [
    PersistedActionStatus.FAILED, PersistedActionStatus.REJECTED,
    PersistedActionStatus.CANCELLED, PersistedActionStatus.BLOCKED,
])
async def test_terminal_failure_statuses_are_consistent_failed(session, sandbox_root, status):
    action = _action()
    await _persist_action(session, action, status=status)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_FAILED
    assert result.safe_to_retry is False
    assert result.human_review_required is False


async def test_permission_checked_no_attempts_is_execution_not_started(session, sandbox_root):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.PERMISSION_CHECKED)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.EXECUTION_NOT_STARTED
    assert result.safe_to_retry is True


async def test_approved_no_attempts_is_approval_consumed_execution_missing(session, sandbox_root):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.APPROVED, approval_required=True)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.APPROVAL_CONSUMED_EXECUTION_MISSING
    assert result.safe_to_retry is False
    assert result.human_review_required is True


async def test_advanced_status_with_no_attempt_is_security_inconsistency(session, sandbox_root):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.SECURITY_INCONSISTENCY
    assert result.human_review_required is True


# --- Window B/C: attempt exists, no ExecutionResult ---------------------------


async def test_no_side_effect_found_is_execution_interrupted_and_safe_to_retry(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    # No file was ever written.
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.EXECUTION_INTERRUPTED
    assert result.safe_to_retry is True
    assert result.recovered is False


async def test_matching_side_effect_recovers_to_completed_without_rewriting(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    target = sandbox_root / "note.txt"
    target.write_text("recovered content", encoding="utf-8")
    mtime_before = target.stat().st_mtime

    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)

    assert result.classification == ReconciliationClassification.SIDE_EFFECT_PRESENT_RESULT_MISSING
    assert result.recovered is True
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status == PersistedActionStatus.COMPLETED
    assert target.read_text(encoding="utf-8") == "recovered content"
    assert target.stat().st_mtime == mtime_before  # never rewritten


async def test_mismatched_side_effect_is_blocked_not_completed(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    target = sandbox_root / "note.txt"
    target.write_text("WRONG content entirely", encoding="utf-8")

    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)

    assert result.classification == ReconciliationClassification.SIDE_EFFECT_MISMATCH
    assert result.safe_to_retry is False
    assert result.human_review_required is True
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status != PersistedActionStatus.COMPLETED
    assert target.read_text(encoding="utf-8") == "WRONG content entirely"  # untouched, not overwritten


async def test_no_adapter_for_inspection_is_ambiguous(session, sandbox_root):
    action = _action(tool_name="communication.send_email", action_type="send")
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash, tool_name="communication.send_email", adapter_name="communication.send_email")
    empty_adapters = ToolAdapterRegistry()
    result = await reconcile_action(action.id, session=session, adapter_registry=empty_adapters, sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.AMBIGUOUS_STATE
    assert result.human_review_required is True


async def test_adapter_without_inspect_capability_is_ambiguous(session, sandbox_root):
    class _NoInspectAdapter:
        name = "test.no_inspect"
        version = "1.0.0"

        async def execute(self, action, context):
            raise AssertionError("must never be called during reconciliation")

        async def verify(self, action, execution_result, context):
            raise AssertionError("must never be called before inspection resolves")

    action = _action(tool_name="test.no_inspect")
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash, tool_name="test.no_inspect", adapter_name="test.no_inspect")
    registry = ToolAdapterRegistry()
    registry.register("test.no_inspect", _NoInspectAdapter())
    result = await reconcile_action(action.id, session=session, adapter_registry=registry, sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.AMBIGUOUS_STATE


# --- Execution result failed -> consistent, not recoverable ------------------


async def test_execution_result_recorded_failure_is_consistent_failed(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.FAILED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    now = datetime.now(timezone.utc)
    failed_result = ExecutionResult(
        action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now,
        success=False, error_code="SANDBOX_VIOLATION", error_message="boom",
    )
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, failed_result))
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_FAILED


# --- Window D/E: execution succeeded, no VerificationResult ------------------


async def test_missing_verification_recovers_to_completed(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTION_SUCCEEDED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    target = sandbox_root / "note.txt"
    target.write_text("recovered content", encoding="utf-8")
    now = datetime.now(timezone.utc)
    import hashlib

    digest = hashlib.sha256(b"recovered content").hexdigest()
    success_result = ExecutionResult(
        action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now,
        success=True, output={"resolved_relative_path": "note.txt", "bytes_written": 17, "content_hash": digest},
        side_effect_occurred=True,
    )
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, success_result))

    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)

    assert result.classification == ReconciliationClassification.EXECUTION_SUCCEEDED_VERIFICATION_MISSING
    assert result.recovered is True
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status == PersistedActionStatus.COMPLETED
    verification_row = await VerificationResultRepository(session).get_by_attempt(attempt.id)
    assert verification_row.passed is True
    assert verification_row.provenance == ResultProvenance.RECONSTRUCTED


async def test_missing_verification_that_actually_fails_does_not_complete(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTION_SUCCEEDED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    # No file was written at all, but ExecutionResult claims success — a
    # genuinely inconsistent state; deterministic verification must fail.
    now = datetime.now(timezone.utc)
    bogus_result = ExecutionResult(
        action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now,
        success=True, output={"resolved_relative_path": "note.txt", "bytes_written": 18, "content_hash": "0" * 64},
        side_effect_occurred=True,
    )
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, bogus_result))

    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status != PersistedActionStatus.COMPLETED


# --- Window F: verification passed, completion missing -----------------------


async def test_verified_but_not_completed_recovers_to_completed(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.VERIFIED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    target = sandbox_root / "note.txt"
    target.write_text("recovered content", encoding="utf-8")
    import hashlib

    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(b"recovered content").hexdigest()
    success_result = ExecutionResult(
        action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now,
        success=True, output={"resolved_relative_path": "note.txt", "bytes_written": 17, "content_hash": digest},
        side_effect_occurred=True,
    )
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, success_result))
    passed_verification = VerificationResult(action_id=action.id, method="sandbox_file_verification", passed=True, confidence=1.0, verified_at=now)
    await VerificationResultRepository(session).create(**verification_result_to_record_fields(attempt.id, passed_verification))

    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)

    assert result.classification == ReconciliationClassification.VERIFICATION_PASSED_COMPLETION_MISSING
    assert result.recovered is True
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status == PersistedActionStatus.COMPLETED


async def test_verified_and_already_completed_is_consistent(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.COMPLETED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    now = datetime.now(timezone.utc)
    success_result = ExecutionResult(action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now, success=True, side_effect_occurred=True)
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, success_result))
    passed_verification = VerificationResult(action_id=action.id, method="m", passed=True, confidence=1.0, verified_at=now)
    await VerificationResultRepository(session).create(**verification_result_to_record_fields(attempt.id, passed_verification))

    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_COMPLETED
    assert result.recovered is False


async def test_verification_failed_is_consistent_failed(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.FAILED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    now = datetime.now(timezone.utc)
    success_result = ExecutionResult(action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now, success=True, side_effect_occurred=True)
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, success_result))
    failed_verification = VerificationResult(action_id=action.id, method="m", passed=False, confidence=0.0, issues=["bad"], verified_at=now)
    await VerificationResultRepository(session).create(**verification_result_to_record_fields(attempt.id, failed_verification))

    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_FAILED


# --- Crash simulation tests: one per spec section 37 point -------------------


async def test_crash_1_after_approval_consumption_before_attempt(session, sandbox_root):
    action = _action(status=ActionStatus.APPROVED)
    await _persist_action(session, action, status=PersistedActionStatus.APPROVED, approval_required=True)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.APPROVAL_CONSUMED_EXECUTION_MISSING
    assert result.human_review_required is True


async def test_crash_2_after_attempt_creation_before_claim_started(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    attempt = await _claim_attempt(session, action, row.action_hash)  # stays CREATED, never STARTED
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.EXECUTION_INTERRUPTED
    assert result.safe_to_retry is True


async def test_crash_3_after_claim_before_adapter_write(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    attempt = await _claim_attempt(session, action, row.action_hash)
    now = datetime.now(timezone.utc)
    await ExecutionAttemptRepository(session).update_fields(attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now)
    # No file written yet.
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.EXECUTION_INTERRUPTED
    assert result.safe_to_retry is True
    assert not (sandbox_root / "note.txt").exists()


async def test_crash_4_after_adapter_write_before_result_persisted(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    attempt = await _claim_attempt(session, action, row.action_hash)
    (sandbox_root / "note.txt").write_text("recovered content", encoding="utf-8")
    # ExecutionResult was never persisted.
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.SIDE_EFFECT_PRESENT_RESULT_MISSING
    assert result.recovered is True
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status == PersistedActionStatus.COMPLETED


async def test_crash_5_after_result_persisted_before_verification(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTION_SUCCEEDED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    (sandbox_root / "note.txt").write_text("recovered content", encoding="utf-8")
    import hashlib

    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(b"recovered content").hexdigest()
    success_result = ExecutionResult(
        action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now,
        success=True, output={"resolved_relative_path": "note.txt", "bytes_written": 17, "content_hash": digest},
        side_effect_occurred=True,
    )
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, success_result))
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.EXECUTION_SUCCEEDED_VERIFICATION_MISSING
    assert result.recovered is True


async def test_crash_6_verification_performed_before_result_persisted(session, sandbox_root):
    # Equivalent, from a durable-state perspective, to crash point 5 — the
    # only durable signal reconciliation can observe is "no
    # VerificationResult row exists yet"; it always re-verifies
    # deterministically rather than trusting an in-memory-only claim.
    await test_crash_5_after_result_persisted_before_verification(session, sandbox_root)


async def test_crash_7_after_verification_before_result_persisted(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.VERIFYING)
    attempt = await _claim_attempt(session, action, row.action_hash)
    (sandbox_root / "note.txt").write_text("recovered content", encoding="utf-8")
    import hashlib

    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(b"recovered content").hexdigest()
    success_result = ExecutionResult(
        action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now,
        success=True, output={"resolved_relative_path": "note.txt", "bytes_written": 17, "content_hash": digest},
        side_effect_occurred=True,
    )
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, success_result))
    # VerificationResult itself never got persisted before the crash.
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.EXECUTION_SUCCEEDED_VERIFICATION_MISSING
    assert result.recovered is True
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status == PersistedActionStatus.COMPLETED


async def test_crash_8_verified_before_completed(session, sandbox_root):
    await test_verified_but_not_completed_recovers_to_completed(session, sandbox_root)


# --- Concurrency: two reconciliation attempts, no duplicate side effects ----


async def test_two_sequential_reconciliations_no_duplicate_writes(session_factory, sandbox_root):
    """Two reconciliation passes against the same recovered Action (e.g. a
    second candidate-discovery sweep re-finding it before the first pass's
    COMPLETED status is somehow missed) must never duplicate the recovery
    — the second pass sees CONSISTENT_COMPLETED and does nothing further."""
    action = _action()
    async with session_factory() as setup:
        row = await _persist_action(setup, action, status=PersistedActionStatus.EXECUTING)
        await _claim_attempt(setup, action, row.action_hash)
    (sandbox_root / "note.txt").write_text("recovered content", encoding="utf-8")

    async def reconcile():
        async with session_factory() as s:
            return await reconcile_action(action.id, session=s, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)

    first = await reconcile()
    second = await reconcile()
    assert first.classification == ReconciliationClassification.SIDE_EFFECT_PRESENT_RESULT_MISSING
    assert first.recovered is True
    assert second.classification == ReconciliationClassification.CONSISTENT_COMPLETED
    assert second.recovered is False

    async with session_factory() as check:
        final_row = await ActionRecordRepository(check).get(action.id)
        exec_results = []
        attempts = await ExecutionAttemptRepository(check).list_for_action(action.id)
        for a in attempts:
            r = await ExecutionResultRepository(check).get_by_attempt(a.id)
            if r is not None:
                exec_results.append(r)

    assert final_row.status == PersistedActionStatus.COMPLETED
    assert len(exec_results) == 1  # never duplicated
    assert (sandbox_root / "note.txt").read_text(encoding="utf-8") == "recovered content"


# --- Security invariants (spec section 36) ------------------------------------


async def test_security_1_reconciliation_cannot_execute_arbitrary_adapters(session, sandbox_root):
    class _MustNeverExecute:
        name = "test.never_execute"
        version = "1.0.0"
        called = False

        async def execute(self, action, context):
            _MustNeverExecute.called = True
            raise AssertionError("execute() must never be called by reconciliation")

        async def verify(self, action, execution_result, context):
            raise AssertionError("unreachable in this test")

    action = _action(tool_name="test.never_execute")
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash, tool_name="test.never_execute", adapter_name="test.never_execute")
    registry = ToolAdapterRegistry()
    registry.register("test.never_execute", _MustNeverExecute())
    await reconcile_action(action.id, session=session, adapter_registry=registry, sandbox_root=sandbox_root)
    assert _MustNeverExecute.called is False


async def test_security_2_reconciliation_cannot_invoke_unknown_tools(session, sandbox_root):
    action = _action(tool_name="evil.magic_shell")
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash, tool_name="evil.magic_shell", adapter_name="evil.magic_shell")
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.AMBIGUOUS_STATE


async def test_security_3_4_no_shell_or_network_call_in_reconciliation_module():
    import inspect

    from app.decision_intelligence import reconciliation

    source = inspect.getsource(reconciliation)
    assert "subprocess" not in source
    assert "os.system" not in source
    assert "anthropic" not in source.lower()
    assert "httpx" not in source
    assert "requests." not in source


async def test_security_5_reconciliation_cannot_escape_sandbox(session, sandbox_root):
    action = _action(inputs={"relative_path": "../escape.txt", "content": "x"})
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    # Path validation still applies during inspection — never escapes.
    assert result.classification in (ReconciliationClassification.AMBIGUOUS_STATE, ReconciliationClassification.EXECUTION_INTERRUPTED)


async def test_security_6_reconciliation_does_not_overwrite(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    target = sandbox_root / "note.txt"
    target.write_text("DIFFERENT from expected", encoding="utf-8")
    await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert target.read_text(encoding="utf-8") == "DIFFERENT from expected"


async def test_security_7_reconciliation_does_not_delete(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    target = sandbox_root / "note.txt"
    target.write_text("WRONG", encoding="utf-8")
    await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert target.exists()  # never deleted, even when mismatched


async def test_security_8_side_effect_mismatch_cannot_complete(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    (sandbox_root / "note.txt").write_text("WRONG", encoding="utf-8")
    await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status != PersistedActionStatus.COMPLETED


async def test_security_9_missing_verification_cannot_complete_without_real_verification(session, sandbox_root):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTION_SUCCEEDED)
    attempt = await _claim_attempt(session, action, row.action_hash)
    # ExecutionResult claims success but nothing was actually written.
    now = datetime.now(timezone.utc)
    fake_result = ExecutionResult(
        action_id=action.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now,
        success=True, output={"resolved_relative_path": "note.txt", "bytes_written": 5, "content_hash": "0" * 64},
        side_effect_occurred=True,
    )
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, fake_result))
    await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status != PersistedActionStatus.COMPLETED


async def test_security_10_duplicate_completed_action_cannot_execute_again(session, sandbox_root):
    action = _action()
    await _persist_action(session, action, status=PersistedActionStatus.COMPLETED)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_COMPLETED
    assert result.recovered is False


async def test_security_11_two_workers_cannot_both_claim(session_factory):
    action = _action()
    async with session_factory() as setup:
        row = await _persist_action(setup, action, status=PersistedActionStatus.EXECUTING)
    key = compute_idempotency_key(action.id, row.action_hash)
    now = datetime.now(timezone.utc)

    async def claim(worker):
        async with session_factory() as s:
            return await ExecutionAttemptRepository(s).claim(
                action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a",
                adapter_version=None, claimed_by=worker, now=now,
            )

    r1, r2 = await asyncio.gather(claim("w1"), claim("w2"))
    assert sorted([r1 is not None, r2 is not None]) == [False, True]


async def test_security_12_one_idempotency_key_cannot_create_two_attempts(session):
    action = _action()
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    key = compute_idempotency_key(action.id, row.action_hash)
    now = datetime.now(timezone.utc)
    repo = ExecutionAttemptRepository(session)
    first = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w1", now=now)
    second = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w2", now=now)
    assert first is not None
    assert second is None
    attempts = await repo.list_for_action(action.id)
    assert len(attempts) == 1


async def test_security_13_stale_action_version_cannot_overwrite_newer_state(session):
    action = _action()
    repo = ActionRecordRepository(session)
    await repo.create(**action_to_record_fields(action))
    await session.commit()
    await repo.update_if_version_matches(action.id, expected_version=1, status=PersistedActionStatus.EXECUTING)
    stale_ok = await repo.update_if_version_matches(action.id, expected_version=1, status=PersistedActionStatus.FAILED)
    assert stale_ok is False
    row = await repo.get(action.id)
    assert row.status == PersistedActionStatus.EXECUTING


async def test_security_14_approval_consumption_remains_single_use_during_reconciliation():
    # Reconciliation never calls consume_approval()/consume_if_valid() at
    # all — verified structurally (no import, no call anywhere).
    import inspect

    from app.decision_intelligence import reconciliation

    source = inspect.getsource(reconciliation)
    assert "consume_approval" not in source
    assert "consume_if_valid" not in source
    assert "consume_durable" not in source


async def test_security_15_changed_action_payload_invalidates_recovery(session, sandbox_root):
    # The inspection recomputes the expected hash from action.inputs as
    # persisted durably — if the durable Action's inputs don't match what
    # is on disk, recovery must not silently proceed to COMPLETED.
    action = _action(inputs={"relative_path": "note.txt", "content": "ORIGINAL"})
    row = await _persist_action(session, action, status=PersistedActionStatus.EXECUTING)
    await _claim_attempt(session, action, row.action_hash)
    (sandbox_root / "note.txt").write_text("SOMETHING ELSE", encoding="utf-8")
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.SIDE_EFFECT_MISMATCH
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status != PersistedActionStatus.COMPLETED


async def test_security_16_reconciliation_cannot_manufacture_approval(session, sandbox_root):
    action = _action(status=ActionStatus.APPROVED)
    await _persist_action(session, action, status=PersistedActionStatus.APPROVED, approval_required=True)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.APPROVAL_CONSUMED_EXECUTION_MISSING
    assert result.safe_to_retry is False  # reconciliation never grants a fresh approval itself
    assert result.human_review_required is True


async def test_security_17_block_permission_cannot_be_recovered_into_execution(session, sandbox_root):
    action = _action(tool_name="system.privileged_shell", action_type="privileged")
    await _persist_action(session, action, status=PersistedActionStatus.BLOCKED)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_FAILED
    assert result.safe_to_retry is False


async def test_security_18_p5_blocked_action_cannot_become_executable_through_recovery(session, sandbox_root):
    action = _action(tool_name="system.install_software", action_type="install")
    await _persist_action(session, action, status=PersistedActionStatus.BLOCKED)
    result = await reconcile_action(action.id, session=session, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert result.classification == ReconciliationClassification.CONSISTENT_FAILED
    final_row = await ActionRecordRepository(session).get(action.id)
    assert final_row.status == PersistedActionStatus.BLOCKED  # unchanged, never advanced
