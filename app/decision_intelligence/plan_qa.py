"""Deterministic ActionPlan QA (v0.1.3.8, spec section 42). NO LLM — reads
only durable/derived state (`Action.status`, `Action.superseded_by`,
`action_eligibility.py::evaluate_action_eligibility`, the existing
Permission Engine's authoritative `permission_level`) and classifies every
Action into one of the seven truthful outcome buckets spec section 43
requires. Never reports a WAITING_FOR_APPROVAL or BLOCKED_BY_DEPENDENCY
Action as COMPLETED — the exact "no false completion" guarantee spec
section 45 demands.

Deliberately NOT a re-invocation of the pre-existing, LLM-driven
`app/orchestration/evaluator.py` QA-agent loop (Worker -> Output -> QA
verdict): that loop belongs to the OLDER Task-based mission architecture
(v0.1.1/v0.1.2) and requires a live/mock model call per verdict. This
module answers a structurally different, code-only question — "what does
this DURABLE ActionPlan's state truthfully say happened?" — using the
v0.1.3.x contracts (`ActionEligibility`, `ActionStatus`,
`PermissionLevel`) that loop never had. See
docs/decision_intelligence.md's v0.1.3.8 section for the full rationale.
"""
from __future__ import annotations

import enum
from collections import Counter
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.database.models import PermissionLevel
from app.decision_intelligence.action_eligibility import ActionEligibility, evaluate_action_eligibility
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class PlanQAStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    BLOCKED_BY_DEPENDENCY = "BLOCKED_BY_DEPENDENCY"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"
    NOT_EXECUTED = "NOT_EXECUTED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


_TERMINAL_BAD = frozenset({ActionStatus.FAILED, ActionStatus.REJECTED})
_HUMAN_REVIEW_STATUSES = frozenset({ActionStatus.CANCELLED, ActionStatus.BLOCKED})
_BLOCKED_ELIGIBILITY = frozenset(
    {
        ActionEligibility.WAITING_FOR_DEPENDENCIES,
        ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY,
        ActionEligibility.BLOCKED_BY_REJECTED_DEPENDENCY,
    }
)


class ActionQAEntry(BaseModel):
    action_id: str
    title: str
    action_type: str
    permission_level: PermissionLevel
    status: PlanQAStatus
    detail: str = ""


class PlanQAReport(BaseModel):
    plan_id: str
    plan_revision: int
    generated_at: datetime = Field(default_factory=_default_now)
    entries: list[ActionQAEntry] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    fully_completed: bool = False
    external_action_executed: bool = False
    financial_action_executed: bool = False


def _classify(action: Action, actions_by_id: dict[str, Action]) -> tuple[PlanQAStatus, str]:
    if action.superseded_by is not None:
        return PlanQAStatus.SUPERSEDED, f"superseded by {action.superseded_by}"
    if action.status == ActionStatus.COMPLETED:
        return PlanQAStatus.COMPLETED, "durably COMPLETED and verified"
    if action.status == ActionStatus.WAITING_FOR_APPROVAL:
        return PlanQAStatus.WAITING_FOR_APPROVAL, "awaiting human approval decision"
    if action.status in _TERMINAL_BAD:
        return PlanQAStatus.FAILED, action.error or f"terminal status {action.status.value}"
    if action.status in _HUMAN_REVIEW_STATUSES:
        return PlanQAStatus.HUMAN_REVIEW, action.error or f"status {action.status.value} requires human review"

    eligibility = evaluate_action_eligibility(action, actions_by_id)
    if eligibility in _BLOCKED_ELIGIBILITY:
        return PlanQAStatus.BLOCKED_BY_DEPENDENCY, eligibility.value
    if eligibility == ActionEligibility.RECONCILIATION_REQUIRED:
        return PlanQAStatus.HUMAN_REVIEW, "reconciliation required"
    return PlanQAStatus.NOT_EXECUTED, f"status {action.status.value}, eligibility {eligibility.value}"


def build_qa_report(plan: ActionPlan, *, revision: int = 1) -> PlanQAReport:
    """Pure — takes the domain `ActionPlan` (already loaded from durable
    state by the caller, same convention as `_recompute_plan_status()`/
    `_summarize()` in action_plan_orchestrator.py) and returns a truthful
    per-Action classification plus plan-level summary flags."""
    actions_by_id = {a.id: a for a in plan.actions}
    ordered = sorted(plan.actions, key=lambda a: (a.sequence, a.id))

    entries: list[ActionQAEntry] = []
    for action in ordered:
        status, detail = _classify(action, actions_by_id)
        entries.append(
            ActionQAEntry(
                action_id=action.id, title=action.title, action_type=action.action_type,
                permission_level=action.permission_level, status=status, detail=detail,
            )
        )

    active_entries = [e for e in entries if e.status != PlanQAStatus.SUPERSEDED]
    counts = dict(Counter(e.status.value for e in entries))
    fully_completed = bool(active_entries) and all(e.status == PlanQAStatus.COMPLETED for e in active_entries)

    external_or_higher = {PermissionLevel.EXTERNAL_ACTION, PermissionLevel.FINANCIAL_ACTION, PermissionLevel.ADMIN}
    external_action_executed = any(
        e.status == PlanQAStatus.COMPLETED and e.permission_level in external_or_higher for e in entries
    )
    financial_action_executed = any(
        e.status == PlanQAStatus.COMPLETED and e.permission_level == PermissionLevel.FINANCIAL_ACTION
        for e in entries
    )

    return PlanQAReport(
        plan_id=plan.id, plan_revision=revision, entries=entries, counts=counts,
        fully_completed=fully_completed, external_action_executed=external_action_executed,
        financial_action_executed=financial_action_executed,
    )
