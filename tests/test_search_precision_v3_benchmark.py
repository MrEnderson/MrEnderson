"""v0.1.2.3 "Search precision": the benchmark fixture matching the second
live mission — "Find three potential digital-product opportunities and
recommend the strongest one" with candidates:

  1. Creator-Focused Digital Product Platform / Marketplace
  2. Niche-Specific Workflow Automation Software & Plugins
  3. Creator Education & Certification Programs (Digital Courses)

For each candidate and each retry gap, the generated external query must
contain the candidate's business concept + requirement-specific intent,
never bare Jarvis orchestration vocabulary, and never accidentally read as
HR/recruiting. Offline — no Tavily calls."""
from __future__ import annotations

from app.research_intelligence.query_builder import build_external_research_query

CANDIDATES = (
    "Creator-Focused Digital Product Platform / Marketplace",
    "Niche-Specific Workflow Automation Software & Plugins",
    "Creator Education & Certification Programs (Digital Courses)",
)

CATEGORIES = ("pricing", "competition", "demand", "customer_pain", "market_size", "feasibility")

_HR_RECRUITING_TERMS = (
    "candidate screening",
    "background screening",
    "hiring coordination",
    "pre-employment testing",
    "ats",
    "applicant tracking",
    "job applicant",
    "recruiter",
    "recruiting tool",
)


def _all_queries():
    for label in CANDIDATES:
        for category in CATEGORIES:
            yield label, category, build_external_research_query(candidate_label=label, category=category)


# --- meaningful business concept + requirement-specific intent ------------


def test_every_query_contains_meaningful_business_concept_and_requirement_intent():
    for label, category, query in _all_queries():
        lowered = query.lower()
        assert query  # non-empty
        assert len(lowered.split()) >= 3  # not degenerate
        # requirement-specific intent word present
        intent_markers = {
            "pricing": "pricing",
            "competition": "competitor",
            "demand": "demand",
            "customer_pain": "problem",
            "market_size": "market",
            "feasibility": "cost",
        }
        assert intent_markers[category] in lowered


# --- no bare Jarvis orchestration vocabulary --------------------------------


def test_no_orchestration_vocabulary_in_any_query():
    for label, category, query in _all_queries():
        lowered = query.lower()
        assert "candidate" not in lowered
        assert "opportunity" not in lowered
        assert "opportunities" not in lowered
        assert "validation task" not in lowered
        assert "research task" not in lowered


# --- 13. No accidental HR/recruiting interpretation of "candidate" --------


def test_no_hr_recruiting_contamination_in_any_query():
    for label, category, query in _all_queries():
        lowered = query.lower()
        for term in _HR_RECRUITING_TERMS:
            assert term not in lowered


# --- 14. Queries for different candidates are distinguishable -------------


def test_queries_are_candidate_specific_and_distinguishable():
    for category in CATEGORIES:
        queries = [build_external_research_query(candidate_label=label, category=category) for label in CANDIDATES]
        assert len(set(queries)) == len(queries)  # all unique

    platform_query = build_external_research_query(candidate_label=CANDIDATES[0], category="pricing")
    workflow_query = build_external_research_query(candidate_label=CANDIDATES[1], category="pricing")
    education_query = build_external_research_query(candidate_label=CANDIDATES[2], category="pricing")

    assert "creator" in platform_query.lower()
    assert "platform" in platform_query.lower() or "marketplace" in platform_query.lower()
    assert "workflow" in workflow_query.lower()
    assert "automation" in workflow_query.lower()
    assert "education" in education_query.lower() or "certification" in education_query.lower()

    # Distinct enough that a search engine would return different results
    # for each — no shared bare-orchestration phrase carrying all the
    # distinguishing weight.
    assert platform_query != workflow_query != education_query


def test_gap_retry_queries_for_these_candidates_are_also_clean_and_distinct():
    from app.agents.research import _validation_gaps
    from app.config.settings import Settings
    from app.research_intelligence.coverage import build_coverage_matrix
    from app.research_intelligence.requirements import generate_requirement_set
    from app.research_intelligence.schemas import ResearchCandidate

    settings = Settings()
    candidates = [
        ResearchCandidate(id=f"c{i}", label=label) for i, label in enumerate(CANDIDATES)
    ]
    requirements = []
    for c in candidates:
        requirements.extend(generate_requirement_set(candidate_id=c.id, candidate_label=c.label, settings=settings))
    coverage_cells = build_coverage_matrix(requirements, {c.id: [] for c in candidates}, settings=settings)

    gaps = _validation_gaps(requirements, coverage_cells, candidates, settings=settings)
    assert gaps
    queries = [g.suggested_query for g in gaps]
    assert len(set(queries)) == len(queries)
    for query in queries:
        lowered = query.lower()
        assert "candidate" not in lowered
        assert "opportunity" not in lowered
        for term in _HR_RECRUITING_TERMS:
            assert term not in lowered
