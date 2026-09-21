"""The deterministic Reconciliation Engine (v0.1.3.5, spec sections 3/14-21/
26-28). NO LLM. NEVER executes an adapter's `execute()` — recovery is
INSPECT (read-only) -> CLASSIFY -> (safely) VERIFY/ADVANCE, never a blind
retry of a side effect.

    UNKNOWN EXECUTION STATE -> INSPECT -> RECONCILE -> VERIFY -> CLASSIFY
    -> ONLY THEN DECIDE WHETHER RETRY IS SAFE

`reconcile_action()` never repeats a side effect, never overwrites, never
deletes, never invokes an unknown/unregistered adapter, and never
fabricates `success=True` merely because a file was found — every
recovered ExecutionResult/VerificationResult is persisted with
`provenance=RECONSTRUCTED` (see app.database.models.ResultProvenance),
visibly distinct from a result produced by a normal
durable_action_executor.py run (`provenance=ORIGINAL`).

Recovery chains as far as is SAFELY, DETERMINISTICALLY justified in one
call (e.g. a proven-matching side effect can be reconstructed AND verified
AND the Action advanced to COMPLETED in a single reconcile_action() call),
because every step in that chain is independently safe/read-only/
deterministic — none of it is "retrying" anything. What is NEVER done
automatically is re-invoking the adapter's execute() to reproduce a side
effect whose presence/correctness could not be established by inspection.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from sqlalchemy.exc import IntegrityError

from app.database.models import ExecutionAttemptStatus, PersistedActionStatus, ResultProvenance
from app.database.repositories import (
    ActionRecordRepository,
    ExecutionAttemptRepository,
    ExecutionResultRepository,
    VerificationResultRepository,
)
from app.decision_intelligence.action_state_machine import can_transition
from app.decision_intelligence.execution_persistence import (
    execution_result_to_record_fields,
    record_to_action,
    record_to_execution_result,
    verification_result_to_record_fields,
)
from app.decision_intelligence.schemas import Action, ActionStatus, ExecutionResult
from app.decision_intelligence.tool_adapters import ExecutionContext, ToolAdapterRegistry


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class ReconciliationClassification(str, enum.Enum):
    CONSISTENT_COMPLETED = "CONSISTENT_COMPLETED"
    CONSISTENT_FAILED = "CONSISTENT_FAILED"
    EXECUTION_NOT_STARTED = "EXECUTION_NOT_STARTED"
    EXECUTION_INTERRUPTED = "EXECUTION_INTERRUPTED"
    SIDE_EFFECT_PRESENT_RESULT_MISSING = "SIDE_EFFECT_PRESENT_RESULT_MISSING"
    EXECUTION_SUCCEEDED_VERIFICATION_MISSING = "EXECUTION_SUCCEEDED_VERIFICATION_MISSING"
    VERIFICATION_PASSED_COMPLETION_MISSING = "VERIFICATION_PASSED_COMPLETION_MISSING"
    SIDE_EFFECT_MISMATCH = "SIDE_EFFECT_MISMATCH"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    APPROVAL_CONSUMED_EXECUTION_MISSING = "APPROVAL_CONSUMED_EXECUTION_MISSING"
    AMBIGUOUS_STATE = "AMBIGUOUS_STATE"
    SECURITY_INCONSISTENCY = "SECURITY_INCONSISTENCY"


class ReconciliationResult(BaseModel):
    action_id: str
    classification: ReconciliationClassification
    observed_state: dict = Field(default_factory=dict)
    durable_state: dict = Field(default_factory=dict)
    recommended_transition: str | None = None
    safe_to_retry: bool = False
    human_review_required: bool = False
    issues: list[str] = Field(default_factory=list)
    recovered: bool = False
    timestamp: datetime = Field(default_factory=_default_now)


async def discover_reconciliation_candidates(session, *, now: Callable[[], datetime] | None = None) -> list[str]:
    """Finds Action IDs whose durable state suggests reconciliation may be
    needed (spec section 28): non-terminal ActionRecord statuses, plus any
    STARTED ExecutionAttempt whose lease has already expired. Read-only —
    performs no recovery itself; a caller must explicitly call
    reconcile_action() for each candidate. NOT wired to any application
    startup hook (spec section 28: "Do NOT automatically execute recovery
    on application startup")."""
    clock = now or _default_now
    action_repo = ActionRecordRepository(session)
    attempt_repo = ExecutionAttemptRepository(session)

    non_terminal = [
        PersistedActionStatus.EXECUTING,
        PersistedActionStatus.EXECUTION_SUCCEEDED,
        PersistedActionStatus.VERIFYING,
        PersistedActionStatus.VERIFIED,
    ]
    candidates = {row.id for row in await action_repo.list_by_status(non_terminal)}

    stale_attempts = await attempt_repo.list_stale_started(before=clock())
    candidates.update(a.action_id for a in stale_attempts)

    return sorted(candidates)


async def _audit(session, workspace_id, event_type, action_id, metadata):
    if session is None or workspace_id is None:
        return
    from app.security.audit import record_event

    await record_event(
        session, workspace_id=workspace_id, actor_type="system", event_type=event_type,
        entity_type="action", entity_id=action_id, metadata=metadata,
    )
    await session.commit()


async def reconcile_action(
    action_id: str,
    *,
    session,
    adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path,
    now: Callable[[], datetime] | None = None,
    workspace_id: str | None = None,
) -> ReconciliationResult:
    """Public entry point. Thin audit-emitting wrapper around
    _reconcile_action_inner() — RECONCILIATION_STARTED before, then
    RECONCILIATION_CLASSIFIED always, plus RECONCILIATION_RECOVERED or
    RECONCILIATION_BLOCKED depending on the outcome (spec section 27).
    Kept as a wrapper rather than instrumenting every internal return
    point, which would be far more error-prone to keep in sync."""
    from app.security.audit import AuditEventType

    await _audit(session, workspace_id, AuditEventType.RECONCILIATION_STARTED, action_id, {})
    result = await _reconcile_action_inner(
        action_id, session=session, adapter_registry=adapter_registry, sandbox_root=sandbox_root, now=now
    )
    await _audit(
        session, workspace_id, AuditEventType.RECONCILIATION_CLASSIFIED, action_id,
        {"classification": result.classification.value},
    )
    if result.classification == ReconciliationClassification.EXECUTION_INTERRUPTED:
        await _audit(session, workspace_id, AuditEventType.EXECUTION_INTERRUPTED, action_id, {})
    if result.recovered:
        await _audit(session, workspace_id, AuditEventType.RECONCILIATION_RECOVERED, action_id, {"classification": result.classification.value})
    elif result.human_review_required:
        await _audit(session, workspace_id, AuditEventType.RECONCILIATION_BLOCKED, action_id, {"classification": result.classification.value})
    return result


async def _reconcile_action_inner(
    action_id: str,
    *,
    session,
    adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path,
    now: Callable[[], datetime] | None = None,
) -> ReconciliationResult:
    clock = now or _default_now
    ts = clock()

    action_repo = ActionRecordRepository(session)
    attempt_repo = ExecutionAttemptRepository(session)
    result_repo = ExecutionResultRepository(session)
    verification_repo = VerificationResultRepository(session)

    action_row = await action_repo.get(action_id)
    if action_row is None:
        return ReconciliationResult(
            action_id=action_id,
            classification=ReconciliationClassification.AMBIGUOUS_STATE,
            issues=["no durable ActionRecord found for this action_id"],
            safe_to_retry=False,
            human_review_required=True,
            timestamp=ts,
        )

    durable_state = {"status": action_row.status.value, "version": action_row.version}

    if action_row.status == PersistedActionStatus.COMPLETED:
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.CONSISTENT_COMPLETED,
            durable_state=durable_state, safe_to_retry=False, human_review_required=False, recovered=False, timestamp=ts,
        )

    if action_row.status in (
        PersistedActionStatus.FAILED, PersistedActionStatus.REJECTED,
        PersistedActionStatus.CANCELLED, PersistedActionStatus.BLOCKED,
    ):
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.CONSISTENT_FAILED,
            durable_state=durable_state, safe_to_retry=False, human_review_required=False, recovered=False, timestamp=ts,
        )

    attempts = await attempt_repo.list_for_action(action_id)
    if not attempts:
        if action_row.status in (
            PersistedActionStatus.EXECUTING, PersistedActionStatus.EXECUTION_SUCCEEDED,
            PersistedActionStatus.VERIFYING, PersistedActionStatus.VERIFIED,
        ):
            # Window A: durable Action state advanced without a durable
            # ExecutionAttempt ever being created. execute_action_durably()
            # always creates+commits the attempt BEFORE this state is
            # reached, so this combination should never occur in practice —
            # treated as a security-relevant inconsistency, not assumed benign.
            return ReconciliationResult(
                action_id=action_id, classification=ReconciliationClassification.SECURITY_INCONSISTENCY,
                durable_state=durable_state, issues=["Action durably past EXECUTING with no ExecutionAttempt on record"],
                safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
            )
        if action_row.approval_required and action_row.status == PersistedActionStatus.APPROVED:
            # Window A specifically: an ActionRecord only ever gets
            # persisted at durable_action_executor.py's step D, which runs
            # AFTER approval consumption (step C) for an approval-required
            # Action — so an APPROVED, approval-required row with no
            # attempt at all means the approval was consumed but the
            # process didn't survive to create the ExecutionAttempt. Not
            # safe to retry with the SAME approval (already consumed,
            # single-use) — a fresh approval is required, which is a human
            # decision, not something reconciliation can grant itself
            # (spec section 16: "reconciliation cannot manufacture approval").
            return ReconciliationResult(
                action_id=action_id, classification=ReconciliationClassification.APPROVAL_CONSUMED_EXECUTION_MISSING,
                durable_state=durable_state, safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
                issues=["approval was already consumed for this Action but no ExecutionAttempt was ever created"],
            )
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.EXECUTION_NOT_STARTED,
            durable_state=durable_state, safe_to_retry=True, human_review_required=False, recovered=False, timestamp=ts,
        )

    attempt = attempts[-1]
    execution_result_row = await result_repo.get_by_attempt(attempt.id)
    verification_result_row = await verification_repo.get_by_attempt(attempt.id)
    action = record_to_action(action_row)

    observed_state = {
        "attempt_status": attempt.status.value,
        "has_execution_result": execution_result_row is not None,
        "has_verification_result": verification_result_row is not None,
    }

    if execution_result_row is None:
        return await _reconcile_missing_execution_result(
            action_row=action_row, action=action, attempt=attempt, adapter_registry=adapter_registry,
            sandbox_root=sandbox_root, action_repo=action_repo, attempt_repo=attempt_repo, result_repo=result_repo,
            verification_repo=verification_repo, durable_state=durable_state, observed_state=observed_state, clock=clock,
        )

    if not execution_result_row.success:
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.CONSISTENT_FAILED,
            durable_state=durable_state, observed_state=observed_state, safe_to_retry=False,
            human_review_required=False, recovered=False, timestamp=ts,
        )

    if verification_result_row is None:
        return await _reconcile_missing_verification(
            action_row=action_row, action=action, attempt=attempt, execution_result_row=execution_result_row,
            adapter_registry=adapter_registry, sandbox_root=sandbox_root, action_repo=action_repo,
            attempt_repo=attempt_repo, verification_repo=verification_repo, durable_state=durable_state,
            observed_state=observed_state, clock=clock,
        )

    if verification_result_row.passed and action_row.status != PersistedActionStatus.COMPLETED:
        return await _reconcile_missing_completion(
            action_row=action_row, action=action, attempt=attempt, action_repo=action_repo, attempt_repo=attempt_repo,
            durable_state=durable_state, observed_state=observed_state, clock=clock,
        )

    if verification_result_row.passed:
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.CONSISTENT_COMPLETED,
            durable_state=durable_state, observed_state=observed_state, safe_to_retry=False,
            human_review_required=False, recovered=False, timestamp=ts,
        )

    return ReconciliationResult(
        action_id=action_id, classification=ReconciliationClassification.CONSISTENT_FAILED,
        durable_state=durable_state, observed_state=observed_state, safe_to_retry=False,
        human_review_required=False, recovered=False, timestamp=ts,
    )


