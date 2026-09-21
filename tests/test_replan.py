"""Controlled, Deterministic Replanning (v0.1.3.7, spec sections 14-22/45-52)."""
from __future__ import annotations

import asyncio

import pytest

from app.database.models import PersistedActionStatus, ReplanProposalStatus
from app.database.repositories import ActionPlanRecordRepository, ActionRecordRepository, ReplanProposalRepository
from app.decision_intelligence.action_plan_persistence import compute_plan_hash, load_plan, persist_new_plan
from app.decision_intelligence.replan import (
    ActionNotFailedError,
    FailedActionNotFoundError,
    apply_replan,
    persist_proposal,
    propose_replan,
)
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus, FailureCategory


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="will-be-set", action_type="internal", title="A",
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    fields.update(overrides)
    return Action(**fields)


def _plan(actions: list[Action], **overrides) -> ActionPlan:
    fields = dict(decision_id="dec-1", title="Test plan", actions=[])
    fields.update(overrides)
    plan = ActionPlan(**fields)
    fixed = [a.model_copy(update={"action_plan_id": plan.id}) for a in actions]
    return plan.model_copy(update={"actions": fixed})


async def _persist_plan(session, plan: ActionPlan):
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()
    return plan_repo, action_repo


async def _mark_failed(action_repo: ActionRecordRepository, action_id: str):
    row = await action_repo.get(action_id)
    await action_repo.update_if_version_matches(action_id, expected_version=row.version, status=PersistedActionStatus.FAILED, last_error="boom")
    return await action_repo.get(action_id)


class TestProposeReplanValidation:
    def test_raises_when_failed_action_not_in_plan(self):
        plan = _plan([_action()])
        stranger = _action()
        replacement = _action()
        with pytest.raises(FailedActionNotFoundError):
            propose_replan(plan, stranger, replacement)

    def test_raises_when_action_not_actually_failed(self):
        a1 = _action(status=ActionStatus.VALIDATED)
        plan = _plan([a1])
        replacement = _action(action_plan_id=plan.id)
        with pytest.raises(ActionNotFailedError):
            propose_replan(plan, plan.actions[0], replacement)

    def test_rejects_a_cycle_without_raising(self):
        a1 = _action(title="A1", status=ActionStatus.FAILED)
        a2 = _action(title="A2")
        plan = _plan([a1, a2])
        failed = plan.actions[0]
        other = plan.actions[1]
        # Replacement for A1 depends on A2, and A2 already depends on A1 —
        # would create A2 -> replacement -> A2 once rewired.
        other_with_dep = other.model_copy(update={"dependencies": [failed.id]})
        plan = plan.model_copy(update={"actions": [failed, other_with_dep]})
        replacement = _action(action_plan_id=plan.id, dependencies=[other.id])
        proposal = propose_replan(plan, failed, replacement)
        assert proposal.status == ReplanProposalStatus.REJECTED
        assert any("CYCLE_DETECTED" in code for code in proposal.reason_codes)

    def test_replacement_inherits_failed_actions_dependencies_by_default(self):
        upstream = _action(title="Upstream")
        failed = _action(title="Failed", status=ActionStatus.FAILED, dependencies=[upstream.id])
        plan = _plan([upstream, failed])
        failed = plan.actions[1]
        replacement = _action(action_plan_id=plan.id)  # no explicit dependencies
        proposal = propose_replan(plan, failed, replacement)
        assert proposal.status == ReplanProposalStatus.PROPOSED
        assert proposal.replacement_dependencies == [upstream.id]

    def test_explicit_replacement_dependencies_are_respected(self):
        failed = _action(status=ActionStatus.FAILED)
        plan = _plan([failed])
        failed = plan.actions[0]
        replacement = _action(action_plan_id=plan.id, dependencies=["custom-dep"])
        proposal = propose_replan(plan, failed, replacement)
        assert proposal.replacement_dependencies == ["custom-dep"]


