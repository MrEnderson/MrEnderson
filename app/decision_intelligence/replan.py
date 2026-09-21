"""Controlled, Deterministic Replanning (v0.1.3.7, spec sections 14-22/45-52).
NO LLM ever generates a replacement Action here — `propose_replan()` always
takes a caller-supplied (test fixture, deterministic plan machinery, or a
future human-reviewed) replacement `Action` object as-is; this module only
validates, persists, and (once accepted) durably applies it.

SECURITY INVARIANT (spec sections 16/17/47/48), enforced ENTIRELY BY REUSE,
not by any new check in this module: the replacement Action is persisted at
`ActionStatus.VALIDATED` — the SAME starting point every brand-new Action
in this codebase has always started from. It carries NO approval_id, NO
inherited APPROVED status, and its `permission_level`/`risk_level` are
PROPOSED metadata only. The very next time the orchestrator advances it,
the unmodified v0.1.3.2 Permission Engine (`evaluate_permission`) computes
its authoritative floor fresh from its `action_type`/`tool_name`, exactly
as it would for any Action it had never seen before — a proposed
downgrade cannot lower that floor (see permission_engine.py), and if the
floor requires approval, the unmodified v0.1.3.3 Approval Engine requires a
brand new `ApprovalRequest`, bound to the replacement's own new
`action_hash` — the OLD Action's approval (if any) is never read, copied,
or re-validated against the new Action anywhere in this module.

DEPENDENCY REWIRING (spec section 18): the failed Action's OWN row is
NEVER deleted or overwritten — only `superseded_by_action_id` is set on it
(spec section 21 — preserve history). Every OTHER Action that depended on
the failed one is rewired to depend on the replacement instead.

CYCLE PROTECTION (spec section 49): reuses
`plan_validation.py::detect_dependency_cycle()` verbatim against the
PROJECTED post-replan graph before anything is persisted — no competing
cycle-detection algorithm.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.database.models import (
    BudgetScope,
    BudgetType,
    PermissionLevel,
    PersistedActionPlanStatus,
    ReplanProposalStatus,
    RiskLevel,
)
from app.database.repositories import (
    ActionPlanRecordRepository,
    ActionRecordRepository,
    BudgetAccountRepository,
    BudgetEventRepository,
    ReplanProposalRepository,
)
from app.decision_intelligence.action_plan_persistence import compute_plan_hash, load_plan, load_plan_actions
from app.decision_intelligence.budget import reserve_and_consume
from app.decision_intelligence.execution_persistence import action_to_record_fields
from app.decision_intelligence.plan_validation import detect_dependency_cycle
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus, FailureCategory


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class ReplanError(Exception):
    """Base class for caller-misuse errors — never raised for a routine
    "this proposal cannot be applied right now" business outcome (those
    are ReplanResult returns)."""


class FailedActionNotFoundError(ReplanError):
    def __init__(self, action_id: str):
        super().__init__(f"Action '{action_id}' is not a member of this plan")
        self.action_id = action_id


class ActionNotFailedError(ReplanError):
    def __init__(self, action_id: str, status: ActionStatus):
        super().__init__(f"Action '{action_id}' is in status {status.value}, not FAILED — only a FAILED Action may be replanned")
        self.action_id = action_id
        self.status = status


class ProposalNotFoundError(ReplanError):
    def __init__(self, proposal_id: str):
        super().__init__(f"No durable ReplanProposalRecord found for '{proposal_id}'")
        self.proposal_id = proposal_id


class ReplanProposal(BaseModel):
    """Domain-level view of one proposed replan — see
    app.database.models.ReplanProposalRecord for the durable row shape."""

    id: str = Field(default_factory=_new_id)
    plan_id: str
    failed_action_id: str
    replacement_action_id: str = Field(default_factory=_new_id)
    replacement_action_type: str
    replacement_title: str
    replacement_tool_name: str | None = None
    replacement_inputs: dict = Field(default_factory=dict)
    replacement_expected_result: str = ""
    replacement_success_criteria: str = ""
    replacement_verification_method: str = ""
    replacement_permission_level: PermissionLevel = PermissionLevel.WRITE
    replacement_risk_level: RiskLevel = RiskLevel.LOW
    replacement_dependencies: list[str] = Field(default_factory=list)
    reason: str = ""
    failure_category: FailureCategory | None = None
    status: ReplanProposalStatus = ReplanProposalStatus.PROPOSED
    reason_codes: list[str] = Field(default_factory=list)
    created_by: str = "system"
    created_at: datetime = Field(default_factory=_default_now)
    applied_at: datetime | None = None
    new_plan_revision: int | None = None


class ReplanResult(BaseModel):
    proposal_id: str
    plan_id: str
    old_action_id: str
    replacement_action_id: str | None = None
    old_plan_revision: int | None = None
    new_plan_revision: int | None = None
    status: ReplanProposalStatus
    approval_required: bool | None = None
    reason_codes: list[str] = Field(default_factory=list)


def _project_post_replan_actions(plan: ActionPlan, failed_action_id: str, replacement: Action) -> list[Action]:
    """Builds the hypothetical Action list this plan WOULD have after the
    replan (failed Action kept as-is/historical; every dependent rewired to
    the replacement; replacement appended) — used ONLY for cycle validation
    before anything is persisted."""
    projected: list[Action] = []
    for action in plan.actions:
        if action.id == failed_action_id:
            projected.append(action)
            continue
        if failed_action_id in action.dependencies:
            rewired = [replacement.id if d == failed_action_id else d for d in action.dependencies]
            projected.append(action.model_copy(update={"dependencies": rewired}))
        else:
            projected.append(action)
    projected.append(replacement)
    return projected


def propose_replan(
    plan: ActionPlan,
    failed_action: Action,
    replacement: Action,
    *,
    reason: str = "",
    created_by: str = "system",
    failure_category: FailureCategory | None = None,
    now: Callable[[], datetime] | None = None,
) -> ReplanProposal:
    """Pure, in-memory validation + construction (spec section 49: cycle
    protection happens HERE, before any durable write). Raises
    FailedActionNotFoundError/ActionNotFailedError for caller misuse;
    returns a ReplanProposal with status=REJECTED (never raises) for a
    detected dependency cycle, since that is a legitimate, expected
    business outcome a caller should be able to inspect, not a programming
    error."""
    clock = now or _default_now
    plan_actions_by_id = {a.id: a for a in plan.actions}
    if failed_action.id not in plan_actions_by_id:
        raise FailedActionNotFoundError(failed_action.id)
    if failed_action.status != ActionStatus.FAILED:
        raise ActionNotFailedError(failed_action.id, failed_action.status)

    resolved_dependencies = (
        list(replacement.dependencies) if replacement.dependencies else list(failed_action.dependencies)
    )
    replacement_for_projection = replacement.model_copy(update={"dependencies": resolved_dependencies})

    proposal = ReplanProposal(
        plan_id=plan.id,
        failed_action_id=failed_action.id,
        replacement_action_id=replacement.id,
        replacement_action_type=replacement.action_type,
        replacement_title=replacement.title,
        replacement_tool_name=replacement.tool_name,
        replacement_inputs=dict(replacement.inputs),
        replacement_expected_result=replacement.expected_result,
        replacement_success_criteria=replacement.success_criteria,
        replacement_verification_method=replacement.verification_method,
        replacement_permission_level=replacement.permission_level,
        replacement_risk_level=replacement.risk_level,
        replacement_dependencies=resolved_dependencies,
        reason=reason,
        failure_category=failure_category,
        created_by=created_by,
        created_at=clock(),
    )

    projected = _project_post_replan_actions(plan, failed_action.id, replacement_for_projection)
    cycle = detect_dependency_cycle(projected)
    if cycle:
        proposal = proposal.model_copy(
            update={"status": ReplanProposalStatus.REJECTED, "reason_codes": [f"CYCLE_DETECTED:{'->'.join(cycle)}"]}
        )
    return proposal


def proposal_to_record_fields(proposal: ReplanProposal) -> dict:
    return dict(
        id=proposal.id,
        plan_id=proposal.plan_id,
        failed_action_id=proposal.failed_action_id,
        replacement_action_id=proposal.replacement_action_id,
        replacement_action_type=proposal.replacement_action_type,
        replacement_title=proposal.replacement_title,
        replacement_tool_name=proposal.replacement_tool_name,
        replacement_inputs_json=json.dumps(proposal.replacement_inputs, sort_keys=True, default=str),
        replacement_expected_result=proposal.replacement_expected_result or None,
        replacement_success_criteria=proposal.replacement_success_criteria or None,
        replacement_verification_method=proposal.replacement_verification_method or None,
        replacement_permission_level=proposal.replacement_permission_level,
        replacement_risk_level=proposal.replacement_risk_level,
        replacement_dependencies_json=json.dumps(proposal.replacement_dependencies, sort_keys=True),
        reason=proposal.reason or None,
        failure_category=proposal.failure_category.value if proposal.failure_category else None,
        status=proposal.status,
        reason_codes_json=json.dumps(proposal.reason_codes),
        created_by=proposal.created_by,
        created_at=proposal.created_at,
    )


async def persist_proposal(repo: ReplanProposalRepository, proposal: ReplanProposal):
    return await repo.create(**proposal_to_record_fields(proposal))


def _replacement_action_from_row(row) -> Action:
    return Action(
        id=row.replacement_action_id,
        action_plan_id=row.plan_id,
        action_type=row.replacement_action_type,
        title=row.replacement_title,
        tool_name=row.replacement_tool_name,
        inputs=json.loads(row.replacement_inputs_json) if row.replacement_inputs_json else {},
        expected_result=row.replacement_expected_result or "",
        success_criteria=row.replacement_success_criteria or "",
        verification_method=row.replacement_verification_method or "",
        permission_level=row.replacement_permission_level,
        risk_level=row.replacement_risk_level,
        dependencies=json.loads(row.replacement_dependencies_json) if row.replacement_dependencies_json else [],
        status=ActionStatus.VALIDATED,
    )


async def apply_replan(
    proposal_id: str,
    *,
    session,
    max_replans: float | None = None,
    now: Callable[[], datetime] | None = None,
) -> ReplanResult:
    """Idempotent, restart-safe, concurrency-guarded (spec sections 50-52).
    Every downstream mutation is individually idempotent (existence checks
    / IntegrityError-tolerant), so this function is always safe to call
    again — on a crashed-and-restarted caller, a duplicate caller, or a
    caller that only wants to confirm an already-applied proposal's
    result. Only the actual PROPOSED -> APPLIED status flip is exclusive
    (spec section 51 — via ReplanProposalRepository.claim_for_apply()'s
    version guard), so two concurrent callers can both safely run this
    function on the same proposal_id and each gets a correct
    ReplanResult, but only one is ever recorded as the one that applied it.
    """
    clock = now or _default_now
    proposal_repo = ReplanProposalRepository(session)
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    budget_account_repo = BudgetAccountRepository(session)
    budget_event_repo = BudgetEventRepository(session)

    row = await proposal_repo.get(proposal_id)
    if row is None:
        raise ProposalNotFoundError(proposal_id)

    # v0.1.3.8 bug fix (found by the hostile benchmark's repeated
    # full-suite runs, reproducible ~25% of the time under real
    # concurrency): capture every scalar field this function needs as a
    # plain Python local IMMEDIATELY after loading `row`, and use ONLY
    # these locals for the rest of the function — never `row.<attr>`
    # again. `action_repo.session.rollback()` below (hit whenever two
    # concurrent callers race to create the same replacement Action —
    # exactly what test_concurrent_apply_creates_exactly_one_replacement
    # exercises) EXPIRES every ORM instance in this session's identity
    # map, `row` included. A later plain attribute read on an expired
    # instance (`row.failed_action_id`, etc.) triggers an implicit
    # lazy-refresh that requires the SQLAlchemy async greenlet bridge —
    # which is not guaranteed to be active at that point, and raised
    # `sqlalchemy.exc.MissingGreenlet` intermittently. Snapshotting the
    # values up front sidesteps the expired-attribute access entirely, and
    # is also the semantically correct thing to do for `initial_status`/
    # `initial_version` below (an optimistic-concurrency CAS must use the
    # version this call ORIGINALLY observed, never a value re-read later
    # in the same function).
    proposal_pk = row.id
    plan_id = row.plan_id
    failed_action_id = row.failed_action_id
    replacement_action_id = row.replacement_action_id
    initial_status = row.status
    initial_version = row.version

    if initial_status == ReplanProposalStatus.REJECTED:
        return ReplanResult(
            proposal_id=proposal_pk, plan_id=plan_id, old_action_id=failed_action_id,
            status=ReplanProposalStatus.REJECTED,
            reason_codes=json.loads(row.reason_codes_json) if row.reason_codes_json else [],
        )
    if initial_status == ReplanProposalStatus.CANCELLED:
        return ReplanResult(proposal_id=proposal_pk, plan_id=plan_id, old_action_id=failed_action_id, status=initial_status)

    # spec section 69: a CANCELLED plan accepts no further recovery of any
    # kind — no retry, no replan. Checked BEFORE budget consumption so a
    # doomed attempt never spends plan-level REPLANS budget.
    plan_row_check = await plan_repo.get(plan_id)
    if plan_row_check is not None and plan_row_check.status == PersistedActionPlanStatus.CANCELLED:
        await proposal_repo.update_fields(
            proposal_pk, expected_version=initial_version, status=ReplanProposalStatus.REJECTED,
            reason_codes_json=json.dumps(["PLAN_CANCELLED"]),
        )
        return ReplanResult(
            proposal_id=proposal_pk, plan_id=plan_id, old_action_id=failed_action_id,
            status=ReplanProposalStatus.REJECTED, reason_codes=["PLAN_CANCELLED"],
        )

    # --- budget: plan-scoped REPLANS (spec sections 22/28/39) ---
    if max_replans is not None:
        outcome = await reserve_and_consume(
            budget_account_repo, budget_event_repo,
            scope_type=BudgetScope.PLAN, scope_id=plan_id, budget_type=BudgetType.REPLANS,
            amount=1.0, idempotency_key=f"replan:{proposal_pk}", reason="apply_replan", default_limit=max_replans,
            now=clock,
        )
        if not outcome.granted:
            await proposal_repo.update_fields(
                proposal_pk, expected_version=initial_version, status=ReplanProposalStatus.REJECTED,
                reason_codes_json=json.dumps(["REPLAN_BUDGET_EXHAUSTED"]),
            )
            return ReplanResult(
                proposal_id=proposal_pk, plan_id=plan_id, old_action_id=failed_action_id,
                status=ReplanProposalStatus.REJECTED, reason_codes=["REPLAN_BUDGET_EXHAUSTED"],
            )

    plan_row_before = await plan_repo.get(plan_id)
    old_revision = plan_row_before.revision if plan_row_before is not None else None

    # --- idempotent creation of the replacement ActionRecord ---
    replacement_action = _replacement_action_from_row(row)
    existing_replacement = await action_repo.get(replacement_action_id)
    if existing_replacement is None:
        try:
            await action_repo.create(**action_to_record_fields(replacement_action))
        except IntegrityError:
            await action_repo.session.rollback()  # a concurrent caller created it first — fine, converge

    # --- idempotent supersede marking on the failed Action ---
    failed_row = await action_repo.get(failed_action_id)
    if failed_row is not None and failed_row.superseded_by_action_id is None:
        await action_repo.update_if_version_matches(
            failed_row.id, expected_version=failed_row.version, superseded_by_action_id=replacement_action_id
        )

    # --- idempotent dependency rewiring on every dependent Action ---
    all_actions = await load_plan_actions(action_repo, plan_id)
    for action in all_actions:
        if action.id in (failed_action_id, replacement_action_id):
            continue
        if failed_action_id not in action.dependencies:
            continue
        current_row = await action_repo.get(action.id)
        if current_row is None or failed_action_id not in json.loads(current_row.dependencies_json or "[]"):
            continue
        rewired = [replacement_action_id if d == failed_action_id else d for d in action.dependencies]
        await action_repo.update_if_version_matches(
            current_row.id, expected_version=current_row.version, dependencies_json=json.dumps(sorted(rewired))
        )

    # --- idempotent plan_hash/revision recompute ---
    loaded = await load_plan(plan_repo, action_repo, plan_id)
    plan_row, plan = loaded
    new_hash = compute_plan_hash(plan)
    if plan_row.plan_hash != new_hash:
        await plan_repo.update_if_version_matches(
            plan_id, expected_version=plan_row.version, plan_hash=new_hash, revision=plan_row.revision + 1
        )
    plan_row = await plan_repo.get(plan_id)
    new_revision = plan_row.revision

    # --- revive the plan for further orchestration (spec section 19) ---
    # A plan whose ONLY remaining work was blocked behind the now-replaced
    # failure was very likely already recomputed to FAILED/
    # PARTIALLY_COMPLETED by a prior run_plan_until_blocked() call (that
    # recompute happens unconditionally at the end of every orchestration
    # run — see action_plan_orchestrator.py). READY/WAITING_FOR_APPROVAL/
    # PARTIALLY_COMPLETED -> EXECUTING is already a legal
    # action_plan_state_machine.py transition; FAILED -> EXECUTING is NOT
    # (FAILED has no outgoing edges — a deliberate v0.1.3.6 fail-closed
    # design for the NORMAL, unauthorized case). An APPLIED ReplanProposal
    # is precisely the explicit, authorized mutation spec section 19 calls
    # for, so this bypasses assert_plan_transition() for exactly this one
    # source status, the SAME "authorized deliberate reset" reasoning
    # retry_controller.py uses to bypass action_state_machine.py for a
    # single Action — action_plan_state_machine.py itself is left
    # completely untouched by this checkpoint.
    if plan_row.status in (
        PersistedActionPlanStatus.FAILED, PersistedActionPlanStatus.READY,
        PersistedActionPlanStatus.WAITING_FOR_APPROVAL, PersistedActionPlanStatus.PARTIALLY_COMPLETED,
    ):
        await plan_repo.update_if_version_matches(
            plan_id, expected_version=plan_row.version, status=PersistedActionPlanStatus.EXECUTING,
        )
        plan_row = await plan_repo.get(plan_id)

    # --- exclusive terminal status flip (spec section 51) ---
    if initial_status == ReplanProposalStatus.PROPOSED:
        await proposal_repo.claim_for_apply(proposal_pk, expected_version=initial_version)
    final_row = await proposal_repo.get(proposal_pk)
    if final_row.applied_at is None:
        await proposal_repo.update_fields(
            final_row.id, expected_version=final_row.version, applied_at=clock(), new_plan_revision=new_revision
        )

    return ReplanResult(
        proposal_id=proposal_pk, plan_id=plan_id, old_action_id=failed_action_id,
        replacement_action_id=replacement_action_id, old_plan_revision=old_revision,
        new_plan_revision=new_revision, status=ReplanProposalStatus.APPLIED,
    )
