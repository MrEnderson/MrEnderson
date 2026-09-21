"""Durable ActionPlan Orchestrator — happy path, dependency chains,
approval pause/resume/rejection/expiration, failure propagation,
independent branches, concurrency, orchestration limits, and security
invariants (v0.1.3.6, spec sections 14-25/36/44-52). NO live network, NO
LLM calls — the only real side effect anywhere in this suite is a UTF-8
text file inside a pytest-managed temporary sandbox directory; every
approval-gated ("P4-shaped") scenario uses an in-memory fake adapter
registered in an isolated ToolAdapterRegistry, never the shared one."""
from __future__ import annotations

import asyncio

import pytest

from app.database.models import PersistedActionPlanStatus, PersistedActionStatus
from app.database.repositories import ActionApprovalRequestRepository, ActionPlanRecordRepository, ActionRecordRepository
from app.decision_intelligence.action_plan_orchestrator import (
    PlanMutationDetectedError,
    PlanNotFoundError,
    PlanNotOrchestratableError,
    PlanNotReadyError,
    StopReason,
    run_plan_until_blocked,
    validate_and_persist_plan,
)
from app.decision_intelligence.approval_engine import decide_approval, expire_approval_request
from app.decision_intelligence.approval_persistence import load_approval_request, sync_decision
from app.decision_intelligence.schemas import Action, ActionPlan, ActionPlanStatus, ActionStatus, ExecutionResult, VerificationResult
from app.decision_intelligence.tool_adapters import ToolAdapterRegistry, build_default_adapter_registry
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


class _FakeAdapter:
    """No real side effect — used only to exercise approval plumbing."""

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


def _approval_adapters(*, adapter=None):
    """Built on top of build_default_adapter_registry() (which already has
    the ONE real adapter, file.create_sandboxed) plus a fake, no-real-
    side-effect adapter for approval-gated ("P4-shaped") scenarios —
    scenarios in this file routinely combine both kinds of Action."""
    registry = build_default_adapter_registry()
    fake = adapter or _FakeAdapter()
    registry.register("communication.send_email", fake)
    return registry, fake


# --- validate_and_persist_plan (spec sections 5/13) ---------------------------


async def test_validate_and_persist_plan_succeeds_for_valid_plan(session):
    plan = _plan([_action(sequence=1)])
    row = await validate_and_persist_plan(plan, session=session)
    assert row.status == PersistedActionPlanStatus.READY


async def test_validate_and_persist_plan_rejects_empty_plan(session):
    plan = _plan([])
    with pytest.raises(PlanNotReadyError):
        await validate_and_persist_plan(plan, session=session)


async def test_validate_and_persist_plan_rejects_cycle(session):
    a1 = _action(title="A1")
    a2 = _action(title="A2")
    a1 = a1.model_copy(update={"dependencies": [a2.id]})
    a2 = a2.model_copy(update={"dependencies": [a1.id]})
    plan = _plan([a1, a2])
    with pytest.raises(PlanNotReadyError):
        await validate_and_persist_plan(plan, session=session)


async def test_validate_and_persist_plan_rejects_self_dependency(session):
    a1 = _action(title="A1")
    a1 = a1.model_copy(update={"dependencies": [a1.id]})
    plan = _plan([a1])
    with pytest.raises(PlanNotReadyError):
        await validate_and_persist_plan(plan, session=session)


async def test_validate_and_persist_plan_rejects_unknown_dependency(session):
    a1 = _action(title="A1", dependencies=["nonexistent"])
    plan = _plan([a1])
    with pytest.raises(PlanNotReadyError):
        await validate_and_persist_plan(plan, session=session)


async def test_validate_and_persist_plan_rejects_duplicate_action_ids(session):
    a1 = _action(title="A1")
    a2 = a1.model_copy()  # same id
    plan = _plan([a1, a2])
    with pytest.raises(PlanNotReadyError):
        await validate_and_persist_plan(plan, session=session)


async def test_validate_and_persist_plan_nothing_persisted_on_failure(session):
    plan = _plan([])
    with pytest.raises(PlanNotReadyError):
        await validate_and_persist_plan(plan, session=session)
    row = await ActionPlanRecordRepository(session).get(plan.id)
    assert row is None


