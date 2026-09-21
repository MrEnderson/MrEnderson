"""The DURABLE Action Executor (v0.1.3.5, spec sections 3/12/13/22-25).
Adds durability/recovery on top of v0.1.3.4's Action Executor WITHOUT
modifying it — `app/decision_intelligence/action_executor.py` is FROZEN
this checkpoint and remains the in-memory/lightly-durable entry point
exactly as it was. This module is a new, additive orchestration layer that
reimplements the same lifecycle with a durable persistence checkpoint
after every stage spec section 12 calls out, so each crash window (spec
section 13) is a real, independently observable boundary rather than an
implementation detail hidden inside one in-memory function call.

Ordering (spec section 12), each letter a durable checkpoint a crash could
land between:

    A. validate Action                    (in-memory, same guards as v0.1.3.4)
    B. permission check                   (decision, supplied by caller)
    C. approval check/consumption         (approval_engine.py + durable repo)
    D. persist Action execution state     -> ActionRecord upserted
    E. create + commit ExecutionAttempt   -> atomic claim (idempotency_key)
    F. execute adapter
    G. persist ExecutionResult immediately
    H. persist side-effect fingerprint if effect occurred
    I. transition durable Action
    J. verify
    K. persist VerificationResult
    L. persist final Action state

DUPLICATE REQUESTS (spec section 22): an already-COMPLETED durable Action
is detected FIRST, before any of the above — no adapter call, no approval
consumption, no new ExecutionAttempt.

CONCURRENT CLAIMS (spec section 24): step E's ExecutionAttempt INSERT races
against a UNIQUE constraint on `idempotency_key` (deterministically derived
from `(action_id, action_hash)` — never model-chosen). Losing that race
means another attempt already owns this exact authorized payload; this
function never proceeds to F for that caller.

This module NEVER adds a new real ToolAdapter, NEVER executes anything
beyond what v0.1.3.4's `file.create_sandboxed` already does, and performs
no LLM/network call anywhere in its own code (see the structural test in
tests/test_durable_action_executor.py mirroring v0.1.3.4's equivalent).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy.exc import IntegrityError

from app.database.models import ExecutionAttemptStatus, PersistedActionStatus, ResultProvenance
from app.database.repositories import (
    ActionRecordRepository,
    ExecutionAttemptRepository,
    ExecutionResultRepository,
    VerificationResultRepository,
)
from app.decision_intelligence.action_executor import (
    _FAIL_TARGET_BY_SOURCE,
    ActionDecisionMismatchError,
    ExecutionOutcome,
)
from app.decision_intelligence.action_state_machine import assert_transition, can_transition
from app.decision_intelligence.approval_engine import ApprovalEngineError, consume_approval, validate_approval_for_action
from app.decision_intelligence.approval_persistence import consume_durable, load_approval_request
from app.decision_intelligence.execution_persistence import (
    action_to_record_fields,
    compute_idempotency_key,
    compute_side_effect_fingerprint,
    execution_result_to_record_fields,
    record_to_action,
    record_to_execution_result,
    verification_result_to_record_fields,
)
from app.decision_intelligence.permission_engine import PermissionDecision, PermissionOutcome
from app.decision_intelligence.schemas import (
    EXECUTOR_FAILURE_CATEGORY,
    Action,
    ActionStatus,
    ApprovalRequest,
    ExecutionResult,
    ExecutorFailureCode,
)
from app.decision_intelligence.tool_adapters import ExecutionContext, ToolAdapterRegistry
from app.decision_intelligence.tool_registry import (
    DisabledToolError,
    ToolRegistry,
    UnknownToolError,
    UnsupportedActionTypeError,
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class DurableExecutorError(Exception):
    """Base class for caller-misuse / genuine-conflict errors — never
    raised for a routine "this Action cannot proceed" business outcome
    (those are ExecutionOutcome returns, matching action_executor.py's
    convention)."""


class StaleActionVersionError(DurableExecutorError):
    """Optimistic concurrency conflict (spec section 6): another writer
    already advanced this ActionRecord past the version this call expected.
    Never retried automatically — the caller must reload durable state and
    decide afresh."""

    def __init__(self, action_id: str, expected_version: int):
        super().__init__(
            f"ActionRecord '{action_id}' was not at expected version {expected_version} "
            "(a concurrent writer already advanced it) — reload and retry from scratch"
        )
        self.action_id = action_id
        self.expected_version = expected_version


# Ordinal position in the happy-path lifecycle, used ONLY to detect a
# late/stale caller trying to write a status that regresses an
# ActionRecord past where it has already legitimately progressed (spec
# section 38's concurrency scenario: a slow loser's own "persist Action
# execution state" step D can otherwise land AFTER the winner has already
# advanced well past it, silently overwriting newer field values with
# stale ones even though the optimistic-concurrency version check alone
# would not catch it, since both callers started from the same version).
_TERMINAL_STATUSES = frozenset(
    {ActionStatus.FAILED, ActionStatus.REJECTED, ActionStatus.CANCELLED, ActionStatus.BLOCKED, ActionStatus.COMPLETED}
)
_HAPPY_PATH_ORDER: dict[ActionStatus, int] = {
    ActionStatus.PLANNED: 0,
    ActionStatus.VALIDATED: 1,
    ActionStatus.PERMISSION_CHECKED: 2,
    ActionStatus.WAITING_FOR_APPROVAL: 3,
    ActionStatus.APPROVED: 4,
    ActionStatus.EXECUTING: 5,
    ActionStatus.EXECUTION_SUCCEEDED: 6,
    ActionStatus.VERIFYING: 7,
    ActionStatus.VERIFIED: 8,
}


_UPSERT_MAX_ATTEMPTS = 5


async def _upsert_action_record(action_repo: ActionRecordRepository, action: Action):
    """Create-or-optimistically-update, robust against concurrent callers
    racing on the SAME action_id (spec section 38). Retries internally
    (bounded) rather than surfacing every transient version conflict as an
    error: on each attempt it re-fetches the current row and re-applies
    the monotonic-progress guard above, so a losing caller's write
    naturally resolves to a no-op once the winner's progress becomes
    visible, instead of needing a hand-tuned fix for every possible
    interleaving. Raises StaleActionVersionError only if genuinely unable
    to converge after `_UPSERT_MAX_ATTEMPTS` attempts — a real anomaly,
    not routine concurrent progress."""
    existing = None
    for _ in range(_UPSERT_MAX_ATTEMPTS):
        existing = await action_repo.get(action.id)

        if existing is not None:
            existing_status = ActionStatus(existing.status.value)
            if existing_status in _TERMINAL_STATUSES:
                return existing  # already terminal — never written over again
            if action.status not in _TERMINAL_STATUSES:
                existing_rank = _HAPPY_PATH_ORDER.get(existing_status, -1)
                incoming_rank = _HAPPY_PATH_ORDER.get(action.status, -1)
                if existing_rank > incoming_rank:
                    # A stale/late, non-terminal write trying to regress a
                    # row that has already legitimately progressed further
                    # — silently a no-op, not an error: the row already
                    # reflects more current information than this caller has.
                    return existing

        fields = action_to_record_fields(action)
        if existing is None:
            fields["version"] = 1
            try:
                return await action_repo.create(**fields)
            except IntegrityError:
                # Two concurrent callers can both observe existing=None
                # before either commits (spec section 38's exact scenario)
                # — the loser's INSERT collides on the primary key. Not a
                # corruption: a concurrent writer won the race to create
                # this row first. Roll back this failed INSERT and loop —
                # the next iteration re-fetches and re-applies the guard
                # against whatever the winner actually persisted.
                await action_repo.session.rollback()
                continue

        fields.pop("id", None)
        fields.pop("version", None)  # update_if_version_matches() sets this itself; avoid a duplicate kwarg
        ok = await action_repo.update_if_version_matches(action.id, expected_version=existing.version, **fields)
        if ok:
            return await action_repo.get(action.id)
        # Lost the optimistic-concurrency race this attempt — loop back to
        # re-fetch the now-current row and re-apply the guard rather than
        # failing immediately; almost every real-world case is a benign
        # "someone else made progress" situation the guard resolves cleanly.

    raise StaleActionVersionError(action.id, existing.version if existing is not None else -1)


async def _fail_durable(
    action: Action,
    action_repo: ActionRecordRepository,
    code: ExecutorFailureCode,
    message: str,
    clock: Callable[[], datetime],
) -> ExecutionOutcome:
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
        failed_action = action

    existing = await action_repo.get(action.id)
    if existing is not None:
        try:
            await _upsert_action_record(action_repo, failed_action)
        except StaleActionVersionError:
            pass  # best-effort: the failure is still correctly reported to the caller either way

    return ExecutionOutcome(action=failed_action, execution_result=result)


async def _audit(session, workspace_id, event_type, action_id, metadata):
    if session is None or workspace_id is None:
        return
    from app.security.audit import record_event

    await record_event(
        session, workspace_id=workspace_id, actor_type="system", event_type=event_type,
        entity_type="action", entity_id=action_id, metadata=metadata,
    )
    await session.commit()


async def execute_action_durably(
    action: Action,
    decision: PermissionDecision,
    *,
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path,
    session,
    approval_request: ApprovalRequest | None = None,
    approval_repo=None,
    claimed_by: str = "system",
    now: Callable[[], datetime] | None = None,
    workspace_id: str | None = None,
    retry_number: int = 0,
) -> ExecutionOutcome:
    """The durable Action Executor entry point. Requires a real `session`
    (unlike v0.1.3.4's execute_action(), which treats persistence as
    optional) — durability is this function's entire purpose.

    `retry_number` (v0.1.3.7, additive, default 0 — every pre-v0.1.3.7
    caller and test is byte-for-byte unaffected): only ever passed by
    action_plan_orchestrator.py after retry_controller.py has durably
    authorized and recorded a bounded retry, using the Action's own
    (already-bumped) `retry_count`. It is threaded into the idempotency-key
    computation ONLY — see compute_idempotency_key()'s docstring — so a
    retry of the exact same action_hash claims a NEW ExecutionAttempt
    instead of colliding with the failed attempt's own claim."""
    clock = now or _default_now

    action_repo = ActionRecordRepository(session)
    attempt_repo = ExecutionAttemptRepository(session)
    result_repo = ExecutionResultRepository(session)
    verification_repo = VerificationResultRepository(session)

    if decision.action_id != action.id:
        raise ActionDecisionMismatchError(action.id, decision.action_id)

    # --- Duplicate execution request (spec section 22) — checked FIRST ---
    from app.security.audit import AuditEventType

    existing_record = await action_repo.get(action.id)
    if existing_record is not None and existing_record.status == PersistedActionStatus.COMPLETED:
        await _audit(session, workspace_id, AuditEventType.DUPLICATE_EXECUTION_BLOCKED, action.id, {})
        return ExecutionOutcome(action=record_to_action(existing_record))

    if action.status == ActionStatus.COMPLETED:
        return ExecutionOutcome(action=action)

    # --- A/B: permission gate ---
    if decision.outcome == PermissionOutcome.BLOCK:
        return await _fail_durable(action, action_repo, ExecutorFailureCode.PERMISSION_FAILURE, "PermissionDecision is BLOCK; cannot execute", clock)

    # --- C: approval gate ---
    if decision.outcome == PermissionOutcome.REQUIRE_APPROVAL:
        if action.status != ActionStatus.APPROVED:
            return await _fail_durable(action, action_repo, ExecutorFailureCode.APPROVAL_FAILURE, "Action requires approval but is not ActionStatus.APPROVED", clock)
        if approval_request is None:
            return await _fail_durable(action, action_repo, ExecutorFailureCode.APPROVAL_FAILURE, "No ApprovalRequest supplied for an approval-gated action", clock)

        current_request = approval_request
        if approval_repo is not None:
            durable = await load_approval_request(approval_repo, approval_request.id)
            if durable is None:
                return await _fail_durable(action, action_repo, ExecutorFailureCode.APPROVAL_FAILURE, "durable ApprovalRequest row not found", clock)
            current_request = durable

        validity = validate_approval_for_action(current_request, action, now=clock())
        if not validity.valid:
            return await _fail_durable(action, action_repo, ExecutorFailureCode.APPROVAL_FAILURE, f"ApprovalRequest invalid: {', '.join(validity.reason_codes)}", clock)

        if approval_repo is not None:
            consumed_ok = await consume_durable(approval_repo, current_request.id, action_id=action.id, action_hash=current_request.action_hash, now=clock())
            if not consumed_ok:
                return await _fail_durable(action, action_repo, ExecutorFailureCode.APPROVAL_FAILURE, "Approval could not be atomically consumed", clock)
            await _audit(session, workspace_id, AuditEventType.APPROVAL_CONSUMED, action.id, {"approval_request_id": current_request.id})
        else:
            try:
                consume_approval(current_request, action=action, now=clock())
            except ApprovalEngineError as exc:
                return await _fail_durable(action, action_repo, ExecutorFailureCode.APPROVAL_FAILURE, str(exc), clock)
    else:
        if action.status != ActionStatus.PERMISSION_CHECKED:
            return await _fail_durable(action, action_repo, ExecutorFailureCode.VALIDATION_FAILURE, "Action is not ActionStatus.PERMISSION_CHECKED", clock)

    # --- D: persist Action execution state (CRASH WINDOW A boundary) ---
    # Concurrent callers can race here (spec section 38) before either has
    # claimed the ExecutionAttempt idempotency_key below — a genuine
    # optimistic-concurrency conflict at this stage means another worker
    # is (or was) already handling this exact Action, which is a routine,
    # expected business outcome, not a crash-worthy caller error.
    try:
        action_row = await _upsert_action_record(action_repo, action)
    except StaleActionVersionError:
        # Same reasoning as the claim-loss path below: a concurrent writer
        # already owns this row's progress — report locally, never write
        # over it (see the comment on the claim-loss branch for why).
        fail_now = clock()
        code = ExecutorFailureCode.VALIDATION_FAILURE
        result = ExecutionResult(
            action_id=action.id, tool_name=action.tool_name, started_at=fail_now, completed_at=fail_now,
            success=False, error_type=EXECUTOR_FAILURE_CATEGORY[code], error_code=code.value,
            error_message="Action state changed concurrently while persisting execution state; another worker may already be handling it",
            side_effect_occurred=False,
        )
        return ExecutionOutcome(action=action, execution_result=result)
    action_hash = action_row.action_hash

    try:
        tool_registry.resolve(action.tool_name, action.action_type)
    except (UnknownToolError, DisabledToolError, UnsupportedActionTypeError) as exc:
        return await _fail_durable(action, action_repo, ExecutorFailureCode.ADAPTER_NOT_FOUND, str(exc), clock)

    if not adapter_registry.contains(action.tool_name):
        return await _fail_durable(action, action_repo, ExecutorFailureCode.ADAPTER_NOT_FOUND, f"No trusted adapter registered for '{action.tool_name}'", clock)
    adapter = adapter_registry.get(action.tool_name)

    # --- E: atomic execution claim (CRASH WINDOW A/B boundary) ---
    idempotency_key = compute_idempotency_key(action.id, action_hash, retry_number)
    claim_time = clock()
    attempt = await attempt_repo.claim(
        action_id=action.id,
        idempotency_key=idempotency_key,
        tool_name=action.tool_name,
        adapter_name=adapter.name,
        adapter_version=getattr(adapter, "version", None),
        claimed_by=claimed_by,
        now=claim_time,
    )
    if attempt is None:
        # Another caller already holds this exact claim (spec section 24).
        # Deliberately does NOT call _fail_durable()/_upsert_action_record()
        # here: the winner of the claim legitimately owns this
        # ActionRecord's ongoing progress, and a loser writing a
        # FAILED/CANCELLED status onto it — even via a correctly
        # version-guarded update — would still be wrong: it can race
        # against and clobber a version the winner is about to advance
        # from, which is a genuine, observed flakiness source under real
        # concurrency (see the v0.1.3.5 delivery report). The loser
        # reports its own local, non-durable failure result and leaves the
        # shared row entirely alone.
        existing_attempt = await attempt_repo.get_by_idempotency_key(idempotency_key)
        await _audit(session, workspace_id, AuditEventType.DUPLICATE_EXECUTION_BLOCKED, action.id, {"idempotency_key": idempotency_key})
        code = ExecutorFailureCode.APPROVAL_FAILURE if existing_attempt is None else ExecutorFailureCode.VALIDATION_FAILURE
        fail_now = clock()
        result = ExecutionResult(
            action_id=action.id, tool_name=action.tool_name, started_at=fail_now, completed_at=fail_now,
            success=False, error_type=EXECUTOR_FAILURE_CATEGORY[code], error_code=code.value,
            error_message=f"Execution already claimed for this Action (idempotency_key={idempotency_key[:16]}...)",
            side_effect_occurred=False,
        )
        return ExecutionOutcome(action=action, execution_result=result)

    await _audit(session, workspace_id, AuditEventType.EXECUTION_ATTEMPT_CREATED, action.id, {"attempt_id": attempt.id})
    await _audit(session, workspace_id, AuditEventType.EXECUTION_CLAIMED, action.id, {"attempt_id": attempt.id, "claimed_by": claimed_by})

    # Lease + STARTED — set before the adapter is ever called (spec section 8/25).
    lease_ttl_seconds = 900  # 15 minutes; generous for a single sandboxed file write.
    started = clock()
    await attempt_repo.update_fields(
        attempt.id,
        status=ExecutionAttemptStatus.STARTED,
        started_at=started,
        lease_expires_at=started + timedelta(seconds=lease_ttl_seconds),
    )

    assert_transition(action.status, ActionStatus.EXECUTING)
    executing_action = action.model_copy(update={"status": ActionStatus.EXECUTING, "started_at": started})
    # Routed through _upsert_action_record() (retry + monotonic-progress
    # guard), not a raw update_if_version_matches() call — this is the
    # SOLE winner's own write, but a still-in-flight loser's earlier,
    # now-stale step D write can otherwise land in between and cause a
    # spurious version conflict here purely from bad timing, not a real
    # anomaly (see the v0.1.3.5 delivery report's concurrency discussion).
    action_row = await _upsert_action_record(action_repo, executing_action)

    context = ExecutionContext(sandbox_root=sandbox_root, now=clock, attempt_id=attempt.id)

    # --- F: execute adapter (CRASH WINDOW B/C boundary) ---
    execution_result = await adapter.execute(executing_action, context)

    # --- G: persist ExecutionResult immediately (CRASH WINDOW C/D boundary) ---
    await result_repo.create(**execution_result_to_record_fields(attempt.id, execution_result))

    # --- H: persist side-effect fingerprint if occurred ---
    fingerprint = None
    if execution_result.side_effect_occurred and execution_result.output:
        relative_path = execution_result.output.get("resolved_relative_path")
        content_hash = execution_result.output.get("content_hash")
        bytes_written = execution_result.output.get("bytes_written")
        if relative_path and content_hash is not None and bytes_written is not None:
            fingerprint = compute_side_effect_fingerprint(
                tool_name=action.tool_name, relative_path=relative_path, content_hash=content_hash, expected_bytes=bytes_written
            )

    if not execution_result.success:
        await attempt_repo.update_fields(
            attempt.id,
            status=ExecutionAttemptStatus.EXECUTION_FAILED,
            finished_at=execution_result.completed_at,
            side_effect_occurred=execution_result.side_effect_occurred,
            side_effect_fingerprint=fingerprint,
            error_code=execution_result.error_code,
            error_message=execution_result.error_message,
        )
        assert_transition(executing_action.status, ActionStatus.FAILED)
        failed_action = executing_action.model_copy(
            update={"status": ActionStatus.FAILED, "completed_at": execution_result.completed_at, "error": execution_result.error_message, "result": execution_result.output}
        )
        await _upsert_action_record(action_repo, failed_action)
        return ExecutionOutcome(action=failed_action, execution_result=execution_result)

    await attempt_repo.update_fields(
        attempt.id,
        status=ExecutionAttemptStatus.EXECUTION_SUCCEEDED,
        side_effect_occurred=execution_result.side_effect_occurred,
        side_effect_fingerprint=fingerprint,
    )

    # --- I: transition durable Action ---
    assert_transition(executing_action.status, ActionStatus.EXECUTION_SUCCEEDED)
    succeeded_action = executing_action.model_copy(
        update={"status": ActionStatus.EXECUTION_SUCCEEDED, "completed_at": execution_result.completed_at, "result": execution_result.output}
    )
    action_row = await _upsert_action_record(action_repo, succeeded_action)

    assert_transition(succeeded_action.status, ActionStatus.VERIFYING)
    verifying_action = succeeded_action.model_copy(update={"status": ActionStatus.VERIFYING})
    action_row = await _upsert_action_record(action_repo, verifying_action)
    await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.VERIFYING)

    # --- J: verify (CRASH WINDOW D/E boundary) ---
    verification_result = await adapter.verify(verifying_action, execution_result, context)

    # --- K: persist VerificationResult (CRASH WINDOW E/F boundary) ---
    await verification_repo.create(**verification_result_to_record_fields(attempt.id, verification_result))

    if not verification_result.passed:
        await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.VERIFICATION_FAILED, finished_at=verification_result.verified_at)
        assert_transition(verifying_action.status, ActionStatus.VERIFICATION_FAILED)
        verification_failed_action = verifying_action.model_copy(update={"status": ActionStatus.VERIFICATION_FAILED})
        assert_transition(verification_failed_action.status, ActionStatus.FAILED)
        final_action = verification_failed_action.model_copy(update={"status": ActionStatus.FAILED, "error": "; ".join(verification_result.issues)})
        await _upsert_action_record(action_repo, final_action)
        return ExecutionOutcome(action=final_action, execution_result=execution_result, verification_result=verification_result)

    await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.VERIFIED, finished_at=verification_result.verified_at)

    assert_transition(verifying_action.status, ActionStatus.VERIFIED)
    verified_action = verifying_action.model_copy(update={"status": ActionStatus.VERIFIED})
    action_row = await _upsert_action_record(action_repo, verified_action)

    # --- L: persist final Action state (CRASH WINDOW F/G boundary) ---
    assert_transition(verified_action.status, ActionStatus.COMPLETED)
    completed_action = verified_action.model_copy(update={"status": ActionStatus.COMPLETED})
    await _upsert_action_record(action_repo, completed_action)

    return ExecutionOutcome(action=completed_action, execution_result=execution_result, verification_result=verification_result)
