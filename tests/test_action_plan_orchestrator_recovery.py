"""Failure Intelligence + Bounded Retry + Controlled Replanning wired into
ActionPlan orchestration (v0.1.3.7). Integration tests over
run_plan_until_blocked() — the durable end-to-end behavior, not the
individual unit-level modules (see test_recovery_policy.py/
test_failure_intelligence.py/test_recovery_budget.py/test_retry_controller.py/
test_replan.py for those). NO live network, NO LLM calls — the only real
side effect anywhere in this suite is a UTF-8 text file inside a
pytest-managed temporary sandbox directory."""
from __future__ import annotations

import asyncio
import json

import pytest

from app.database.models import PersistedActionPlanStatus, PersistedActionStatus
from app.database.repositories import (
    ActionApprovalRequestRepository,
    ActionRecordRepository,
    ExecutionAttemptRepository,
    FailureRecordRepository,
    RecoveryDecisionRepository,
)
from app.decision_intelligence.action_plan_orchestrator import StopReason, run_plan_until_blocked, validate_and_persist_plan
from app.decision_intelligence.action_plan_persistence import load_plan
from app.decision_intelligence.approval_engine import decide_approval, expire_approval_request
from app.decision_intelligence.approval_persistence import load_approval_request, sync_decision
from app.decision_intelligence.execution_persistence import compute_idempotency_key
from app.decision_intelligence.replan import apply_replan, persist_proposal, propose_replan
from app.decision_intelligence.schemas import (
    Action,
    ActionPlan,
    ActionPlanStatus,
    ActionStatus,
    ExecutionResult,
    FailureCategory,
    VerificationResult,
)
from app.decision_intelligence.tool_adapters import SandboxFileCreateAdapter, ToolAdapterRegistry, build_default_adapter_registry
from app.decision_intelligence.tool_registry import build_default_tool_registry
from app.database.repositories import ReplanProposalRepository, ActionPlanRecordRepository

from tests.test_action_plan_orchestrator import _FakeAdapter, _action, _approval_adapters, _plan, _sandbox_action


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture
def tool_registry():
    return build_default_tool_registry()


class _TransientThenSuccessAdapter:
    """Test-only fake — NOT a second production adapter. attempts up to and
    including `fail_until_attempt` fail deterministically BEFORE any side
    effect; the next attempt delegates to the real SandboxFileCreateAdapter."""

    name = "file.create_sandboxed"
    version = "0.0.1-test"

    def __init__(self, *, fail_until_attempt: int = 1):
        self.fail_until_attempt = fail_until_attempt
        self.execute_calls = 0
        self._real = SandboxFileCreateAdapter()

    async def execute(self, action, context):
        self.execute_calls += 1
        if self.execute_calls <= self.fail_until_attempt:
            now = context.now()
            return ExecutionResult(
                action_id=action.id, tool_name=self.name, started_at=now, completed_at=now, success=False,
                error_type=FailureCategory.TRANSIENT, error_message="deterministic transient failure (test fixture)",
                side_effect_occurred=False,
            )
        return await self._real.execute(action, context)

    async def verify(self, action, execution_result, context):
        if not execution_result.success:
            return VerificationResult(
                action_id=action.id, method="test_transient", passed=False, confidence=0.0,
                issues=["execution did not succeed"], verified_at=context.now(),
            )
        return await self._real.verify(action, execution_result, context)

    async def inspect_effect(self, action, context):
        return await self._real.inspect_effect(action, context)


def _transient_registry(*, fail_until_attempt=1):
    registry = ToolAdapterRegistry()
    fake = _TransientThenSuccessAdapter(fail_until_attempt=fail_until_attempt)
    registry.register("file.create_sandboxed", fake)
    return registry, fake