class TestApplyReplan:
    async def test_full_lifecycle_rewires_dependents_and_preserves_history(self, session):
        a1 = _action(title="A1")
        a2 = _action(title="A2 (will fail)", dependencies=[a1.id])
        a3 = _action(title="A3", dependencies=[a2.id])
        plan = _plan([a1, a2, a3])
        plan_repo, action_repo = await _persist_plan(session, plan)

        a1_id, a2_id, a3_id = plan.actions[0].id, plan.actions[1].id, plan.actions[2].id
        await action_repo.update_if_version_matches(a1_id, expected_version=1, status=PersistedActionStatus.COMPLETED)
        await _mark_failed(action_repo, a2_id)

        loaded_row, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
        failed_action = next(a for a in loaded_plan.actions if a.id == a2_id)
        replacement = _action(action_plan_id=plan.id, title="A2b")

        proposal = propose_replan(loaded_plan, failed_action, replacement, reason="deterministic fixture", failure_category=FailureCategory.VALIDATION)
        assert proposal.status == ReplanProposalStatus.PROPOSED
        proposal_repo = ReplanProposalRepository(session)
        row = await persist_proposal(proposal_repo, proposal)
        await session.commit()

        result = await apply_replan(row.id, session=session)
        assert result.status == ReplanProposalStatus.APPLIED
        assert result.new_plan_revision == 2  # revision 1 -> 2

        # A1 remains COMPLETED and untouched.
        a1_row = await action_repo.get(a1_id)
        assert a1_row.status == PersistedActionStatus.COMPLETED

        # A2 (failed) is preserved as history, now superseded.
        a2_row = await action_repo.get(a2_id)
        assert a2_row.status == PersistedActionStatus.FAILED
        assert a2_row.superseded_by_action_id == replacement.id

        # A2b exists, fresh, VALIDATED — no inherited authority.
        a2b_row = await action_repo.get(replacement.id)
        assert a2b_row is not None
        assert a2b_row.status == PersistedActionStatus.VALIDATED
        assert a2b_row.approval_id is None

        # A3's dependency was rewired from A2 to A2b.
        a3_row = await action_repo.get(a3_id)
        import json

        assert json.loads(a3_row.dependencies_json) == [replacement.id]

        # Plan hash reflects the new structure.
        plan_row_after = await plan_repo.get(plan.id)
        _, plan_after = await load_plan(plan_repo, action_repo, plan.id)
        assert plan_row_after.plan_hash == compute_plan_hash(plan_after)

    async def test_apply_is_idempotent_on_duplicate_call(self, session):
        a1 = _action(status=ActionStatus.FAILED)
        plan = _plan([a1])
        plan_repo, action_repo = await _persist_plan(session, plan)
        await _mark_failed(action_repo, plan.actions[0].id)
        _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
        failed = loaded_plan.actions[0]
        replacement = _action(action_plan_id=plan.id)
        proposal = propose_replan(loaded_plan, failed, replacement)
        proposal_repo = ReplanProposalRepository(session)
        row = await persist_proposal(proposal_repo, proposal)
        await session.commit()

        first = await apply_replan(row.id, session=session)
        second = await apply_replan(row.id, session=session)
        assert first.replacement_action_id == second.replacement_action_id
        assert first.new_plan_revision == second.new_plan_revision

        # Exactly ONE replacement Action was created.
        all_rows = await action_repo.list_by_plan(plan.id)
        assert len([r for r in all_rows if r.id == replacement.id]) == 1

    async def test_concurrent_apply_creates_exactly_one_replacement(self, session_factory):
        a1 = _action(status=ActionStatus.FAILED)
        plan = _plan([a1])
        async with session_factory() as setup:
            plan_repo, action_repo = await _persist_plan(setup, plan)
            await _mark_failed(action_repo, plan.actions[0].id)
            _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
            failed = loaded_plan.actions[0]
            replacement = _action(action_plan_id=plan.id)
            proposal = propose_replan(loaded_plan, failed, replacement)
            proposal_repo = ReplanProposalRepository(setup)
            row = await persist_proposal(proposal_repo, proposal)
            await setup.commit()

        async def _apply():
            async with session_factory() as s:
                return await apply_replan(row.id, session=s)

        results = await asyncio.gather(_apply(), _apply())
        assert results[0].replacement_action_id == results[1].replacement_action_id

        async with session_factory() as check:
            rows = await ActionRecordRepository(check).list_by_plan(plan.id)
            assert len([r for r in rows if r.id == replacement.id]) == 1

    async def test_rejected_proposal_is_never_applied(self, session):
        a1 = _action(title="A1", status=ActionStatus.FAILED)
        a2 = _action(title="A2", dependencies=[a1.id])
        plan = _plan([a1, a2])
        plan_repo, action_repo = await _persist_plan(session, plan)
        failed = plan.actions[0]
        other = plan.actions[1]
        other_with_dep = other.model_copy(update={"dependencies": [failed.id]})
        cyclic_plan = plan.model_copy(update={"actions": [failed, other_with_dep]})
        replacement = _action(action_plan_id=plan.id, dependencies=[other.id])
        proposal = propose_replan(cyclic_plan, failed, replacement)
        assert proposal.status == ReplanProposalStatus.REJECTED

        proposal_repo = ReplanProposalRepository(session)
        row = await persist_proposal(proposal_repo, proposal)
        await session.commit()

        result = await apply_replan(row.id, session=session)
        assert result.status == ReplanProposalStatus.REJECTED
        assert await action_repo.get(replacement.id) is None  # never created


class TestReplanBudget:
    async def test_replan_budget_exhaustion_rejects_proposal(self, session):
        a1 = _action(status=ActionStatus.FAILED)
        plan = _plan([a1])
        plan_repo, action_repo = await _persist_plan(session, plan)
        await _mark_failed(action_repo, plan.actions[0].id)
        _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
        failed = loaded_plan.actions[0]

        proposal_repo = ReplanProposalRepository(session)
        first_replacement = _action(action_plan_id=plan.id, title="first")
        first_proposal = propose_replan(loaded_plan, failed, first_replacement)
        first_row = await persist_proposal(proposal_repo, first_proposal)
        await session.commit()
        first_result = await apply_replan(first_row.id, session=session, max_replans=1.0)
        assert first_result.status == ReplanProposalStatus.APPLIED

        # A second, independent replan proposal against the plan's REPLANS
        # budget (already exhausted at 1) must be rejected.
        _, loaded_plan_2 = await load_plan(plan_repo, action_repo, plan.id)
        second_replacement = _action(action_plan_id=plan.id, title="second")
        second_proposal = propose_replan(loaded_plan_2, failed, second_replacement)
        second_row = await persist_proposal(proposal_repo, second_proposal)
        await session.commit()
        second_result = await apply_replan(second_row.id, session=session, max_replans=1.0)
        assert second_result.status == ReplanProposalStatus.REJECTED
        assert await action_repo.get(second_replacement.id) is None
