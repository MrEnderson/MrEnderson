"""The durable Action Executor — lifecycle, duplicate handling, atomic
claiming, and durable persistence at every checkpoint (v0.1.3.5, spec
sections 3/12/13/22/24). NO live network, NO LLM calls — the only real
side effect anywhere in this suite is a UTF-8 text file inside a
pytest-managed temporary sandbox directory."""
from __future__ import annotations

import asyncio

import pytest

from app.database.models import ExecutionAttemptStatus, PersistedActionStatus, ResultProvenance
from app.database.repositories import (
    ActionRecordRepository,
    ExecutionAttemptRepository,
    ExecutionResultRepository,
    VerificationResultRepository,
)
from app.decision_intelligence.action_executor import ActionDecisionMismatchError
from app.decision_intelligence.approval_engine import (
    advance_to_waiting_for_approval,
    authorize_action,
    create_approval_request,
    decide_approval,
)
from app.decision_intelligence.approval_persistence import persist_new_approval_request, sync_decision
from app.decision_intelligence.durable_action_executor import execute_action_durably
from app.decision_intelligence.permission_engine import (
    PermissionOutcome,
    apply_permission_decision,
    evaluate_permission,
)
from app.decision_intelligence.schemas import Action, ActionStatus, ExecutionResult, VerificationResult
from app.decision_intelligence.tool_adapters import ExecutionContext, ToolAdapterRegistry, build_default_adapter_registry
from app.decision_intelligence.tool_registry import build_default_tool_registry
from app.database.repositories import ActionApprovalRequestRepository


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


def _p2_action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="sandbox_create", tool_name="file.create_sandboxed",
        title="Write a note", inputs={"relative_path": "note.txt", "content": "hello durable"},
        expected_result="a sandbox file is created", status=ActionStatus.VALIDATED,
    )
    fields.update(overrides)
    return Action(**fields)


def _permission_checked_p2(**overrides):
    registry = build_default_tool_registry()
    action = _p2_action(**overrides)
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    return checked, decision, registry


class _FakeAdapter:
    name = "communication.send_email"
    version = "0.0.1-fake"

    def __init__(self, *, execute_fails=False, verify_fails=False):
        self.execute_fails = execute_fails
        self.verify_fails = verify_fails
        self.execute_calls = 0

    async def execute(self, action, context):
        self.execute_calls += 1
        now = context.now()
        if self.execute_fails:
            from app.decision_intelligence.schemas import FailureCategory

            return ExecutionResult(action_id=action.id, tool_name=self.name, started_at=now, completed_at=now, success=False, error_type=FailureCategory.TOOL, error_code="TOOL_EXECUTION_FAILURE", error_message="fake failure")
        return ExecutionResult(action_id=action.id, tool_name=self.name, started_at=now, completed_at=now, success=True, output={"ok": True}, side_effect_occurred=False)

    async def verify(self, action, execution_result, context):
        now = context.now()
        if self.verify_fails:
            return VerificationResult(action_id=action.id, method="fake", passed=False, confidence=0.0, issues=["fake"], verified_at=now)
        return VerificationResult(action_id=action.id, method="fake", passed=True, confidence=1.0, verified_at=now)


# --- Happy path lifecycle -------------------------------------------------------


