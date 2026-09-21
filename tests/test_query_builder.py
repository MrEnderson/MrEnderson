"""Defect 1 (v0.1.2.2): Jarvis's own orchestration vocabulary must never
leak into an external search query. A live benchmark reproduced this
exactly — retrieval for "candidate opportunities" pulled in political-
candidate and HR-recruitment content instead of the actual digital-product
concepts. Offline, deterministic — no network calls."""
from __future__ import annotations

from app.research_intelligence.query_builder import (
    build_external_research_query,
    build_external_search_concept,
)

AI_EDUCATION = ("AI Tool Education & Tutorials (Courses/Templates)", "Courses and templates teaching AI tools.")
COHORT_COURSES = (
    "Expertise-Based Educational Products (eBooks/Cohort Courses)",
    "Ebooks and cohort-based courses built on niche expertise.",
)
TEMPLATES_PLANNERS = (
    "Niche Templates & Planners (Design Assets)",
    "Digital planner and template design assets sold on marketplaces.",
)

_HR_TERMS = ("job applicant", "resume", "interview process", "hiring manager", "recruiter")
_POLITICAL_TERMS = ("election", "ballot", "voter", "campaign trail", "running for office")


# --- 1. No internal "candidate opportunity" leakage -------------------------


def test_no_candidate_opportunity_leakage_in_any_benchmark_query():
    for category in ("pricing", "competition", "demand"):
        for label, description in (AI_EDUCATION, COHORT_COURSES, TEMPLATES_PLANNERS):
            query = build_external_research_query(
                candidate_label=label, candidate_description=description, category=category
            )
            lowered = query.lower()
            assert "candidate" not in lowered
            assert "opportunity" not in lowered
            assert "opportunities" not in lowered


# --- 2. AI education pricing query contains AI/course/pricing concepts -----


def test_ai_education_pricing_query_contains_expected_concepts():
    label, description = AI_EDUCATION
    query = build_external_research_query(candidate_label=label, candidate_description=description, category="pricing")
    lowered = query.lower()
    assert "ai" in lowered
    assert "course" in lowered
    assert "pricing" in lowered


def test_ai_education_competition_query_contains_expected_concepts():
    label, description = AI_EDUCATION
    query = build_external_research_query(candidate_label=label, candidate_description=description, category="competition")
    lowered = query.lower()
    assert "ai" in lowered
    assert "competitor" in lowered


# --- 3. Template competition query contains template/planner/competition --


def test_template_competition_query_contains_expected_concepts():
    label, description = TEMPLATES_PLANNERS
    query = build_external_research_query(candidate_label=label, candidate_description=description, category="competition")
    lowered = query.lower()
    assert "template" in lowered
    assert "planner" in lowered
    assert "competitor" in lowered


def test_template_pricing_query_contains_expected_concepts():
    label, description = TEMPLATES_PLANNERS
    query = build_external_research_query(candidate_label=label, candidate_description=description, category="pricing")
    lowered = query.lower()
    assert "template" in lowered
    assert "pricing" in lowered


# --- 4. Cohort-course pricing query contains cohort/course/pricing --------


def test_cohort_course_pricing_query_contains_expected_concepts():
    label, description = COHORT_COURSES
    query = build_external_research_query(candidate_label=label, candidate_description=description, category="pricing")
    lowered = query.lower()
    assert "cohort" in lowered
    assert "course" in lowered
    assert "pricing" in lowered


def test_cohort_course_competition_query_contains_expected_concepts():
    label, description = COHORT_COURSES
    query = build_external_research_query(candidate_label=label, candidate_description=description, category="competition")
    lowered = query.lower()
    assert "cohort" in lowered
    assert "competitor" in lowered


# --- 5/6. Neither HR recruitment nor political-candidate interpretation ---
#          appears anywhere


def test_no_hr_recruitment_interpretation_in_any_query():
    for label, description in (AI_EDUCATION, COHORT_COURSES, TEMPLATES_PLANNERS):
        for category in ("pricing", "competition", "demand", "customer_pain", None):
            query = build_external_research_query(candidate_label=label, candidate_description=description, category=category)
            lowered = query.lower()
            assert not any(term in lowered for term in _HR_TERMS)


def test_no_political_candidate_interpretation_in_any_query():
    for label, description in (AI_EDUCATION, COHORT_COURSES, TEMPLATES_PLANNERS):
        for category in ("pricing", "competition", "demand", "customer_pain", None):
            query = build_external_research_query(candidate_label=label, candidate_description=description, category=category)
            lowered = query.lower()
            assert not any(term in lowered for term in _POLITICAL_TERMS)


# --- 7. Queries remain bounded in length ------------------------------------


def test_queries_remain_bounded_in_length():
    long_label = "Extremely Verbose Candidate Opportunity Label " * 10 + "(with lots of parenthetical detail/extra words)"
    query = build_external_research_query(candidate_label=long_label, candidate_description="a" * 500, category="pricing")
    assert len(query) <= 200


def test_search_concept_never_empty_for_orchestration_only_label():
    """A label that's PURELY orchestration vocabulary must not produce an
    empty/degenerate query."""
    concept = build_external_search_concept("candidate opportunity")
    assert concept == ""  # correctly stripped to nothing
    query = build_external_research_query(candidate_label="candidate opportunity", category="pricing")
    assert query  # but the query builder still produces something usable
    assert "candidate" not in query.lower()


def test_discovery_title_orchestration_terms_stripped():
    """The exact contamination scenario: a planner-authored DISCOVERY task
    title containing Jarvis's own vocabulary must never reach an external
    query unsanitized."""
    concept = build_external_search_concept("Discover candidate digital-product opportunities")
    lowered = concept.lower()
    assert "candidate" not in lowered
    assert "opportunit" not in lowered
    assert "digital" in lowered
    assert "product" in lowered
