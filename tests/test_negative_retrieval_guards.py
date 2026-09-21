"""v0.1.2.5 Phase 5: negative retrieval guards. The live v0.1.2.4 mission
kept retrieving HR/ATS material for digital-product validation. These
terms are never a global ban — they're excluded only when the candidate
being researched doesn't itself genuinely relate to that domain. Offline
— no network call."""
from __future__ import annotations

from app.research_intelligence.prescreen import is_contextually_excluded, prescreen_search_result
from app.research_intelligence.query_builder import build_candidate_concepts
from app.tools.research_tools import SearchResult

DIGITAL_PRODUCT_CONCEPTS = build_candidate_concepts(
    "AI-Powered Content Creation Tools & Templates",
    "A marketplace of AI prompt templates and workflow automation for small businesses.",
)


# --- 10. HR candidate-assessment result rejected for digital-product research


def test_hr_result_prescreen_rejected_for_digital_product_research():
    hr_result = SearchResult(
        title="Candidate Experience Statistics and Applicant Tracking Software Market Report",
        url="https://www.grandviewresearch.com/candidate-assessment-market",
        snippet="The global candidate assessment and applicant tracking system (ATS) market size...",
    )
    assert is_contextually_excluded(hr_result, concepts=DIGITAL_PRODUCT_CONCEPTS) is True
    assert prescreen_search_result(hr_result, concepts=DIGITAL_PRODUCT_CONCEPTS) is False


# --- 11. political candidate result rejected --------------------------------


def test_political_result_prescreen_rejected():
    political_result = SearchResult(
        title="Political Candidate Election Fundraising Report",
        url="https://example-news.com/election-2026",
        snippet="The political candidate's campaign donation totals ahead of the primary election.",
    )
    assert is_contextually_excluded(political_result, concepts=DIGITAL_PRODUCT_CONCEPTS) is True
    assert prescreen_search_result(political_result, concepts=DIGITAL_PRODUCT_CONCEPTS) is False


# --- 12. legitimate ambiguous result preserved when the candidate itself is
# actually about recruitment/elections (GENERAL mode) ------------------------


def test_ambiguous_result_preserved_when_candidate_is_genuinely_about_recruiting():
    recruiting_candidate_concepts = build_candidate_concepts(
        "AI-Powered Recruiting and Applicant Tracking Platform",
        "Helps small businesses with hiring, recruiting, and applicant tracking for open jobs.",
    )
    hr_result = SearchResult(
        title="Applicant Tracking Software Market Report",
        url="https://www.grandviewresearch.com/candidate-assessment-market",
        snippet="The applicant tracking and candidate assessment market continues to grow.",
    )
    assert is_contextually_excluded(hr_result, concepts=recruiting_candidate_concepts) is False
    assert prescreen_search_result(hr_result, concepts=recruiting_candidate_concepts) is True


def test_ambiguous_result_preserved_when_candidate_is_genuinely_about_civic_tech():
    civic_tech_concepts = build_candidate_concepts(
        "Civic Election Transparency Platform",
        "A civic-tech platform helping voters track political campaign donations and election data.",
    )
    political_result = SearchResult(
        title="Political Candidate Election Fundraising Report",
        url="https://example-news.com/election-2026",
        snippet="The political candidate's campaign donation totals ahead of the primary election.",
    )
    assert is_contextually_excluded(political_result, concepts=civic_tech_concepts) is False
    assert prescreen_search_result(political_result, concepts=civic_tech_concepts) is True


def test_guard_is_never_a_global_ban_only_applies_when_candidate_context_calls_for_it():
    """A single word ('jobs') never triggers the guard on its own outside
    a recognized noise-marker PHRASE — conservative, not trigger-happy."""
    result = SearchResult(
        title="Best jobs to be automated by AI content tools",
        url="https://example.com/blog/ai-jobs-automation",
        snippet="AI content creation tools are changing certain jobs in the marketing industry.",
    )
    # "jobs" alone (not "job posting"/"recruitment"/etc.) never matches a
    # noise marker — this is legitimate content about the actual candidate.
    assert is_contextually_excluded(result, concepts=DIGITAL_PRODUCT_CONCEPTS) is False


def test_legitimate_unrelated_result_is_not_rejected_by_the_guard():
    """The negative guard only fires on its OWN specific noise markers —
    it must never become a general off-topic filter (that's the Admission
    Gate's job, not pre-screen's)."""
    generic_seo_blog = SearchResult(
        title="10 Best AI Content Tools for Small Business Marketing",
        url="https://example-blog.com/best-ai-content-tools",
        snippet="Our top picks for AI content creation tools and template marketplaces in 2026.",
    )
    assert is_contextually_excluded(generic_seo_blog, concepts=DIGITAL_PRODUCT_CONCEPTS) is False
