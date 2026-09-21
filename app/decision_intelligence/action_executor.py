"""The deterministic Action Executor (v0.1.3.4, spec sections 3/13-30).
FIRST REAL EXECUTION CAPABILITY in this codebase — strictly sandboxed (see
docs/decision_intelligence.md's v0.1.3.4 section).

    Action -> permission evaluation -> approval if required
      -> current authorization (re)validation -> durable atomic consumption
      -> Action Executor -> Trusted Tool Adapter -> ExecutionResult
      -> Verification -> VerificationResult -> Action COMPLETED

`execute_action()` is the single entry point. It NEVER raises for a
legitimate "this Action cannot execute right now" outcome (unknown tool, no
adapter, BLOCKed permission, missing/invalid/expired/consumed approval,
already-COMPLETED action) — those are expected, routine results an
orchestrator must handle, not exceptional control flow, so they are
returned as a structured `ExecutionOutcome` with a failed `ExecutionResult`
and (where the state machine allows it) the Action moved to a terminal
state. It DOES raise a typed `ActionExecutorError` for genuine caller
misuse (e.g. `decision.action_id != action.id`), matching
approval_engine.py's own create_approval_request()-style convention.

The Executor OWNS every ActionStatus transition; no adapter ever decides
one (spec section 13's closing line) — see EXECUTING/EXECUTION_SUCCEEDED/
VERIFYING/VERIFIED/COMPLETED below, all driven through the unmodified
action_state_machine.assert_transition().

TRANSACTION / CRASH-WINDOW HONESTY (spec section 30): durable approval
consumption (ActionApprovalRequestRepository.consume_if_valid(), COMMITted
immediately) and the sandbox filesystem write are NOT one atomic operation
— they cannot be; a SQL transaction cannot span a filesystem write. Two
failure windows are real and NOT solved by this checkpoint:

  1. approval consumed (committed) -> process crashes before the file write
     happens. Result: the approval is durably marked used, but no file
     exists. Recovery today: none automatic — a human/future reconciliation
     process must notice the Action never reached COMPLETED and decide
     whether to re-approve.
  2. file written -> process crashes before ExecutionResult/Action-state is
     persisted anywhere (nothing here persists ExecutionResult/Action
     itself — see "Persistence" in the docs). Recovery today: the file
     exists but nothing durable says why; a later identical attempt is
     blocked by SandboxTargetExistsError (accidental, not designed,
     protection) rather than a clean idempotency record.

This checkpoint's idempotency guarantee is therefore narrower than "exactly
once": it is "at most one successful write per (sandbox path), enforced by
the no-overwrite policy" plus "an already-COMPLETED Action is never
re-executed by this function" — not a general crash-safe exactly-once
executor. See docs/decision_intelligence.md for the explicit v0.1.3.5
requirement this implies (durable Action/ExecutionResult persistence +
a reconciliation pass).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from app.decision_intelligence.action_state_machine import assert_transition, can_transition
from app.decision_intelligence.approval_engine import ApprovalEngineError, consume_approval, validate_approval_for_action
from app.decision_intelligence.approval_persistence import consume_durable, load_approval_request
from app.decision_intelligence.permission_engine import PermissionDecision, PermissionOutcome
from app.decision_intelligence.schemas import (
    EXECUTOR_FAILURE_CATEGORY,
    Action,
    ActionStatus,
    ApprovalRequest,
    ExecutionResult,
    ExecutorFailureCode,
    VerificationResult,
)
from app.decision_intelligence.tool_adapters import ExecutionContext, ToolAdapterRegistry, UnknownAdapterError
from app.decision_intelligence.tool_registry import (
    DisabledToolError,
    ToolRegistry,
    UnknownToolError,
    UnsupportedActionTypeError,
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class ActionExecutorError(Exception):
    """Base class for caller-misuse errors — NOT the same as a legitimate
    "this Action cannot execute" business outcome, which is always a
    returned ExecutionOutcome instead. See the module docstring."""


class ActionDecisionMismatchError(ActionExecutorError):
    def __init__(self, action_id: str, decision_action_id: str):
        super().__init__(
            f"PermissionDecision.action_id '{decision_action_id}' does not match Action.id '{action_id}'"
        )
        self.action_id = action_id
        self.decision_action_id = decision_action_id


class ExecutionOutcome(BaseModel):
    """The Executor's return value. `action` always reflects the final
    state reached; `execution_result`/`verification_result` are populated
    only once the corresponding step actually ran."""

    action: Action
    execution_result: ExecutionResult | None = None
    verification_result: VerificationResult | None = None


# A legitimate fail-closed refusal moves the Action to whatever terminal
# state the EXISTING action_state_machine (v0.1.3.1, unmodified) actually
# allows from its current status. FAILED is not legal from APPROVED/
# WAITING_FOR_APPROVAL (only EXECUTING/CANCELLED and APPROVED/REJECTED/
# CANCELLED are, respectively) — CANCELLED is used there instead, matching
# the precedent approval_engine.py already set for EXPIRED->CANCELLED.
_FAIL_TARGET_BY_SOURCE: dict[ActionStatus, ActionStatus] = {
    ActionStatus.PLANNED: ActionStatus.FAILED,
    ActionStatus.VALIDATED: ActionStatus.FAILED,
    ActionStatus.PERMISSION_CHECKED: ActionStatus.FAILED,
    ActionStatus.APPROVED: ActionStatus.CANCELLED,
    ActionStatus.WAITING_FOR_APPROVAL: ActionStatus.CANCELLED,
}


def _fail_outcome(action: Action, code: ExecutorFailureCode, message: str, clock: Callable[[], datetime]) -> ExecutionOutcome:
    now = clock()
    result = ExecutionResult(
        action_id=action.id,
        tool_name=action.tool_name,
        started_at=now,
        completed_at=now,
        success=False,
        error_type=EXECUTOR_FAILURE_CATEGORY[code],
        error_code=code.value,
        error_message=message,
        side_effect_occurred=False,
    )
    target = _FAIL_TARGET_BY_SOURCE.get(action.status)
    if target is not None and can_transition(action.status, target):
        failed_action = action.model_copy(update={"status": target, "completed_at": now, "error": message})
    else:
        failed_action = action  # already terminal, or nothing legal to do — left untouched
    return ExecutionOutcome(action=failed_action, execution_result=result)


async def _audit(session, workspace_id, event_type, action_id, metadata):
    if session is None or workspace_id is None:
        return  # no natural workspace to attribute to — documented limitation, not a silent bug
    from app.security.audit import record_event

    await record_event(
        session,
        workspace_id=workspace_id,
        actor_type="system",
        event_type=event_type,
        entity_type="action",
        entity_id=action_id,
        metadata=metadata,
    )
    await session.commit()


async def execute_action(
    action: Action,
    decision: PermissionDecision,
    *,
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path,
    approval_request: ApprovalRequest | None = None,
    approval_repo=None,
    now: Callable[[], datetime] | None = None,
    workspace_id: str | None = None,
    session=None,
) -> ExecutionOutcome:
    """The single Action Executor entry point (spec section 13's 16 steps).

    `approval_repo` (an ActionApprovalRequestRepository, optional): when
    given, approval revalidation reads the DURABLE row (never the
    in-memory `approval_request` the caller happened to be holding — spec
    section 19) and consumption goes through the atomic, committed
    conditional UPDATE (spec section 18). When omitted, the in-memory
    `consume_approval()` single-use guard is used instead — sufficient for
    unit tests exercising approval plumbing without a database, but NOT
    safe against concurrent executors (no cross-process atomicity without
    `approval_repo`).
    """
    from app.security.audit import AuditEventType

    clock = now or _default_now

    if decision.action_id != action.id:
        raise ActionDecisionMismatchError(action.id, decision.action_id)

    # Idempotency (spec section 20): an already-COMPLETED Action is never
    # re-executed, full stop — no adapter is even resolved.
    if action.status == ActionStatus.COMPLETED:
        return ExecutionOutcome(action=action)

    # 1. Permission gate — BLOCK never executes, regardless of tool/sandbox.
    if decision.outcome == PermissionOutcome.BLOCK:
        return _fail_outcome(action, ExecutorFailureCode.PERMISSION_FAILURE, "PermissionDecision is BLOCK; cannot execute", clock)

    # 2. Approval gate.
    if decision.outcome == PermissionOutcome.REQUIRE_APPROVAL:
        if action.status != ActionStatus.APPROVED:
            return _fail_outcome(
                action, ExecutorFailureCode.APPROVAL_FAILURE,
                "Action requires approval but is not ActionStatus.APPROVED", clock,
            )
        if approval_request is None:
            return _fail_outcome(
                action, ExecutorFailureCode.APPROVAL_FAILURE,
                "No ApprovalRequest supplied for an approval-gated action", clock,
            )

        current_request = approval_request
        if approval_repo is not None:
            durable = await load_approval_request(approval_repo, approval_request.id)
            if durable is None:
                return _fail_outcome(
                    action, ExecutorFailureCode.APPROVAL_FAILURE,
                    "durable ApprovalRequest row not found", clock,
                )
            current_request = durable

        # Revalidate NOW, against current/durable state — never a cached
        # earlier validity result (spec section 19).
        validity = validate_approval_for_action(current_request, action, now=clock())
        if not validity.valid:
            return _fail_outcome(
                action, ExecutorFailureCode.APPROVAL_FAILURE,
                f"ApprovalRequest invalid: {', '.join(validity.reason_codes)}", clock,
            )

        if approval_repo is not None:
            consumed_ok = await consume_durable(
                approval_repo, current_request.id,
                action_id=action.id, action_hash=current_request.action_hash, now=clock(),
            )
            if not consumed_ok:
                return _fail_outcome(
                    action, ExecutorFailureCode.APPROVAL_FAILURE,
                    "Approval could not be atomically consumed (already consumed, or no longer valid)", clock,
                )
        else:
            # In-memory path: consume_approval() RAISES a typed
            # ApprovalEngineError (e.g. ApprovalAlreadyConsumedError) rather
            # than returning a bool, unlike the durable path above — catch
            # it here so this branch still fails closed via a normal
            # ExecutionOutcome rather than an uncaught exception (a caller
            # can legitimately pass an already-consumed request object,
            # e.g. one it consumed directly via approval_engine outside the
            # Executor, or the same in-memory object across two calls — the
            # in-memory path has no shared state to prevent that itself;
            # this is the fail-closed backstop for when it happens anyway).
            try:
                consume_approval(current_request, action=action, now=clock())
            except ApprovalEngineError as exc:
                return _fail_outcome(action, ExecutorFailureCode.APPROVAL_FAILURE, str(exc), clock)

        await _audit(session, workspace_id, AuditEventType.APPROVAL_CONSUMED, action.id, {"approval_request_id": current_request.id})
    else:
        if action.status != ActionStatus.PERMISSION_CHECKED:
            return _fail_outcome(
                action, ExecutorFailureCode.VALIDATION_FAILURE,
                "Action is not ActionStatus.PERMISSION_CHECKED", clock,
            )

    # 3. Resolve ToolDefinition, then the trusted adapter (spec section 12:
    # metadata and executable capability are separate — a known
    # ToolDefinition with no registered adapter fails ADAPTER_NOT_FOUND).
    try:
        tool_registry.resolve(action.tool_name, action.action_type)
    except (UnknownToolError, DisabledToolError, UnsupportedActionTypeError) as exc:
        return _fail_outcome(action, ExecutorFailureCode.ADAPTER_NOT_FOUND, str(exc), clock)

    if not adapter_registry.contains(action.tool_name):
        return _fail_outcome(
            action, ExecutorFailureCode.ADAPTER_NOT_FOUND,
            f"No trusted adapter registered for '{action.tool_name}'", clock,
        )
    adapter = adapter_registry.get(action.tool_name)

    # 4. EXECUTING — the Executor, not the adapter, drives every transition.
    assert_transition(action.status, ActionStatus.EXECUTING)
    started = clock()
    executing_action = action.model_copy(update={"status": ActionStatus.EXECUTING, "started_at": started})

    context = ExecutionContext(sandbox_root=sandbox_root, now=clock)
    await _audit(session, workspace_id, AuditEventType.EXECUTION_STARTED, action.id, {"attempt_id": context.attempt_id})

    execution_result = await adapter.execute(executing_action, context)

    if not execution_result.success:
        assert_transition(executing_action.status, ActionStatus.FAILED)
        failed_action = executing_action.model_copy(
            update={
                "status": ActionStatus.FAILED,
                "completed_at": execution_result.completed_at,
                "error": execution_result.error_message,
                "result": execution_result.output,
            }
        )
        await _audit(session, workspace_id, AuditEventType.EXECUTION_FAILED, action.id, {"error_code": execution_result.error_code})
        return ExecutionOutcome(action=failed_action, execution_result=execution_result)

    await _audit(session, workspace_id, AuditEventType.EXECUTION_SUCCEEDED, action.id, {"attempt_id": context.attempt_id})

    assert_transition(executing_action.status, ActionStatus.EXECUTION_SUCCEEDED)
    succeeded_action = executing_action.model_copy(
        update={
            "status": ActionStatus.EXECUTION_SUCCEEDED,
            "completed_at": execution_result.completed_at,
            "result": execution_result.output,
        }
    )

    assert_transition(succeeded_action.status, ActionStatus.VERIFYING)
    verifying_action = succeeded_action.model_copy(update={"status": ActionStatus.VERIFYING})
    await _audit(session, workspace_id, AuditEventType.VERIFICATION_STARTED, action.id, {})

    verification_result = await adapter.verify(verifying_action, execution_result, context)

    if not verification_result.passed:
        # spec section 25: file may already exist (side_effect_occurred was
        # already truthfully set by the adapter) — never mark COMPLETED,
        # never auto-retry, never auto-delete the artifact.
        assert_transition(verifying_action.status, ActionStatus.VERIFICATION_FAILED)
        verification_failed_action = verifying_action.model_copy(update={"status": ActionStatus.VERIFICATION_FAILED})
        assert_transition(verification_failed_action.status, ActionStatus.FAILED)
        final_action = verification_failed_action.model_copy(
            update={"status": ActionStatus.FAILED, "error": "; ".join(verification_result.issues)}
        )
        await _audit(
            session, workspace_id, AuditEventType.VERIFICATION_FAILED, action.id, {"issues": verification_result.issues}
        )
        return ExecutionOutcome(action=final_action, execution_result=execution_result, verification_result=verification_result)

    await _audit(session, workspace_id, AuditEventType.VERIFICATION_SUCCEEDED, action.id, {})

    assert_transition(verifying_action.status, ActionStatus.VERIFIED)
    verified_action = verifying_action.model_copy(update={"status": ActionStatus.VERIFIED})
    assert_transition(verified_action.status, ActionStatus.COMPLETED)
    completed_action = verified_action.model_copy(update={"status": ActionStatus.COMPLETED})

    return ExecutionOutcome(action=completed_action, execution_result=execution_result, verification_result=verification_result)