# Ordinal position in the recovery chain this module ever advances
# through — used ONLY to decide whether a hop is "already done" (current
# position at or past target) versus "needs to happen now". Deliberately
# not a general-purpose ActionStatus ordering; BLOCKED/REJECTED/CANCELLED/
# FAILED are never reached through this helper (reconcile_action() already
# routes those to CONSISTENT_FAILED before any advancement is attempted).
_LIFECYCLE_ORDER: dict[ActionStatus, int] = {
    ActionStatus.EXECUTING: 0,
    ActionStatus.EXECUTION_SUCCEEDED: 1,
    ActionStatus.VERIFYING: 2,
    ActionStatus.VERIFIED: 3,
    ActionStatus.COMPLETED: 4,
}


async def _advance_through(action_repo: ActionRecordRepository, action_row, target: ActionStatus, ts: datetime, **extra_fields):
    """Advances the durable Action to `target` via the SAME optimistic-
    concurrency conditional UPDATE the normal executor uses — never a
    direct unconditional write. Idempotent across repeated recovery calls:
    if `action_row` is already AT OR PAST `target` in the recovery chain,
    returns it unchanged rather than attempting an illegal self/backward
    transition. Returns None only when the transition IS required but a
    concurrent writer beat us to it (fail closed: caller must not assume
    its recovery succeeded)."""
    current_status = ActionStatus(action_row.status.value)
    if _LIFECYCLE_ORDER.get(current_status, -1) >= _LIFECYCLE_ORDER.get(target, 10**9):
        return action_row
    if not can_transition(current_status, target):
        return None
    ok = await action_repo.update_if_version_matches(
        action_row.id, expected_version=action_row.version, status=PersistedActionStatus(target.value), **extra_fields
    )
    if not ok:
        return None
    return await action_repo.get(action_row.id)