async def test_p2_action_executes_and_persists_durably(session, sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    outcome = await execute_action_durably(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root, session=session)
    assert outcome.action.status == ActionStatus.COMPLETED

    action_row = await ActionRecordRepository(session).get(checked.id)
    assert action_row.status == PersistedActionStatus.COMPLETED

    attempts = await ExecutionAttemptRepository(session).list_for_action(checked.id)
    assert len(attempts) == 1
    assert attempts[0].status == ExecutionAttemptStatus.VERIFIED
    assert attempts[0].side_effect_occurred is True
    assert attempts[0].side_effect_fingerprint is not None

    exec_result_row = await ExecutionResultRepository(session).get_by_attempt(attempts[0].id)
    assert exec_result_row.success is True
    assert exec_result_row.provenance == ResultProvenance.ORIGINAL

    verify_result_row = await VerificationResultRepository(session).get_by_attempt(attempts[0].id)
    assert verify_result_row.passed is True
    assert verify_result_row.provenance == ResultProvenance.ORIGINAL

    assert (sandbox_root / "note.txt").read_text() == "hello durable"


async def test_decision_action_id_mismatch_raises(session, sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    mismatched = decision.model_copy(update={"action_id": "wrong-id"})
    with pytest.raises(ActionDecisionMismatchError):
        await execute_action_durably(checked, mismatched, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root, session=session)


# --- Duplicate execution (spec section 22) --------------------------------------


async def test_duplicate_execution_request_never_reexecutes(session, sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    adapters = build_default_adapter_registry()
    first = await execute_action_durably(checked, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=session)
    assert first.action.status == ActionStatus.COMPLETED

    second = await execute_action_durably(checked, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=session)
    assert second.action.status == ActionStatus.COMPLETED
    assert second.execution_result is None

    attempts = await ExecutionAttemptRepository(session).list_for_action(checked.id)
    assert len(attempts) == 1  # no second attempt row was ever created
    assert (sandbox_root / "note.txt").read_text() == "hello durable"


# --- BLOCK / permission -----------------------------------------------------------


async def test_block_permission_cannot_execute_durably(session, sandbox_root):
    registry = build_default_tool_registry()
    action = Action(action_plan_id="plan-1", action_type="privileged", tool_name="system.privileged_shell", title="x", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    checked = apply_permission_decision(action, decision)
    outcome = await execute_action_durably(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root, session=session)
    assert outcome.execution_result.success is False
    assert outcome.action.status == ActionStatus.BLOCKED


# --- Approval-gated durable execution + atomic consumption --------------------


async def _durable_approval_gated(session, *, adapter=None):
    tool_registry = build_default_tool_registry()
    adapter_registry = ToolAdapterRegistry()
    fake = adapter or _FakeAdapter()
    adapter_registry.register("communication.send_email", fake)
    approval_repo = ActionApprovalRequestRepository(session)

    action = Action(action_plan_id="plan-1", action_type="send", tool_name="communication.send_email", title="x", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, tool_registry)
    checked = apply_permission_decision(action, decision)

    in_memory_request = create_approval_request(checked, decision, requested_by="planner-agent")
    persisted = await persist_new_approval_request(approval_repo, in_memory_request)
    await session.commit()

    waiting = advance_to_waiting_for_approval(checked)
    approved_request = decide_approval(persisted, "APPROVE", decided_by="human:alice")
    await sync_decision(approval_repo, approved_request)
    await session.commit()

    approved_action = authorize_action(waiting, approved_request)
    return approved_action, decision, approved_request, tool_registry, adapter_registry, fake, approval_repo


async def test_durable_approval_gated_execution_completes_and_consumes(session, sandbox_root):
    action, decision, request, tool_registry, adapters, fake, approval_repo = await _durable_approval_gated(session)
    outcome = await execute_action_durably(action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=session, approval_request=request, approval_repo=approval_repo)
    assert outcome.action.status == ActionStatus.COMPLETED
    row = await approval_repo.get(request.id)
    assert row.consumed is True


async def test_durable_approval_cannot_be_consumed_twice(session, sandbox_root):
    action, decision, request, tool_registry, adapters, fake, approval_repo = await _durable_approval_gated(session)
    first = await execute_action_durably(action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=session, approval_request=request, approval_repo=approval_repo)
    assert first.action.status == ActionStatus.COMPLETED

    second = await execute_action_durably(action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=session, approval_request=request, approval_repo=approval_repo)
    assert second.action.status == ActionStatus.COMPLETED
    assert second.execution_result is None  # duplicate-completed short circuit — no re-execution attempted
    assert fake.execute_calls == 1


# --- Concurrent execution claims for the same Action (spec sections 24/38) ---


async def test_two_concurrent_execute_calls_exactly_one_claims(session_factory, sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    adapters = build_default_adapter_registry()

    async def attempt():
        async with session_factory() as s:
            outcome = await execute_action_durably(checked, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=s)
            return outcome

    outcomes = await asyncio.gather(attempt(), attempt())
    statuses = [o.action.status for o in outcomes]
    assert ActionStatus.COMPLETED in statuses
    # Exactly one real write occurred — file content is untouched/singular.
    assert (sandbox_root / "note.txt").read_text() == "hello durable"

    async with session_factory() as check:
        attempts = await ExecutionAttemptRepository(check).list_for_action(checked.id)
        assert len(attempts) == 1


# --- Failure / verification-failure handling -------------------------------------


async def test_execution_failure_marks_action_failed_durably(session, sandbox_root):
    action, decision, request, tool_registry, adapters, fake, approval_repo = await _durable_approval_gated(session, adapter=_FakeAdapter(execute_fails=True))
    outcome = await execute_action_durably(action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=session, approval_request=request, approval_repo=approval_repo)
    assert outcome.action.status == ActionStatus.FAILED
    row = await ActionRecordRepository(session).get(action.id)
    assert row.status == PersistedActionStatus.FAILED


async def test_verification_failure_prevents_completed_durably(session, sandbox_root):
    action, decision, request, tool_registry, adapters, fake, approval_repo = await _durable_approval_gated(session, adapter=_FakeAdapter(verify_fails=True))
    outcome = await execute_action_durably(action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, session=session, approval_request=request, approval_repo=approval_repo)
    assert outcome.action.status == ActionStatus.FAILED
    assert outcome.action.status != ActionStatus.COMPLETED
    row = await ActionRecordRepository(session).get(action.id)
    assert row.status != PersistedActionStatus.COMPLETED


# --- No LLM / no network ---------------------------------------------------------


async def test_durable_executor_performs_no_llm_or_network_call():
    import inspect

    from app.decision_intelligence import durable_action_executor

    source = inspect.getsource(durable_action_executor)
    assert "anthropic" not in source.lower()
    assert "openai" not in source.lower()
    assert "httpx" not in source
    assert "requests." not in source
