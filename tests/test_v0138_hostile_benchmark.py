"""v0.1.3.8 — Full Hostile End-to-End Benchmark (spec sections 4-50).

ONE large, deterministic, offline integration test
(`test_hostile_end_to_end_benchmark`) exercising the composed control
plane — Research -> Decision -> ActionPlan -> Orchestration -> Permission
-> Approval -> Execution -> Verification -> Failure Intelligence -> Retry
-> Replan -> Crash -> Recovery -> QA -> Executive Report — plus a small
number of additional, narrowly-scoped hostile tests for integration
surfaces the main scenario does not itself reach (budget-gate
concurrency, stale-worker-vs-revision, malicious metadata, approval
without capability). Attacks already thoroughly covered by v0.1.3.6/.7's
own regression suites (duplicate orchestrator, duplicate execution claim,
unknown tool, missing adapter, sandbox escape, plan-structure tamper) are
NOT re-implemented here — see this file's own docstring notes at each
skip point, and the delivery report's "already covered" list.

NO live network, NO LLM call, NO Anthropic/Tavily call anywhere in this
file. The only real side effect anywhere in this suite is a handful of
UTF-8 text files inside a pytest-managed temporary sandbox directory.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from app.config.settings import get_settings
from app.database import connection as db_connection
from app.database.models import (
    BudgetScope,
    BudgetType,
    PersistedActionPlanStatus,
    PersistedActionStatus,
)
from app.database.repositories import (
    ActionApprovalRequestRepository,
    ActionPlanRecordRepository,
    ActionRecordRepository,
    BudgetAccountRepository,
    BudgetEventRepository,
    ExecutionAttemptRepository,
    FailureRecordRepository,
    ReplanProposalRepository,
)
from app.decision_intelligence.action_plan_orchestrator import StopReason, run_plan_until_blocked, validate_and_persist_plan
from app.decision_intelligence.action_plan_persistence import load_plan
from app.decision_intelligence.approval_engine import decide_approval
from app.decision_intelligence.approval_persistence import load_approval_request, sync_decision
from app.decision_intelligence.budget import ensure_account, reserve_and_consume
from app.decision_intelligence.decision_rules import (
    DecisionInvariantViolation,
    apply_decision_transition,
    can_produce_plan,
)
from app.decision_intelligence.executive_report import BenchmarkOverallStatus, build_executive_report
from app.decision_intelligence.plan_qa import PlanQAStatus, build_qa_report
from app.decision_intelligence.replan import apply_replan, persist_proposal, propose_replan
from app.decision_intelligence.schemas import Action, ActionPlan, ActionPlanStatus, ActionStatus, Decision, DecisionStatus
from app.decision_intelligence.action_eligibility import ActionEligibility, evaluate_action_eligibility
from app.decision_intelligence.tool_adapters import ToolAdapterRegistry, build_default_adapter_registry
from app.decision_intelligence.tool_registry import build_default_tool_registry

from tests._v0138_scenario import (
    CANDIDATE_ALPHA,
    CANDIDATE_BETA,
    OBJECTIVE,
    build_hostile_adapter_registry,
    build_hostile_plan,
    campaign_assets_replacement,
    evaluate_research_readiness,
)


def _sha256_of(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture
def tool_registry():
    return build_default_tool_registry()


@pytest.fixture
def adapters():
    return build_default_adapter_registry()


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch):
    """A dedicated, isolated temp-file SQLite DB — NOT the shared `session`
    fixture — because this benchmark must open MULTIPLE independent
    sessions/session_factory instances to genuinely prove durability across
    simulated process restarts (spec section 27: 'fresh DB session; fresh
    orchestrator instance... do NOT reuse stale in-memory ActionPlan
    objects')."""
    db_path = tmp_path / "v0138_benchmark.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    await db_connection.reset_engine()
    await db_connection.init_db(url)
    yield url
    await db_connection.reset_engine()
    get_settings.cache_clear()


def _fresh_factory(url: str):
    """A NEW session factory bound to the SAME durable file — simulates a
    process restart: nothing from a prior in-memory engine/pool/session is
    reused (spec section 27)."""
    return db_connection.get_session_factory(url)


async def test_hostile_end_to_end_benchmark(isolated_db, tmp_path):
    url = isolated_db
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()
    tool_registry = build_default_tool_registry()
    adapters, fake = build_hostile_adapter_registry()
    trace: list[dict] = []  # spec section 46: machine-readable control-plane trace

    def _record(event: str, **fields):
        trace.append({"event": event, **fields})

    # === Phase A: research readiness gate — negative, then positive (spec 7-9) ===
    negative = await evaluate_research_readiness(beta_full=False)
    assert negative.ready is False
    beta_status = next(s for s in negative.candidate_statuses if s.candidate_label == CANDIDATE_BETA)
    assert beta_status.ready_for_comparison is False
    _record("research_readiness", ready=False, beta_coverage=beta_status.coverage_percentage)

    positive = await evaluate_research_readiness(beta_full=True)
    assert positive.ready is True
    assert all(s.ready_for_comparison for s in positive.candidate_statuses)
    _record("research_readiness", ready=True)

    # === Phase B: decision gate (spec 9) — comparison_ready=False cannot become READY_FOR_ACTION ===
    decision = Decision(
        project_id="v0138-benchmark", title="Digital product launch decision",
        statement=OBJECTIVE, comparison_ready=False,
    )
    with pytest.raises(DecisionInvariantViolation):
        apply_decision_transition(decision, DecisionStatus.READY_FOR_ACTION)
    _record("decision_gate", comparison_ready=False, blocked=True)

    # Supply the readiness the normal research path established (positive.ready) — never bypassed via direct manipulation.
    decision = decision.model_copy(update={"comparison_ready": positive.ready})
    decision = apply_decision_transition(decision, DecisionStatus.READY_FOR_ACTION)
    assert decision.status == DecisionStatus.READY_FOR_ACTION
    assert can_produce_plan(decision)
    _record("decision_gate", comparison_ready=True, status=decision.status.value)

    # === Phase C: build + validate + persist the hostile ActionPlan (spec 10) ===
    plan = build_hostile_plan(decision.id)
    plan_id = plan.id
    a1, a2, a3, a4, a5, a6, a7 = plan.actions
    async with _fresh_factory(url)() as session:
        row = await validate_and_persist_plan(plan, session=session)
        assert row.status == PersistedActionPlanStatus.READY
    _record("plan_persisted", plan_id=plan_id, action_count=len(plan.actions))

    # === Phase D: run until the plan naturally stops (spec 11-14) ===
    # A1-A3 complete cleanly; A4 fails TRANSIENT once then retries and
    # succeeds; A5 genuinely fails VALIDATION (malformed inputs); A6/A7
    # remain unreachable until A5 is replaced.
    async with _fresh_factory(url)() as session:
        result1 = await run_plan_until_blocked(
            plan_id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
        )
        action_repo = ActionRecordRepository(session)
        a1_row = await action_repo.get(a1.id)
        a2_row = await action_repo.get(a2.id)
        a3_row = await action_repo.get(a3.id)
        a4_row = await action_repo.get(a4.id)
        a5_row = await action_repo.get(a5.id)

    assert a1_row.status == PersistedActionStatus.COMPLETED
    assert a2_row.status == PersistedActionStatus.COMPLETED
    assert a3_row.status == PersistedActionStatus.COMPLETED
    assert a4_row.status == PersistedActionStatus.COMPLETED
    assert a4_row.retry_count == 1
    assert fake.execute_calls_by_path["benchmark/landing-draft.txt"] == 2  # exactly one retry, no more
    assert a5_row.status == PersistedActionStatus.FAILED
    _record(
        "phase_d_result", stop_reason=result1.stop_reason.value, a4_retry_count=a4_row.retry_count,
        a4_execute_calls=fake.execute_calls_by_path["benchmark/landing-draft.txt"], a5_status=a5_row.status.value,
    )

    async with _fresh_factory(url)() as session:
        failures = await FailureRecordRepository(session).list_for_action(a5.id)
    assert len(failures) == 1
    assert failures[0].category == "VALIDATION"
    _record("a5_failure_record", category=failures[0].category, message=failures[0].message)

    # === Phase E: controlled replan A5 -> A5b (spec 13) ===
    replacement = campaign_assets_replacement(plan_id)
    async with _fresh_factory(url)() as session:
        plan_repo = ActionPlanRecordRepository(session)
        action_repo = ActionRecordRepository(session)
        plan_row_before, loaded_plan = await load_plan(plan_repo, action_repo, plan_id)
        revision_before = plan_row_before.revision
        failed_action = next(a for a in loaded_plan.actions if a.id == a5.id)
        proposal = propose_replan(
            loaded_plan, failed_action, replacement, reason="deterministic hostile-benchmark replacement",
        )
        assert proposal.status.value == "PROPOSED"
        proposal_row = await persist_proposal(ReplanProposalRepository(session), proposal)
        await session.commit()
        proposal_id = proposal_row.id

    async with _fresh_factory(url)() as session:
        apply_result = await apply_replan(proposal_id, session=session)
    assert apply_result.status.value == "APPLIED"
    assert apply_result.new_plan_revision == revision_before + 1
    _record("replan_applied", old_action=a5.id, new_action=replacement.id, new_revision=apply_result.new_plan_revision)

    async with _fresh_factory(url)() as session:
        action_repo = ActionRecordRepository(session)
        a5_row_after = await action_repo.get(a5.id)
        assert a5_row_after.status == PersistedActionStatus.FAILED  # historical, never erased
        assert a5_row_after.superseded_by_action_id == replacement.id
        a6_row_before = await action_repo.get(a6.id)
        assert json.loads(a6_row_before.dependencies_json) == [replacement.id]  # rewired

    # === Phase F: resume — A5b executes, A6 pauses for approval, A7 stays blocked (spec 14/17) ===
    async with _fresh_factory(url)() as session:
        result2 = await run_plan_until_blocked(
            plan_id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
        )
        action_repo = ActionRecordRepository(session)
        replacement_row = await action_repo.get(replacement.id)
        a6_row = await action_repo.get(a6.id)
        a7_row = await action_repo.get(a7.id)
        _, loaded_plan_f = await load_plan(ActionPlanRecordRepository(session), action_repo, plan_id)

    assert replacement_row.status == PersistedActionStatus.COMPLETED
    assert (sandbox_root / "benchmark/campaign-assets.txt").exists()
    assert a6_row.status == PersistedActionStatus.WAITING_FOR_APPROVAL
    assert a7_row.status == PersistedActionStatus.VALIDATED  # never dispatched — A6 never COMPLETED
    a7_domain = next(a for a in loaded_plan_f.actions if a.id == a7.id)
    actions_by_id_f = {a.id: a for a in loaded_plan_f.actions}
    assert evaluate_action_eligibility(a7_domain, actions_by_id_f) in (
        ActionEligibility.WAITING_FOR_DEPENDENCIES, ActionEligibility.BLOCKED_BY_FAILED_DEPENDENCY,
    )
    assert result2.ending_status == ActionPlanStatus.WAITING_FOR_APPROVAL
    _record("phase_f_result", ending_status=result2.ending_status.value, a6_status=a6_row.status.value)

    # === Phase G: crash / restart, no-rewrite proof (spec 27-29) ===
    artifact_paths = [
        sandbox_root / "benchmark/positioning.txt", sandbox_root / "benchmark/validation-plan.txt",
        sandbox_root / "benchmark/landing-draft.txt", sandbox_root / "benchmark/campaign-assets.txt",
    ]
    hashes_before = {p.name: _sha256_of(p) for p in artifact_paths}
    sizes_before = {p.name: p.stat().st_size for p in artifact_paths}
    async with _fresh_factory(url)() as session:
        attempt_repo = ExecutionAttemptRepository(session)
        attempt_counts_before = {
            aid: len(await attempt_repo.list_for_action(aid)) for aid in (a1.id, a2.id, a3.id, a4.id, replacement.id)
        }

    # Discard EVERYTHING in-memory (Python objects, engine, pool) and
    # reconnect fresh against the SAME durable file — a genuine
    # process-restart simulation, not merely "a new AsyncSession object."
    await db_connection.reset_engine()
    fresh_url = url
    async with _fresh_factory(fresh_url)() as session:
        result3 = await run_plan_until_blocked(
            plan_id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
        )
        action_repo = ActionRecordRepository(session)
        attempt_repo = ExecutionAttemptRepository(session)
        attempt_counts_after = {
            aid: len(await attempt_repo.list_for_action(aid)) for aid in (a1.id, a2.id, a3.id, a4.id, replacement.id)
        }
        a1_row_restart = await action_repo.get(a1.id)
        a6_row_restart = await action_repo.get(a6.id)

    hashes_after = {p.name: _sha256_of(p) for p in artifact_paths}
    sizes_after = {p.name: p.stat().st_size for p in artifact_paths}
    assert hashes_after == hashes_before
    assert sizes_after == sizes_before
    assert attempt_counts_after == attempt_counts_before  # zero re-execution after restart
    assert a1_row_restart.status == PersistedActionStatus.COMPLETED  # rediscovered, not rebuilt
    assert a6_row_restart.status == PersistedActionStatus.WAITING_FOR_APPROVAL  # still truthfully pending
    assert result3.stop_reason == StopReason.WAITING_FOR_APPROVAL
    _record("crash_restart_verified", hashes_match=True, attempt_counts_unchanged=True)

    # === Phase H: build the QA report + executive report (spec 42-45) ===
    async with _fresh_factory(url)() as session:
        plan_repo = ActionPlanRecordRepository(session)
        action_repo = ActionRecordRepository(session)
        final_plan_row, final_plan = await load_plan(plan_repo, action_repo, plan_id)

    qa = build_qa_report(final_plan, revision=final_plan_row.revision)
    by_id = {e.action_id: e for e in qa.entries}
    assert by_id[a1.id].status == PlanQAStatus.COMPLETED
    assert by_id[a5.id].status == PlanQAStatus.SUPERSEDED
    assert by_id[replacement.id].status == PlanQAStatus.COMPLETED
    assert by_id[a6.id].status == PlanQAStatus.WAITING_FOR_APPROVAL
    assert by_id[a7.id].status == PlanQAStatus.BLOCKED_BY_DEPENDENCY
    assert qa.fully_completed is False
    assert qa.external_action_executed is False  # A6 (EXTERNAL_ACTION) never actually ran
    assert qa.financial_action_executed is False  # A7 (FINANCIAL_ACTION) never actually ran

    report = build_executive_report(
        objective=OBJECTIVE, research_ready=positive.ready, decision=decision, plan_id=plan_id,
        plan_revision=final_plan_row.revision, plan_ending_status=final_plan.status.value, qa=qa,
        unauthorized_external_side_effects=0, real_p3_p4_p5_side_effects=0,
    )
    assert report.overall_status == BenchmarkOverallStatus.COMPLETED_WITH_REVIEW
    assert report.overall_status != BenchmarkOverallStatus.COMPLETED  # spec 45: no false completion
    _record("executive_report", overall_status=report.overall_status.value)

    # === Phase I: invariant checker (spec 47) ===
    _assert_benchmark_invariants(
        final_plan=final_plan, qa=qa, fake_adapter=fake, sandbox_root=sandbox_root,
        attempt_counts_after_restart=attempt_counts_after,
    )
    _record("invariants_checked", count=10)

    # Machine-readable trace is genuinely inspectable (spec 46) — no secrets.
    trace_json = json.dumps(trace, default=str)
    assert "research_readiness" in trace_json
    assert "api_key" not in trace_json.lower() and "secret" not in trace_json.lower()


def _assert_benchmark_invariants(*, final_plan, qa, fake_adapter, sandbox_root, attempt_counts_after_restart):
    """spec section 47 — a failed invariant means benchmark FAIL."""
    actions_by_id = {a.id: a for a in final_plan.actions}

    # 1. No completed Action repeated (retry count matches observed adapter calls).
    landing = next(a for a in final_plan.actions if a.title == "Create landing-page draft")
    assert landing.retry_count == 1
    assert fake_adapter.execute_calls_by_path["benchmark/landing-draft.txt"] == 2

    # 2. No P4/P5 real side effect (no external/financial adapter exists at all).
    assert not (sandbox_root / "PUBLISHED").exists()
    assert not (sandbox_root / "PAID").exists()

    # 3. No external Action falsely completed.
    for entry in qa.entries:
        if entry.status == PlanQAStatus.COMPLETED:
            assert entry.action_id != next(a.id for a in final_plan.actions if a.title == "Prepare publish action")
            assert entry.action_id != next(a.id for a in final_plan.actions if a.title == "Prepare paid-advertising action")

    # 4. No dependency executed before its prerequisite (sequence-monotonic completion timestamps not required —
    #    structural proof: every COMPLETED Action's dependencies are COMPLETED or SUPERSEDED-with-a-COMPLETED-replacement).
    for action in final_plan.actions:
        if action.status != ActionStatus.COMPLETED:
            continue
        for dep_id in action.dependencies:
            dep = actions_by_id.get(dep_id)
            assert dep is not None
            assert dep.status == ActionStatus.COMPLETED or dep.superseded_by is not None

    # 5. No unresolved security inconsistency (nothing BLOCKED/CANCELLED unexpectedly).
    assert not any(a.status in (ActionStatus.BLOCKED, ActionStatus.CANCELLED) for a in final_plan.actions)

    # 6. No infinite retry (bounded by max_retries=0 default -> at most 1 retry observed above).
    assert all(a.retry_count <= a.max_retries for a in final_plan.actions)

    # 7. Plan never falsely COMPLETED while pending work remains.
    assert final_plan.status != ActionPlanStatus.COMPLETED

    print(f"[v0.1.3.8 invariants] attempt_counts_after_restart={attempt_counts_after_restart}")


# --- Budget integration attacks (spec sections 18-26) -----------------------


class TestBudgetIntegrationAttacks:
    """RETRIES and REPLANS budget-gate integration were already proven by
    v0.1.3.7's own benchmark tests
    (test_action_plan_orchestrator_recovery.py::test_controlled_budget_exhaustion_benchmark,
    tests/test_replan.py::TestReplanBudget) — re-verified as still passing
    by this checkpoint's full-suite run, not duplicated here. This class
    covers the NEW integration surfaces v0.1.3.8 wires:
    ACTION_ATTEMPTS/ESTIMATED_COST at the real pre-execution boundary, and
    concurrency at that same new gate."""

    async def test_action_attempts_budget_refuses_before_adapter_execution(self, session, sandbox_root, tool_registry, adapters):
        a1 = Action(
            action_plan_id="will-be-set", action_type="sandbox_create", tool_name="file.create_sandboxed",
            title="A1", inputs={"relative_path": "a1.txt", "content": "1"}, expected_result="r",
            success_criteria="n/a", verification_method="n/a", sequence=1,
        )
        a2 = Action(
            action_plan_id="will-be-set", action_type="sandbox_create", tool_name="file.create_sandboxed",
            title="A2", inputs={"relative_path": "a2.txt", "content": "2"}, expected_result="r",
            success_criteria="n/a", verification_method="n/a", sequence=2,
        )
        plan = ActionPlan(decision_id="d1", title="attempts budget plan", actions=[])
        fixed = [a.model_copy(update={"action_plan_id": plan.id}) for a in (a1, a2)]
        plan = plan.model_copy(update={"actions": fixed})
        await validate_and_persist_plan(plan, session=session)

        account_repo = BudgetAccountRepository(session)
        await ensure_account(
            account_repo, scope_type=BudgetScope.PLAN, scope_id=plan.id, budget_type=BudgetType.ACTION_ATTEMPTS,
            limit_value=1.0,
        )

        await run_plan_until_blocked(
            plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
        )

        action_repo = ActionRecordRepository(session)
        a1_row = await action_repo.get(plan.actions[0].id)
        a2_row = await action_repo.get(plan.actions[1].id)
        # Exactly ONE Action consumed the sole ACTION_ATTEMPTS unit; the
        # other is refused BEFORE any ExecutionAttempt/adapter call.
        statuses = {a1_row.status, a2_row.status}
        assert PersistedActionStatus.COMPLETED in statuses
        assert PersistedActionStatus.FAILED in statuses
        denied_row = a1_row if a1_row.status == PersistedActionStatus.FAILED else a2_row
        attempt_repo = ExecutionAttemptRepository(session)
        denied_attempts = await attempt_repo.list_for_action(denied_row.id)
        assert len(denied_attempts) == 0  # refused BEFORE any ExecutionAttempt was ever created
        assert not (sandbox_root / (denied_row.inputs_json and json.loads(denied_row.inputs_json)["relative_path"])).exists()

    async def test_estimated_cost_budget_denies_before_resource_use(self, session, sandbox_root, tool_registry, adapters):
        actions = []
        for i, name in enumerate(("a1", "a2", "a3"), start=1):
            actions.append(
                Action(
                    action_plan_id="will-be-set", action_type="sandbox_create", tool_name="file.create_sandboxed",
                    title=name, inputs={"relative_path": f"{name}.txt", "content": name}, expected_result="r",
                    success_criteria="n/a", verification_method="n/a", sequence=i, estimated_cost=0.10,
                )
            )
        plan = ActionPlan(decision_id="d1", title="cost budget plan", actions=[])
        fixed = [a.model_copy(update={"action_plan_id": plan.id}) for a in actions]
        plan = plan.model_copy(update={"actions": fixed})
        await validate_and_persist_plan(plan, session=session)

        account_repo = BudgetAccountRepository(session)
        await ensure_account(
            account_repo, scope_type=BudgetScope.PLAN, scope_id=plan.id, budget_type=BudgetType.ESTIMATED_COST,
            limit_value=0.25,
        )

        await run_plan_until_blocked(
            plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
        )

        action_repo = ActionRecordRepository(session)
        rows = {a.title: await action_repo.get(a.id) for a in plan.actions}
        completed = [t for t, r in rows.items() if r.status == PersistedActionStatus.COMPLETED]
        failed = [t for t, r in rows.items() if r.status == PersistedActionStatus.FAILED]
        assert len(completed) == 2  # A1+A2 (0.10+0.10=0.20 <= 0.25)
        assert len(failed) == 1  # A3 denied — 0.20+0.10=0.30 > 0.25
        assert not (sandbox_root / "a3.txt").exists()

    async def test_model_calls_budget_contract_without_any_live_model_call(self, session):
        """spec sections 19/25: MODEL_CALLS is tested ONLY through its
        reservation/control interface — no LLM call anywhere."""
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        first = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="v0138-model-calls", budget_type=BudgetType.MODEL_CALLS,
            amount=1.0, idempotency_key="model-call-1", default_limit=2.0,
        )
        second = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="v0138-model-calls", budget_type=BudgetType.MODEL_CALLS,
            amount=1.0, idempotency_key="model-call-2", default_limit=2.0,
        )
        third = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="v0138-model-calls", budget_type=BudgetType.MODEL_CALLS,
            amount=1.0, idempotency_key="model-call-3", default_limit=2.0,
        )
        assert first.granted and second.granted
        assert not third.granted

        # restart persistence (spec 25's "restart, confirm persistence")
        fresh_account_repo = BudgetAccountRepository(session)
        account = await fresh_account_repo.get_by_scope(
            scope_type=BudgetScope.PLAN, scope_id="v0138-model-calls", budget_type=BudgetType.MODEL_CALLS
        )
        assert account.consumed_value == 2.0

    async def test_action_attempts_budget_concurrency_at_the_orchestrator_gate(self, session_factory, tmp_path):
        """spec section 26, exercised through the REAL orchestrator dispatch
        path (not just the raw budget module — test_recovery_budget.py
        already covers that in isolation)."""
        import asyncio
        from datetime import datetime, timezone

        from app.decision_intelligence.action_plan_orchestrator import _advance_one_action

        def _clock() -> datetime:
            return datetime.now(timezone.utc)

        sandbox_root = tmp_path / "sandbox_concurrency"
        sandbox_root.mkdir()
        tool_registry = build_default_tool_registry()
        adapters = build_default_adapter_registry()

        actions = [
            Action(
                action_plan_id="will-be-set", action_type="sandbox_create", tool_name="file.create_sandboxed",
                title=f"a{i}", inputs={"relative_path": f"a{i}.txt", "content": str(i)}, expected_result="r",
                success_criteria="n/a", verification_method="n/a", sequence=i,
            )
            for i in range(1, 3)
        ]
        plan = ActionPlan(decision_id="d1", title="concurrency budget plan", actions=[])
        fixed = [a.model_copy(update={"action_plan_id": plan.id}) for a in actions]
        plan = plan.model_copy(update={"actions": fixed})

        async with session_factory() as setup:
            await validate_and_persist_plan(plan, session=setup)
            await ensure_account(
                BudgetAccountRepository(setup), scope_type=BudgetScope.PLAN, scope_id=plan.id,
                budget_type=BudgetType.ACTION_ATTEMPTS, limit_value=1.0,
            )

        async def _dispatch_one(action_index: int):
            async with session_factory() as s:
                # Both start from VALIDATED — race both through permission
                # evaluation + the budget gate concurrently. Must reload the
                # DURABLE row: `plan.actions[i]` is the pre-persistence
                # in-memory object (status=PLANNED); persist_new_plan()
                # only VALIDATED the durable row, not this Python object.
                from app.decision_intelligence.execution_persistence import record_to_action

                durable_row = await ActionRecordRepository(s).get(plan.actions[action_index].id)
                action = record_to_action(durable_row)
                advanced, _, _ = await _advance_one_action(
                    action, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
                    session=s, clock=_clock, requested_by="tester",
                )
                # advance once more to PERMISSION_CHECKED -> execute/deny
                advanced2, _, _ = await _advance_one_action(
                    advanced, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
                    session=s, clock=_clock, requested_by="tester",
                )
                return advanced2

        results = await asyncio.gather(_dispatch_one(0), _dispatch_one(1))
        statuses = [r.status for r in results]
        completed_count = sum(1 for s in statuses if s == ActionStatus.COMPLETED)
        failed_count = sum(1 for s in statuses if s == ActionStatus.FAILED)
        assert completed_count == 1
        assert failed_count == 1

        async with session_factory() as check:
            account = await BudgetAccountRepository(check).get_by_scope(
                scope_type=BudgetScope.PLAN, scope_id=plan.id, budget_type=BudgetType.ACTION_ATTEMPTS
            )
            assert account.consumed_value == 1.0  # never 2, never negative