async def _reconcile_missing_execution_result(
    *, action_row, action: Action, attempt, adapter_registry: ToolAdapterRegistry, sandbox_root: Path,
    action_repo, attempt_repo, result_repo, verification_repo, durable_state: dict, observed_state: dict,
    clock: Callable[[], datetime],
) -> ReconciliationResult:
    ts = clock()
    action_id = action_row.id

    if not adapter_registry.contains(attempt.tool_name):
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.AMBIGUOUS_STATE,
            durable_state=durable_state, observed_state=observed_state,
            issues=[f"no adapter registered for '{attempt.tool_name}'; cannot safely inspect"],
            safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
        )
    adapter = adapter_registry.get(attempt.tool_name)
    inspect = getattr(adapter, "inspect_effect", None)
    if inspect is None:
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.AMBIGUOUS_STATE,
            durable_state=durable_state, observed_state=observed_state,
            issues=[f"adapter '{attempt.tool_name}' has no inspect_effect() capability"],
            safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
        )

    context = ExecutionContext(sandbox_root=sandbox_root, now=clock, attempt_id=attempt.id)
    inspection = await inspect(action, context)
    observed_state = {**observed_state, "inspection": inspection.model_dump(mode="json")}

    if not inspection.exists:
        await attempt_repo.update_fields(
            attempt.id, status=ExecutionAttemptStatus.INTERRUPTED, recovery_state="NO_SIDE_EFFECT_FOUND"
        )
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.EXECUTION_INTERRUPTED,
            durable_state=durable_state, observed_state=observed_state, safe_to_retry=True,
            human_review_required=False, recovered=False, timestamp=ts,
        )

    if inspection.matches_expected is not True:
        # Present but wrong, or presence-without-a-usable-comparison — both
        # fail closed. NEVER overwritten, deleted, or replaced.
        await attempt_repo.update_fields(
            attempt.id, status=ExecutionAttemptStatus.BLOCKED, recovery_state="SIDE_EFFECT_MISMATCH"
        )
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.SIDE_EFFECT_MISMATCH,
            durable_state=durable_state, observed_state=observed_state,
            issues=inspection.issues or ["on-disk effect does not match the expected authorized payload"],
            safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
        )

    # Side effect present AND provably matches the expected authorized
    # payload — safe to catch up the durable bookkeeping. Never re-executes.
    reconstructed_result = ExecutionResult(
        action_id=action.id,
        tool_name=attempt.tool_name,
        started_at=attempt.started_at or ts,
        completed_at=ts,
        success=True,
        output={
            "resolved_relative_path": inspection.relative_path,
            "bytes_written": inspection.size,
            "content_hash": inspection.sha256,
        },
        side_effects=[f"created:{inspection.relative_path}"],
        side_effect_occurred=True,
        execution_attempt_id=attempt.id,
        adapter_version=attempt.adapter_version,
    )
    # Two concurrent reconcile_action() calls can both reach this point for
    # the same attempt (spec section 38) — attempt_id is UNIQUE per result
    # row, so re-check first, and treat a race on the INSERT itself as
    # "someone else already reconciled this," not an error.
    if await result_repo.get_by_attempt(attempt.id) is None:
        try:
            await result_repo.create(
                **execution_result_to_record_fields(attempt.id, reconstructed_result, provenance=ResultProvenance.RECONSTRUCTED)
            )
        except IntegrityError:
            await result_repo.session.rollback()
    await attempt_repo.update_fields(
        attempt.id, status=ExecutionAttemptStatus.EXECUTION_SUCCEEDED,
        side_effect_occurred=True, side_effect_fingerprint=inspection.sha256, recovery_state="RECONSTRUCTED_RESULT",
    )

    advanced = await _advance_through(action_repo, action_row, ActionStatus.EXECUTION_SUCCEEDED, ts, completed_at=ts)
    if advanced is None:
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.SIDE_EFFECT_PRESENT_RESULT_MISSING,
            durable_state=durable_state, observed_state=observed_state,
            issues=["reconstructed ExecutionResult, but could not advance Action state (concurrent writer)"],
            safe_to_retry=False, human_review_required=True, recovered=True, timestamp=ts,
        )

    # Chain forward through verification/completion — each step is
    # independently safe/deterministic/read-only, not a retried side effect.
    final = await _reconcile_missing_verification(
        action_row=advanced, action=record_to_action(advanced), attempt=attempt, execution_result_row=None,
        reconstructed_execution_result=reconstructed_result, adapter_registry=adapter_registry, sandbox_root=sandbox_root,
        action_repo=action_repo, attempt_repo=attempt_repo, verification_repo=verification_repo,
        durable_state=durable_state, observed_state=observed_state, clock=clock,
    )
    final.classification = ReconciliationClassification.SIDE_EFFECT_PRESENT_RESULT_MISSING
    final.recovered = True
    return final


