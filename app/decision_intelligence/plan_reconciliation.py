"""Deterministic ActionPlan Reconciliation (v0.1.3.6, spec sections 26-28).
NO LLM. Delegates ALL Action-level recovery to v0.1.3.5's
reconcile_action() — never re-executes or duplicates that logic; this
module only recomputes plan-level truth from the (possibly just-recovered)
Action-level truth underneath it.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from app.database.models import PersistedActionPlanStatus
from app.database.repositories import ActionPlanRecordRepository, ActionRecordRepository
from app.decision_intelligence.action_plan_persistence import load_plan
from app.decision_intelligence.reconciliation import reconcile_action
from app.decision_intelligence.schemas import ActionPlanStatus, ActionStatus
from app.decision_intelligence.tool_adapters import ToolAdapterRegistry


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class PlanReconciliationClassification(str, enum.Enum):
    CONSISTENT_READY = "CONSISTENT_READY"
    CONSISTENT_EXECUTING = "CONSISTENT_EXECUTING"
    CONSISTENT_WAITING_FOR_APPROVAL = "CONSISTENT_WAITING_FOR_APPROVAL"
    CONSISTENT_PARTIAL = "CONSISTENT_PARTIAL"
    CONSISTENT_COMPLETED = "CONSISTENT_COMPLETED"
    CONSISTENT_FAILED = "CONSISTENT_FAILED"
    ACTION_RECONCILIATION_REQUIRED = "ACTION_RECONCILIATION_REQUIRED"
    AMBIGUOUS_PLAN_STATE = "AMBIGUOUS_PLAN_STATE"


class PlanReconciliationResult(BaseModel):
    plan_id: str
    classification: PlanReconciliationClassification
    actions_reconciled: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recovered: bool = False
    human_review_required: bool = False
    timestamp: datetime = Field(default_factory=_default_now)


_IN_PROGRESS_ACTION_STATUSES = frozenset(
    {ActionStatus.EXECUTING, ActionStatus.EXECUTION_SUCCEEDED, ActionStatus.VERIFYING, ActionStatus.VERIFIED}
)
_TERMINAL_BAD_ACTION_STATUSES = frozenset(
    {ActionStatus.FAILED, ActionStatus.REJECTED, ActionStatus.CANCELLED, ActionStatus.BLOCKED}
)


async def discover_plan_reconciliation_candidates(
    session, *, now: Callable[[], datetime] | None = None
) -> list[str]:
    """Read-only (spec section 26): identifies plans left EXECUTING/
    WAITING_FOR_APPROVAL/PARTIALLY_COMPLETED, plus any plan whose
    orchestration lease has expired. Never mutates anything; a caller must
    explicitly call reconcile_plan() for each candidate."""
    clock = now or _default_now
    plan_repo = ActionPlanRecordRepository(session)
    non_terminal = [
        PersistedActionPlanStatus.EXECUTING,
        PersistedActionPlanStatus.WAITING_FOR_APPROVAL,
        PersistedActionPlanStatus.PARTIALLY_COMPLETED,
    ]
    candidates = {row.id for row in await plan_repo.list_by_status(non_terminal)}
    stale = await plan_repo.list_stale_leases(before=clock())
    candidates.update(row.id for row in stale)
    return sorted(candidates)


async def reconcile_plan(
    plan_id: str,
    *,
    session,
    adapter_registry: ToolAdapterRegistry,
    sandbox_root: Path,
    now: Callable[[], datetime] | None = None,
) -> PlanReconciliationResult:
    """Loads durable plan + Actions, delegates uncertain (in-progress)
    Actions to reconcile_action(), then recomputes truthful plan-level
    status from the (possibly just-recovered) Action states. Never repeats
    external/side-effecting work merely because state was uncertain — that
    invariant is entirely inherited from reconcile_action() itself."""
    clock = now or _default_now
    ts = clock()
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)

    loaded = await load_plan(plan_repo, action_repo, plan_id)
    if loaded is None:
        return PlanReconciliationResult(
            plan_id=plan_id,
            classification=PlanReconciliationClassification.AMBIGUOUS_PLAN_STATE,
            issues=["no durable ActionPlanRecord found for this plan_id"],
            human_review_required=True,
            timestamp=ts,
        )
    _, plan = loaded

    if plan.status == ActionPlanStatus.COMPLETED:
        return PlanReconciliationResult(
            plan_id=plan_id, classification=PlanReconciliationClassification.CONSISTENT_COMPLETED, timestamp=ts
        )
    if plan.status in (ActionPlanStatus.FAILED, ActionPlanStatus.CANCELLED):
        return PlanReconciliationResult(
            plan_id=plan_id, classification=PlanReconciliationClassification.CONSISTENT_FAILED, timestamp=ts
        )
    if plan.status in (ActionPlanStatus.DRAFT, ActionPlanStatus.VALIDATING, ActionPlanStatus.READY):
        # READY is the actual durable "persisted but not yet started"
        # state in this checkpoint — validate_and_persist_plan() persists
        # straight to READY, never a separately-observed DRAFT/VALIDATING
        # row (spec section 43 crash window A).
        return PlanReconciliationResult(
            plan_id=plan_id, classification=PlanReconciliationClassification.CONSISTENT_READY, timestamp=ts
        )

    reconciled_ids: list[str] = []
    issues: list[str] = []
    any_blocked = False

    for action in plan.actions:
        if action.status in _IN_PROGRESS_ACTION_STATUSES:
            result = await reconcile_action(
                action.id, session=session, adapter_registry=adapter_registry, sandbox_root=sandbox_root, now=clock
            )
            reconciled_ids.append(action.id)
            if result.human_review_required and not result.recovered:
                any_blocked = True
                issues.extend(result.issues)

    # Reload fresh — reconciliation above may have advanced Action state.
    loaded_after = await load_plan(plan_repo, action_repo, plan_id)
    _, plan = loaded_after

    if any_blocked:
        return PlanReconciliationResult(
            plan_id=plan_id,
            classification=PlanReconciliationClassification.ACTION_RECONCILIATION_REQUIRED,
            actions_reconciled=reconciled_ids,
            issues=issues,
            recovered=False,
            human_review_required=True,
            timestamp=ts,
        )

    statuses = [a.status for a in plan.actions]
    completed = sum(1 for s in statuses if s == ActionStatus.COMPLETED)
    total = len(statuses)

    if total > 0 and completed == total:
        classification = PlanReconciliationClassification.CONSISTENT_COMPLETED
    elif any(s in _TERMINAL_BAD_ACTION_STATUSES for s in statuses):
        classification = (
            PlanReconciliationClassification.CONSISTENT_PARTIAL
            if completed > 0
            else PlanReconciliationClassification.CONSISTENT_FAILED
        )
    elif any(s == ActionStatus.WAITING_FOR_APPROVAL for s in statuses):
        classification = PlanReconciliationClassification.CONSISTENT_WAITING_FOR_APPROVAL
    else:
        classification = PlanReconciliationClassification.CONSISTENT_EXECUTING

    return PlanReconciliationResult(
        plan_id=plan_id,
        classification=classification,
        actions_reconciled=reconciled_ids,
        recovered=bool(reconciled_ids),
        human_review_required=False,
        timestamp=ts,
    )
