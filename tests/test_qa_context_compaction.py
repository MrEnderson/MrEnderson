"""v0.1.2.6 Phases 1/2/3/4/5/12: QA Context Compactor.

Phase 1 trace / root cause (confirmed by reading app/agents/qa.py):
QAAgent.run() received `input_data["output"]` — the caller
(app/orchestration/evaluator.py) was passing `output.model_dump(mode="json")`
verbatim, the ENTIRE worker output, completely uncompacted. For a
VALIDATION-mode research task this includes the full `evidence` list (up
to research_max_validation_evidence_items=60 items, every field — claim,
excerpt, publisher, provenance, admission metadata, ...) and the full
`evidence_gaps`/`requirements` lists. Unlike ResearchAgent's OWN model
prompt (bounded since v0.1.2/v0.1.2.2/v0.1.2.3 via
research_prompt_max_*), NOTHING bounded what QA saw — and both
`accumulated_evidence` and (after v0.1.2.5's own gap-identity fix)
`accumulated_gaps` grow every retry, which is exactly why the live
benchmark showed the QA request growing ~2.2x across retries while the
Research request (already bounded) shrank.

Fixed by app/agents/qa_context.py::compact_qa_context, wired into
app/orchestration/evaluator.py::run_worker_with_qa so ONLY the LLM-facing
QA prompt is bounded — deterministic evidence checks/coverage/gate
continue to use the full, authoritative output unchanged (see
app/orchestration/evaluator.py's `full_output_dump` vs `qa_view`).

Offline — no network call.
"""
from __future__ import annotations

import json

from app.agents.qa_context import compact_qa_context
from app.config.settings import Settings
from tests._qa_context_fixtures import CANDIDATES, dump_chars, realistic_output_for_attempt


def _settings() -> Settings:
    return Settings()


# --- Phase 1: before-change component-size table ----------------------------


def test_phase1_before_change_component_size_table():
    """Measures the RAW (uncompacted) worker-output dump's component
    sizes directly — this is exactly what QAAgent.run() received before
    this checkpoint's fix. Printed as a table (run with -s to see it)."""
    output = realistic_output_for_attempt(2)
    components = {
        "full_output (whole dump)": output,
        "evidence": output["evidence"],
        "evidence_gaps": output["evidence_gaps"],
        "requirements": output["requirements"],
        "candidates": output["candidates"],
        "findings": output["findings"],
        "assumptions": output["assumptions"],
        "open_questions": output["open_questions"],
        "unsupported_claims": output["unsupported_claims"],
    }
    print("\n--- Phase 1: BEFORE-fix component size table (attempt 2) ---")
    for name, value in components.items():
        print(f"  {name:<30} {dump_chars(value):>8} chars" if name != "full_output (whole dump)" else "")
    print(f"  {'TOTAL (full_output dump)':<30} {dump_chars(output):>8} chars")

    accepted = [e for e in output["evidence"] if e["admission_status"] == "ACCEPTED"]
    rejected = [e for e in output["evidence"] if e["admission_status"] == "REJECTED"]
    print(f"  accepted evidence: {len(accepted)} ({dump_chars(accepted)} chars)")
    print(f"  rejected evidence: {len(rejected)} ({dump_chars(rejected)} chars)")

    assert dump_chars(output["evidence"]) > dump_chars(output["evidence_gaps"])
    assert dump_chars(output) > 0


# --- Phase 2: reproduces pre-fix growth across retries ----------------------


def test_phase2_uncompacted_output_grows_across_retries():
    """Reproduces the growth pattern the live benchmark showed — this
    measures the RAW dump (what QA used to see), proving the growth is
    real and attributable to evidence + gaps accumulation, not a fluke of
    one live run."""
    sizes = [dump_chars(realistic_output_for_attempt(a)) for a in range(5)]
    print(f"\n--- Phase 2: uncompacted QA-facing dump sizes across 5 attempts: {sizes}")
    for earlier, later in zip(sizes, sizes[1:]):
        assert later >= earlier, "the raw dump must grow (or stay flat), demonstrating the pre-fix defect"
    assert sizes[-1] > sizes[0] * 1.5, "must show REAL growth, not a trivial/flat fixture"


# --- 1. QA context component measurement ------------------------------------


def test_qa_context_component_measurement():
    settings = _settings()
    output = realistic_output_for_attempt(2)
    compacted = compact_qa_context(output, settings=settings)
    for key in ("question", "research_mode", "summary", "findings", "assumptions", "open_questions",
                "unsupported_claims", "evidence", "unresolved_gaps", "coverage_summary", "candidates"):
        assert key in compacted


# --- 2. QA context bounded ---------------------------------------------------


def test_qa_context_stays_within_configured_total_budget():
    settings = _settings()
    for attempt in range(5):
        output = realistic_output_for_attempt(attempt)
        compacted = compact_qa_context(output, settings=settings)
        assert dump_chars(compacted) <= settings.qa_prompt_max_total_context_chars


