"""v0.1.2.5 Phase 1: traces every search query the v0.1.2.4 pipeline would
generate for DISCOVERY initial, VALIDATION initial, VALIDATION retry 1,
and VALIDATION retry 2 — using deterministic fixtures shaped like the
three real candidates from the live benchmark:

1. AI-Powered Content Creation Tools & Templates
2. Digital Asset Bundles & Creator Marketplaces
3. Niche Educational Courses & Learning Subscriptions

Offline only — builds queries through the real
app/research_intelligence/query_builder.py machinery (the same functions
app/agents/research.py calls), never a network call. Prints a compact
diagnostic table (run with `pytest -s` to see it).
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.query_builder import build_external_search_concept, build_query_plan
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.schemas import ResearchCandidate

CANDIDATES = [
    ("candidate-ai-content-tools", "AI-Powered Content Creation Tools & Templates",
     "A marketplace of AI prompt templates and content-workflow automation for small businesses."),
    ("candidate-digital-asset-bundles", "Digital Asset Bundles & Creator Marketplaces",
     "Bundled digital design assets sold through creator marketplaces."),
    ("candidate-niche-courses", "Niche Educational Courses & Learning Subscriptions",
     "Paid subscription access to niche professional online courses."),
]


def _print_row(row: dict) -> None:
    print(
        f"| {row.get('phase',''):<18} | {row.get('candidate_id') or '-':<28} | "
        f"{row.get('candidate_label') or '-':<45} | {row.get('requirement_category') or '-':<12} | "
        f"{row.get('unresolved_gap') or '-':<8} | max_results={row.get('max_results')} "
        f"extract={row.get('extraction_attempted')} | {row.get('query')}"
    )


def test_trace_discovery_initial_attempt():
    """DISCOVERY: no candidates exist yet — one broad, orchestration-safe
    query from the mission title/description alone."""
    title = "Discover candidate digital-product opportunities"
    description = "Find three potential digital-product opportunities and recommend the strongest one."
    query = build_external_search_concept(title, description)

    row = {
        "phase": "DISCOVERY init", "candidate_id": None, "candidate_label": None,
        "requirement_category": None, "unresolved_gap": None, "query": query,
        "max_results": Settings().research_max_results, "extraction_attempted": False,
    }
    _print_row(row)

    assert "candidate" not in query.lower()
    assert "opportunit" not in query.lower()


def test_trace_validation_initial_attempt():
    """VALIDATION attempt 0: one broad, candidate-scoped query per
    candidate — no requirement_category yet (that's what retries add),
    extraction not attempted (targeted=False on a first attempt)."""
    settings = Settings()
    rows = []
    for candidate_id, label, description in CANDIDATES:
        plan = build_query_plan(
            candidate_id=candidate_id, candidate_label=label, candidate_description=description,
            requirement=None, max_results=settings.research_max_results,
        )
        rows.append(
            {
                "phase": "VALIDATION init", "candidate_id": plan.candidate_id, "candidate_label": plan.candidate_label,
                "requirement_category": plan.requirement_category, "unresolved_gap": None, "query": plan.query,
                "max_results": plan.max_results, "extraction_attempted": False,
            }
        )
    for row in rows:
        _print_row(row)

    assert len(rows) == 3
    assert {r["candidate_id"] for r in rows} == {c[0] for c in CANDIDATES}
    for row in rows:
        assert "candidate" not in row["query"].lower()


def _validation_retry_rows(*, phase_label: str, categories_by_candidate: dict[str, list[str]]) -> list[dict]:
    settings = Settings()
    rows = []
    for candidate_id, label, description in CANDIDATES:
        requirements = {
            r.category: r
            for r in generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
        }
        for category in categories_by_candidate.get(candidate_id, []):
            requirement = requirements[category]
            plan = build_query_plan(
                candidate_id=candidate_id, candidate_label=label, candidate_description=description,
                requirement=requirement, max_results=settings.research_max_gap_queries_per_attempt,
            )
            rows.append(
                {
                    "phase": phase_label, "candidate_id": plan.candidate_id, "candidate_label": plan.candidate_label,
                    "requirement_category": plan.requirement_category,
                    "unresolved_gap": f"{candidate_id}:{category}", "query": plan.query,
                    "max_results": plan.max_results, "extraction_attempted": True,
                }
            )
    return rows


def test_trace_validation_retry_1_targets_specific_cells():
    """VALIDATION retry 1: each of the three candidates still missing
    pricing coverage — one query per (candidate, pricing) cell, never a
    single shared cross-candidate query."""
    rows = _validation_retry_rows(
        phase_label="VALIDATION retry1",
        categories_by_candidate={c[0]: ["pricing"] for c in CANDIDATES},
    )
    for row in rows:
        _print_row(row)

    assert len(rows) == 3
    queries = {row["query"] for row in rows}
    assert len(queries) == 3, "each candidate's pricing retry query must be distinct"
    for row in rows:
        assert row["requirement_category"] == "pricing"
        assert row["candidate_id"] in row["unresolved_gap"]


def test_trace_validation_retry_2_targets_different_cells_per_candidate():
    """VALIDATION retry 2: candidates now have DIFFERENT remaining gaps
    (e.g. one still needs market_size, another competition) — proves the
    query plan is genuinely per-cell, not per-attempt-globally-uniform."""
    rows = _validation_retry_rows(
        phase_label="VALIDATION retry2",
        categories_by_candidate={
            "candidate-ai-content-tools": ["market_size"],
            "candidate-digital-asset-bundles": ["competition"],
            "candidate-niche-courses": ["customer_pain"],
        },
    )
    for row in rows:
        _print_row(row)

    assert len(rows) == 3
    by_candidate = {row["candidate_id"]: row["requirement_category"] for row in rows}
    assert by_candidate["candidate-ai-content-tools"] == "market_size"
    assert by_candidate["candidate-digital-asset-bundles"] == "competition"
    assert by_candidate["candidate-niche-courses"] == "customer_pain"


def test_trace_which_query_produced_each_admitted_or_rejected_item():
    """End-to-end trace: tags synthetic evidence for one candidate and
    prints which query produced each admitted/rejected item — the last
    required piece of Phase 1's trace."""
    from app.research_intelligence.admission import apply_admission_gate
    from app.research_intelligence.tagging import tag_evidence_for_candidate
    from app.schemas.evidence import EvidenceItem

    settings = Settings()
    candidate_id, label, description = CANDIDATES[0]
    requirements = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)

    on_topic = EvidenceItem(
        claim=f"{label} competitor pricing plans start at $29/month.",
        source_url="https://www.g2.com/products/example",
        excerpt=f"{label} competitors list pricing tiers starting at $29/month.",
        query_used="AI content creation tools pricing competitors",
        research_mode="VALIDATION",
    )
    off_topic = EvidenceItem(
        claim="Candidate skills assessment market size report for HR software.",
        source_url="https://www.grandviewresearch.com/candidate-assessment-market",
        excerpt="HR candidate assessment market sizing based on vendor revenue.",
        query_used="AI content creation tools pricing competitors",
        research_mode="VALIDATION",
    )
    tagged = tag_evidence_for_candidate(
        [on_topic, off_topic], candidate_id=candidate_id, candidate_label=label, requirements=requirements
    )
    stamped = apply_admission_gate(tagged, candidates_by_id={candidate_id: (label, description)}, settings=settings)

    print("\n--- which query produced each admitted/rejected item ---")
    for item in stamped:
        print(f"query={item.query_used!r} admission_status={item.admission_status} claim={item.claim[:60]!r}")

    admitted = [i for i in stamped if i.admission_status == "ACCEPTED"]
    rejected = [i for i in stamped if i.admission_status == "REJECTED"]
    assert len(admitted) == 1 and admitted[0].claim.startswith(label)
    assert len(rejected) == 1 and rejected[0].claim.startswith("Candidate skills assessment")
    # Both came from the SAME query — proves admission, not query
    # identity, is what separates them; the trace must show the query
    # alongside the outcome, not imply query choice alone explains it.
    assert admitted[0].query_used == rejected[0].query_used
