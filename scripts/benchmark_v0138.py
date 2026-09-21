"""v0.1.3.8 — standalone, offline hostile end-to-end benchmark harness
(spec section 51). Runs the SAME deterministic scenario as
`tests/test_v0138_hostile_benchmark.py::test_hostile_end_to_end_benchmark`
(imported from the shared `tests/_v0138_scenario.py` module, so the two
never drift apart), but as a plain script rather than a pytest test —
useful for a human to run directly and read the printed trace.

Deterministic. Offline. Isolated temp DB + temp sandbox directory, both
cleaned up on exit. Never touches `.env`, never makes a network call,
never touches the developer's real `jarvis.db`.

Run from the repository root:

    python scripts/benchmark_v0138.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

# Repo root on sys.path so `app.*`/`tests.*` import regardless of CWD.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _print_section(title: str) -> None:
    print(f"\n{'=' * 10} {title} {'=' * 10}")


async def run_benchmark() -> bool:
    """Returns True if every hostile scenario/invariant passed."""
    from app.config.settings import get_settings
    from app.database import connection as db_connection
    from app.database.models import PersistedActionPlanStatus, PersistedActionStatus
    from app.database.repositories import ActionPlanRecordRepository, ActionRecordRepository, ExecutionAttemptRepository, FailureRecordRepository, ReplanProposalRepository
    from app.decision_intelligence.action_plan_orchestrator import StopReason, run_plan_until_blocked, validate_and_persist_plan
    from app.decision_intelligence.action_plan_persistence import load_plan
    from app.decision_intelligence.decision_rules import DecisionInvariantViolation, apply_decision_transition, can_produce_plan
    from app.decision_intelligence.executive_report import BenchmarkOverallStatus, build_executive_report
    from app.decision_intelligence.plan_qa import build_qa_report
    from app.decision_intelligence.replan import apply_replan, persist_proposal, propose_replan
    from app.decision_intelligence.schemas import Decision, DecisionStatus
    from app.decision_intelligence.tool_registry import build_default_tool_registry

    from tests._v0138_scenario import (
        CANDIDATE_BETA,
        OBJECTIVE,
        build_hostile_adapter_registry,
        build_hostile_plan,
        campaign_assets_replacement,
        evaluate_research_readiness,
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="jarvis_v0138_benchmark_"))
    db_path = tmp_dir / "benchmark.db"
    sandbox_root = tmp_dir / "sandbox"
    sandbox_root.mkdir()
    url = f"sqlite+aiosqlite:///{db_path}"

    import os

    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()

    trace: list[dict] = []
    ok = True

    def _record(event: str, **fields) -> None:
        trace.append({"event": event, **fields})
        print(f"  [{event}] " + ", ".join(f"{k}={v}" for k, v in fields.items()))

    def _fresh_factory():
        return db_connection.get_session_factory(url)

    try:
        await db_connection.init_db(url)
        tool_registry = build_default_tool_registry()
        adapters, fake = build_hostile_adapter_registry()

        _print_section("Phase A: research readiness gate")
        negative = await evaluate_research_readiness(beta_full=False)
        assert negative.ready is False
        _record("research_readiness", ready=False)
        positive = await evaluate_research_readiness(beta_full=True)
        assert positive.ready is True
        _record("research_readiness", ready=True)

        _print_section("Phase B: decision gate")
        decision = Decision(
            project_id="v0138-benchmark", title="Digital product launch decision", statement=OBJECTIVE,
            comparison_ready=False,
        )
        try:
            apply_decision_transition(decision, DecisionStatus.READY_FOR_ACTION)
            raise AssertionError("expected DecisionInvariantViolation")
        except DecisionInvariantViolation:
            _record("decision_gate", comparison_ready=False, blocked=True)
        decision = decision.model_copy(update={"comparison_ready": positive.ready})
        decision = apply_decision_transition(decision, DecisionStatus.READY_FOR_ACTION)
        assert can_produce_plan(decision)
        _record("decision_gate", comparison_ready=True, status=decision.status.value)

        _print_section("Phase C: build + persist plan")
        plan = build_hostile_plan(decision.id)
        plan_id = plan.id
        a1, a2, a3, a4, a5, a6, a7 = plan.actions
        async with _fresh_factory()() as session:
            row = await validate_and_persist_plan(plan, session=session)
            assert row.status == PersistedActionPlanStatus.READY
        _record("plan_persisted", plan_id=plan_id, action_count=len(plan.actions))

        _print_section("Phase D: transient retry + validation failure")
        async with _fresh_factory()() as session:
            result1 = await run_plan_until_blocked(
                plan_id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
            )
            action_repo = ActionRecordRepository(session)
            a4_row = await action_repo.get(a4.id)
            a5_row = await action_repo.get(a5.id)
        assert a4_row.status == PersistedActionStatus.COMPLETED and a4_row.retry_count == 1
        assert a5_row.status == PersistedActionStatus.FAILED
        _record(
            "phase_d", stop_reason=result1.stop_reason.value, a4_execute_calls=fake.execute_calls_by_path["benchmark/landing-draft.txt"],
            a5_status=a5_row.status.value,
        )

        _print_section("Phase E: controlled replan A5 -> A5b")
        replacement = campaign_assets_replacement(plan_id)
        async with _fresh_factory()() as session:
            plan_repo = ActionPlanRecordRepository(session)
            action_repo = ActionRecordRepository(session)
            plan_row_before, loaded_plan = await load_plan(plan_repo, action_repo, plan_id)
            revision_before = plan_row_before.revision
            failed_action = next(a for a in loaded_plan.actions if a.id == a5.id)
            proposal = propose_replan(loaded_plan, failed_action, replacement, reason="deterministic hostile-benchmark replacement")
            assert proposal.status.value == "PROPOSED"
            proposal_row = await persist_proposal(ReplanProposalRepository(session), proposal)
            await session.commit()
        async with _fresh_factory()() as session:
            apply_result = await apply_replan(proposal_row.id, session=session)
        assert apply_result.status.value == "APPLIED"
        assert apply_result.new_plan_revision == revision_before + 1
        _record("replan_applied", new_revision=apply_result.new_plan_revision)

        _print_section("Phase F: resume — A5b executes, A6 pauses for approval")
        async with _fresh_factory()() as session:
            result2 = await run_plan_until_blocked(
                plan_id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
            )
            action_repo = ActionRecordRepository(session)
            a6_row = await action_repo.get(a6.id)
        assert a6_row.status == PersistedActionStatus.WAITING_FOR_APPROVAL
        _record("phase_f", ending_status=result2.ending_status.value, a6_status=a6_row.status.value)

        _print_section("Phase G: crash / restart, no-rewrite proof")
        artifact_paths = [
            sandbox_root / "benchmark/positioning.txt", sandbox_root / "benchmark/validation-plan.txt",
            sandbox_root / "benchmark/landing-draft.txt", sandbox_root / "benchmark/campaign-assets.txt",
        ]
        hashes_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_paths}
        async with _fresh_factory()() as session:
            attempt_repo = ExecutionAttemptRepository(session)
            attempt_counts_before = {
                aid: len(await attempt_repo.list_for_action(aid)) for aid in (a1.id, a2.id, a3.id, a4.id, replacement.id)
            }
        await db_connection.reset_engine()
        async with _fresh_factory()() as session:
            result3 = await run_plan_until_blocked(
                plan_id, session=session, tool_registry=tool_registry, adapter_registry=adapters, sandbox_root=sandbox_root,
            )
            attempt_repo = ExecutionAttemptRepository(session)
            attempt_counts_after = {
                aid: len(await attempt_repo.list_for_action(aid)) for aid in (a1.id, a2.id, a3.id, a4.id, replacement.id)
            }
        hashes_after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_paths}
        assert hashes_after == hashes_before
        assert attempt_counts_after == attempt_counts_before
        assert result3.stop_reason == StopReason.WAITING_FOR_APPROVAL
        _record("crash_restart_verified", hashes_match=True, attempts_unchanged=True)

        _print_section("Phase H: QA + executive report")
        async with _fresh_factory()() as session:
            plan_repo = ActionPlanRecordRepository(session)
            action_repo = ActionRecordRepository(session)
            final_plan_row, final_plan = await load_plan(plan_repo, action_repo, plan_id)
        qa = build_qa_report(final_plan, revision=final_plan_row.revision)
        report = build_executive_report(
            objective=OBJECTIVE, research_ready=positive.ready, decision=decision, plan_id=plan_id,
            plan_revision=final_plan_row.revision, plan_ending_status=final_plan.status.value, qa=qa,
        )
        assert report.overall_status == BenchmarkOverallStatus.COMPLETED_WITH_REVIEW
        for line in report.summary_lines:
            print(f"  {line}")
        _record("executive_report", overall_status=report.overall_status.value)

        _print_section("RESULT")
        print("HOSTILE BENCHMARK: PASS")
        print(f"Trace: {len(trace)} events recorded (see printed lines above)")
        return True
    except AssertionError as exc:
        ok = False
        print(f"\nHOSTILE BENCHMARK: FAIL — {exc}")
        return False
    finally:
        await db_connection.reset_engine()
        get_settings.cache_clear()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        if ok:
            print(f"(temp DB/sandbox at {tmp_dir} cleaned up)")


def main() -> int:
    passed = asyncio.run(run_benchmark())
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