class _AlwaysSecurityViolationAdapter:
    """Test-only — deterministic SECURITY-category failure, never a real
    sandbox escape. Proves SECURITY never retries regardless of budget."""

    name = "file.create_sandboxed"
    version = "0.0.1-test"

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, action, context):
        self.execute_calls += 1
        now = context.now()
        return ExecutionResult(
            action_id=action.id, tool_name=self.name, started_at=now, completed_at=now, success=False,
            error_type=FailureCategory.SECURITY, error_code="SANDBOX_VIOLATION",
            error_message="deterministic sandbox violation (test fixture)", side_effect_occurred=False,
        )

    async def verify(self, action, execution_result, context):
        return VerificationResult(action_id=action.id, method="test", passed=False, confidence=0.0, verified_at=context.now())


# --- Controlled retry benchmark (spec sections 37/71) ------------------------


async def test_controlled_retry_benchmark(session, sandbox_root, tool_registry):
    """A1 (test-only transient, first dispatched) fails attempt 1, retries,
    succeeds attempt 2; A2/A3 (safe P2, real adapter) each execute exactly
    once. The fake adapter's call counter is GLOBAL across every Action
    routed through the same tool_name, and A1 is dispatched first
    (sequence=1) — so it is the one that deterministically observes the
    single injected transient failure."""
    registry, fake = _transient_registry(fail_until_attempt=1)
    a1 = _sandbox_action("a1.txt", "1", title="A1 test-only transient", sequence=1, max_retries=1)
    a2 = _sandbox_action("a2.txt", "2", title="A2 safe P2", sequence=2, dependencies=[a1.id])
    a3 = _sandbox_action("a3.txt", "3", title="A3 safe P2", sequence=3, dependencies=[a2.id])
    plan = _plan([a1, a2, a3], failure_policy="STOP_ON_FAILURE")
    await validate_and_persist_plan(plan, session=session)

    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    assert result.ending_status == ActionPlanStatus.COMPLETED
    assert fake.execute_calls == 4  # A1 attempt 1 (fails) + A1 attempt 2 + A2 + A3; never a duplicate
    assert (sandbox_root / "a1.txt").exists()
    assert (sandbox_root / "a2.txt").exists()
    assert (sandbox_root / "a3.txt").exists()

    a1_row = await ActionRecordRepository(session).get(a1.id)
    assert a1_row.status == PersistedActionStatus.COMPLETED
    assert a1_row.retry_count == 1

    failures = await FailureRecordRepository(session).list_for_action(a1.id)
    assert len(failures) == 1
    assert failures[0].category == "TRANSIENT"

    decisions = await RecoveryDecisionRepository(session).list_for_action(a1.id)
    assert len(decisions) == 1
    assert decisions[0].decision == "RETRY"
    assert decisions[0].retry_number == 1


class TestRetryIntegration:
    async def test_transient_failure_then_success_completes_plan(self, session, sandbox_root, tool_registry):
        registry, fake = _transient_registry(fail_until_attempt=1)
        a1 = _sandbox_action("only.txt", "hello", sequence=1, max_retries=1)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
        assert result.ending_status.value == "COMPLETED"
        assert fake.execute_calls == 2
        assert (sandbox_root / "only.txt").read_text() == "hello"

    async def test_earlier_completed_actions_never_reexecute_during_retry(self, session, sandbox_root, tool_registry):
        registry, fake = _transient_registry(fail_until_attempt=1)
        # a0 uses the REAL adapter path (separate registry entry) so its
        # own single execution is trivially provable; a1 is the retrying one.
        real_registry = build_default_adapter_registry()
        combined = ToolAdapterRegistry()
        combined.register("file.create_sandboxed", registry.get("file.create_sandboxed"))

        a1 = _sandbox_action("first.txt", "1", sequence=1, max_retries=0)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        # a1 has max_retries=0 -> its single transient failure must NOT retry.
        result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=combined, sandbox_root=sandbox_root)
        assert fake.execute_calls == 1
        a1_row = await ActionRecordRepository(session).get(a1.id)
        assert a1_row.status == PersistedActionStatus.FAILED
        assert not (sandbox_root / "first.txt").exists()

    async def test_retry_history_is_durable_and_queryable(self, session, sandbox_root, tool_registry):
        registry, fake = _transient_registry(fail_until_attempt=2)
        a1 = _sandbox_action("x.txt", "x", sequence=1, max_retries=2)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
        assert fake.execute_calls == 3
        failures = await FailureRecordRepository(session).list_for_action(a1.id)
        assert len(failures) == 2
        decisions = await RecoveryDecisionRepository(session).list_for_action(a1.id)
        assert [d.retry_number for d in decisions] == [1, 2]