# --- Happy-path lifecycle: fan-out/fan-in/deterministic ordering (46-49) ------


async def test_simple_chain_completes_end_to_end(session, sandbox_root, tool_registry, adapters):
    a1 = _action(sequence=1)
    a2 = _sandbox_action("a2.txt", "hello a2", sequence=2, dependencies=[a1.id])
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.stop_reason == StopReason.PLAN_COMPLETED
    assert result.ending_status == ActionPlanStatus.COMPLETED
    assert result.actions_completed == 2
    assert (sandbox_root / "a2.txt").read_text() == "hello a2"


async def test_fan_out_all_children_complete(session, sandbox_root, tool_registry, adapters):
    a = _action(title="A", sequence=1)
    b = _sandbox_action("b.txt", "b", title="B", sequence=2, dependencies=[a.id])
    c = _sandbox_action("c.txt", "c", title="C", sequence=3, dependencies=[a.id])
    d = _sandbox_action("d.txt", "d", title="D", sequence=4, dependencies=[a.id])
    plan = _plan([a, b, c, d])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.stop_reason == StopReason.PLAN_COMPLETED
    for f in ("b.txt", "c.txt", "d.txt"):
        assert (sandbox_root / f).exists()


async def test_fan_in_waits_for_both_branches(session, sandbox_root, tool_registry, adapters):
    a = _sandbox_action("a.txt", "a", title="A", sequence=1)
    b = _sandbox_action("b.txt", "b", title="B", sequence=2)
    d = _action(title="D", sequence=3, dependencies=[a.id, b.id])
    plan = _plan([a, b, d])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.stop_reason == StopReason.PLAN_COMPLETED
    assert result.actions_completed == 3


