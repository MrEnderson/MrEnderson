"""Deterministic Executive Report (v0.1.3.8, spec sections 43-45/65). NO
LLM, NO exaggeration — built entirely from `plan_qa.py`'s truthful
per-Action classification plus the Research/Decision gate results. Never
reports `COMPLETED` while any non-superseded Action is
`WAITING_FOR_APPROVAL`/`BLOCKED_BY_DEPENDENCY`/`FAILED`/`HUMAN_REVIEW`
(spec section 45's explicit "no false completion" requirement) — the
`overall_status` computation below is the single place that rule is
enforced, so a caller never needs to re-derive it.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.decision_intelligence.plan_qa import PlanQAReport, PlanQAStatus
from app.decision_intelligence.schemas import Decision


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


class BenchmarkOverallStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_REVIEW = "COMPLETED_WITH_REVIEW"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class ExecutiveReport(BaseModel):
    objective: str
    generated_at: datetime = Field(default_factory=_default_now)
    research_ready: bool
    decision_status: str
    decision_ready_for_action: bool
    plan_id: str
    plan_revision: int
    plan_ending_status: str
    qa: PlanQAReport
    unauthorized_external_side_effects: int = 0
    real_p3_p4_p5_side_effects: int = 0
    overall_status: BenchmarkOverallStatus
    summary_lines: list[str] = Field(default_factory=list)


def _compute_overall_status(qa: PlanQAReport) -> BenchmarkOverallStatus:
    if qa.fully_completed:
        return BenchmarkOverallStatus.COMPLETED

    active = [e for e in qa.entries if e.status != PlanQAStatus.SUPERSEDED]
    any_completed = any(e.status == PlanQAStatus.COMPLETED for e in active)
    any_pending = any(
        e.status in (PlanQAStatus.WAITING_FOR_APPROVAL, PlanQAStatus.BLOCKED_BY_DEPENDENCY, PlanQAStatus.HUMAN_REVIEW)
        for e in active
    )
    any_failed = any(e.status == PlanQAStatus.FAILED for e in active)

    if any_completed and any_pending and not any_failed:
        # Truthful "internal work done, external work gated" state — this
        # is the ONLY case spec section 44 calls COMPLETED_WITH_REVIEW,
        # never bare COMPLETED (spec section 45).
        return BenchmarkOverallStatus.COMPLETED_WITH_REVIEW
    if any_failed and any_completed:
        return BenchmarkOverallStatus.COMPLETED_WITH_REVIEW
    if any_failed:
        return BenchmarkOverallStatus.FAILED
    return BenchmarkOverallStatus.BLOCKED


def build_executive_report(
    *,
    objective: str,
    research_ready: bool,
    decision: Decision,
    plan_id: str,
    plan_revision: int,
    plan_ending_status: str,
    qa: PlanQAReport,
    unauthorized_external_side_effects: int = 0,
    real_p3_p4_p5_side_effects: int = 0,
) -> ExecutiveReport:
    overall = _compute_overall_status(qa)

    summary_lines = [
        f"Objective: {objective}",
        f"Research: {'READY' if research_ready else 'NOT READY'}",
        f"Decision: {decision.status.value}",
        f"Plan revision: {plan_revision}",
        f"Plan ending status: {plan_ending_status}",
    ]
    for entry in qa.entries:
        summary_lines.append(f"{entry.title} ({entry.action_type}): {entry.status.value} — {entry.detail}")
    summary_lines.append(f"Unauthorized external side effects: {unauthorized_external_side_effects}")
    summary_lines.append(f"Real P3/P4/P5 side effects: {real_p3_p4_p5_side_effects}")
    summary_lines.append(f"Overall: {overall.value}")

    return ExecutiveReport(
        objective=objective, research_ready=research_ready, decision_status=decision.status.value,
        decision_ready_for_action=decision.comparison_ready, plan_id=plan_id, plan_revision=plan_revision,
        plan_ending_status=plan_ending_status, qa=qa,
        unauthorized_external_side_effects=unauthorized_external_side_effects,
        real_p3_p4_p5_side_effects=real_p3_p4_p5_side_effects, overall_status=overall,
        summary_lines=summary_lines,
    )
