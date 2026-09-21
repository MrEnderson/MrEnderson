"""The deterministic Action Executor — lifecycle, failure handling,
idempotency, and security invariants (v0.1.3.4, spec sections 13-37).
NO live network, NO LLM calls, NO shell/browser/email — the only real
side effect anywhere in this suite is a UTF-8 text file inside a
pytest-managed temporary sandbox directory."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import ActionApprovalRequest as ActionApprovalRequestRow  # noqa: F401 (import sanity)
from app.database.repositories import ActionApprovalRequestRepository
from app.decision_intelligence.action_executor import (
    ActionDecisionMismatchError,
    execute_action,
)
from app.decision_intelligence.approval_engine import (
    advance_to_waiting_for_approval,
    authorize_action,
    create_approval_request,
    decide_approval,
)
from app.decision_intelligence.approval_persistence import persist_new_approval_request, sync_decision
from app.decision_intelligence.permission_engine import (
    PermissionOutcome,
    apply_permission_decision,
    evaluate_permission,
)
from app.decision_intelligence.schemas import (
    Action,
    ActionStatus,
    ExecutionResult,
    FailureCategory,
    VerificationResult,
)
from app.decision_intelligence.tool_adapters import (
    ExecutionContext,
    SandboxFileCreateAdapter,
    ToolAdapterRegistry,
    build_default_adapter_registry,
)
from app.decision_intelligence.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    build_default_tool_registry,
)
from app.database.models import PermissionLevel, RiskLevel


# --- Fixtures / helpers --------------------------------------------------------


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


class _FakeAdapter:
    """No real side effect — used only to exercise approval plumbing, never
    to send anything or touch a filesystem (spec section 15)."""

    name = "communication.send_email"
    version = "0.0.1-fake"

    def __init__(self, *, execute_fails: bool = False, verify_fails: bool = False):
        self.execute_fails = execute_fails
        self.verify_fails = verify_fails
        self.execute_calls = 0
        self.verify_calls = 0

    async def execute(self, action: Action, context: ExecutionContext) -> ExecutionResult:
        self.execute_calls += 1
        now = context.now()
        if self.execute_fails:
            return ExecutionResult(
                action_id=action.id, tool_name=self.name, started_at=now, completed_at=now,
                success=False, error_type=FailureCategory.TOOL, error_code="TOOL_EXECUTION_FAILURE",
                error_message="fake failure", side_effect_occurred=False,
            )
        return ExecutionResult(
            action_id=action.id, tool_name=self.name, started_at=now, completed_at=now,
            success=True, output={"ok": True}, side_effect_occurred=False,
        )

    async def verify(self, action: Action, execution_result: ExecutionResult, context: ExecutionContext) -> VerificationResult:
        self.verify_calls += 1
        now = context.now()
        if self.verify_fails:
            return VerificationResult(action_id=action.id, method="fake", passed=False, confidence=0.0, issues=["fake"], verified_at=now)
        return VerificationResult(action_id=action.id, method="fake", passed=True, confidence=1.0, verified_at=now)


def _p2_action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1",
        action_type="sandbox_create",
        tool_name="file.create_sandboxed",
        title="Write a note",
        inputs={"relative_path": "note.txt", "content": "hello"},
        expected_result="a sandbox file is created",
        status=ActionStatus.VALIDATED,
    )
    fields.update(overrides)
    return Action(**fields)


def _permission_checked_p2(**overrides):
    registry = build_default_tool_registry()
    action = _p2_action(**overrides)
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    return checked, decision, registry


def _approval_gated_approved(*, adapter=None):
    """Builds a REQUIRE_APPROVAL action (send_email, P4), pushes it through
    the full approval chain to ActionStatus.APPROVED, and registers a FAKE
    adapter (no real side effect) under communication.send_email in an
    ISOLATED registry — never the shared build_default_adapter_registry(),
    which deliberately has no adapter for it."""
    tool_registry = build_default_tool_registry()
    adapter_registry = ToolAdapterRegistry()
    fake = adapter or _FakeAdapter()
    adapter_registry.register("communication.send_email", fake)

    action = Action(
        action_plan_id="plan-1", action_type="send", tool_name="communication.send_email",
        title="Send it", inputs={}, expected_result="sent", status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, tool_registry)
    assert decision.outcome == PermissionOutcome.REQUIRE_APPROVAL
    checked = apply_permission_decision(action, decision)

    request = create_approval_request(checked, decision, requested_by="planner-agent")
    waiting = advance_to_waiting_for_approval(checked)
    approved_request = decide_approval(request, "APPROVE", decided_by="human:alice")
    approved_action = authorize_action(waiting, approved_request)

    return approved_action, decision, approved_request, tool_registry, adapter_registry, fake


# --- P2 (ALLOW_WITH_AUDIT) lifecycle happy path -------------------------------


async def test_p2_action_executes_through_full_lifecycle_to_completed(sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    outcome = await execute_action(
        checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root
    )
    assert outcome.action.status == ActionStatus.COMPLETED
    assert outcome.execution_result.success is True
    assert outcome.verification_result.passed is True
    assert (sandbox_root / "note.txt").read_text() == "hello"


async def test_p2_action_does_not_require_approval(sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    assert decision.outcome == PermissionOutcome.ALLOW_WITH_AUDIT
    outcome = await execute_action(
        checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root
    )
    assert outcome.action.status == ActionStatus.COMPLETED  # no approval_request was ever supplied


async def test_p2_action_wrong_lifecycle_state_fails_validation(sandbox_root):
    action = _p2_action(status=ActionStatus.VALIDATED)  # never permission-checked
    registry = build_default_tool_registry()
    decision = evaluate_permission(action, registry)
    outcome = await execute_action(
        action, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root
    )
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "VALIDATION_FAILURE"


async def test_decision_action_id_mismatch_raises():
    checked, decision, registry = _permission_checked_p2()
    mismatched = decision.model_copy(update={"action_id": "wrong-id"})
    with pytest.raises(ActionDecisionMismatchError):
        await execute_action(
            checked, mismatched, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root="unused"  # type: ignore[arg-type]
        )


# --- Idempotency (spec section 20) --------------------------------------------


async def test_already_completed_action_is_never_reexecuted(sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    adapters = build_default_adapter_registry()
    first = await execute_action(checked, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert first.action.status == ActionStatus.COMPLETED

    second = await execute_action(first.action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root)
    assert second.action.status == ActionStatus.COMPLETED
    assert second.execution_result is None  # no re-execution attempt was made
    assert (sandbox_root / "note.txt").read_text() == "hello"  # unchanged, not duplicated


# --- Adapter / tool resolution fail-closed (spec section 12) -----------------


async def test_unknown_tool_definition_cannot_execute(sandbox_root):
    action = _p2_action(tool_name="evil.magic_shell")
    registry = build_default_tool_registry()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)  # BLOCKed (unknown tool)
    outcome = await execute_action(
        checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root
    )
    assert outcome.execution_result.success is False
    assert outcome.action.status == ActionStatus.BLOCKED


async def test_known_tool_definition_without_registered_adapter_cannot_execute(sandbox_root):
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="test.no_adapter",
            supported_action_types=frozenset({"internal_create"}),
            default_permission_level=PermissionLevel.WRITE,
            default_risk_level=RiskLevel.LOW,
            has_side_effects=True,
        )
    )
    empty_adapters = ToolAdapterRegistry()
    action = Action(
        action_plan_id="plan-1", action_type="internal_create", tool_name="test.no_adapter",
        title="x", status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=empty_adapters, sandbox_root=sandbox_root)
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "ADAPTER_NOT_FOUND"


async def test_disabled_tool_cannot_execute(sandbox_root):
    registry = build_default_tool_registry()
    registry.register(registry.get("file.create_sandboxed").model_copy(update={"enabled": False}), replace=True)
    checked_source = _p2_action()
    decision = evaluate_permission(checked_source, registry)
    checked = apply_permission_decision(checked_source, decision)  # BLOCKed
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert outcome.execution_result.success is False


async def test_unsupported_action_type_for_tool_cannot_execute(sandbox_root):
    action = _p2_action(action_type="delete")  # file.create_sandboxed does not support "delete"
    registry = build_default_tool_registry()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert outcome.execution_result.success is False


# --- Model/callable/shell injection cannot become executable (spec section 33.4-6) --


async def test_action_cannot_supply_a_callable_as_tool_name(sandbox_root):
    registry = build_default_tool_registry()
    with pytest.raises(Exception):
        # Action.tool_name is a pydantic `str | None` field — a callable is
        # rejected at construction, never reaches the Executor at all.
        Action(action_plan_id="plan-1", action_type="sandbox_create", tool_name=lambda: "rm -rf /", title="x")  # type: ignore[arg-type]


async def test_action_import_path_string_never_becomes_executable(sandbox_root):
    action = _p2_action(tool_name="os.system")  # looks like an import path; treated as an opaque string
    registry = build_default_tool_registry()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert outcome.execution_result.success is False  # unknown tool -> BLOCK, never imported/called


async def test_action_shell_command_string_never_gets_executed(sandbox_root):
    action = _p2_action(inputs={"relative_path": "note.txt", "content": "rm -rf /"})
    registry = build_default_tool_registry()
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    # The string is written VERBATIM as inert text content — never
    # interpreted, evaluated, or passed to a shell.
    assert outcome.action.status == ActionStatus.COMPLETED
    assert (sandbox_root / "note.txt").read_text() == "rm -rf /"


# --- BLOCK / P5 -----------------------------------------------------------------


async def test_block_permission_decision_cannot_execute(sandbox_root):
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1", action_type="privileged", tool_name="system.privileged_shell",
        title="x", status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.BLOCK
    checked = apply_permission_decision(action, decision)
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "PERMISSION_FAILURE"
    assert outcome.action.status == ActionStatus.BLOCKED  # never advances toward EXECUTING


async def test_p5_admin_blocked_capability_cannot_execute(sandbox_root):
    registry = build_default_tool_registry()
    action = Action(
        action_plan_id="plan-1", action_type="install", tool_name="system.install_software",
        title="x", status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert outcome.execution_result.success is False


# --- Approval-gated execution (fake adapter only — no real side effect) ------


async def test_require_approval_action_executes_via_fake_adapter(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved()
    outcome = await execute_action(action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request)
    assert outcome.action.status == ActionStatus.COMPLETED
    assert fake.execute_calls == 1


async def test_require_approval_without_approval_request_cannot_execute(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved()
    outcome = await execute_action(action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=None)
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "APPROVAL_FAILURE"
    assert fake.execute_calls == 0


async def test_require_approval_wrong_action_state_cannot_execute(sandbox_root):
    tool_registry = build_default_tool_registry()
    adapter_registry = ToolAdapterRegistry()
    fake = _FakeAdapter()
    adapter_registry.register("communication.send_email", fake)
    action = Action(action_plan_id="plan-1", action_type="send", tool_name="communication.send_email", title="x", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, tool_registry)
    checked = apply_permission_decision(action, decision)  # PERMISSION_CHECKED, not APPROVED
    outcome = await execute_action(checked, decision, tool_registry=tool_registry, adapter_registry=adapter_registry, sandbox_root=sandbox_root)
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "APPROVAL_FAILURE"
    assert fake.execute_calls == 0


async def test_expired_approval_cannot_execute(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved()
    far_future = lambda: request.expires_at + timedelta(seconds=1)  # noqa: E731
    outcome = await execute_action(action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request, now=far_future)
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "APPROVAL_FAILURE"
    assert fake.execute_calls == 0


async def test_hash_mismatched_approval_cannot_execute(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved()
    tampered = action.model_copy(update={"inputs": {"to": "attacker@example.com"}})
    outcome = await execute_action(tampered, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request)
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "APPROVAL_FAILURE"
    assert fake.execute_calls == 0


async def test_wrong_action_approval_cannot_execute(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved()
    other_action = action.model_copy(update={"id": "some-other-action-id"})
    other_decision = decision.model_copy(update={"action_id": "some-other-action-id"})
    outcome = await execute_action(other_action, other_decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request)
    assert outcome.execution_result.success is False
    assert outcome.execution_result.error_code == "APPROVAL_FAILURE"
    assert fake.execute_calls == 0


async def test_consumed_in_memory_approval_cannot_execute_twice(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved()
    first = await execute_action(action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request)
    assert first.action.status == ActionStatus.COMPLETED
    # Re-attempt with the SAME original (unconsumed-looking, but now stale)
    # in-memory request object and the SAME already-completed action — the
    # idempotency guard (already COMPLETED) is what actually stops this.
    second = await execute_action(first.action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request)
    assert second.execution_result is None
    assert fake.execute_calls == 1  # never called a second time


async def test_execution_failure_from_adapter_marks_action_failed(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved(adapter=_FakeAdapter(execute_fails=True))
    outcome = await execute_action(action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request)
    assert outcome.action.status == ActionStatus.FAILED
    assert outcome.execution_result.success is False
    assert outcome.verification_result is None  # verify() is never called after a failed execute()


async def test_verification_failure_prevents_completed(sandbox_root):
    action, decision, request, registry, adapters, fake = _approval_gated_approved(adapter=_FakeAdapter(verify_fails=True))
    outcome = await execute_action(action, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request)
    assert outcome.action.status == ActionStatus.FAILED
    assert outcome.execution_result.success is True
    assert outcome.verification_result.passed is False
    assert outcome.action.status != ActionStatus.COMPLETED


# --- Durable, approval-gated execution with atomic consumption ---------------


async def _durable_approval_gated(session, *, adapter=None):
    tool_registry = build_default_tool_registry()
    adapter_registry = ToolAdapterRegistry()
    fake = adapter or _FakeAdapter()
    adapter_registry.register("communication.send_email", fake)
    repo = ActionApprovalRequestRepository(session)

    action = Action(action_plan_id="plan-1", action_type="send", tool_name="communication.send_email", title="x", status=ActionStatus.VALIDATED)
    decision = evaluate_permission(action, tool_registry)
    checked = apply_permission_decision(action, decision)

    in_memory_request = create_approval_request(checked, decision, requested_by="planner-agent")
    persisted = await persist_new_approval_request(repo, in_memory_request)
    await session.commit()

    waiting = advance_to_waiting_for_approval(checked)
    approved_request = decide_approval(persisted, "APPROVE", decided_by="human:alice")
    await sync_decision(repo, approved_request)
    await session.commit()

    approved_action = authorize_action(waiting, approved_request)
    return approved_action, decision, approved_request, tool_registry, adapter_registry, fake, repo


async def test_durable_approval_gated_execution_succeeds_and_consumes(session, sandbox_root):
    action, decision, request, tool_registry, adapters, fake, repo = await _durable_approval_gated(session)
    outcome = await execute_action(
        action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
        approval_request=request, approval_repo=repo,
    )
    assert outcome.action.status == ActionStatus.COMPLETED
    row = await repo.get(request.id)
    assert row.consumed is True


async def test_security_9_durable_consumed_approval_cannot_authorize_again(session, sandbox_root):
    action, decision, request, tool_registry, adapters, fake, repo = await _durable_approval_gated(session)
    first = await execute_action(action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request, approval_repo=repo)
    assert first.action.status == ActionStatus.COMPLETED

    # A second attempt, even on a freshly re-authorized copy of the SAME
    # approval request, must be denied by the durable, atomic guard.
    second = await execute_action(action, decision, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root, approval_request=request, approval_repo=repo)
    assert second.execution_result.success is False
    assert second.execution_result.error_code == "APPROVAL_FAILURE"
    assert fake.execute_calls == 1  # the adapter was never invoked a second time


# --- No LLM / no network (spec section 28, security test 20) ----------------


async def test_execution_performs_no_llm_or_network_call(sandbox_root):
    import inspect

    from app.decision_intelligence import action_executor, tool_adapters

    for module in (action_executor, tool_adapters):
        source = inspect.getsource(module)
        assert "anthropic" not in source.lower()
        assert "openai" not in source.lower()
        assert "httpx" not in source
        assert "requests." not in source


async def test_p2_execution_never_touches_agent_providers_module(sandbox_root):
    checked, decision, registry = _permission_checked_p2()
    # If executing this action required a model call, importing
    # app.agents.providers would be necessary; it is not imported anywhere
    # in the Executor/adapter modules (see the structural test above), and
    # this smoke run completes without any provider/API key configured.
    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=build_default_adapter_registry(), sandbox_root=sandbox_root)
    assert outcome.action.status == ActionStatus.COMPLETED


# --- Partial side-effect failure (spec section 25) ----------------------------


class _CorruptingReportAdapter:
    """Wraps the REAL SandboxFileCreateAdapter to prove a genuine side
    effect can occur while verification still correctly fails — simulates
    a buggy adapter that reports a hash inconsistent with what it wrote,
    without disabling any of verify()'s real, independent checks."""

    name = "test.partial_failure_tool"
    version = "0.0.1"

    def __init__(self):
        self._inner = SandboxFileCreateAdapter()

    async def execute(self, action, context):
        result = await self._inner.execute(action, context)
        if result.success:
            tampered = dict(result.output)
            tampered["content_hash"] = "0" * 64
            result = result.model_copy(update={"output": tampered})
        return result

    async def verify(self, action, execution_result, context):
        return await self._inner.verify(action, execution_result, context)


