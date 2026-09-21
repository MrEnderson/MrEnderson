"""v0.1.2.6 Phase 7: coverage contribution trace. The live benchmark
showed substantial ACCEPTED evidence but final coverage stuck at 2%/5%/8%.
Traced root cause: (D) source-role suitability — most REAL, admitted
evidence comes from commercial vendor domains
app/research_intelligence/source_roles.py doesn't recognize (Algolia,
Bloomreach, Voyado, Zylo, ...), defaulting to source_role=UNKNOWN. Per
app/research_intelligence/suitability.py's policy table, UNKNOWN is
UNSUITABLE (not merely WEAK) for market_size/growth/pricing/
unit_economics/willingness_to_pay/customer_validation — an UNSUITABLE
item contributes to NEITHER strong/acceptable/weak in
coverage.py::_build_cell, so a cell can have several admitted, genuinely
on-topic evidence items and still compute as MISSING (not even WEAK).
This is intentional conservatism (an unrecognized source shouldn't
silently count as authoritative for a market-wide claim) working exactly
as designed — NOT a bug in coverage math (F), evidence dedup (E),
candidate assignment (C), or requirement_category tagging (B). Offline —
no network call.
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.admission import admitted_only, apply_admission_gate
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.coverage_trace import summarize_contribution_reasons, trace_evidence_contributions
from app.research_intelligence.completeness import evaluate_completeness
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.schemas.evidence import EvidenceItem

CANDIDATE_A = ("candidate-a", "AI-Powered Content Personalization Platform for E-commerce")
CANDIDATE_B = ("candidate-b", "Compliance and Audit Documentation Automation SaaS")


def _settings() -> Settings:
    return Settings()


def _unknown_vendor_evidence(candidate_label: str, category: str, n: int) -> list[EvidenceItem]:
    """Shaped like the live benchmark's actual problem: genuinely on-topic
    evidence from real commercial vendor domains this project's
    source_roles.py doesn't recognize — defaults to UNKNOWN."""
    return [
        EvidenceItem(
            claim=f"{candidate_label} addressable market size estimate {i} reported by an industry vendor blog.",
            source_url=f"https://www.example-vendor-{i}.com/blog/industry-report",
            excerpt=f"Industry analysis {i} covering the {candidate_label} market size and valuation.",
        )
        for i in range(n)
    ]


# --- Phase 7 root-cause demonstration ---------------------------------------
#
# Two distinct mechanisms, both rooted in the SAME cause (UNKNOWN source
# role for unrecognized real vendor domains — see
# tests/test_source_role_vendor_classification.py), both traced here:
#
# (a) For market_size/pricing/growth/unit_economics/willingness_to_pay/
#     customer_validation, UNKNOWN role is UNSUITABLE — the item is
#     REJECTED AT ADMISSION (rule 7), never becomes evidence at all.
# (b) For demand/competition/customer_pain/feasibility, UNKNOWN role is
#     only WEAK (not UNSUITABLE) — the item DOES get admitted, but
#     contributes only to the cell's `weak` count, which can never reach
#     SUFFICIENT (qualifying = strong+acceptable stays 0) — capped at
#     WEAK status (0.15 weight) at best.


def test_root_cause_a_unknown_role_market_size_evidence_rejected_at_admission():
    """Mechanism (a): market_size's UNKNOWN policy is UNSUITABLE, so
    admission rule 7 rejects the item outright — it never reaches
    coverage as authoritative evidence at all."""
    settings = _settings()
    candidate_id, label = CANDIDATE_A
    requirements = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
    raw_evidence = _unknown_vendor_evidence(label, "market_size", 3)
    tagged = tag_evidence_for_candidate(raw_evidence, candidate_id=candidate_id, candidate_label=label, requirements=requirements)
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={candidate_id: (label, "")}, settings=settings)

    assert all(i.source_role == "UNKNOWN" for i in stamped)
    assert all(i.admission_status == "REJECTED" for i in stamped)
    assert all("SOURCE_UNSUITABLE_FOR_REQUIREMENT" in i.admission_rejection_reasons for i in stamped)

    coverage_cells = build_coverage_matrix(requirements, {candidate_id: admitted_only(stamped)}, settings=settings)
    market_size_cell = next(c for c in coverage_cells if c.category == "market_size")
    assert market_size_cell.status == "MISSING"

    trace = trace_evidence_contributions(stamped, coverage_cells, settings=settings)
    reasons = summarize_contribution_reasons(trace)
    assert reasons == {"NOT_ADMITTED": 3}


