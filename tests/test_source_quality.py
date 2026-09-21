"""Conservative source-quality classification. Never asserts PRIMARY
automatically, and never claims the classification proves a claim true —
see app/agents/research.py::_classify_source_quality."""
from __future__ import annotations

from app.agents.research import _classify_source_quality


def test_gov_domain_is_authoritative():
    assert _classify_source_quality("https://www.census.gov/data") == "AUTHORITATIVE"


def test_edu_domain_is_authoritative():
    assert _classify_source_quality("https://stanford.edu/research") == "AUTHORITATIVE"


def test_reddit_is_community():
    assert _classify_source_quality("https://reddit.com/r/SaaS") == "COMMUNITY"


def test_unknown_commercial_domain_is_unknown_not_authoritative():
    assert _classify_source_quality("https://some-blog.example.com/post") == "UNKNOWN"


def test_missing_url_is_unknown():
    assert _classify_source_quality(None) == "UNKNOWN"


def test_never_auto_assigns_primary():
    urls = [
        "https://www.census.gov/data",
        "https://stanford.edu/research",
        "https://reddit.com/r/SaaS",
        "https://example.com/x",
        None,
    ]
    assert all(_classify_source_quality(u) != "PRIMARY" for u in urls)