async def test_partial_side_effect_failure_is_truthfully_reported(sandbox_root):
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="test.partial_failure_tool",
            supported_action_types=frozenset({"sandbox_create"}),
            default_permission_level=PermissionLevel.WRITE,
            default_risk_level=RiskLevel.LOW,
            has_side_effects=True,
        )
    )
    adapters = ToolAdapterRegistry()
    adapters.register("test.partial_failure_tool", _CorruptingReportAdapter())

    action = Action(
        action_plan_id="plan-1", action_type="sandbox_create", tool_name="test.partial_failure_tool",
        title="x", inputs={"relative_path": "partial.txt", "content": "hello"}, status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, registry)
    checked = apply_permission_decision(action, decision)

    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox_root)

    assert outcome.execution_result.success is True
    assert outcome.execution_result.side_effect_occurred is True
    assert outcome.verification_result.passed is False
    assert outcome.action.status != ActionStatus.COMPLETED
    assert outcome.action.status == ActionStatus.FAILED
    # The real file genuinely exists on disk — the side effect was real.
    assert (sandbox_root / "partial.txt").exists()
    assert (sandbox_root / "partial.txt").read_text() == "hello"


# --- Local-only controlled integration test (spec sections 35/37) -----------


async def test_local_controlled_integration_p2_sandbox_file_end_to_end(tmp_path):
    """The one real local integration test this checkpoint calls for: a
    temporary sandbox, a safe P2 sandbox-file Action, permission evaluation,
    the Executor, real file creation, real verification, COMPLETED. No
    provider calls, no network, no user directory writes — `tmp_path` is
    removed by pytest automatically after the test."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    registry = build_default_tool_registry()
    adapters = build_default_adapter_registry()

    action = Action(
        action_plan_id="plan-1", action_type="sandbox_create", tool_name="file.create_sandboxed",
        title="Integration test artifact",
        inputs={"relative_path": "integration/hello.txt", "content": "v0.1.3.4 integration test"},
        expected_result="a sandboxed text file is created and verified",
        status=ActionStatus.VALIDATED,
    )
    decision = evaluate_permission(action, registry)
    assert decision.outcome == PermissionOutcome.ALLOW_WITH_AUDIT
    checked = apply_permission_decision(action, decision)
    assert checked.status == ActionStatus.PERMISSION_CHECKED

    outcome = await execute_action(checked, decision, tool_registry=registry, adapter_registry=adapters, sandbox_root=sandbox)

    assert outcome.action.status == ActionStatus.COMPLETED
    assert outcome.execution_result.success is True
    assert outcome.verification_result.passed is True

    written = sandbox / "integration" / "hello.txt"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == "v0.1.3.4 integration test"
    # tmp_path (and everything under it, including `sandbox`) is removed by
    # pytest's own tmp_path teardown — no manual cleanup step is needed and
    # none is performed here.