def test_root_cause_b_unknown_role_demand_evidence_admitted_but_capped_at_weak():
    """Mechanism (b): demand's UNKNOWN policy is only WEAK (not
    UNSUITABLE), so the item IS admitted — but WEAK suitability can never
    push a cell past WEAK status, regardless of how much of it there is."""
    settings = _settings()
    candidate_id, label = CANDIDATE_A
    requirements = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
    raw_evidence = [
        EvidenceItem(
            claim=f"{label} shows strong demand and adoption trends reported by an industry vendor blog, source {i}.",
            source_url=f"https://www.example-vendor-{i}.com/blog/industry-report",
            excerpt=f"Industry analysis {i} covering {label} demand and adoption signals.",
        )
        for i in range(3)
    ]
    tagged = tag_evidence_for_candidate(raw_evidence, candidate_id=candidate_id, candidate_label=label, requirements=requirements)
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={candidate_id: (label, "")}, settings=settings)

    assert all(i.source_role == "UNKNOWN" for i in stamped)
    assert all(i.admission_status == "ACCEPTED" for i in stamped), "WEAK suitability must still pass admission"

    coverage_cells = build_coverage_matrix(requirements, {candidate_id: admitted_only(stamped)}, settings=settings)
    demand_cell = next(c for c in coverage_cells if c.category == "demand")
    # Admitted, on-topic, even THREE independent sources — still capped at
    # WEAK, never SUFFICIENT/PARTIAL, purely because of source suitability.
    assert demand_cell.status == "WEAK"
    assert demand_cell.strong_count == 0 and demand_cell.acceptable_count == 0
    assert demand_cell.weak_count == 3

    trace = trace_evidence_contributions(stamped, coverage_cells, settings=settings)
    reasons = summarize_contribution_reasons(trace)
    assert reasons == {"WEAK": 3}


# --- 17. accepted evidence coverage trace -----------------------------------


def test_trace_shows_full_chain_for_each_accepted_item():
    settings = _settings()
    candidate_id, label = CANDIDATE_A
    requirements = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
    good_evidence = [
        EvidenceItem(
            claim=f"{label} pricing plans start at $29/month, source {i}.",
            source_url=f"https://www.g2.com/products/example-{i}",
            excerpt=f"{label} pricing plan comparison {i}.",
        )
        for i in range(2)
    ]
    tagged = tag_evidence_for_candidate(good_evidence, candidate_id=candidate_id, candidate_label=label, requirements=requirements)
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={candidate_id: (label, "")}, settings=settings)
    coverage_cells = build_coverage_matrix(requirements, {candidate_id: admitted_only(stamped)}, settings=settings)

    trace = trace_evidence_contributions(stamped, coverage_cells, settings=settings)
    for row in trace:
        assert row.evidence_id
        assert row.candidate_id == candidate_id
        assert row.requirement_category is not None
        assert row.contribution in ("STRONG", "ACCEPTABLE", "WEAK", "NONE", "NOT_ADMITTED")
        assert row.resulting_cell_status is not None


# --- 18. rejected evidence zero contribution --------------------------------


def test_rejected_evidence_contributes_not_admitted():
    settings = _settings()
    candidate_id, label = CANDIDATE_A
    requirements = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
    off_topic = EvidenceItem(
        claim="Candidate skills assessment market size report for HR software.",
        source_url="https://www.grandviewresearch.com/candidate-assessment-market",
        excerpt="HR candidate assessment market sizing.",
    )
    tagged = tag_evidence_for_candidate([off_topic], candidate_id=candidate_id, candidate_label=label, requirements=requirements)
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={candidate_id: (label, "")}, settings=settings)
    coverage_cells = build_coverage_matrix(requirements, {candidate_id: admitted_only(stamped)}, settings=settings)

    trace = trace_evidence_contributions(stamped, coverage_cells, settings=settings)
    assert all(row.contribution == "NOT_ADMITTED" for row in trace)


# --- 19. discovery evidence zero validation contribution --------------------


def test_discovery_evidence_contributes_zero_to_validation_coverage():
    from app.research_intelligence.gate import evaluate_comparison_readiness

    settings = _settings()
    discovery_item = {
        "id": "d1", "claim": "AI content personalization platform demand traction on Product Hunt.",
        "source_url": "https://www.producthunt.com/posts/x", "excerpt": "traction data",
        "research_mode": "DISCOVERY",
    }
    research_results = [
        {
            "task_id": "t1", "title": "t1", "question": "t1", "evidence": [discovery_item],
            "candidates": [{"label": CANDIDATE_A[1]}, {"label": CANDIDATE_B[1]}],
        }
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=settings)
    status = next(s for s in readiness.candidate_statuses if s.candidate_label == CANDIDATE_A[1])
    assert status.coverage_percentage == 0.0


# --- 20/21. correct candidate/requirement coverage contribution ------------