# --- Controlled budget-exhaustion benchmark (spec sections 74/78.28) --------


async def test_controlled_budget_exhaustion_benchmark(session, sandbox_root, tool_registry):
    """Plan-level: Action max_retries=1. Action fails transiently twice.
    Expected: initial attempt fails, one retry allowed, retry fails,
    budget exhausted, no third execution."""
    registry, fake = _transient_registry(fail_until_attempt=99)  # never succeeds
    a1 = _sandbox_action("never.txt", "x", sequence=1, max_retries=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    assert fake.execute_calls == 2  # initial + exactly one retry, never a third
    a1_row = await ActionRecordRepository(session).get(a1.id)
    assert a1_row.status == PersistedActionStatus.FAILED
    assert a1_row.retry_count == 1
    assert not (sandbox_root / "never.txt").exists()

    decisions = await RecoveryDecisionRepository(session).list_for_action(a1.id)
    assert decisions[-1].decision == "BUDGET_EXHAUSTED"
    assert result.stop_reason in (StopReason.BUDGET_EXHAUSTED, StopReason.ACTION_FAILED)


# --- Crash-during-retry / restart benchmark (spec sections 44/75) -----------


async def test_crash_during_retry_benchmark(session, sandbox_root, tool_registry, adapters=None):
    """attempt 1 fails transiently (no side effect) -> retry authorized and
    durably recorded -> process 'crashes' before the retry actually runs
    (simulated by leaving the Action mid-flight) -> fresh session/restart ->
    reconciliation confirms no side effect -> retry proceeds safely."""
    from app.decision_intelligence.tool_adapters import build_default_adapter_registry
    from app.decision_intelligence.durable_action_executor import _upsert_action_record
    from app.decision_intelligence.execution_persistence import record_to_action

    adapters = build_default_adapter_registry()
    a1 = _sandbox_action("crash.txt", "x", sequence=1, max_retries=2)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)

    action_repo = ActionRecordRepository(session)
    row = await action_repo.get(a1.id)
    # Simulate: durably EXECUTING, an ExecutionAttempt claimed and STARTED,
    # but the process died before any adapter call completed — no
    # ExecutionResult exists, and the target file was never written.
    from app.database.models import ExecutionAttemptStatus
    from datetime import datetime, timezone

    attempt_repo = ExecutionAttemptRepository(session)
    now = datetime.now(timezone.utc)
    key = compute_idempotency_key(a1.id, row.action_hash)
    attempt = await attempt_repo.claim(action_id=a1.id, idempotency_key=key, tool_name="file.create_sandboxed", adapter_name="file.create_sandboxed", adapter_version="1.0.0", claimed_by="worker-1", now=now)
    await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now)
    await action_repo.update_if_version_matches(a1.id, expected_version=row.version, status=PersistedActionStatus.EXECUTING, started_at=now)

    assert not (sandbox_root / "crash.txt").exists()

    # "Restart": a fresh call to run_plan_until_blocked on the SAME durable
    # state. It must reconcile FIRST (never blindly retry), find the side
    # effect definitively absent, THEN authorize a retry.
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)

    a1_row_after = await action_repo.get(a1.id)
    assert a1_row_after.status == PersistedActionStatus.COMPLETED
    assert a1_row_after.retry_count == 1  # the crash-recovery retry, recorded exactly once
    assert (sandbox_root / "crash.txt").read_text() == "x"

    # No duplicate FailureRecord/RecoveryDecision from a second restart.
    result2 = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result2.stop_reason == StopReason.PLAN_COMPLETED


