"""Deterministic ActionPlan QA (v0.1.3.8, spec section 42-45)."""
from __future__ import annotations

from app.database.models import PermissionLevel
from app.decision_intelligence.plan_qa import PlanQAStatus, build_qa_report
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="internal", title="A",
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    fields.update(overrides)
    return Action(**fields)


def _plan(actions: list[Action]) -> ActionPlan:
    return ActionPlan(id="plan-1", decision_id="d1", title="t", actions=actions)


def test_completed_action_reports_completed():
    plan = _plan([_action(status=ActionStatus.COMPLETED)])
    report = build_qa_report(plan)
    assert report.entries[0].status == PlanQAStatus.COMPLETED
    assert report.fully_completed is True


def test_waiting_for_approval_never_reported_completed():
    plan = _plan([_action(status=ActionStatus.WAITING_FOR_APPROVAL)])
    report = build_qa_report(plan)
    assert report.entries[0].status == PlanQAStatus.WAITING_FOR_APPROVAL
    assert report.fully_completed is False


def test_dependency_blocked_action():
    upstream = _action(title="up", status=ActionStatus.FAILED)
    downstream = _action(title="down", dependencies=[upstream.id])
    plan = _plan([upstream, downstream])
    report = build_qa_report(plan)
    by_title = {e.title: e for e in report.entries}
    assert by_title["down"].status == PlanQAStatus.BLOCKED_BY_DEPENDENCY
    assert by_title["up"].status == PlanQAStatus.FAILED


def test_superseded_action_excluded_from_fully_completed():
    replacement = _action(title="replacement", status=ActionStatus.COMPLETED)
    original = _action(title="original", status=ActionStatus.FAILED, superseded_by=replacement.id)
    plan = _plan([original, replacement])
    report = build_qa_report(plan)
    by_title = {e.title: e for e in report.entries}
    assert by_title["original"].status == PlanQAStatus.SUPERSEDED
    assert by_title["replacement"].status == PlanQAStatus.COMPLETED
    assert report.fully_completed is True  # only ACTIVE (non-superseded) entries count


def test_cancelled_and_blocked_map_to_human_review():
    plan = _plan([_action(title="c", status=ActionStatus.CANCELLED), _action(title="b", status=ActionStatus.BLOCKED)])
    report = build_qa_report(plan)
    assert all(e.status == PlanQAStatus.HUMAN_REVIEW for e in report.entries)


def test_never_started_action_is_not_executed():
    plan = _plan([_action(status=ActionStatus.PLANNED)])
    report = build_qa_report(plan)
    assert report.entries[0].status == PlanQAStatus.NOT_EXECUTED


def test_external_and_financial_action_execution_flags():
    external = _action(
        title="ext", status=ActionStatus.COMPLETED, permission_level=PermissionLevel.EXTERNAL_ACTION,
    )
    plan = _plan([external])
    report = build_qa_report(plan)
    assert report.external_action_executed is True
    assert report.financial_action_executed is False

    financial = _action(title="fin", status=ActionStatus.COMPLETED, permission_level=PermissionLevel.FINANCIAL_ACTION)
    report2 = build_qa_report(_plan([financial]))
    assert report2.financial_action_executed is True


def test_external_action_not_flagged_when_only_waiting():
    external = _action(status=ActionStatus.WAITING_FOR_APPROVAL, permission_level=PermissionLevel.EXTERNAL_ACTION)
    report = build_qa_report(_plan([external]))
    assert report.external_action_executed is False


def test_counts_reflect_every_entry_including_superseded():
    replacement = _action(title="r", status=ActionStatus.COMPLETED)
    original = _action(title="o", status=ActionStatus.FAILED, superseded_by=replacement.id)
    report = build_qa_report(_plan([original, replacement]))
    assert report.counts.get("SUPERSEDED") == 1
    assert report.counts.get("COMPLETED") == 1