def test_evidence_contributes_only_to_its_own_candidate_and_requirement():
    settings = _settings()
    candidate_a_id, candidate_a_label = CANDIDATE_A
    candidate_b_id, candidate_b_label = CANDIDATE_B
    requirements_a = generate_requirement_set(candidate_id=candidate_a_id, candidate_label=candidate_a_label, settings=settings)
    requirements_b = generate_requirement_set(candidate_id=candidate_b_id, candidate_label=candidate_b_label, settings=settings)

    pricing_evidence_a = [
        EvidenceItem(
            claim=f"{candidate_a_label} pricing plans start at $29/month, source {i}.",
            source_url=f"https://www.g2.com/products/example-{i}",
            excerpt=f"{candidate_a_label} pricing plan comparison {i}.",
        )
        for i in range(2)
    ]
    tagged_a = tag_evidence_for_candidate(pricing_evidence_a, candidate_id=candidate_a_id, candidate_label=candidate_a_label, requirements=requirements_a)
    tagged_a = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged_a]
    stamped_a = apply_admission_gate(tagged_a, candidates_by_id={candidate_a_id: (candidate_a_label, "")}, settings=settings)

    all_requirements = requirements_a + requirements_b
    evidence_by_candidate = {candidate_a_id: admitted_only(stamped_a), candidate_b_id: []}
    coverage_cells = build_coverage_matrix(all_requirements, evidence_by_candidate, settings=settings)

    a_pricing = next(c for c in coverage_cells if c.candidate_id == candidate_a_id and c.category == "pricing")
    b_pricing = next(c for c in coverage_cells if c.candidate_id == candidate_b_id and c.category == "pricing")
    a_demand = next(c for c in coverage_cells if c.candidate_id == candidate_a_id and c.category == "demand")

    assert a_pricing.status != "MISSING"
    assert b_pricing.status == "MISSING"  # candidate B never got candidate A's evidence
    assert a_demand.status == "MISSING"  # pricing evidence never satisfies demand


# --- 22. independent-source coverage behavior -------------------------------


def test_sufficient_independent_suitable_evidence_changes_cell_status():
    settings = _settings()
    candidate_id, label = CANDIDATE_A
    requirements = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)

    # Two INDEPENDENT-domain, STRONG-suitability (PRIMARY/MARKETPLACE)
    # pricing sources — meets minimum_evidence_count=2 and
    # requires_independent_sources for pricing.
    good_evidence = [
        EvidenceItem(
            claim=f"{label} pricing plans start at 29 dollars per month.", source_url="https://gumroad.com/l/example-a",
            excerpt=f"{label} pricing tiers listed clearly.",
        ),
        EvidenceItem(
            claim=f"{label} pricing tiers range from 19 to 49 dollars per month.",
            source_url="https://www.g2.com/products/example-b", excerpt=f"{label} pricing plan review.",
        ),
    ]
    tagged = tag_evidence_for_candidate(good_evidence, candidate_id=candidate_id, candidate_label=label, requirements=requirements)
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={candidate_id: (label, "")}, settings=settings)
    coverage_cells = build_coverage_matrix(requirements, {candidate_id: admitted_only(stamped)}, settings=settings)

    pricing_cell = next(c for c in coverage_cells if c.category == "pricing")
    assert pricing_cell.independent_domain_count >= 2
    assert pricing_cell.status == "SUFFICIENT"

    # Now the single-source control: only ONE of the two sources.
    coverage_cells_single = build_coverage_matrix(requirements, {candidate_id: admitted_only(stamped)[:1]}, settings=settings)
    pricing_cell_single = next(c for c in coverage_cells_single if c.category == "pricing")
    assert pricing_cell_single.status != "SUFFICIENT"


# --- percentage is deterministic from cell states ---------------------------


def test_coverage_percentage_is_deterministic_from_cell_states():
    settings = _settings()
    candidate_id, label = CANDIDATE_A
    requirements = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
    good_evidence = [
        EvidenceItem(
            claim=f"{label} pricing plans start at 29 dollars per month.", source_url="https://gumroad.com/l/example-a",
            excerpt=f"{label} pricing tiers listed clearly.",
        ),
        EvidenceItem(
            claim=f"{label} pricing tiers range from 19 to 49 dollars per month.",
            source_url="https://www.g2.com/products/example-b", excerpt=f"{label} pricing plan review.",
        ),
    ]
    tagged = tag_evidence_for_candidate(good_evidence, candidate_id=candidate_id, candidate_label=label, requirements=requirements)
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={candidate_id: (label, "")}, settings=settings)
    coverage_cells = build_coverage_matrix(requirements, {candidate_id: admitted_only(stamped)}, settings=settings)

    readiness = evaluate_completeness(requirements, coverage_cells, {candidate_id: label}, settings=settings)
    status = readiness.candidate_statuses[0]

    # Recompute independently from the SAME cell statuses — must match
    # exactly (deterministic, no hidden randomness/model input).
    weight = {"SUFFICIENT": 1.0, "PARTIAL": 0.5, "WEAK": 0.15, "MISSING": 0.0}
    expected = sum(weight[c.status] for c in coverage_cells) / len(coverage_cells)
    # CandidateResearchStatus.coverage_percentage is itself stored rounded
    # to 4 decimals (see app/research_intelligence/completeness.py) — round
    # both sides to that same precision for a fair comparison.
    assert round(status.coverage_percentage, 4) == round(expected, 4)

    # Running it again must produce the identical result.
    readiness_again = evaluate_completeness(requirements, coverage_cells, {candidate_id: label}, settings=settings)
    assert readiness_again.candidate_statuses[0].coverage_percentage == status.coverage_percentage