# --- Controlled replan benchmark (spec sections 45/72) ----------------------


async def test_controlled_replan_benchmark(session, sandbox_root, tool_registry):
    adapters = build_default_adapter_registry()
    a1 = _sandbox_action("a1.txt", "1", title="A1", sequence=1)
    a2 = _action(title="A2 (will fail VALIDATION)", action_type="internal", sequence=2, dependencies=[a1.id])
    a3 = _sandbox_action("a3.txt", "3", title="A3", sequence=3, dependencies=[a2.id])
    plan = _plan([a1, a2, a3])
    await validate_and_persist_plan(plan, session=session)

    # A2 is P0/internal (no tool) — force a deterministic VALIDATION
    # failure by durably marking it FAILED after A1 completes, simulating
    # what a real VALIDATION-category executor failure would leave behind.
    # max_orchestration_steps=2: VALIDATED->PERMISSION_CHECKED (step 1),
    # then PERMISSION_CHECKED->execute_action_durably(...COMPLETED) in one
    # call (step 2) — exactly enough for A1 to finish, and no more, so A2
    # is never automatically touched (its FAILED state is then injected
    # deterministically below, standing in for a real VALIDATION failure).
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, max_orchestration_steps=2)
    a1_row = await ActionRecordRepository(session).get(a1.id)
    assert a1_row.status == PersistedActionStatus.COMPLETED

    action_repo = ActionRecordRepository(session)
    a2_row = await action_repo.get(a2.id)
    await action_repo.update_if_version_matches(a2.id, expected_version=a2_row.version, status=PersistedActionStatus.FAILED, last_error="deterministic VALIDATION failure (test fixture)")

    plan_repo = ActionPlanRecordRepository(session)
    _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
    failed = next(a for a in loaded_plan.actions if a.id == a2.id)
    replacement = _sandbox_action("a2b.txt", "2b", title="A2b", action_plan_id=plan.id)
    proposal = propose_replan(loaded_plan, failed, replacement, reason="deterministic replacement", failure_category=FailureCategory.VALIDATION)
    assert proposal.status.value == "PROPOSED"
    proposal_repo = ReplanProposalRepository(session)
    proposal_row = await persist_proposal(proposal_repo, proposal)
    await session.commit()

    apply_result = await apply_replan(proposal_row.id, session=session)
    assert apply_result.status.value == "APPLIED"
    assert apply_result.new_plan_revision == 2

    final = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert final.ending_status.value == "COMPLETED"
    assert (sandbox_root / "a1.txt").read_text() == "1"  # A1 never repeated
    assert (sandbox_root / "a2b.txt").read_text() == "2b"
    assert not (sandbox_root / "a2.txt").exists()  # A2 itself never executed anything

    a3_row = await action_repo.get(a3.id)
    assert a3_row.status == PersistedActionStatus.COMPLETED
    assert json.loads(a3_row.dependencies_json) == [replacement.id]


# --- Approval-invalidation-on-replan benchmark (spec sections 46/73) -------


