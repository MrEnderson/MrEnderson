"""Research Requirement Planner (Phase 2): comparison objectives get a
common, bounded requirement set per candidate. Offline, deterministic."""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.requirements import (
    CORE_COMPARISON_CATEGORIES,
    generate_candidate_requirement_sets,
    generate_requirement_set,
)


def test_comparison_produces_common_requirement_categories_across_candidates():
    sets = generate_candidate_requirement_sets(
        [("cand-a", "Candidate A"), ("cand-b", "Candidate B")], settings=Settings()
    )
    categories_a = {r.category for r in sets["cand-a"]}
    categories_b = {r.category for r in sets["cand-b"]}
    assert categories_a == categories_b == set(CORE_COMPARISON_CATEGORIES)


def test_candidates_remain_distinct():
    sets = generate_candidate_requirement_sets(
        [("cand-a", "Candidate A"), ("cand-b", "Candidate B")], settings=Settings()
    )
    for req in sets["cand-a"]:
        assert req.candidate_id == "cand-a"
        assert "Candidate A" in req.question
    for req in sets["cand-b"]:
        assert req.candidate_id == "cand-b"
        assert "Candidate B" in req.question
    assert {r.id for r in sets["cand-a"]}.isdisjoint({r.id for r in sets["cand-b"]})


def test_requirements_bounded_by_settings():
    settings = Settings(research_max_requirements_per_candidate=3)
    reqs = generate_requirement_set(candidate_id="c", candidate_label="C", settings=settings)
    assert len(reqs) == 3


def test_requirement_set_reusable_across_business_types_no_hardcoded_vertical():
    """The planner never special-cases a specific vertical — the same
    category machinery works for any candidate label."""
    for label in ("SaaS billing tool", "Etsy print-on-demand shop", "Local dog walking service"):
        reqs = generate_requirement_set(candidate_id="c", candidate_label=label, settings=Settings())
        assert {r.category for r in reqs} == set(CORE_COMPARISON_CATEGORIES)
        assert all(label in r.question for r in reqs)


def test_default_status_is_missing_before_any_coverage_computed():
    reqs = generate_requirement_set(candidate_id="c", candidate_label="C", settings=Settings())
    assert all(r.status == "MISSING" for r in reqs)
