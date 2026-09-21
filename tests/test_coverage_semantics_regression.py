"""v0.1.2.5 Phase 13: coverage must continue using ACCEPTED evidence
only. Neither a pre-screen rejection nor an admission-gate rejection may
ever satisfy candidate completeness, requirement coverage, or comparison
readiness — only genuinely admitted evidence may. Offline — no network
call."""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.admission import admitted_only, apply_admission_gate
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.schemas.evidence import EvidenceItem

CANDIDATE_LABEL = "Vertical-Specific Data & Analytics Dashboard"


def _settings() -> Settings:
    return Settings()


# --- 18. pre-screen rejection cannot increase coverage ----------------------


def test_prescreen_rejected_result_never_enters_the_evidence_pool_so_cannot_affect_coverage():
    """A pre-screen-rejected SearchResult never becomes an EvidenceItem at
    all (see app/agents/research.py::_gather_evidence) — this is a
    structural guarantee, verified here at the coverage-computation layer:
    an empty candidate evidence pool (as if every result had been
    pre-screened out) yields zero coverage, never a manufactured
    SUFFICIENT status."""
    settings = _settings()
    requirements = generate_requirement_set(candidate_id="c", candidate_label=CANDIDATE_LABEL, settings=settings)
    coverage_cells = build_coverage_matrix(requirements, {"c": []}, settings=settings)
    assert all(cell.status == "MISSING" for cell in coverage_cells)


# --- 19. admission rejection cannot increase coverage ------------------------


def test_admission_rejected_evidence_cannot_increase_coverage():
    settings = _settings()
    requirements = generate_requirement_set(candidate_id="c", candidate_label=CANDIDATE_LABEL, settings=settings)

    off_topic = EvidenceItem(
        claim="The candidate skills assessment market size was estimated using vendor revenue disclosures.",
        source_title="Candidate Skills Assessment: Market Size Report",
        source_url="https://www.grandviewresearch.com/industry-analysis/candidate-assessment-market",
        excerpt="This report values the global candidate skills assessment market size.",
    )
    tagged = tag_evidence_for_candidate(
        [off_topic], candidate_id="c", candidate_label=CANDIDATE_LABEL, requirements=requirements
    )
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={"c": (CANDIDATE_LABEL, "")}, settings=settings)
    assert all(item.admission_status == "REJECTED" for item in stamped)

    # Feeding the REJECTED item straight into coverage (bypassing
    # admitted_only, the mistake this regression test guards against)
    # must show it can't produce SUFFICIENT status:
    coverage_cells = build_coverage_matrix(requirements, {"c": stamped}, settings=settings)
    market_size_cell = next(c for c in coverage_cells if c.category == "market_size")
    # relevance_label != REJECT already excludes it at the coverage layer
    # (belt-and-suspenders with admission) — either way, MISSING/not
    # SUFFICIENT.
    assert market_size_cell.status != "SUFFICIENT"

    # The correct path — admitted_only() — obviously also can't increase
    # coverage, since there's nothing left to feed it.
    coverage_cells_correct = build_coverage_matrix(requirements, {"c": admitted_only(stamped)}, settings=settings)
    assert all(cell.status != "SUFFICIENT" for cell in coverage_cells_correct)


# --- 20. accepted evidence CAN increase coverage ----------------------------


def test_accepted_evidence_can_increase_coverage():
    """The positive control: genuinely on-topic, admitted evidence DOES
    move a cell toward SUFFICIENT — proves the regression tests above are
    testing a real gate, not a filter that rejects everything."""
    settings = _settings()
    requirements = generate_requirement_set(candidate_id="c", candidate_label=CANDIDATE_LABEL, settings=settings)

    on_topic_items = [
        EvidenceItem(
            claim=f"{CANDIDATE_LABEL} addressable market sized using vendor revenue disclosures, source {i}.",
            source_url=f"https://www.gartner.com/data-analytics-dashboard-market-{i}",
            excerpt=f"Analyst estimate {i} of the {CANDIDATE_LABEL} market size and growth trajectory.",
        )
        for i in range(2)
    ]
    tagged = tag_evidence_for_candidate(
        on_topic_items, candidate_id="c", candidate_label=CANDIDATE_LABEL, requirements=requirements
    )
    tagged = [t.model_copy(update={"research_mode": "VALIDATION"}) for t in tagged]
    stamped = apply_admission_gate(tagged, candidates_by_id={"c": (CANDIDATE_LABEL, "")}, settings=settings)
    assert any(item.admission_status == "ACCEPTED" for item in stamped)

    coverage_cells = build_coverage_matrix(requirements, {"c": admitted_only(stamped)}, settings=settings)
    market_size_cell = next(c for c in coverage_cells if c.category == "market_size")
    assert market_size_cell.status in ("PARTIAL", "SUFFICIENT", "WEAK")
    assert market_size_cell.status != "MISSING"