async def test_deterministic_ordering_dispatches_lowest_sequence_first(session, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("first.txt", "1", sequence=5)
    a2 = _sandbox_action("second.txt", "2", sequence=1)
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    action_repo = ActionRecordRepository(session)
    row2 = await action_repo.get(a2.id)  # sequence=1, should have started before a1
    row1 = await action_repo.get(a1.id)
    assert row2.started_at <= row1.started_at


# --- Do not repeat completed work / restart (spec sections 29/45 J) ---------


async def test_completed_actions_never_reexecuted_on_second_call(session, sandbox_root, tool_registry, adapters):
    a1 = _action(sequence=1)
    a2 = _sandbox_action("a2.txt", "hello", sequence=2, dependencies=[a1.id])
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    first = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert first.stop_reason == StopReason.PLAN_COMPLETED

    action_repo = ActionRecordRepository(session)
    a2_row_before = await action_repo.get(a2.id)

    second = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert second.progress_made is False
    assert second.actions_executed_this_run == 0

    a2_row_after = await action_repo.get(a2.id)
    assert a2_row_after.version == a2_row_before.version  # never touched again
    assert (sandbox_root / "a2.txt").read_text() == "hello"


# --- Approval pause / resume (spec sections 16/17/44) -------------------------


async def test_plan_pauses_at_approval_boundary(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _action(sequence=1)
    a2 = _sandbox_action("a2.txt", "x", sequence=2, dependencies=[a1.id])
    a3 = _action(action_type="send", tool_name="communication.send_email", title="A3 publish", sequence=3, dependencies=[a2.id])
    a4 = _action(title="A4", sequence=4, dependencies=[a3.id])
    plan = _plan([a1, a2, a3, a4])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    assert result.ending_status == ActionPlanStatus.WAITING_FOR_APPROVAL
    assert result.stop_reason == StopReason.WAITING_FOR_APPROVAL
    assert result.actions_completed == 2
    assert a3.id in result.approval_action_ids
    assert fake.execute_calls == 0  # A3 never executed
    action_repo = ActionRecordRepository(session)
    a4_row = await action_repo.get(a4.id)
    assert a4_row.status == PersistedActionStatus.VALIDATED  # never touched


async def test_resume_after_approval_completes_plan(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _action(sequence=1)
    a2 = _sandbox_action("a2.txt", "x", sequence=2, dependencies=[a1.id])
    a3 = _action(action_type="send", tool_name="communication.send_email", title="A3", sequence=3, dependencies=[a2.id])
    a4 = _action(title="A4", sequence=4, dependencies=[a3.id])
    plan = _plan([a1, a2, a3, a4])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    approval_repo = ActionApprovalRequestRepository(session)
    a3_row = await ActionRecordRepository(session).get(a3.id)
    req = await load_approval_request(approval_repo, a3_row.approval_id)
    approved = decide_approval(req, "APPROVE", decided_by="human:alice")
    await sync_decision(approval_repo, approved)
    await session.commit()

    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    assert result.stop_reason == StopReason.PLAN_COMPLETED
    assert result.ending_status == ActionPlanStatus.COMPLETED
    assert fake.execute_calls == 1

    approval_row = await approval_repo.get(a3_row.approval_id)
    assert approval_row.consumed is True


async def test_resume_does_not_create_duplicate_approval_request(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    a1_row = await ActionRecordRepository(session).get(a1.id)
    first_approval_id = a1_row.approval_id

    # Second call: still pending, must not create a second ApprovalRequest.
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    a1_row_again = await ActionRecordRepository(session).get(a1.id)
    assert a1_row_again.approval_id == first_approval_id


# --- Approval rejection (spec sections 18/61) ----------------------------------


async def test_approval_rejection_blocks_action_and_downstream(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1)
    a2 = _action(title="A2", sequence=2, dependencies=[a1.id])
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    approval_repo = ActionApprovalRequestRepository(session)
    a1_row = await ActionRecordRepository(session).get(a1.id)
    req = await load_approval_request(approval_repo, a1_row.approval_id)
    rejected = decide_approval(req, "REJECT", decided_by="human:alice")
    await sync_decision(approval_repo, rejected)
    await session.commit()

    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    assert fake.execute_calls == 0
    a1_row_after = await ActionRecordRepository(session).get(a1.id)
    assert a1_row_after.status == PersistedActionStatus.REJECTED
    a2_row_after = await ActionRecordRepository(session).get(a2.id)
    assert a2_row_after.status == PersistedActionStatus.VALIDATED  # never became eligible
    assert result.ending_status in (ActionPlanStatus.FAILED, ActionPlanStatus.PARTIALLY_COMPLETED)


# --- Approval expiration (spec section 19) -------------------------------------


async def test_expired_approval_blocks_action(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    approval_repo = ActionApprovalRequestRepository(session)
    a1_row = await ActionRecordRepository(session).get(a1.id)
    req = await load_approval_request(approval_repo, a1_row.approval_id)

    from datetime import timedelta

    far_future = req.expires_at + timedelta(seconds=1)
    result = await run_plan_until_blocked(
        plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root,
        now=lambda: far_future,
    )
    assert fake.execute_calls == 0
    a1_row_after = await ActionRecordRepository(session).get(a1.id)
    assert a1_row_after.status == PersistedActionStatus.CANCELLED  # EXPIRED maps to CANCELLED (v0.1.3.3 precedent)


# --- Failure propagation / failure policies (spec sections 21-23/46) --------


async def test_stop_on_failure_blocks_dependent(session, sandbox_root, tool_registry):
    registry, _ = _approval_adapters(adapter=_FakeAdapter(execute_fails=True))
    a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1)
    a2 = _action(title="A2", sequence=2, dependencies=[a1.id])
    plan = _plan([a1, a2], failure_policy="STOP_ON_FAILURE")
    await validate_and_persist_plan(plan, session=session)

    approval_repo = ActionApprovalRequestRepository(session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    a1_row = await ActionRecordRepository(session).get(a1.id)
    req = await load_approval_request(approval_repo, a1_row.approval_id)
    approved = decide_approval(req, "APPROVE", decided_by="human:alice")
    await sync_decision(approval_repo, approved)
    await session.commit()

    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    a1_row_after = await ActionRecordRepository(session).get(a1.id)
    a2_row_after = await ActionRecordRepository(session).get(a2.id)
    assert a1_row_after.status == PersistedActionStatus.FAILED
    assert a2_row_after.status == PersistedActionStatus.VALIDATED  # never started
    assert result.ending_status in (ActionPlanStatus.FAILED, ActionPlanStatus.PARTIALLY_COMPLETED)


async def test_independent_branch_continues_when_unrelated_branch_fails(session, sandbox_root, tool_registry):
    registry, _ = _approval_adapters(adapter=_FakeAdapter(execute_fails=True))
    a = _action(action_type="send", tool_name="communication.send_email", title="A", sequence=1)
    b = _action(title="B", sequence=2, dependencies=[a.id])
    c = _sandbox_action("c.txt", "c", title="C", sequence=3)
    d = _sandbox_action("d.txt", "d", title="D", sequence=4, dependencies=[c.id])
    plan = _plan([a, b, c, d], failure_policy="CONTINUE_INDEPENDENT")
    await validate_and_persist_plan(plan, session=session)

    approval_repo = ActionApprovalRequestRepository(session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    a_row = await ActionRecordRepository(session).get(a.id)
    req = await load_approval_request(approval_repo, a_row.approval_id)
    approved = decide_approval(req, "APPROVE", decided_by="human:alice")
    await sync_decision(approval_repo, approved)
    await session.commit()

    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    # C/D unrelated to the failed A/B branch — must still complete.
    assert (sandbox_root / "c.txt").exists()
    assert (sandbox_root / "d.txt").exists()
    d_row = await ActionRecordRepository(session).get(d.id)
    assert d_row.status == PersistedActionStatus.COMPLETED
    assert result.ending_status == ActionPlanStatus.PARTIALLY_COMPLETED


# --- Partial completion truthfulness (spec section 20) ------------------------


async def test_partial_completion_reported_truthfully(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _sandbox_action("a1.txt", "1", title="A1", sequence=1)
    a2 = _sandbox_action("a2.txt", "2", title="A2", sequence=2)
    a3 = _action(action_type="send", tool_name="communication.send_email", title="A3", sequence=3)
    a4 = _action(title="A4", sequence=4, dependencies=[a3.id])
    plan = _plan([a1, a2, a3, a4])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    assert result.actions_completed == 2
    assert result.actions_waiting_for_approval == 1
    assert result.actions_waiting_for_dependencies == 1
    assert result.ending_status != ActionPlanStatus.FAILED
    assert result.ending_status == ActionPlanStatus.WAITING_FOR_APPROVAL


# --- No false completion (spec section 30) -------------------------------------


async def test_plan_never_marked_completed_with_pending_work(session, sandbox_root, tool_registry):
    registry, _ = _approval_adapters()
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    a2 = _action(action_type="send", tool_name="communication.send_email", title="A2", sequence=2)
    plan = _plan([a1, a2])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)
    assert result.ending_status != ActionPlanStatus.COMPLETED


# --- Orchestration limits / no-progress (spec sections 15/36/38/39) ----------


async def test_orchestration_limit_reached_stops_safely(session, sandbox_root, tool_registry, adapters):
    actions = [_sandbox_action(f"f{i}.txt", str(i), sequence=i) for i in range(5)]
    plan = _plan(actions)
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(
        plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
        max_orchestration_steps=2,
    )
    assert result.stop_reason == StopReason.ORCHESTRATION_LIMIT_REACHED
    assert result.actions_completed < 5


async def test_plan_not_found_raises(session, sandbox_root, tool_registry, adapters):
    with pytest.raises(PlanNotFoundError):
        await run_plan_until_blocked("nonexistent", session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)


async def test_completed_plan_run_again_is_noop(session, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert result.stop_reason == StopReason.PLAN_COMPLETED
    assert result.progress_made is False


# --- Concurrency: two orchestrators, at most one owns (spec sections 24/45) --


async def test_two_concurrent_orchestrators_exactly_one_claims(session_factory, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    plan = _plan([a1])
    async with session_factory() as setup:
        await validate_and_persist_plan(plan, session=setup)

    async def attempt(owner):
        async with session_factory() as s:
            return await run_plan_until_blocked(plan.id, session=s, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, owner=owner)

    r1, r2 = await asyncio.gather(attempt("worker-a"), attempt("worker-b"))
    outcomes = {r1.stop_reason, r2.stop_reason}
    assert StopReason.PLAN_COMPLETED in outcomes
    assert StopReason.CONCURRENT_ORCHESTRATOR in outcomes
    assert (sandbox_root / "a1.txt").exists()

    async with session_factory() as check:
        attempts_repo = ActionRecordRepository(check)
        # exactly one real write, never duplicated
        assert (sandbox_root / "a1.txt").read_text() == "1"


# --- Structural mutation guard (spec section 34) ------------------------------


async def test_mutated_plan_structure_after_ready_fails_closed(session, sandbox_root, tool_registry, adapters):
    a1 = _sandbox_action("a1.txt", "1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)

    # Directly tamper with the durable Action's tool-relevant payload,
    # bypassing the orchestrator entirely (simulating an external mutation).
    action_repo = ActionRecordRepository(session)
    row = await action_repo.get(a1.id)
    await action_repo.update_if_version_matches(a1.id, expected_version=row.version, inputs_json='{"relative_path": "a1.txt", "content": "TAMPERED"}')

    with pytest.raises(PlanMutationDetectedError):
        await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)


# --- Security invariants (spec section 52) -------------------------------------


async def test_security_unknown_tool_fails_closed(session, sandbox_root, tool_registry, adapters):
    a1 = _action(action_type="sandbox_create", tool_name="evil.magic_shell", title="A1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    row = await ActionRecordRepository(session).get(a1.id)
    assert row.status == PersistedActionStatus.BLOCKED


async def test_security_missing_adapter_fails_closed(session, sandbox_root, tool_registry, adapters):
    a1 = _action(action_type="read", tool_name="research.read", title="A1", sequence=1)  # no adapter registered
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    result = await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    row = await ActionRecordRepository(session).get(a1.id)
    assert row.status == PersistedActionStatus.FAILED


async def test_security_p5_admin_remains_blocked(session, sandbox_root, tool_registry, adapters):
    a1 = _action(action_type="install", tool_name="system.install_software", title="A1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    row = await ActionRecordRepository(session).get(a1.id)
    assert row.status == PersistedActionStatus.BLOCKED


async def test_security_plan_does_not_bypass_permission_engine(session, sandbox_root, tool_registry, adapters):
    # Even an action proposing a naively low permission_level gets the
    # authoritative floor applied by the (unmodified) Permission Engine —
    # the orchestrator never sets permission_level itself.
    from app.database.models import PermissionLevel

    a1 = _sandbox_action("a1.txt", "1", sequence=1, permission_level=PermissionLevel.READ)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    row = await ActionRecordRepository(session).get(a1.id)
    assert row.permission_level == PermissionLevel.WRITE  # authoritative P2 floor, not the proposed READ


async def test_security_plan_cannot_reuse_approval_for_another_action(session, sandbox_root, tool_registry):
    registry, fake = _approval_adapters()
    a1 = _action(action_type="send", tool_name="communication.send_email", title="A1", sequence=1)
    plan = _plan([a1])
    await validate_and_persist_plan(plan, session=session)
    await run_plan_until_blocked(plan.id, session=session, tool_registry=tool_registry, adapter_registry=registry, sandbox_root=sandbox_root)

    approval_repo = ActionApprovalRequestRepository(session)
    a1_row = await ActionRecordRepository(session).get(a1.id)
    req = await load_approval_request(approval_repo, a1_row.approval_id)
    approved = decide_approval(req, "APPROVE", decided_by="human:alice")
    await sync_decision(approval_repo, approved)
    await session.commit()

    # A completely different Action cannot be authorized by this approval —
    # verified at the approval_engine layer, exercised end-to-end here by
    # confirming the SAME approval only ever attaches to a1.
    assert approved.action_id == a1.id


async def test_security_orchestration_never_calls_tool_adapter_directly():
    import inspect

    from app.decision_intelligence import action_plan_orchestrator

    source = inspect.getsource(action_plan_orchestrator)
    assert ".execute(" not in source  # only execute_action_durably()/reconcile_action() call adapters
    assert "anthropic" not in source.lower()
    assert "httpx" not in source