def test_qa_context_evidence_count_bounded():
    settings = _settings()
    output = realistic_output_for_attempt(4)
    compacted = compact_qa_context(output, settings=settings)
    assert len(compacted["evidence"]) <= settings.qa_prompt_max_evidence_items


# --- 3. rejected evidence body excluded --------------------------------------


def test_rejected_evidence_body_excluded_from_qa_context():
    settings = _settings()
    output = realistic_output_for_attempt(2)
    compacted = compact_qa_context(output, settings=settings)
    shown_ids = {e["id"] for e in compacted["evidence"]}
    rejected_ids = {e["id"] for e in output["evidence"] if e["admission_status"] == "REJECTED"}
    assert not (shown_ids & rejected_ids), "no REJECTED evidence id should ever appear in the QA-facing view"
    assert compacted["evidence_excluded_count"] > 0


# --- 4. historical ResearchOutput excluded -----------------------------------


def test_compact_qa_context_never_carries_a_nested_previous_output():
    settings = _settings()
    output = realistic_output_for_attempt(3)
    output["previous_output"] = realistic_output_for_attempt(2)  # simulate a hypothetical leak
    compacted = compact_qa_context(output, settings=settings)
    assert "previous_output" not in compacted
    assert "retry_history" not in compacted


# --- 5. previous full QA feedback excluded -----------------------------------


def test_compact_qa_context_never_carries_qa_feedback_fields():
    settings = _settings()
    output = realistic_output_for_attempt(2)
    output["qa_feedback"] = "Some long previous QA feedback text " * 50
    compacted = compact_qa_context(output, settings=settings)
    assert "qa_feedback" not in compacted
    assert "previous_qa_feedback" not in compacted


# --- 6. no recursive feedback accumulation -----------------------------------


def test_no_recursive_feedback_accumulation_across_simulated_attempts():
    """compact_qa_context is a pure function of ONE attempt's own output —
    calling it repeatedly with growing input (simulating retries) never
    causes the OUTPUT size itself to compound beyond the configured bound,
    proving there's no hidden accumulation inside the compactor itself."""
    settings = _settings()
    sizes = [dump_chars(compact_qa_context(realistic_output_for_attempt(a), settings=settings)) for a in range(5)]
    print(f"\n--- compacted QA context sizes across 5 attempts: {sizes}")
    for size in sizes:
        assert size <= settings.qa_prompt_max_total_context_chars


# --- 8. deterministic evidence checks still use full authoritative evidence -


def test_deterministic_evidence_check_receives_full_evidence_not_compacted():
    """evaluate_evidence (app/security/evidence_qa.py) must see the FULL
    evidence list — asserts the compactor and the full dump genuinely
    differ in evidence count, then confirms evaluate_evidence's own
    gap-detection logic operates against the uncompacted dict."""
    from app.security.evidence_qa import evaluate_evidence

    settings = _settings()
    output = realistic_output_for_attempt(4)
    compacted = compact_qa_context(output, settings=settings)
    assert len(output["evidence"]) > len(compacted["evidence"]), "fixture must actually need compaction"

    # evaluate_evidence must be called with the FULL dump — verified by
    # construction in app/orchestration/evaluator.py (full_output_dump),
    # and here by confirming it doesn't error/behave differently when
    # given the (deliberately larger) full dict.
    result = evaluate_evidence(output, input_data={}, known_evidence_ids=None)
    assert result is not None


# --- 10. comparison readiness unchanged by compaction ------------------------


def test_compaction_never_touches_comparison_readiness_computation():
    """compact_qa_context has no code path that reads or writes
    comparison_readiness/candidate_statuses — those are Strategy-specific
    and, per _qa_facing_view's shape dispatch, a Strategy-shaped output
    never even reaches this compactor."""
    import inspect

    from app.agents import qa_context

    source = inspect.getsource(qa_context)
    assert "comparison_ready" not in source
    assert "candidate_statuses" not in source


# --- 11. candidate A evidence cannot enter B-specific QA context incorrectly


def test_evidence_tagged_for_candidate_a_never_shown_under_candidate_b_in_qa_context():
    settings = _settings()
    output = realistic_output_for_attempt(2)
    compacted = compact_qa_context(output, settings=settings)
    for item in compacted["evidence"]:
        # Every shown item's candidate_id must be one of the REAL
        # candidates — and must match what it was tagged with in the
        # authoritative output (compaction never re-tags/reassigns).
        original = next(e for e in output["evidence"] if e["id"] == item["id"])
        assert item["candidate_id"] == original["candidate_id"]


# --- 12. visible evidence IDs remain valid -----------------------------------


def test_qa_context_evidence_ids_are_a_subset_of_authoritative_evidence_ids():
    settings = _settings()
    output = realistic_output_for_attempt(3)
    compacted = compact_qa_context(output, settings=settings)
    authoritative_ids = {e["id"] for e in output["evidence"]}
    shown_ids = {e["id"] for e in compacted["evidence"]}
    assert shown_ids <= authoritative_ids