async def _reconcile_missing_verification(
    *, action_row, action: Action, attempt, execution_result_row, adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path, action_repo, attempt_repo, verification_repo, durable_state: dict, observed_state: dict,
    clock: Callable[[], datetime], reconstructed_execution_result: ExecutionResult | None = None,
) -> ReconciliationResult:
    ts = clock()
    action_id = action_row.id

    execution_result = (
        reconstructed_execution_result if reconstructed_execution_result is not None else record_to_execution_result(execution_result_row)
    )

    if not adapter_registry.contains(attempt.tool_name):
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.EXECUTION_SUCCEEDED_VERIFICATION_MISSING,
            durable_state=durable_state, observed_state=observed_state,
            issues=[f"no adapter registered for '{attempt.tool_name}'; cannot verify"],
            safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
        )
    adapter = adapter_registry.get(attempt.tool_name)
    context = ExecutionContext(sandbox_root=sandbox_root, now=clock, attempt_id=attempt.id)

    verification_result = await adapter.verify(action, execution_result, context)
    if await verification_repo.get_by_attempt(attempt.id) is None:
        try:
            await verification_repo.create(
                **verification_result_to_record_fields(attempt.id, verification_result, provenance=ResultProvenance.RECONSTRUCTED)
            )
        except IntegrityError:
            await verification_repo.session.rollback()

    if not verification_result.passed:
        await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.VERIFICATION_FAILED)
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.EXECUTION_SUCCEEDED_VERIFICATION_MISSING,
            durable_state=durable_state, observed_state=observed_state, issues=list(verification_result.issues),
            safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
        )

    await attempt_repo.update_fields(attempt.id, status=ExecutionAttemptStatus.VERIFIED)

    advanced = await _advance_through(action_repo, action_row, ActionStatus.VERIFYING, ts)
    if advanced is not None:
        advanced = await _advance_through(action_repo, advanced, ActionStatus.VERIFIED, ts)

    if advanced is None:
        return ReconciliationResult(
            action_id=action_id, classification=ReconciliationClassification.EXECUTION_SUCCEEDED_VERIFICATION_MISSING,
            durable_state=durable_state, observed_state=observed_state,
            issues=["verification passed, but could not advance Action state (concurrent writer)"],
            safe_to_retry=False, human_review_required=True, recovered=True, timestamp=ts,
        )

    return await _reconcile_missing_completion(
        action_row=advanced, action=record_to_action(advanced), attempt=attempt, action_repo=action_repo,
        attempt_repo=attempt_repo, durable_state=durable_state, observed_state=observed_state, clock=clock,
        classification=ReconciliationClassification.EXECUTION_SUCCEEDED_VERIFICATION_MISSING,
    )


async def _reconcile_missing_completion(
    *, action_row, action: Action, attempt, action_repo, attempt_repo, durable_state: dict, observed_state: dict,
    clock: Callable[[], datetime], classification: ReconciliationClassification = ReconciliationClassification.VERIFICATION_PASSED_COMPLETION_MISSING,
) -> ReconciliationResult:
    ts = clock()
    advanced = await _advance_through(action_repo, action_row, ActionStatus.COMPLETED, ts)
    if advanced is None:
        return ReconciliationResult(
            action_id=action_row.id, classification=classification, durable_state=durable_state,
            observed_state=observed_state, issues=["verified, but could not advance Action to COMPLETED (concurrent writer)"],
            safe_to_retry=False, human_review_required=True, recovered=False, timestamp=ts,
        )
    return ReconciliationResult(
        action_id=action_row.id, classification=classification, durable_state={**durable_state, "status": advanced.status.value, "version": advanced.version},
        observed_state=observed_state, safe_to_retry=False, human_review_required=False, recovered=True,
        recommended_transition=ActionStatus.COMPLETED.value, timestamp=ts,
    )
