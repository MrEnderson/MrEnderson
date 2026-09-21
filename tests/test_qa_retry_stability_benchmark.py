"""v0.1.2.6 Phase 5/13: retry stability invariant + offline before/after
benchmark. Offline — no network call.
"""
from __future__ import annotations

from app.agents.qa_context import compact_qa_context
from app.agents.research import _query_for_gap, _candidate_lookup
from app.config.settings import Settings
from app.research_intelligence.query_builder import build_external_research_query
from tests._qa_context_fixtures import CANDIDATES, dump_chars, realistic_output_for_attempt


def _settings() -> Settings:
    return Settings()


# --- Phase 5: retry stability invariant --------------------------------------


def test_qa_request_size_does_not_grow_linearly_with_historical_evidence_across_5_retries():
    settings = _settings()

    before = [dump_chars(realistic_output_for_attempt(a)) for a in range(5)]
    after = [dump_chars(compact_qa_context(realistic_output_for_attempt(a), settings=settings)) for a in range(5)]

    print("\nQA REQUEST SIZE")
    print("BEFORE:")
    for i, size in enumerate(before):
        label = "attempt 0" if i == 0 else f"retry {i}"
        print(f"  {label}: {size} chars")
    print("AFTER:")
    for i, size in enumerate(after):
        label = "attempt 0" if i == 0 else f"retry {i}"
        print(f"  {label}: {size} chars")

    # BEFORE must show real (non-trivial) growth — otherwise this isn't
    # actually reproducing the defect.
    assert before[-1] > before[0] * 1.5

    # AFTER: bounded. Never grows past the configured total budget, and
    # critically does NOT grow approximately linearly with historical
    # evidence/output the way BEFORE does — a generous ceiling well under
    # BEFORE's own growth curve.
    for size in after:
        assert size <= settings.qa_prompt_max_total_context_chars

    # The core invariant: once evidence/gaps exist at all (retry 1
    # onward — attempt 0 in this fixture happens to admit nothing, an
    # edge case not the point being tested), AFTER stays essentially FLAT
    # across retries, unlike BEFORE's compounding growth. Compare retry 1
    # to retry 4 directly rather than a ratio anchored on a near-empty
    # baseline.
    before_growth_1_to_4 = before[4] / before[1]
    after_growth_1_to_4 = after[4] / after[1]
    assert before_growth_1_to_4 > 1.5, "BEFORE must show real growth from retry 1 to retry 4"
    assert after_growth_1_to_4 < 1.2, (
        f"AFTER must stay essentially flat from retry 1 to retry 4, not compound like BEFORE: "
        f"before={before_growth_1_to_4:.2f}x after={after_growth_1_to_4:.2f}x"
    )


def test_retries_1_through_5_do_not_recursively_accumulate_previous_qa_context():
    """Each attempt's compacted view is built from THAT attempt's own
    output alone — never references, embeds, or grows because of a prior
    attempt's compacted view (there is no cross-attempt state inside
    compact_qa_context at all — it's a pure function)."""
    settings = _settings()
    import inspect

    from app.agents import qa_context

    sig = inspect.signature(qa_context.compact_qa_context)
    # Only ever takes THIS attempt's own output + settings — no
    # previous-attempt/history parameter exists to accumulate through.
    assert set(sig.parameters) == {"output", "settings"}

    compacted_views = [compact_qa_context(realistic_output_for_attempt(a), settings=settings) for a in range(1, 6)]
    for view in compacted_views:
        assert dump_chars(view) <= settings.qa_prompt_max_total_context_chars


# --- Phase 13: offline before/after benchmark --------------------------------


def test_phase13_full_before_after_benchmark_report():
    settings = _settings()
    print("\n=== Phase 13 offline before/after benchmark ===")
    for attempt in range(5):
        output = realistic_output_for_attempt(attempt)
        compacted = compact_qa_context(output, settings=settings)
        accepted = [e for e in output["evidence"] if e["admission_status"] == "ACCEPTED"]
        rejected = [e for e in output["evidence"] if e["admission_status"] == "REJECTED"]
        label = "attempt 0" if attempt == 0 else f"retry {attempt}"
        print(
            f"{label}: BEFORE={dump_chars(output)} chars AFTER={dump_chars(compacted)} chars | "
            f"evidence_authoritative={len(output['evidence'])} evidence_shown_to_qa={len(compacted['evidence'])} "
            f"rejected_omitted={len(rejected)} gap_count={len(output['evidence_gaps'])} "
            f"candidate_count={len(output['candidates'])} coverage_cells={len(output['requirements'])}"
        )
        assert len(compacted["evidence"]) <= len(accepted)
        assert dump_chars(compacted) <= settings.qa_prompt_max_total_context_chars

    print("\n=== Phase 13: exact generated validation retry queries ===")
    scenarios = [
        ("candidate-ecommerce", "AI-Powered Content Personalization Platform for E-commerce", "market_size"),
        ("candidate-bluecollar", "Niche Video Course Marketplace for Blue-Collar Skills", "demand"),
        ("candidate-compliance", "Compliance & Audit Documentation Automation SaaS", "pricing"),
    ]
    candidates_by_id = _candidate_lookup(
        [{"id": cid, "label": label, "description": ""} for cid, label, _ in scenarios]
    )
    for candidate_id, label, category in scenarios:
        gap = {
            "candidate_id": candidate_id, "requirement_category": category, "gap_type": category,
            "suggested_query": "Validate and compare candidate opportunities " + category.replace("_", " "),
        }
        query = _query_for_gap(gap, title="Validate and compare candidate opportunities", candidates_by_id=candidates_by_id)
        print(f"  {label} / {category}: {query!r}")
        assert "validate and compare candidate opportunities" not in query.lower()
        expected = build_external_research_query(candidate_label=label, candidate_description="", category=category)
        assert query == expected
