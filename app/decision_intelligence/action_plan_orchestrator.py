"""Durable ActionPlan Orchestrator (v0.1.3.6, spec sections 14/15/58/59).

A COORDINATOR, NOT A SUPERUSER: it never gains authority an individual
Action's own pipeline didn't already grant, and it NEVER calls a
ToolAdapter directly.

    ActionPlan Orchestrator
      -> eligible Action -> Permission Engine -> Approval Engine (if
         required) -> Durable Action Executor -> Trusted Tool Adapter
      -> ExecutionResult -> VerificationResult -> Action COMPLETED
      -> dependency released -> next eligible Action -> ... -> Plan COMPLETED

Recovery principle (spec section 59), the plan-level analog of v0.1.3.5's
Action-level rule — every `run_plan_until_blocked()` call re-derives
everything from durable state; nothing is cached in memory across calls:

    UNKNOWN PLAN STATE -> LOAD DURABLE PLAN -> INSPECT ACTIONS ->
    RECONCILE UNCERTAIN ACTIONS -> REBUILD DEPENDENCY STATE ->
    RECOMPUTE PLAN STATE -> ONLY THEN RESUME
"""
from __future__ import annotations

import enum
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from app.database.models import PersistedActionPlanStatus
from app.database.repositories import (
    ActionApprovalRequestRepository,
    ActionPlanRecordRepository,
    ActionRecordRepository,
    ExecutionAttemptRepository,
    ExecutionResultRepository,
    FailureRecordRepository,
    RecoveryDecisionRepository,
)
from app.decision_intelligence.action_eligibility import ActionEligibility, evaluate_action_eligibility
from app.decision_intelligence.action_plan_persistence import (
    compute_plan_hash,
    load_plan,
    persist_new_plan,
)
from app.decision_intelligence.action_plan_state_machine import (
    assert_transition as assert_plan_transition,
    can_transition as can_plan_transition,
)
from app.decision_intelligence.approval_engine import (
    ApprovalEngineError,
    advance_to_waiting_for_approval,
    authorize_action,
    create_approval_request,
    expire_approval_request,
    finalize_action_from_approval_outcome,
    is_expired,
)
from app.decision_intelligence.approval_persistence import (
    load_approval_request,
    persist_new_approval_request,
    sync_decision,
)
from app.decision_intelligence.action_state_machine import assert_transition
from app.decision_intelligence.durable_action_executor import _upsert_action_record, execute_action_durably
from app.decision_intelligence.execution_persistence import record_to_action, record_to_execution_result
from app.decision_intelligence.failure_intelligence import build_failure_record, classify_failure, persist_failure_record
from app.decision_intelligence.permission_engine import PermissionOutcome, apply_permission_decision, evaluate_permission
from app.decision_intelligence.plan_reconciliation import reconcile_plan
from app.decision_intelligence.plan_validation import evaluate_plan_readiness, requires_tool
from app.decision_intelligence.reconciliation import reconcile_action
from app.decision_intelligence.recovery_policy import RecoveryDecision, evaluate_recovery
from app.decision_intelligence.retry_controller import RetryAuthorizationError, authorize_retry
from app.decision_intelligence.schemas import (
    Action,
    ActionPlan,
    ActionPlanStatus,
    ActionStatus,
    ApprovalRequestStatus,
    ExecutionResult,
    FailureCategory,
)
from app.decision_intelligence.tool_adapters import ToolAdapterRegistry
from app.decision_intelligence.tool_registry import ToolRegistry

DEFAULT_MAX_ORCHESTRATION_STEPS = 50
DEFAULT_ORCHESTRATION_LEASE_SECONDS = 300

