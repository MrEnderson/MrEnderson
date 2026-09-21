"""Source-role classification (Phase 3). Deterministic URL/domain heuristics
only — never a truth score. Offline."""
from __future__ import annotations

from app.research_intelligence.source_roles import classify_source_role


def test_official_pricing_page_is_primary():
    assert classify_source_role("https://notion.so/pricing", candidate_label="Notion") == "PRIMARY"


def test_government_domain_is_authoritative():
    assert classify_source_role("https://www.census.gov/data") == "AUTHORITATIVE"


def test_academic_domain_is_authoritative():
    assert classify_source_role("https://stanford.edu/research") == "AUTHORITATIVE"


def test_recognized_research_provider_is_commercial_research():
    assert classify_source_role("https://www.statista.com/statistics/12345") == "COMMERCIAL_RESEARCH"
    assert classify_source_role("https://www.gartner.com/en/reports/x") == "COMMERCIAL_RESEARCH"


def test_marketplace_domain_is_marketplace():
    assert classify_source_role("https://www.producthunt.com/posts/x") == "MARKETPLACE"
    assert classify_source_role("https://gumroad.com/l/x") == "MARKETPLACE"


def test_reddit_and_forum_are_community():
    assert classify_source_role("https://reddit.com/r/SaaS") == "COMMUNITY"
    assert classify_source_role("https://www.indiehackers.com/post/x") == "COMMUNITY"


def test_youtube_and_blog_are_discovery():
    assert classify_source_role("https://www.youtube.com/watch?v=abc") == "DISCOVERY"
    assert classify_source_role("https://medium.com/@someone/post") == "DISCOVERY"


def test_unrecognized_domain_is_unknown():
    assert classify_source_role("https://some-random-blog.example.com/post") == "UNKNOWN"


def test_missing_url_is_unknown():
    assert classify_source_role(None) == "UNKNOWN"


def test_own_domain_without_official_path_is_not_primary():
    """A candidate's own domain with no pricing/product/docs-style path is
    not confidently PRIMARY — PRIMARY requires both signals."""
    assert classify_source_role("https://notion.so/blog/random-post", candidate_label="Notion") != "PRIMARY"


def test_competitor_own_pricing_page_is_also_primary():
    """v0.1.2.3: an official pricing page is PRIMARY for THAT vendor's own
    claims regardless of whether the vendor happens to be the candidate
    being researched or a named competitor — "official vendor pricing" is
    always a first-party claim about itself. See
    docs/research_intelligence.md, "Source quality/coverage"."""
    assert classify_source_role("https://competitor.com/pricing", candidate_label="Notion") == "PRIMARY"


def test_primary_classification_does_not_depend_on_candidate_label_matching():
    """The same URL classifies identically regardless of which (or
    whether any) candidate_label is passed — PRIMARY is about the source
    itself, not about matching the current research subject."""
    assert (
        classify_source_role("https://competitor.com/pricing", candidate_label="Notion")
        == classify_source_role("https://competitor.com/pricing", candidate_label=None)
        == classify_source_role("https://competitor.com/pricing")
        == "PRIMARY"
    )


def test_generic_blog_path_is_not_misclassified_as_primary():
    """A path that merely CONTAINS "pricing" as a substring (not a real
    path segment) must not trigger a false PRIMARY — e.g. a blog post
    slug like "our-2026-pricing-guide-roundup"."""
    assert classify_source_role("https://some-random-blog.example.com/our-2026-pricing-guide-roundup") == "UNKNOWN"