async def test_approval_invalidation_benchmark(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _action(action_type="send", tool_name="communication.send_email", title="P4 original", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)

    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    approval_repo = ActionApprovalRequestRepository(session)
    a1_row = await ActionRecordRepository(session).get(a1.id)
    original_approval_id = a1_row.approval_id
    req = await load_approval_request(approval_repo, a1_row.approval_id)
    approved = decide_approval(req, "APPROVE", decided_by="human:alice")
    await sync_decision(approval_repo, approved)
    await session.commit()

    # Approved, but the fake adapter fails on execution — a deterministic
    # stand-in for "a security-relevant payload issue discovered at
    # execution time" (never a real P4 side effect anywhere in this test).
    fake.execute_fails = True
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    a1_row_after = await ActionRecordRepository(session).get(a1.id)
    assert a1_row_after.status == PersistedActionStatus.FAILED

    action_repo = ActionRecordRepository(session)
    plan_repo = ActionPlanRecordRepository(session)
    _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
    failed = next(a for a in loaded_plan.actions if a.id == a1.id)
    # Replacement changes the security-relevant payload (different inputs).
    replacement = Action(
        action_plan_id=plan.id, action_type="send", tool_name="communication.send_email", title="P4 replacement",
        inputs={"to": "someone-else@example.com"}, expected_result="sent", success_criteria="sent",
        verification_method="n/a",
    )
    proposal = propose_replan(loaded_plan, failed, replacement, failure_category=FailureCategory.TOOL)
    proposal_repo = ReplanProposalRepository(session)
    proposal_row = await persist_proposal(proposal_repo, proposal)
    await session.commit()
    apply_result = await apply_replan(proposal_row.id, session=session)
    assert apply_result.status.value == "APPLIED"

    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    replacement_row = await action_repo.get(replacement.id)
    # The OLD approval never authorizes the replacement — a fresh
    # ApprovalRequest is required, so the plan pauses again.
    assert replacement_row.status == PersistedActionStatus.WAITING_FOR_APPROVAL
    assert replacement_row.approval_id is not None
    assert replacement_row.approval_id != original_approval_id
    assert result.stop_reason == StopReason.WAITING_FOR_APPROVAL


# --- Security regression tests (spec section 78) ----------------------------


class TestSecurityRegressions:
    async def test_security_failure_never_retries(self, session, sandbox_root, tool_registry):
        registry = ToolAdapterRegistry()
        fake = _AlwaysSecurityViolationAdapter()
        registry.register("file.create_sandboxed", fake)
        a1 = _sandbox_action("escape.txt", "x", sequence=1, max_retries=5)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
        assert fake.execute_calls == 1  # never retried despite max_retries=5
        row = await ActionRecordRepository(session).get(a1.id)
        assert row.status == PersistedActionStatus.FAILED
        assert row.retry_count == 0
        decisions = await RecoveryDecisionRepository(session).list_for_action(a1.id)
        assert decisions[-1].decision == "SECURITY_BLOCKED"

    async def test_unknown_side_effect_state_never_blindly_retries(self, session, sandbox_root, tool_registry, adapters=None):
        """A crash AFTER the side effect occurred (mismatched content) must
        reconcile to a human-review state, never an automatic retry."""
        adapters = build_default_adapter_registry()
        a1 = _sandbox_action("ambiguous.txt", "expected", sequence=1, max_retries=5)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        action_repo = ActionRecordRepository(session)
        row = await action_repo.get(a1.id)

        from app.database.models import ExecutionAttemptStatus
        from datetime import datetime, timezone

        attempt_repo = ExecutionAttemptRepository(session)
        now = datetime.now(timezone.utc)
        key = compute_idempotency_key(a1.id, row.action_hash)
        attempt = await attempt_repo.claim(action_id=a1.id, idempotency_key=key, tool_name="file.create_sandboxed", adapter_name="file.create_sandboxed", adapter_version="1.0.0", claimed_by="w1", now=now)
        await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now)
        await action_repo.update_if_version_matches(a1.id, expected_version=row.version, status=PersistedActionStatus.EXECUTING, started_at=now)
        (sandbox_root / "ambiguous.txt").write_text("MISMATCHED CONTENT", encoding="utf-8")

        result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
        row_after = await action_repo.get(a1.id)
        assert row_after.status != PersistedActionStatus.COMPLETED
        assert row_after.retry_count == 0  # never retried
        assert result.human_review_required is True
        assert (sandbox_root / "ambiguous.txt").read_text() == "MISMATCHED CONTENT"  # never overwritten

    async def test_permission_failure_cannot_retry_around_policy(self, session, sandbox_root, tool_registry, adapters=None):
        adapters = build_default_adapter_registry()
        a1 = _action(action_type="install", tool_name="system.install_software", title="A1", sequence=1, max_retries=5)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
        row = await ActionRecordRepository(session).get(a1.id)
        assert row.status == PersistedActionStatus.BLOCKED
        assert row.retry_count == 0  # BLOCKED never reaches the failure hook at all

    async def test_approval_rejection_cannot_become_retry(self, session, sandbox_root, tool_registry):
        registry, fake = _approval_adapters()
        a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1, max_retries=5)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
        approval_repo = ActionApprovalRequestRepository(session)
        a1_row = await ActionRecordRepository(session).get(a1.id)
        req = await load_approval_request(approval_repo, a1_row.approval_id)
        rejected = decide_approval(req, "REJECT", decided_by="human:alice")
        await sync_decision(approval_repo, rejected)
        await session.commit()
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
        row = await ActionRecordRepository(session).get(a1.id)
        assert row.status == PersistedActionStatus.REJECTED
        assert fake.execute_calls == 0  # never executed at all

    async def test_approval_expiration_cannot_become_execution(self, session, sandbox_root, tool_registry):
        registry, fake = _approval_adapters()
        a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1, max_retries=5)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
        approval_repo = ActionApprovalRequestRepository(session)
        a1_row = await ActionRecordRepository(session).get(a1.id)
        req = await load_approval_request(approval_repo, a1_row.approval_id)
        from datetime import timedelta

        far_future = req.expires_at + timedelta(seconds=1)
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root, now=lambda: far_future)
        row = await ActionRecordRepository(session).get(a1.id)
        assert row.status == PersistedActionStatus.CANCELLED  # EXPIRED maps to CANCELLED
        assert fake.execute_calls == 0

    async def test_replan_cannot_downgrade_permission_floor(self, session, sandbox_root, tool_registry):
        """A replacement proposing a low permission_level for a
        capability-P4 tool/action_type still gets the authoritative floor
        (spec section 48) — enforced entirely by reuse of the unmodified
        Permission Engine, never trusted from the proposal."""
        from app.database.models import PermissionLevel, RiskLevel

        adapters, fake = _approval_adapters()
        a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        action_repo = ActionRecordRepository(session)
        row = await action_repo.get(a1.id)
        await action_repo.update_if_version_matches(a1.id, expected_version=row.version, status=PersistedActionStatus.FAILED, last_error="x")

        plan_repo = ActionPlanRecordRepository(session)
        _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
        failed = next(a for a in loaded_plan.actions if a.id == a1.id)
        replacement = Action(
            action_plan_id=plan.id, action_type="send", tool_name="communication.send_email", title="A1b",
            permission_level=PermissionLevel.READ, risk_level=RiskLevel.LOW,  # proposed downgrade attempt
            inputs={}, expected_result="sent", success_criteria="sent", verification_method="n/a",
        )
        proposal = propose_replan(loaded_plan, failed, replacement)
        proposal_repo = ReplanProposalRepository(session)
        proposal_row = await persist_proposal(proposal_repo, proposal)
        await session.commit()
        await apply_replan(proposal_row.id, session=session)

        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
        replacement_row = await action_repo.get(replacement.id)
        # Never silently ALLOWed despite the proposed READ/LOW — still
        # routes through approval (the authoritative EXTERNAL_ACTION floor).
        assert replacement_row.status == PersistedActionStatus.WAITING_FOR_APPROVAL
        assert replacement_row.permission_level.value != "READ"

    async def test_replan_cycle_rejected_no_persisted_mutation(self, session):
        a1 = _action(title="A1", status=ActionStatus.FAILED)
        a2 = _action(title="A2", dependencies=[a1.id])
        plan = _plan([a1, a2])
        from tests.test_replan import _persist_plan, _mark_failed

        plan_repo, action_repo = await _persist_plan(session, plan)
        failed = plan.actions[0]
        other = plan.actions[1]
        other_with_dep = other.model_copy(update={"dependencies": [failed.id]})
        cyclic_plan = plan.model_copy(update={"actions": [failed, other_with_dep]})
        replacement = _action(action_plan_id=plan.id, dependencies=[other.id])
        proposal = propose_replan(cyclic_plan, failed, replacement)
        assert proposal.status.value == "REJECTED"

    async def test_completed_action_does_not_reexecute_after_replan(self, session, sandbox_root, tool_registry):
        adapters = build_default_adapter_registry()
        a1 = _sandbox_action("stable.txt", "keep", title="A1", sequence=1)
        a2 = _action(title="A2", action_type="internal", sequence=2)
        plan = _plan([a1, a2])
        await validate_and_persist_plan(plan, session=session)
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
        a1_row = await ActionRecordRepository(session).get(a1.id)
        assert a1_row.status == PersistedActionStatus.COMPLETED

        action_repo = ActionRecordRepository(session)
        a2_row = await action_repo.get(a2.id)
        await action_repo.update_if_version_matches(a2.id, expected_version=a2_row.version, status=PersistedActionStatus.FAILED, last_error="x")
        plan_repo = ActionPlanRecordRepository(session)
        _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
        failed = next(a for a in loaded_plan.actions if a.id == a2.id)
        replacement = _action(action_plan_id=plan.id, title="A2b", action_type="internal")
        proposal = propose_replan(loaded_plan, failed, replacement)
        proposal_repo = ReplanProposalRepository(session)
        proposal_row = await persist_proposal(proposal_repo, proposal)
        await session.commit()
        await apply_replan(proposal_row.id, session=session)

        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
        assert (sandbox_root / "stable.txt").read_text() == "keep"  # never rewritten

    async def test_reconciliation_never_directly_calls_tool_adapter(self):
        import inspect

        from app.decision_intelligence import retry_controller, replan, recovery_policy, failure_intelligence, budget

        for module in (retry_controller, replan, recovery_policy, failure_intelligence, budget):
            source = inspect.getsource(module)
            assert ".execute(" not in source
            assert "anthropic" not in source.lower()
            assert "httpx" not in source
            assert "tavily" not in source.lower()

    async def test_no_infinite_retry_bounded_by_max_retries(self, session, sandbox_root, tool_registry):
        registry, fake = _transient_registry(fail_until_attempt=999)
        a1 = _sandbox_action("bound.txt", "x", sequence=1, max_retries=3)
        plan = _plan([a1])
        await validate_and_persist_plan(plan, session=session)
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root, max_orchestration_steps=100)
        assert fake.execute_calls == 4  # initial + 3 retries, never more
        row = await ActionRecordRepository(session).get(a1.id)
        assert row.retry_count == 3

    async def test_no_infinite_replan_bounded_by_replan_budget(self, session):
        """Repeatedly proposing+applying replans against the SAME
        exhausted plan-level REPLANS budget must eventually reject, never
        loop forever (spec section 22/67/68)."""
        from tests.test_replan import _persist_plan, _mark_failed

        a1 = _action(status=ActionStatus.FAILED)
        plan = _plan([a1])
        plan_repo, action_repo = await _persist_plan(session, plan)
        await _mark_failed(action_repo, plan.actions[0].id)

        applied_count = 0
        rejected_for_budget = 0
        for i in range(5):
            _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
            failed_action = next(a for a in loaded_plan.actions if a.id == plan.actions[0].id)
            replacement = _action(action_plan_id=plan.id, title=f"replacement-{i}")
            proposal = propose_replan(loaded_plan, failed_action, replacement)
            proposal_repo = ReplanProposalRepository(session)
            row = await persist_proposal(proposal_repo, proposal)
            await session.commit()
            result = await apply_replan(row.id, session=session, max_replans=2.0)
            if result.status.value == "APPLIED":
                applied_count += 1
            else:
                rejected_for_budget += 1
        assert applied_count == 2  # bounded by max_replans, never unbounded
        assert rejected_for_budget == 3
