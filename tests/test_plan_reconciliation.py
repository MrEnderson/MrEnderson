"""Deterministic ActionPlan Reconciliation — classifications, candidate
discovery, crash-window simulations, and stale-lease recovery (v0.1.3.6,
spec sections 26-28/43/53/54). NO LLM anywhere in this suite."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import ExecutionAttemptStatus, PersistedActionPlanStatus, PersistedActionStatus
from app.database.repositories import (
    ActionPlanRecordRepository,
    ActionRecordRepository,
    ExecutionAttemptRepository,
    ExecutionResultRepository,
)
from app.decision_intelligence.action_plan_orchestrator import run_plan_until_blocked, validate_and_persist_plan
from app.decision_intelligence.action_plan_persistence import compute_plan_hash, load_plan, persist_new_plan
from app.decision_intelligence.execution_persistence import action_to_record_fields, compute_idempotency_key, execution_result_to_record_fields
from app.decision_intelligence.plan_reconciliation import (
    PlanReconciliationClassification,
    discover_plan_reconciliation_candidates,
    reconcile_plan,
)
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus, ExecutionResult
from app.decision_intelligence.tool_adapters import build_default_adapter_registry
from app.decision_intelligence.tool_registry import build_default_tool_registry


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture
def tool_registry():
    return build_default_tool_registry()


@pytest.fixture
def adapters():
    return build_default_adapter_registry()


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="will-be-set", action_type="internal", title="A",
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    fields.update(overrides)
    return Action(**fields)


def _sandbox_action(relative_path: str, content: str, **overrides) -> Action:
    fields = dict(
        action_plan_id="will-be-set", action_type="sandbox_create", tool_name="file.create_sandboxed",
        title=f"write {relative_path}", inputs={"relative_path": relative_path, "content": content},
        expected_result="file created", success_criteria="exists", verification_method="hash",
    )
    fields.update(overrides)
    return Action(**fields)


def _plan(actions: list[Action], **overrides) -> ActionPlan:
    fields = dict(decision_id="dec-1", title="Test plan", actions=[])
    fields.update(overrides)
    plan = ActionPlan(**fields)
    fixed = [a.model_copy(update={"action_plan_id": plan.id}) for a in actions]
    return plan.model_copy(update={"actions": fixed})


async def _persist_plan_with_status(session, plan: ActionPlan, *, status: PersistedActionPlanStatus, action_statuses: dict[str, PersistedActionStatus] | None = None):
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    fields = dict(**_plan_fields(plan))
    fields["status"] = status
    await plan_repo.create(**fields)
    for action in plan.actions:
        a_fields = action_to_record_fields(action)
        if action_statuses and action.id in action_statuses:
            a_fields["status"] = action_statuses[action.id]
        else:
            a_fields["status"] = PersistedActionStatus.VALIDATED
        await action_repo.create(**a_fields)
    await session.commit()


def _plan_fields(plan: ActionPlan) -> dict:
    from app.decision_intelligence.action_plan_persistence import plan_to_record_fields

    return plan_to_record_fields(plan)


# --- discover_plan_reconciliation_candidates (spec section 26) ---------------


async def test_discover_finds_executing_plan(session):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING)
    candidates = await discover_plan_reconciliation_candidates(session)
    assert plan.id in candidates


async def test_discover_finds_waiting_for_approval_plan(session):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.WAITING_FOR_APPROVAL)
    candidates = await discover_plan_reconciliation_candidates(session)
    assert plan.id in candidates


async def test_discover_finds_partially_completed_plan(session):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.PARTIALLY_COMPLETED)
    candidates = await discover_plan_reconciliation_candidates(session)
    assert plan.id in candidates


async def test_discover_does_not_flag_completed_plan(session):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.COMPLETED)
    candidates = await discover_plan_reconciliation_candidates(session)
    assert plan.id not in candidates


async def test_discover_finds_stale_lease(session):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING)
    plan_repo = ActionPlanRecordRepository(session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=past, lease_seconds=1)
    candidates = await discover_plan_reconciliation_candidates(session)
    assert plan.id in candidates


async def test_discover_is_read_only(session):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING)
    plan_repo = ActionPlanRecordRepository(session)
    before = await plan_repo.get(plan.id)
    await discover_plan_reconciliation_candidates(session)
    after = await plan_repo.get(plan.id)
    assert before.version == after.version


# --- Basic classifications (spec section 28) -----------------------------------


async def test_unknown_plan_id_is_ambiguous(session, sandbox_root, adapters):
    result = await reconcile_plan("nonexistent", session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.AMBIGUOUS_PLAN_STATE
    assert result.human_review_required is True


async def test_completed_plan_is_consistent_completed(session, sandbox_root, adapters):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.COMPLETED)
    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_COMPLETED


async def test_failed_plan_is_consistent_failed(session, sandbox_root, adapters):
    plan = _plan([_action()])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.FAILED)
    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_FAILED


async def test_executing_plan_no_in_progress_actions_is_consistent(session, sandbox_root, adapters):
    a1 = _action()
    plan = _plan([a1])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING, action_statuses={a1.id: PersistedActionStatus.PERMISSION_CHECKED})
    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_EXECUTING


async def test_waiting_for_approval_action_gives_consistent_waiting(session, sandbox_root, adapters):
    a1 = _action()
    plan = _plan([a1])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.WAITING_FOR_APPROVAL, action_statuses={a1.id: PersistedActionStatus.WAITING_FOR_APPROVAL})
    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_WAITING_FOR_APPROVAL


# --- Reconciliation delegates to Action-level reconcile_action (spec 27) ----


async def _claim_and_write(session, action, action_row, *, tool_name="file.create_sandboxed", write=True, sandbox_root=None):
    attempt_repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_row.action_hash)
    now = datetime.now(timezone.utc)
    attempt = await attempt_repo.claim(action_id=action.id, idempotency_key=key, tool_name=tool_name, adapter_name=tool_name, adapter_version="1.0.0", claimed_by="worker-1", now=now)
    await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now)
    if write and sandbox_root is not None:
        content = action.inputs["content"]
        (sandbox_root / action.inputs["relative_path"]).write_text(content, encoding="utf-8")
    return attempt


async def test_plan_reconciliation_recovers_interrupted_action(session, sandbox_root, adapters):
    a1 = _sandbox_action("a1.txt", "hello")
    plan = _plan([a1])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING, action_statuses={a1.id: PersistedActionStatus.EXECUTING})
    action_row = await ActionRecordRepository(session).get(a1.id)
    await _claim_and_write(session, a1, action_row, sandbox_root=sandbox_root)

    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.recovered is True
    assert a1.id in result.actions_reconciled
    row = await ActionRecordRepository(session).get(a1.id)
    assert row.status == PersistedActionStatus.COMPLETED


async def test_plan_reconciliation_blocks_on_mismatched_side_effect(session, sandbox_root, adapters):
    a1 = _sandbox_action("a1.txt", "expected")
    plan = _plan([a1])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING, action_statuses={a1.id: PersistedActionStatus.EXECUTING})
    action_row = await ActionRecordRepository(session).get(a1.id)
    attempt_repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(a1.id, action_row.action_hash)
    now = datetime.now(timezone.utc)
    attempt = await attempt_repo.claim(action_id=a1.id, idempotency_key=key, tool_name="file.create_sandboxed", adapter_name="file.create_sandboxed", adapter_version="1.0.0", claimed_by="w1", now=now)
    await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now)
    (sandbox_root / "a1.txt").write_text("WRONG", encoding="utf-8")

    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.ACTION_RECONCILIATION_REQUIRED
    assert result.human_review_required is True
    row = await ActionRecordRepository(session).get(a1.id)
    assert row.status != PersistedActionStatus.COMPLETED


async def test_plan_reconciliation_never_writes_a_file(session, sandbox_root, adapters):
    a1 = _sandbox_action("a1.txt", "hello")
    plan = _plan([a1])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING, action_statuses={a1.id: PersistedActionStatus.EXECUTING})
    action_row = await ActionRecordRepository(session).get(a1.id)
    await _claim_and_write(session, a1, action_row, write=False)
    # no file exists at all -> EXECUTION_INTERRUPTED, safe_to_retry, but
    # reconciliation itself never writes anything.
    await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert not (sandbox_root / "a1.txt").exists()


# --- Crash windows A-J (spec section 43) ---------------------------------------


async def test_crash_A_plan_persisted_not_started(session, sandbox_root, adapters):
    plan = _plan([_action()])
    await validate_and_persist_plan(plan, session=session)
    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_READY


async def test_crash_B_plan_claimed_no_action_dispatched(session, sandbox_root, tool_registry, adapters):
    plan = _plan([_action()])
    await validate_and_persist_plan(plan, session=session)
    plan_repo = ActionPlanRecordRepository(session)
    now = datetime.now(timezone.utc)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=now, lease_seconds=300)
    await plan_repo.update_if_version_matches(plan.id, expected_version=1, status=PersistedActionPlanStatus.EXECUTING, started_at=now)
    # crash: lease still active, nothing dispatched yet
    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_EXECUTING


async def test_crash_C_first_action_completed_progress_not_recomputed(session, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    a2 = _sandbox_action("a2.txt", "2", sequence=2, dependencies=[a1.id])
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, max_orchestration_steps=1)
    # simulate crash right after A1's single step — plan status recompute
    # already happened via the normal run, but let's directly verify
    # reconciliation is a safe no-op on top of it.
    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.human_review_required is False


async def test_crash_D_multiple_completed_next_waiting_approval(session, sandbox_root, tool_registry):
    from tests.test_action_plan_orchestrator import _FakeAdapter, _approval_adapters

    registry, fake = _approval_adapters()
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    a2 = _action(action_type="send", tool_name="communication.send_email", title="A2", sequence=2, dependencies=[a1.id])
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    result = await reconcile_plan(plan.id, session=session, adapter_registry=registry, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_WAITING_FOR_APPROVAL


async def test_crash_G_verification_passed_plan_status_not_updated(session, sandbox_root, adapters):
    a1 = _sandbox_action("a1.txt", "hello")
    plan = _plan([a1])
    await _persist_plan_with_status(session, plan, status=PersistedActionPlanStatus.EXECUTING, action_statuses={a1.id: PersistedActionStatus.VERIFIED})
    action_row = await ActionRecordRepository(session).get(a1.id)

    attempt_repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(a1.id, action_row.action_hash)
    now = datetime.now(timezone.utc)
    attempt = await attempt_repo.claim(action_id=a1.id, idempotency_key=key, tool_name="file.create_sandboxed", adapter_name="file.create_sandboxed", adapter_version="1.0.0", claimed_by="w1", now=now)
    await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.VERIFIED)
    digest = hashlib.sha256(b"hello").hexdigest()
    exec_result = ExecutionResult(action_id=a1.id, tool_name="file.create_sandboxed", started_at=now, completed_at=now, success=True, output={"resolved_relative_path": "a1.txt", "bytes_written": 5, "content_hash": digest}, side_effect_occurred=True)
    await ExecutionResultRepository(session).create(**execution_result_to_record_fields(attempt.id, exec_result))
    (sandbox_root / "a1.txt").write_text("hello", encoding="utf-8")
    from app.decision_intelligence.schemas import VerificationResult
    from app.decision_intelligence.execution_persistence import bounded_json
    from app.database.repositories import VerificationResultRepository
    from app.decision_intelligence.execution_persistence import verification_result_to_record_fields as vfields

    verification = VerificationResult(action_id=a1.id, method="m", passed=True, confidence=1.0, verified_at=now)
    await VerificationResultRepository(session).create(**vfields(attempt.id, verification))

    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.recovered is True
    row = await ActionRecordRepository(session).get(a1.id)
    assert row.status == PersistedActionStatus.COMPLETED


async def test_crash_H_all_actions_completed_plan_still_executing(session, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    # Force the plan row back to EXECUTING despite the Action being COMPLETED.
    plan_repo = ActionPlanRecordRepository(session)
    row = await plan_repo.get(plan.id)
    await plan_repo.update_if_version_matches(plan.id, expected_version=row.version, status=PersistedActionPlanStatus.EXECUTING)

    result = await reconcile_plan(plan.id, session=session, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.classification == PlanReconciliationClassification.CONSISTENT_COMPLETED


async def test_crash_I_stale_lease_triggers_reconciliation_before_new_claim(session, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("a1.txt", "hello", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    plan_repo = ActionPlanRecordRepository(session)
    action_row = await ActionRecordRepository(session).get(a1.id)

    # Simulate a worker that claimed the plan, started A1, wrote the file,
    # but crashed before recording anything else, with an already-expired lease.
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await plan_repo.claim_orchestration(plan.id, owner="dead-worker", now=past, lease_seconds=1)
    row = await plan_repo.get(plan.id)
    await plan_repo.update_if_version_matches(plan.id, expected_version=row.version, status=PersistedActionPlanStatus.EXECUTING)
    action_repo = ActionRecordRepository(session)
    a1_row = await action_repo.get(a1.id)
    await action_repo.update_if_version_matches(a1.id, expected_version=a1_row.version, status=PersistedActionStatus.EXECUTING)
    await _claim_and_write(session, a1, await action_repo.get(a1.id), sandbox_root=sandbox_root)

    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, owner="new-worker")
    assert result.stop_reason.value == "PLAN_COMPLETED"
    assert (sandbox_root / "a1.txt").read_text() == "hello"


async def test_crash_J_restart_completed_actions_not_reexecuted(session, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    a2 = _sandbox_action("a2.txt", "2", sequence=2, dependencies=[a1.id])
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)

    a1_row_before = await ActionRecordRepository(session).get(a1.id)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    a1_row_after = await ActionRecordRepository(session).get(a1.id)
    assert a1_row_after.version == a1_row_before.version
    assert result.progress_made is False
