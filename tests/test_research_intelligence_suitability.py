"""Claim <-> source policy (Phase 4). Small, explicit, deterministic table.
Offline."""
from __future__ import annotations

from app.research_intelligence.suitability import evaluate_source_suitability
from app.schemas.evidence import EvidenceItem


def _evidence(url: str, *, source_role=None) -> EvidenceItem:
    item = EvidenceItem(claim="c", source_url=url)
    if source_role is not None:
        item = item.model_copy(update={"source_role": source_role})
    return item


def test_market_size_with_authoritative_source_is_strong():
    assert evaluate_source_suitability("market_size", _evidence("https://census.gov/data", source_role="AUTHORITATIVE")) == "STRONG"


def test_market_size_with_discovery_source_is_unsuitable():
    assert evaluate_source_suitability("market_size", _evidence("https://youtube.com/watch?v=1", source_role="DISCOVERY")) == "UNSUITABLE"


def test_pricing_with_official_competitor_page_is_strong():
    assert evaluate_source_suitability("pricing", _evidence("https://competitor.com/pricing", source_role="PRIMARY")) == "STRONG"


def test_pricing_with_generic_blog_is_weak():
    """Matches the "revenue claim + generic blog -> weak" spirit for
    pricing/financial-adjacent claims."""
    assert evaluate_source_suitability("pricing", _evidence("https://blog.example.com/x", source_role="DISCOVERY")) == "WEAK"


def test_customer_pain_with_reddit_is_strong():
    """Community evidence is not automatically weak — it's the best source
    for qualitative customer pain."""
    assert evaluate_source_suitability("customer_pain", _evidence("https://reddit.com/r/x", source_role="COMMUNITY")) == "STRONG"


def test_derives_role_from_url_when_not_pre_classified():
    item = EvidenceItem(claim="c", source_url="https://www.census.gov/data")
    assert item.source_role == "UNKNOWN"  # not pre-tagged
    assert evaluate_source_suitability("market_size", item) == "STRONG"  # derived AUTHORITATIVE


def test_unrecognized_category_falls_back_to_other_policy():
    assert evaluate_source_suitability("other", _evidence("https://example.com/x", source_role="UNKNOWN")) == "WEAK"