_IN_PROGRESS_ACTION_STATUSES = frozenset(
    {ActionStatus.EXECUTING, ActionStatus.EXECUTION_SUCCEEDED, ActionStatus.VERIFYING, ActionStatus.VERIFIED}
)
_TERMINAL_BAD_ACTION_STATUSES = frozenset(
    {ActionStatus.FAILED, ActionStatus.REJECTED, ActionStatus.CANCELLED, ActionStatus.BLOCKED}
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime | None) -> datetime | None:
    """SQLite does not natively preserve tzinfo (same root cause as
    approval_persistence.py's/execution_persistence.py's identically-named
    helpers) — a raw ActionPlanRecord field read directly off the ORM row
    (not through action_plan_persistence.py's domain bridge) can come back
    naive even though every value ever written into it was UTC-aware."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def _audit(session, workspace_id, event_type, plan_id, metadata):
    if session is None or workspace_id is None:
        return  # no natural workspace to attribute to — same documented limitation as v0.1.3.4/.5
    from app.security.audit import record_event

    await record_event(
        session, workspace_id=workspace_id, actor_type="system", event_type=event_type,
        entity_type="action_plan", entity_id=plan_id, metadata=metadata,
    )
    await session.commit()


async def _complete_toolless_action(action_repo: ActionRecordRepository, action: Action, clock: Callable[[], datetime]) -> Action:
    """P0 "internal reasoning" action types (spec section 4/8 of
    v0.1.3.2's Permission Engine — `plan_validation.requires_tool()`
    returns False for them) have no adapter to call at all: there is
    nothing to execute or verify. `execute_action_durably()` would fail
    looking for a `tool_name` that legitimately doesn't exist. This walks
    the SAME action_state_machine transitions
    (EXECUTING -> EXECUTION_SUCCEEDED -> VERIFYING -> VERIFIED ->
    COMPLETED) the Executor would, persisting each step, but never invokes
    a ToolAdapter — there is no side effect to perform or verify."""
    now = clock()
    for target in (
        ActionStatus.EXECUTING,
        ActionStatus.EXECUTION_SUCCEEDED,
        ActionStatus.VERIFYING,
        ActionStatus.VERIFIED,
        ActionStatus.COMPLETED,
    ):
        assert_transition(action.status, target)
        extra = {"started_at": now} if target == ActionStatus.EXECUTING else {}
        if target == ActionStatus.EXECUTION_SUCCEEDED:
            extra["completed_at"] = now
        action = action.model_copy(update={"status": target, **extra})
        row = await _upsert_action_record(action_repo, action)
        action = record_to_action(row)
    return action


class ActionPlanOrchestratorError(Exception):
    """Base class for caller-misuse errors — never raised for a routine
    "the plan cannot make progress right now" business outcome (those are
    OrchestrationResult returns, matching action_executor.py's/
    reconciliation.py's own convention)."""


class PlanNotFoundError(ActionPlanOrchestratorError):
    def __init__(self, plan_id: str):
        super().__init__(f"No durable ActionPlanRecord found for '{plan_id}'")
        self.plan_id = plan_id


class PlanNotReadyError(ActionPlanOrchestratorError):
    """Raised by validate_and_persist_plan() when plan_validation.py's
    structural checks fail — the plan is never persisted."""

    def __init__(self, blockers: list[str]):
        super().__init__(f"ActionPlan failed readiness validation: {'; '.join(blockers)}")
        self.blockers = blockers


class PlanNotOrchestratableError(ActionPlanOrchestratorError):
    def __init__(self, plan_id: str, status: ActionPlanStatus):
        super().__init__(f"Plan '{plan_id}' is in status {status.value}, not eligible for orchestration")
        self.plan_id = plan_id
        self.status = status


class PlanMutationDetectedError(ActionPlanOrchestratorError):
    """spec section 34: the plan's structural hash changed after READY —
    fails closed rather than silently adopting a changed graph."""

    def __init__(self, plan_id: str):
        super().__init__(f"ActionPlan '{plan_id}' structure changed after becoming READY; refusing to proceed")
        self.plan_id = plan_id


class StopReason(str, enum.Enum):
    PLAN_COMPLETED = "PLAN_COMPLETED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    DEPENDENCY_BLOCKED = "DEPENDENCY_BLOCKED"
    ACTION_FAILED = "ACTION_FAILED"
    SECURITY_BLOCKED = "SECURITY_BLOCKED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    ORCHESTRATION_LIMIT_REACHED = "ORCHESTRATION_LIMIT_REACHED"
    NO_PROGRESS = "NO_PROGRESS"
    CONCURRENT_ORCHESTRATOR = "CONCURRENT_ORCHESTRATOR"
    CANCELLED = "CANCELLED"
    # v0.1.3.7 (spec section 7's suggested outcome list, adopted as-is):
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    REPLAN_REQUIRED = "REPLAN_REQUIRED"


async def _load_latest_execution_result(action_id: str, *, session) -> ExecutionResult | None:
    """Best-effort lookup of the most recent ExecutionResult for an Action
    that just reached FAILED synchronously (v0.1.3.7) — feeds
    failure_intelligence.classify_failure() real error_code/error_type/
    side_effect_occurred data instead of guessing from Action.error alone."""
    attempt_repo = ExecutionAttemptRepository(session)
    result_repo = ExecutionResultRepository(session)
    attempts = await attempt_repo.list_for_action(action_id)
    if not attempts:
        return None
    row = await result_repo.get_by_attempt(attempts[-1].id)
    if row is None:
        return None
    return record_to_execution_result(row)


# StopReason for every RecoveryDecision this checkpoint's evaluate_recovery()
# can return, EXCEPT RETRY (handled separately — a successful retry
# authorization means the plan keeps going, no stop at all) and NO_ACTION/
# WAIT_FOR_APPROVAL (not reachable from this synchronous/reconciliation
# call site today, but mapped defensively rather than left to KeyError).
_RECOVERY_DECISION_STOP: dict[RecoveryDecision, tuple[StopReason, bool]] = {
    RecoveryDecision.SECURITY_BLOCKED: (StopReason.SECURITY_BLOCKED, True),
    RecoveryDecision.BUDGET_EXHAUSTED: (StopReason.BUDGET_EXHAUSTED, True),
    RecoveryDecision.REPLAN: (StopReason.REPLAN_REQUIRED, True),
    RecoveryDecision.RECONCILE: (StopReason.HUMAN_REVIEW_REQUIRED, True),
    RecoveryDecision.HUMAN_REVIEW: (StopReason.HUMAN_REVIEW_REQUIRED, True),
    RecoveryDecision.WAIT_FOR_APPROVAL: (StopReason.WAITING_FOR_APPROVAL, False),
    RecoveryDecision.STOP: (StopReason.ACTION_FAILED, False),
    RecoveryDecision.NO_ACTION: (StopReason.ACTION_FAILED, False),
}


async def _process_failure(
    action: Action,
    *,
    plan_id: str,
    session,
    clock: Callable[[], datetime],
    workspace_id: str | None,
    execution_result: ExecutionResult | None,
    fallback_category: FailureCategory = FailureCategory.UNKNOWN,
    side_effect_occurred_override: bool | None = None,
) -> tuple[StopReason | None, bool]:
    """The v0.1.3.7 failure-handling hook (spec section 56): classify ->
    persist FailureRecord -> evaluate recovery -> persist RecoveryDecision
    -> retry (durably, via retry_controller.py) OR stop with a truthful
    reason. Called from exactly two places in run_plan_until_blocked():
    right after a synchronous in-process failure, and from the
    reconciliation pass for a crash-interrupted Action reconciliation
    confirmed safe to retry (spec sections 9/44/75). Returns
    `(stop_reason, human_review_required)` — `stop_reason=None` means a
    retry was authorized and the caller should let the plan keep going.
    NEVER calls a ToolAdapter, NEVER calls execute_action_durably() itself
    — the SAME dispatch loop that already owns that call is what picks the
    now-VALIDATED, retry-authorized Action back up on its next iteration.
    """
    from app.security.audit import AuditEventType

    action_repo = ActionRecordRepository(session)
    failure_repo = FailureRecordRepository(session)
    decision_repo = RecoveryDecisionRepository(session)

    category = classify_failure(execution_result=execution_result, fallback_category=fallback_category)
    side_effect_occurred = (
        side_effect_occurred_override
        if side_effect_occurred_override is not None
        else (bool(execution_result.side_effect_occurred) if execution_result is not None else False)
    )

    recovery = evaluate_recovery(
        category=category,
        side_effect_occurred=side_effect_occurred,
        retry_count=action.retry_count,
        max_retries=action.max_retries,
        approval_required=action.approval_required,
    )

    failure_record = build_failure_record(
        action, plan_id=plan_id, execution_result=execution_result, retry_safe=recovery.retry_permitted,
        fallback_category=fallback_category, now=clock,
    )
    persisted_failure = await persist_failure_record(failure_repo, failure_record)
    await _audit(
        session, workspace_id, AuditEventType.ACTION_FAILURE_CLASSIFIED, action.id,
        {"category": category.value, "failure_id": persisted_failure.id},
    )

    retry_number = action.retry_count + 1 if recovery.decision == RecoveryDecision.RETRY else None
    await decision_repo.create(
        id=str(uuid.uuid4()), failure_id=persisted_failure.id, action_id=action.id, plan_id=plan_id,
        decision=recovery.decision.value, reason_codes_json=json.dumps(recovery.reason_codes),
        retry_number=retry_number, replan_proposal_id=None, created_at=clock(),
    )
    await _audit(
        session, workspace_id, AuditEventType.RECOVERY_DECISION_CREATED, action.id,
        {"decision": recovery.decision.value, "reason_codes": recovery.reason_codes},
    )

    if recovery.decision == RecoveryDecision.RETRY:
        fresh_row = await action_repo.get(action.id)
        try:
            await authorize_retry(action_repo, fresh_row, now=clock)
            await _audit(session, workspace_id, AuditEventType.ACTION_RETRY_AUTHORIZED, action.id, {"retry_number": retry_number})
            return None, False
        except RetryAuthorizationError as exc:
            await _audit(session, workspace_id, AuditEventType.ACTION_RETRY_EXHAUSTED, action.id, {"error": str(exc)})
            # Fails closed to HUMAN_REVIEW rather than silently treating a
            # retry-authorization failure (e.g. a concurrent writer) as an
            # ordinary STOP — this is an anomaly, not routine exhaustion.
            return StopReason.HUMAN_REVIEW_REQUIRED, True

    stop_reason, human_review = _RECOVERY_DECISION_STOP.get(recovery.decision, (StopReason.HUMAN_REVIEW_REQUIRED, True))
    if recovery.decision == RecoveryDecision.SECURITY_BLOCKED:
        await _audit(session, workspace_id, AuditEventType.SECURITY_RECOVERY_BLOCKED, action.id, {})
    elif recovery.decision == RecoveryDecision.BUDGET_EXHAUSTED:
        await _audit(session, workspace_id, AuditEventType.BUDGET_EXHAUSTED, action.id, {})
    elif human_review:
        await _audit(session, workspace_id, AuditEventType.HUMAN_REVIEW_REQUIRED, action.id, {"decision": recovery.decision.value})
    return stop_reason, human_review


class OrchestrationResult(BaseModel):
    plan_id: str
    starting_status: ActionPlanStatus
    ending_status: ActionPlanStatus
    actions_total: int
    actions_completed: int
    actions_executed_this_run: int
    actions_waiting_for_approval: int
    actions_waiting_for_dependencies: int
    actions_blocked: int
    actions_failed: int
    reconciliation_required: bool = False
    stop_reason: StopReason
    progress_made: bool
    next_action_ids: list[str] = Field(default_factory=list)
    approval_action_ids: list[str] = Field(default_factory=list)
    human_review_required: bool = False


# --------------------------------------------------------------------------
# Plan validation + persistence (DRAFT -> VALIDATING -> READY)
# --------------------------------------------------------------------------


async def validate_and_persist_plan(
    plan: ActionPlan, *, session, workspace_id: str | None = None
) -> "ActionPlanRecord":  # noqa: F821
    """Reuses plan_validation.py::evaluate_plan_readiness() verbatim — no
    competing graph/cycle validation logic (spec section 5/13). Raises
    PlanNotReadyError (nothing is persisted) if validation fails."""
    readiness = evaluate_plan_readiness(plan)
    if not readiness.ready:
        raise PlanNotReadyError(readiness.blockers)

    ready_plan = plan.model_copy(update={"status": ActionPlanStatus.READY})
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    row = await persist_new_plan(plan_repo, action_repo, ready_plan)
    await session.commit()

    from app.security.audit import AuditEventType

    await _audit(session, workspace_id, AuditEventType.ACTION_PLAN_CREATED, plan.id, {"actions_total": len(plan.actions)})
    await _audit(session, workspace_id, AuditEventType.ACTION_PLAN_VALIDATED, plan.id, {})
    await _audit(session, workspace_id, AuditEventType.ACTION_PLAN_READY, plan.id, {})
    return row


# --------------------------------------------------------------------------
# Per-Action single-step advancement (never calls a ToolAdapter directly)
# --------------------------------------------------------------------------


async def _check_execution_budget(
    action: Action, *, session, clock: Callable[[], datetime]
) -> tuple[bool, str | None]:
    """v0.1.3.8 hostile-benchmark fix (spec sections 18-21/56): the
    PLAN-scoped `ACTION_ATTEMPTS`/`ESTIMATED_COST` budgets v0.1.3.7
    introduced structurally were never actually consulted at the real
    resource-consumption boundary — nothing stopped an N+1'th adapter call
    once a plan's attempt/cost ceiling was configured. Gated HERE, in the
    orchestrator (the "controlled execution boundary" spec section 56
    requires), strictly BEFORE either `execute_action_durably()` call site
    below — never inside the Durable Executor or an adapter, so budget
    policy is never duplicated or decided anywhere else. Opt-in, exactly
    like every other v0.1.3.7 budget: no configured `BudgetAccountRecord`
    for a scope+type means unlimited, so a plan with no budget configured
    behaves exactly as every pre-v0.1.3.8 test already proved. Returns
    `(may_proceed, denied_budget_type_or_None)`.
    """
    from app.database.models import BudgetScope, BudgetType
    from app.database.repositories import BudgetAccountRepository, BudgetEventRepository
    from app.decision_intelligence.budget import reserve_and_consume

    budget_account_repo = BudgetAccountRepository(session)
    budget_event_repo = BudgetEventRepository(session)
    plan_id = action.action_plan_id

    # Keyed by (plan, action, retry_count) — a genuinely NEW dispatch
    # attempt (including a retry) consumes a fresh unit; re-entering
    # run_plan_until_blocked() for the SAME attempt (e.g. after a crash
    # before this check ever ran) replays the same idempotency_key rather
    # than double-consuming (spec sections 27/54 of v0.1.3.7, unchanged).
    attempts_key = f"action_attempts:{plan_id}:{action.id}:{action.retry_count}"
    attempts_result = await reserve_and_consume(
        budget_account_repo, budget_event_repo, scope_type=BudgetScope.PLAN, scope_id=plan_id,
        budget_type=BudgetType.ACTION_ATTEMPTS, amount=1.0, idempotency_key=attempts_key,
        reason="pre-execution ACTION_ATTEMPTS gate", now=clock,
    )
    if not attempts_result.granted:
        return False, BudgetType.ACTION_ATTEMPTS.value

    if action.estimated_cost:
        cost_key = f"estimated_cost:{plan_id}:{action.id}:{action.retry_count}"
        cost_result = await reserve_and_consume(
            budget_account_repo, budget_event_repo, scope_type=BudgetScope.PLAN, scope_id=plan_id,
            budget_type=BudgetType.ESTIMATED_COST, amount=float(action.estimated_cost), idempotency_key=cost_key,
            reason="pre-execution ESTIMATED_COST gate", now=clock,
        )
        if not cost_result.granted:
            return False, BudgetType.ESTIMATED_COST.value

    return True, None


async def _fail_for_budget_denial(
    action: Action, denied_budget_type: str, *, action_repo: ActionRecordRepository, plan_id: str,
    session, clock: Callable[[], datetime], workspace_id: str | None,
) -> Action:
    """Durably fails `action` for a denied pre-execution budget, WITHOUT
    ever creating an ExecutionAttempt or calling a ToolAdapter — proving
    the refusal happens strictly before adapter execution (spec section
    21). Routes through the SAME failure-intelligence pipeline
    (`_process_failure()`) as any other failure, so the durable
    FailureRecord/RecoveryDecisionRecord history is truthful and complete
    — never a special, undocumented failure path."""
    now = clock()
    failed = action.model_copy(update={
        "status": ActionStatus.FAILED, "completed_at": now,
        "error": f"pre-execution budget denied: {denied_budget_type}",
    })
    row = await _upsert_action_record(action_repo, failed)
    refreshed = record_to_action(row)
    await _process_failure(
        refreshed, plan_id=plan_id, session=session, clock=clock, workspace_id=workspace_id,
        execution_result=None, fallback_category=FailureCategory.BUDGET,
    )
    return refreshed


async def _advance_one_action(
    action: Action,
    *,
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path,
    session,
    clock: Callable[[], datetime],
    requested_by: str,
    workspace_id: str | None = None,
) -> tuple[Action, bool, str | None]:
    """Advances `action` by exactly ONE meaningful step and persists the
    result durably, returning `(refreshed_action, needs_human_review,
    reason)`. Approval remains Action-specific, hash-bound, and single-use
    throughout (spec section 60) — this function never creates a second
    ApprovalRequest when a valid one already exists (tracked via
    `Action.approval_id`), and always routes through
    `approval_engine.py`'s own validity/consumption logic rather than
    re-implementing it.
    """
    action_repo = ActionRecordRepository(session)
    approval_repo = ActionApprovalRequestRepository(session)

    if action.status == ActionStatus.VALIDATED:
        decision = evaluate_permission(action, tool_registry)
        updated = apply_permission_decision(action, decision)
        row = await _upsert_action_record(action_repo, updated)
        return record_to_action(row), False, None

    if action.status == ActionStatus.PERMISSION_CHECKED:
        decision = evaluate_permission(action, tool_registry)
        if decision.outcome == PermissionOutcome.REQUIRE_APPROVAL:
            if action.approval_id is None:
                approval_request = create_approval_request(action, decision, requested_by=requested_by)
                persisted = await persist_new_approval_request(approval_repo, approval_request)
                await session.commit()
                action = action.model_copy(update={"approval_id": persisted.id})
            waiting = advance_to_waiting_for_approval(action)
            row = await _upsert_action_record(action_repo, waiting)
            return record_to_action(row), False, None
        if not requires_tool(action.action_type):
            # P0 "internal reasoning" — nothing to execute or verify; see
            # _complete_toolless_action()'s docstring.
            completed = await _complete_toolless_action(action_repo, action, clock)
            return completed, False, None
        # ALLOW / ALLOW_WITH_AUDIT: no approval required — straight to the
        # durable Executor (P2 and below never pause the plan).
        # v0.1.3.8: PLAN-scoped ACTION_ATTEMPTS/ESTIMATED_COST budgets are
        # gated HERE, strictly before the Executor/adapter are ever called
        # — see _check_execution_budget()'s docstring.
        may_proceed, denied = await _check_execution_budget(action, session=session, clock=clock)
        if not may_proceed:
            failed = await _fail_for_budget_denial(
                action, denied, action_repo=action_repo, plan_id=action.action_plan_id,
                session=session, clock=clock, workspace_id=workspace_id,
            )
            return failed, False, None
        # retry_number=action.retry_count (v0.1.3.7): 0 on a first attempt
        # (byte-identical idempotency key to pre-v0.1.3.7 behavior — see
        # compute_idempotency_key()'s docstring); nonzero only when
        # retry_controller.authorize_retry() has already durably bumped
        # retry_count and reset this Action back to VALIDATED.
        outcome = await execute_action_durably(
            action, decision, tool_registry=tool_registry, adapter_registry=adapter_registry,
            sandbox_root=sandbox_root, session=session, retry_number=action.retry_count,
        )
        return outcome.action, False, None

    if action.status == ActionStatus.WAITING_FOR_APPROVAL:
        if action.approval_id is None:
            return action, True, "Action is WAITING_FOR_APPROVAL but has no linked ApprovalRequest"
        approval_request = await load_approval_request(approval_repo, action.approval_id)
        if approval_request is None:
            return action, True, "linked ApprovalRequest could not be loaded"

        now = clock()
        if approval_request.status == ApprovalRequestStatus.PENDING:
            if is_expired(approval_request, now=now):
                expired = expire_approval_request(approval_request, now=now)
                await sync_decision(approval_repo, expired)
                await session.commit()
                finalized = finalize_action_from_approval_outcome(action, expired)
                row = await _upsert_action_record(action_repo, finalized)
                return record_to_action(row), False, None
            return action, False, None  # still legitimately pending — plan stays paused

        if approval_request.status == ApprovalRequestStatus.APPROVED:
            decision = evaluate_permission(action, tool_registry)
            # v0.1.3.8 (spec section 28's exact ordering — "Budget available
            # /reserved" BEFORE "Execution claim"): checked here, before
            # authorize_action() ever consumes anything, so a denied budget
            # never leaves a validly-APPROVED-but-unconsumed approval
            # dangling — the approval stays untouched/reusable if the
            # caller later frees up budget and resumes.
            may_proceed, denied = await _check_execution_budget(action, session=session, clock=clock)
            if not may_proceed:
                failed = await _fail_for_budget_denial(
                    action, denied, action_repo=action_repo, plan_id=action.action_plan_id,
                    session=session, clock=clock, workspace_id=workspace_id,
                )
                return failed, False, None
            try:
                authorized = authorize_action(action, approval_request)
            except ApprovalEngineError as exc:
                # Hash mismatch / wrong action / already consumed / expired
                # despite the status check above (spec section 19) — never
                # execute; surface for human review rather than guessing.
                return action, True, f"approval is no longer valid for this action: {exc}"
            row = await _upsert_action_record(action_repo, authorized)
            authorized = record_to_action(row)
            outcome = await execute_action_durably(
                authorized, decision, tool_registry=tool_registry, adapter_registry=adapter_registry,
                sandbox_root=sandbox_root, session=session, approval_request=approval_request, approval_repo=approval_repo,
            )
            return outcome.action, False, None

        # REJECTED / CANCELLED / EXPIRED — deterministic, truthful finalization.
        finalized = finalize_action_from_approval_outcome(action, approval_request)
        row = await _upsert_action_record(action_repo, finalized)
        return record_to_action(row), False, None

    return action, False, None  # APPROVED/EXECUTING/etc. are handled via in-progress reconciliation, not here


# --------------------------------------------------------------------------
# Plan-level status recomputation (spec sections 12/16/20/21/30)
# --------------------------------------------------------------------------


def _recompute_plan_status(plan: ActionPlan) -> tuple[ActionPlanStatus, str | None]:
    """Never returns COMPLETED unless EVERY Action is durably COMPLETED
    (spec section 30 — "no false completion"). WAITING_FOR_APPROVAL takes
    priority over PARTIALLY_COMPLETED whenever nothing has failed — an
    approval-paused plan is still fully resumable, not degraded (spec
    section 16's exact example).

    v0.1.3.7 (spec section 21): a SUPERSEDED Action (replaced by an applied
    ReplanProposal — see replan.py) is deliberately excluded from this
    computation. Its row is preserved forever as history, but it is no
    longer part of the plan's CURRENT active membership — counting its
    permanent FAILED status here would make a plan whose replacement
    Action went on to succeed incorrectly, permanently stuck at
    PARTIALLY_COMPLETED, never truthfully COMPLETED."""
    active = [a for a in plan.actions if a.superseded_by is None]
    statuses = [a.status for a in active]
    total = len(statuses)
    completed = sum(1 for s in statuses if s == ActionStatus.COMPLETED)

    if total > 0 and completed == total:
        return ActionPlanStatus.COMPLETED, None

    has_bad = any(s in _TERMINAL_BAD_ACTION_STATUSES for s in statuses)
    has_waiting_approval = any(s == ActionStatus.WAITING_FOR_APPROVAL for s in statuses)

    if has_bad:
        if completed > 0:
            return ActionPlanStatus.PARTIALLY_COMPLETED, "ACTION_FAILURE"
        return ActionPlanStatus.FAILED, "ACTION_FAILURE"

    if has_waiting_approval:
        return ActionPlanStatus.WAITING_FOR_APPROVAL, "WAITING_FOR_APPROVAL"

    return ActionPlanStatus.EXECUTING, None


def _determine_blocking_stop_reason(eligibility: dict[str, ActionEligibility]) -> StopReason:
    values = set(eligibility.values())
    if ActionEligibility.WAITING_FOR_APPROVAL in values:
        return StopReason.WAITING_FOR_APPROVAL
    if ActionEligibility.SECURITY_BLOCKED in values:
        return StopReason.SECURITY_BLOCKED
    if values & {ActionEligibility.TERMINAL_FAILED, ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY, ActionEligibility.BLOCKED_BY_REJECTED_DEPENDENCY}:
        return StopReason.ACTION_FAILED
    if ActionEligibility.WAITING_FOR_DEPENDENCIES in values:
        return StopReason.DEPENDENCY_BLOCKED
    if ActionEligibility.CURRENTLY_EXECUTING in values:
        return StopReason.NO_PROGRESS
    return StopReason.PLAN_COMPLETED


def _summarize(
    plan_id: str,
    starting_status: ActionPlanStatus,
    ending_status: ActionPlanStatus,
    actions: list[Action],
    *,
    stop_reason: StopReason,
    progress_made: bool,
    executed_this_run: int,
    human_review_required: bool = False,
    reconciliation_required: bool = False,
) -> OrchestrationResult:
    actions_by_id = {a.id: a for a in actions}
    # v0.1.3.7: superseded Actions are excluded from summary counts (they
    # are historical, not current — see _recompute_plan_status()'s
    # docstring) but kept in actions_by_id so any stale reference during
    # eligibility evaluation still resolves rather than fails closed.
    active_actions = [a for a in actions if a.superseded_by is None]
    eligibility = {a.id: evaluate_action_eligibility(a, actions_by_id) for a in active_actions}

    waiting_approval = [aid for aid, e in eligibility.items() if e == ActionEligibility.WAITING_FOR_APPROVAL]
    waiting_deps = [aid for aid, e in eligibility.items() if e == ActionEligibility.WAITING_FOR_DEPENDENCIES]
    blocked = [
        aid for aid, e in eligibility.items()
        if e in (ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY, ActionEligibility.BLOCKED_BY_REJECTED_DEPENDENCY, ActionEligibility.SECURITY_BLOCKED)
    ]
    failed = [aid for aid, e in eligibility.items() if e == ActionEligibility.TERMINAL_FAILED]
    ready_next = [aid for aid, e in eligibility.items() if e == ActionEligibility.READY]
    completed = [aid for aid, e in eligibility.items() if e == ActionEligibility.ALREADY_COMPLETED]

    return OrchestrationResult(
        plan_id=plan_id,
        starting_status=starting_status,
        ending_status=ending_status,
        actions_total=len(active_actions),
        actions_completed=len(completed),
        actions_executed_this_run=executed_this_run,
        actions_waiting_for_approval=len(waiting_approval),
        actions_waiting_for_dependencies=len(waiting_deps),
        actions_blocked=len(blocked),
        actions_failed=len(failed),
        reconciliation_required=reconciliation_required,
        stop_reason=stop_reason,
        progress_made=progress_made,
        next_action_ids=ready_next,
        approval_action_ids=waiting_approval,
        human_review_required=human_review_required,
    )


# --------------------------------------------------------------------------
# The main entry point
# --------------------------------------------------------------------------


async def run_plan_until_blocked(
    plan_id: str,
    *,
    session,
    tool_registry: ToolRegistry,
    adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path,
    owner: str = "system",
    requested_by: str | None = None,
    now: Callable[[], datetime] | None = None,
    max_orchestration_steps: int = DEFAULT_MAX_ORCHESTRATION_STEPS,
    lease_seconds: int = DEFAULT_ORCHESTRATION_LEASE_SECONDS,
    workspace_id: str | None = None,
) -> OrchestrationResult:
    """Repeatedly advances the single next eligible Action (deterministic
    order: `sequence` then `id` — spec section 49) until the plan
    completes or a genuine stopping condition is hit (spec section 15).
    Bounded by `max_orchestration_steps`; never runs forever. Also serves
    as `resume_plan()` — there is no separate resume function, because
    resuming IS simply calling this again: every call re-derives
    everything from durable state (spec sections 17/59)."""
    clock = now or _default_now
    requested_by = requested_by or owner

    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)

    loaded = await load_plan(plan_repo, action_repo, plan_id)
    if loaded is None:
        raise PlanNotFoundError(plan_id)
    plan_row, plan = loaded
    starting_status = plan.status

    if plan.status == ActionPlanStatus.COMPLETED:
        return _summarize(plan_id, starting_status, plan.status, plan.actions, stop_reason=StopReason.PLAN_COMPLETED, progress_made=False, executed_this_run=0)
    if plan.status == ActionPlanStatus.FAILED:
        return _summarize(plan_id, starting_status, plan.status, plan.actions, stop_reason=StopReason.ACTION_FAILED, progress_made=False, executed_this_run=0)
    if plan.status == ActionPlanStatus.CANCELLED:
        return _summarize(plan_id, starting_status, plan.status, plan.actions, stop_reason=StopReason.CANCELLED, progress_made=False, executed_this_run=0)
    if plan.status not in (
        ActionPlanStatus.READY, ActionPlanStatus.EXECUTING,
        ActionPlanStatus.WAITING_FOR_APPROVAL, ActionPlanStatus.PARTIALLY_COMPLETED,
    ):
        raise PlanNotOrchestratableError(plan_id, plan.status)

    from app.security.audit import AuditEventType

    # --- Acquire the durable orchestration lease (spec sections 24/25) ---
    claim_time = clock()
    claimed = await plan_repo.claim_orchestration(plan_id, owner=owner, now=claim_time, lease_seconds=lease_seconds)
    if not claimed:
        current_row = await plan_repo.get(plan_id)
        current_lease_expires_at = _ensure_utc(current_row.orchestration_lease_expires_at) if current_row is not None else None
        lease_expired = current_lease_expires_at is not None and current_lease_expires_at < claim_time
        if lease_expired:
            await _audit(session, workspace_id, AuditEventType.ACTION_PLAN_STALE_LEASE_DETECTED, plan_id, {})
            # spec section 25: NEVER blindly steal — reconcile first.
            await reconcile_plan(plan_id, session=session, adapter_registry=adapter_registry, sandbox_root=sandbox_root, now=clock)
            claimed = await plan_repo.claim_orchestration(
                plan_id, owner=owner, now=clock(), lease_seconds=lease_seconds, allow_stale_takeover=True
            )
        if not claimed:
            await _audit(session, workspace_id, AuditEventType.ACTION_PLAN_DUPLICATE_CLAIM_BLOCKED, plan_id, {"owner": owner})
            loaded_after = await load_plan(plan_repo, action_repo, plan_id)
            _, plan_after = loaded_after if loaded_after is not None else (plan_row, plan)
            return _summarize(
                plan_id, starting_status, plan_after.status, plan_after.actions,
                stop_reason=StopReason.CONCURRENT_ORCHESTRATOR, progress_made=False, executed_this_run=0,
            )
    await _audit(session, workspace_id, AuditEventType.ACTION_PLAN_CLAIMED, plan_id, {"owner": owner})

    executed_ids: list[str] = []
    stop_reason: StopReason | None = None
    human_review_required = False
    reconciliation_required = False
    # v0.1.3.7: a non-RETRY recovery decision for one Action must NEVER
    # halt the whole bounded dispatch loop by itself — an unrelated,
    # independent branch (CONTINUE_INDEPENDENT — spec section 22 of
    # v0.1.3.6) must still be allowed to keep making progress, exactly as
    # it already did before this checkpoint existed. This only OVERRIDES
    # the FINAL stop_reason (computed below, same as v0.1.3.6) when that
    # would otherwise be the generic StopReason.ACTION_FAILED, with a more
    # specific/truthful one (BUDGET_EXHAUSTED/REPLAN_REQUIRED/
    # SECURITY_BLOCKED/HUMAN_REVIEW_REQUIRED) recovery_policy.py actually
    # determined.
    pending_recovery_stop_reason: StopReason | None = None
    pending_recovery_human_review = False

    try:
        # Reload fresh — reconciliation above (if it ran) may have changed durable state.
        plan_row, plan = await load_plan(plan_repo, action_repo, plan_id)

        # Structural mutation guard (spec section 34) — only meaningful
        # once a plan_hash was actually frozen at READY.
        if plan_row.plan_hash is not None and compute_plan_hash(plan) != plan_row.plan_hash:
            raise PlanMutationDetectedError(plan_id)

        # Always re-enter through EXECUTING — including on resume from
        # WAITING_FOR_APPROVAL/PARTIALLY_COMPLETED — so the final status
        # recompute below can legally reach ANY downstream state
        # (COMPLETED/PARTIALLY_COMPLETED/FAILED/CANCELLED) from a single,
        # consistent hub state, exactly as spec section 12's diagram
        # depicts EXECUTING fanning out to all of them. Without this, a
        # resumed plan that finishes would be stuck: e.g.
        # WAITING_FOR_APPROVAL -> COMPLETED is not itself a legal direct
        # transition (only EXECUTING -> COMPLETED is).
        if plan.status != ActionPlanStatus.EXECUTING:
            assert_plan_transition(plan.status, ActionPlanStatus.EXECUTING)
            extra_fields = {"started_at": clock()} if plan.status == ActionPlanStatus.READY else {}
            await plan_repo.update_if_version_matches(
                plan_id, expected_version=plan_row.version,
                status=PersistedActionPlanStatus.EXECUTING, **extra_fields,
            )
            plan_row, plan = await load_plan(plan_repo, action_repo, plan_id)

        # --- One-time catch-up pass: check every currently
        # WAITING_FOR_APPROVAL Action's approval status exactly once
        # (spec section 17 — resume must notice a since-granted approval).
        # `_advance_one_action()` only mutates state when there is
        # something new to act on (approval now APPROVED/REJECTED/
        # EXPIRED/CANCELLED); a still-PENDING approval is left untouched
        # and would return unchanged forever if re-polled in a loop, so
        # this is a single pass, not part of the bounded main loop below.
        waiting_actions = [a for a in plan.actions if a.status == ActionStatus.WAITING_FOR_APPROVAL]
        for action in sorted(waiting_actions, key=lambda a: (a.sequence, a.id)):
            advanced, needs_review, review_reason = await _advance_one_action(
                action, tool_registry=tool_registry, adapter_registry=adapter_registry,
                sandbox_root=sandbox_root, session=session, clock=clock, requested_by=requested_by,
                workspace_id=workspace_id,
            )
            if needs_review:
                human_review_required = True
                stop_reason = StopReason.HUMAN_REVIEW_REQUIRED
            elif advanced.status != action.status:
                executed_ids.append(action.id)
                if advanced.status == ActionStatus.FAILED:
                    # v0.1.3.7: an approval-gated Action can still fail
                    # AFTER approval (execution/verification failure) — run
                    # it through the same failure-intelligence pipeline for
                    # a complete durable audit trail. recovery_policy.py
                    # already returns HUMAN_REVIEW (never RETRY) whenever
                    # approval_required is True, so this never authorizes
                    # an automatic retry here — see its docstring.
                    execution_result = await _load_latest_execution_result(action.id, session=session)
                    recovery_stop_reason, recovery_human_review = await _process_failure(
                        advanced, plan_id=plan_id, session=session, clock=clock, workspace_id=workspace_id,
                        execution_result=execution_result,
                    )
                    if recovery_stop_reason is not None:
                        pending_recovery_stop_reason = recovery_stop_reason
                        pending_recovery_human_review = pending_recovery_human_review or recovery_human_review
        if waiting_actions:
            plan_row, plan = await load_plan(plan_repo, action_repo, plan_id)

        steps = 0
        while steps < max_orchestration_steps:
            if stop_reason is not None:
                # The catch-up pass above already found a reason to stop
                # (e.g. HUMAN_REVIEW_REQUIRED) — do not enter another
                # iteration, and do not let the `while...else` below
                # mistake this for exhausting the step budget.
                break
            steps += 1
            actions_by_id = {a.id: a for a in plan.actions}

            # --- Reconcile in-progress Actions FIRST (spec sections 27/59) ---
            any_reconciliation_blocked = False
            for action in list(plan.actions):
                if action.status in _IN_PROGRESS_ACTION_STATUSES:
                    result = await reconcile_action(
                        action.id, session=session, adapter_registry=adapter_registry, sandbox_root=sandbox_root, now=clock,
                    )
                    fresh_row = await action_repo.get(action.id)
                    refreshed_action = record_to_action(fresh_row)
                    actions_by_id[action.id] = refreshed_action

                    # v0.1.3.7 (spec sections 9/44/75): reconciliation
                    # confirmed a crash-interrupted Action's side effect is
                    # DEFINITELY ABSENT (EXECUTION_INTERRUPTED) and left the
                    # durable row non-terminal (status still EXECUTING) —
                    # exactly the "safe to retry" state v0.1.3.5 could
                    # detect but nothing acted on before this checkpoint.
                    # Route it through the SAME classify -> persist ->
                    # evaluate -> (retry | stop) pipeline as a synchronous
                    # failure, never a direct re-call into execute_action_durably().
                    if result.safe_to_retry and not result.recovered and refreshed_action.status == ActionStatus.EXECUTING:
                        retry_stop_reason, retry_human_review = await _process_failure(
                            refreshed_action, plan_id=plan_id, session=session, clock=clock, workspace_id=workspace_id,
                            execution_result=None, fallback_category=FailureCategory.TRANSIENT,
                            side_effect_occurred_override=False,
                        )
                        if retry_stop_reason is None:
                            actions_by_id[action.id] = record_to_action(await action_repo.get(action.id))
                        else:
                            any_reconciliation_blocked = True
                    elif result.human_review_required and not result.recovered:
                        any_reconciliation_blocked = True

            plan = plan.model_copy(update={"actions": list(actions_by_id.values())})

            if any_reconciliation_blocked:
                stop_reason = StopReason.RECONCILIATION_REQUIRED
                reconciliation_required = True
                human_review_required = True
                break

            eligibility = {aid: evaluate_action_eligibility(a, actions_by_id) for aid, a in actions_by_id.items()}

            if any(e == ActionEligibility.RECONCILIATION_REQUIRED for e in eligibility.values()):
                stop_reason = StopReason.RECONCILIATION_REQUIRED
                reconciliation_required = True
                break

            ready = [a for a in actions_by_id.values() if eligibility[a.id] == ActionEligibility.READY]
            ready.sort(key=lambda a: (a.sequence, a.id))  # deterministic ordering (spec section 49)

            if not ready:
                stop_reason = _determine_blocking_stop_reason(eligibility)
                break

            action = ready[0]
            advanced, needs_review, review_reason = await _advance_one_action(
                action, tool_registry=tool_registry, adapter_registry=adapter_registry,
                sandbox_root=sandbox_root, session=session, clock=clock, requested_by=requested_by,
                workspace_id=workspace_id,
            )
            if needs_review:
                human_review_required = True
                stop_reason = StopReason.HUMAN_REVIEW_REQUIRED
                break

            newly_failed = advanced.status == ActionStatus.FAILED and action.status != ActionStatus.FAILED
            if advanced.status != action.status:
                executed_ids.append(action.id)

            if newly_failed:
                # v0.1.3.7 (spec section 56): a synchronous, in-process
                # failure just happened. Classify it, persist durable
                # failure/recovery history, and either authorize a bounded
                # retry (plan keeps going — the now-VALIDATED Action is
                # simply picked up again next iteration by the SAME
                # dispatch logic above) or record a truthful reason
                # WITHOUT halting the loop — see pending_recovery_stop_reason
                # above for why this must not `break` here.
                execution_result = await _load_latest_execution_result(action.id, session=session)
                recovery_stop_reason, recovery_human_review = await _process_failure(
                    advanced, plan_id=plan_id, session=session, clock=clock, workspace_id=workspace_id,
                    execution_result=execution_result,
                )
                if recovery_stop_reason is not None:
                    pending_recovery_stop_reason = recovery_stop_reason
                    pending_recovery_human_review = pending_recovery_human_review or recovery_human_review

            plan_row, plan = await load_plan(plan_repo, action_repo, plan_id)
        else:
            stop_reason = StopReason.ORCHESTRATION_LIMIT_REACHED

        # v0.1.3.7: apply the deferred recovery-policy override — only
        # ever replaces the GENERIC ActionEligibility-derived ACTION_FAILED
        # (or a None from a plan that otherwise looks complete/no-progress)
        # with the more specific reason recovery_policy.py actually
        # determined; never overrides a MORE specific stop reason
        # (WAITING_FOR_APPROVAL/RECONCILIATION_REQUIRED/etc.) that already
        # legitimately took precedence this run.
        if pending_recovery_stop_reason is not None and stop_reason in (None, StopReason.ACTION_FAILED):
            stop_reason = pending_recovery_stop_reason
        human_review_required = human_review_required or pending_recovery_human_review

        # --- Recompute + persist final plan status ---
        plan_row, plan = await load_plan(plan_repo, action_repo, plan_id)
        final_status, pause_reason = _recompute_plan_status(plan)
        if final_status != plan.status and can_plan_transition(plan.status, final_status):
            await plan_repo.update_if_version_matches(
                plan_id, expected_version=plan_row.version,
                status=PersistedActionPlanStatus(final_status.value),
                pause_reason=pause_reason,
                completed_at=(clock() if final_status == ActionPlanStatus.COMPLETED else None),
                reconciliation_required=reconciliation_required,
            )
        plan_row, plan = await load_plan(plan_repo, action_repo, plan_id)

        if stop_reason is None:
            stop_reason = StopReason.PLAN_COMPLETED if plan.status == ActionPlanStatus.COMPLETED else StopReason.NO_PROGRESS

        _status_event = {
            ActionPlanStatus.COMPLETED: AuditEventType.ACTION_PLAN_COMPLETED,
            ActionPlanStatus.FAILED: AuditEventType.ACTION_PLAN_FAILED,
            ActionPlanStatus.CANCELLED: AuditEventType.ACTION_PLAN_CANCELLED,
            ActionPlanStatus.WAITING_FOR_APPROVAL: AuditEventType.ACTION_PLAN_WAITING_FOR_APPROVAL,
            ActionPlanStatus.PARTIALLY_COMPLETED: AuditEventType.ACTION_PLAN_PARTIALLY_COMPLETED,
        }.get(plan.status)
        if _status_event is not None:
            await _audit(session, workspace_id, _status_event, plan_id, {"stop_reason": stop_reason.value})

    finally:
        await plan_repo.release_orchestration(plan_id, owner=owner)

    return _summarize(
        plan_id, starting_status, plan.status, plan.actions,
        stop_reason=stop_reason, progress_made=bool(executed_ids), executed_this_run=len(executed_ids),
        human_review_required=human_review_required, reconciliation_required=reconciliation_required,
    )
