"""Deterministic Executive Report (v0.1.3.8, spec sections 43-45/65)."""
from __future__ import annotations

from app.decision_intelligence.executive_report import BenchmarkOverallStatus, build_executive_report
from app.decision_intelligence.plan_qa import build_qa_report
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus, Decision, DecisionStatus


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="internal", title="A",
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    fields.update(overrides)
    return Action(**fields)


def _decision(**overrides) -> Decision:
    fields = dict(project_id="p1", title="d", statement="s", comparison_ready=True, status=DecisionStatus.READY_FOR_ACTION)
    fields.update(overrides)
    return Decision(**fields)


def _report(actions, **kwargs):
    plan = ActionPlan(id="plan-1", decision_id="d1", title="t", actions=actions)
    qa = build_qa_report(plan)
    fields = dict(
        objective="obj", research_ready=True, decision=_decision(), plan_id="plan-1", plan_revision=1,
        plan_ending_status="EXECUTING", qa=qa,
    )
    fields.update(kwargs)
    return build_executive_report(**fields)


def test_all_completed_is_completed():
    report = _report([_action(status=ActionStatus.COMPLETED)])
    assert report.overall_status == BenchmarkOverallStatus.COMPLETED


def test_never_completed_while_something_is_waiting():
    report = _report([_action(status=ActionStatus.COMPLETED), _action(status=ActionStatus.WAITING_FOR_APPROVAL)])
    assert report.overall_status == BenchmarkOverallStatus.COMPLETED_WITH_REVIEW
    assert report.overall_status != BenchmarkOverallStatus.COMPLETED


def test_all_blocked_no_completion_is_blocked():
    upstream = _action(title="up", status=ActionStatus.FAILED)
    downstream = _action(title="down", dependencies=[upstream.id])
    report = _report([upstream, downstream])
    # upstream FAILED with nothing completed -> FAILED (not BLOCKED, since a
    # real failure exists) — see test below for a pure-blocked case.
    assert report.overall_status == BenchmarkOverallStatus.FAILED


def test_pure_dependency_block_with_no_failure_is_blocked():
    a1 = _action(title="a1", status=ActionStatus.WAITING_FOR_APPROVAL)
    a2 = _action(title="a2", dependencies=[a1.id])
    report = _report([a1, a2])
    assert report.overall_status == BenchmarkOverallStatus.BLOCKED


def test_summary_lines_never_claim_everything_completed_when_pending():
    report = _report([_action(status=ActionStatus.COMPLETED), _action(status=ActionStatus.WAITING_FOR_APPROVAL)])
    joined = "\n".join(report.summary_lines)
    assert "COMPLETED_WITH_REVIEW" in joined
    assert report.overall_status != BenchmarkOverallStatus.COMPLETED


def test_unauthorized_and_real_side_effect_counts_are_surfaced():
    report = _report([_action(status=ActionStatus.COMPLETED)], unauthorized_external_side_effects=0, real_p3_p4_p5_side_effects=0)
    assert report.unauthorized_external_side_effects == 0
    assert report.real_p3_p4_p5_side_effects == 0
    joined = "\n".join(report.summary_lines)
    assert "Unauthorized external side effects: 0" in joined
    assert "Real P3/P4/P5 side effects: 0" in joined