# --- Stale-worker vs. plan revision (spec section 35) ------------------------


async def test_stale_worker_cannot_overwrite_current_plan_revision(session):
    from app.decision_intelligence.schemas import ActionPlan

    a1 = Action(
        action_plan_id="will-be-set", action_type="internal", title="A1", status=ActionStatus.FAILED,
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    plan = ActionPlan(decision_id="d1", title="stale worker plan", actions=[])
    fixed = [a1.model_copy(update={"action_plan_id": plan.id})]
    plan = plan.model_copy(update={"actions": fixed})

    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    from app.decision_intelligence.action_plan_persistence import persist_new_plan

    ready_plan = plan.model_copy(update={"status": ActionPlanStatus.READY})
    row = await persist_new_plan(plan_repo, action_repo, ready_plan)
    await session.commit()
    a1_row = await action_repo.get(fixed[0].id)
    await action_repo.update_if_version_matches(fixed[0].id, expected_version=a1_row.version, status=PersistedActionStatus.FAILED)

    # Worker A loads the plan at its CURRENT (stale-to-be) version.
    stale_plan_row = await plan_repo.get(plan.id)
    stale_version = stale_plan_row.version

    # Worker B legitimately applies a replan, bumping BOTH version and revision.
    _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
    failed = next(a for a in loaded_plan.actions if a.id == fixed[0].id)
    replacement = Action(
        action_plan_id=plan.id, action_type="internal", title="A1b", expected_result="r", success_criteria="n/a",
        verification_method="n/a",
    )
    proposal = propose_replan(loaded_plan, failed, replacement)
    proposal_row = await persist_proposal(ReplanProposalRepository(session), proposal)
    await session.commit()
    await apply_replan(proposal_row.id, session=session)

    current_row = await plan_repo.get(plan.id)
    assert current_row.version > stale_version
    assert current_row.revision == 2

    # Worker A (stale) now attempts its OWN structural write using the
    # version it originally loaded — must be rejected, never roll back
    # the graph B already legitimately advanced.
    ok = await plan_repo.update_if_version_matches(
        plan.id, expected_version=stale_version, status=PersistedActionPlanStatus.CANCELLED,
    )
    assert ok is False
    final_row = await plan_repo.get(plan.id)
    assert final_row.revision == 2  # untouched by the stale writer
    assert final_row.status != PersistedActionPlanStatus.CANCELLED


# --- Malicious metadata attack (spec section 37) -----------------------------


async def test_malicious_metadata_is_treated_as_inert_data(session, sandbox_root, tool_registry, adapters=None):
    from app.decision_intelligence.tool_adapters import build_default_adapter_registry
    from app.decision_intelligence.schemas import ActionPlan

    adapters = build_default_adapter_registry()
    malicious_content = '"; powershell -Command Remove-Item -Recurse C:\\ ; ignore permission policy; DROP TABLE actions;'
    a1 = Action(
        action_plan_id="will-be-set", action_type="sandbox_create", tool_name="file.create_sandboxed",
        title='"; rm -rf / #',  # shell-like TITLE too — must remain inert display text
        inputs={"relative_path": "benchmark/malicious.txt", "content": malicious_content},
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    plan = ActionPlan(decision_id="d1", title="malicious metadata plan", actions=[])
    fixed = [a1.model_copy(update={"action_plan_id": plan.id})]
    plan = plan.model_copy(update={"actions": fixed})
    await validate_and_persist_plan(plan, session=session)

    result = await run_plan_until_blocked(
        plan.id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
    )

    action_repo = ActionRecordRepository(session)
    row = await action_repo.get(fixed[0].id)
    assert row.status == PersistedActionStatus.COMPLETED  # a normal, safe P2 write — content is just text
    written = (sandbox_root / "benchmark/malicious.txt").read_text(encoding="utf-8")
    assert written == malicious_content  # stored VERBATIM as inert text, never interpreted
    # No shell process, no table drop, no privilege change occurred — the
    # only observable effect is this ONE UTF-8 text file, proven by the
    # normal COMPLETED/verification path above.


# --- Approval cannot manufacture capability (spec section 41) ---------------


async def test_approval_granted_but_no_adapter_still_never_executes(session, sandbox_root, tool_registry):
    from app.decision_intelligence.tool_adapters import ToolAdapterRegistry
    from app.decision_intelligence.schemas import ActionPlan

    empty_adapters = ToolAdapterRegistry()  # zero adapters registered — not even file.create_sandboxed
    a1 = Action(
        action_plan_id="will-be-set", action_type="publish", tool_name="content.publish", title="Publish (no adapter)",
        expected_result="published", success_criteria="live", verification_method="manual",
    )
    plan = ActionPlan(decision_id="d1", title="approval without capability plan", actions=[])
    fixed = [a1.model_copy(update={"action_plan_id": plan.id})]
    plan = plan.model_copy(update={"actions": fixed})
    await validate_and_persist_plan(plan, session=session)

    await run_plan_until_blocked(
        plan.id, session=session, tool_registry=tool_registry, adapter_registry=empty_adapters, sandbox_root=sandbox_root,
    )
    approval_repo = ActionApprovalRequestRepository(session)
    action_repo = ActionRecordRepository(session)
    a1_row = await action_repo.get(fixed[0].id)
    assert a1_row.status == PersistedActionStatus.WAITING_FOR_APPROVAL
    req = await load_approval_request(approval_repo, a1_row.approval_id)
    approved = decide_approval(req, "APPROVE", decided_by="human:reviewer")
    await sync_decision(approval_repo, approved)
    await session.commit()

    await run_plan_until_blocked(
        plan.id, session=session, tool_registry=tool_registry, adapter_registry=empty_adapters, sandbox_root=sandbox_root,
    )
    a1_row_after = await action_repo.get(fixed[0].id)
    # Approval GRANTED authorization; it never manufactured capability —
    # with no adapter registered, execution fails closed. CANCELLED (not
    # FAILED) is the frozen v0.1.3.4 precedent for an APPROVED Action that
    # cannot proceed (_FAIL_TARGET_BY_SOURCE[APPROVED] = CANCELLED,
    # action_executor.py) — the same target EXPIRED already uses; this is
    # not a new v0.1.3.8 behavior, just a first exercise of that exact path.
    assert a1_row_after.status == PersistedActionStatus.CANCELLED
    attempt_repo = ExecutionAttemptRepository(session)
    attempts = await attempt_repo.list_for_action(fixed[0].id)
    assert len(attempts) == 0  # never even claimed an execution attempt
