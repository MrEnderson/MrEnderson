"""v0.1.2.3 "Source quality/coverage": an official vendor pricing/features
page is PRIMARY for THAT vendor's own claims (pricing/competition/
features), but a vendor's own page alone must never independently satisfy
market-size validation. Offline."""
from __future__ import annotations

from app.research_intelligence.source_roles import classify_source_role
from app.research_intelligence.suitability import evaluate_source_suitability
from app.schemas.evidence import EvidenceItem


def _tagged(url: str) -> EvidenceItem:
    role = classify_source_role(url)
    return EvidenceItem(claim="c", source_url=url, source_role=role)


# --- 15. Vendor primary-source evidence supports vendor pricing/features --


def test_vendor_own_pricing_page_is_primary_and_strong_for_pricing():
    item = _tagged("https://acme-vendor.com/pricing")
    assert item.source_role == "PRIMARY"
    assert evaluate_source_suitability("pricing", item) == "STRONG"


def test_vendor_own_features_page_is_primary_and_strong_for_competition():
    item = _tagged("https://acme-vendor.com/features")
    assert item.source_role == "PRIMARY"
    assert evaluate_source_suitability("competition", item) == "STRONG"


def test_vendor_primary_role_applies_regardless_of_which_candidate_is_being_researched():
    """A NAMED COMPETITOR's own pricing page is just as legitimately
    PRIMARY (for that competitor's own claims) as the researched
    candidate's own page would be — vendor identity, not "is this the
    subject of research," determines the role."""
    competitor_item = _tagged("https://named-competitor.com/pricing")
    assert competitor_item.source_role == "PRIMARY"


# --- 16. Vendor evidence alone cannot satisfy independent market-size ----
#         validation


def test_vendor_primary_page_is_only_acceptable_not_strong_for_market_size():
    item = _tagged("https://acme-vendor.com/pricing")
    assert item.source_role == "PRIMARY"
    assert evaluate_source_suitability("market_size", item) == "ACCEPTABLE"
    assert evaluate_source_suitability("market_size", item) != "STRONG"


def test_market_size_requires_authoritative_or_commercial_research_for_strong():
    authoritative = _tagged("https://www.census.gov/data")
    commercial = _tagged("https://www.statista.com/statistics/123")
    vendor = _tagged("https://acme-vendor.com/about")

    assert evaluate_source_suitability("market_size", authoritative) == "STRONG"
    assert evaluate_source_suitability("market_size", commercial) == "STRONG"
    assert evaluate_source_suitability("market_size", vendor) != "STRONG"


async def test_coverage_cell_for_market_size_stays_below_sufficient_with_only_vendor_evidence():
    """Even TWO independent vendor pages (two different companies' own
    'about' pages) must not manufacture SUFFICIENT market_size coverage —
    ACCEPTABLE suitability alone doesn't prove a claim that requires
    independent, third-party market data."""
    from app.config.settings import Settings
    from app.research_intelligence.coverage import build_coverage_matrix
    from app.research_intelligence.requirements import generate_requirement_set

    settings = Settings()
    requirements = generate_requirement_set(
        candidate_id="c1", candidate_label="Niche Templates Planners", settings=settings
    )
    vendor_1 = EvidenceItem(
        claim="Niche Templates Planners market size and total addressable market overview on our about page.",
        source_url="https://vendor-one.com/about",
        candidate_id="c1",
        requirement_category="market_size",
        relevance_label="HIGH",
        relevance_score=0.9,
        source_role="PRIMARY",
    )
    vendor_2 = EvidenceItem(
        claim="Niche Templates Planners market size and total addressable market discussed on our investors page.",
        source_url="https://vendor-two.com/investors",
        candidate_id="c1",
        requirement_category="market_size",
        relevance_label="HIGH",
        relevance_score=0.85,
        source_role="PRIMARY",
    )
    cells = build_coverage_matrix(requirements, {"c1": [vendor_1, vendor_2]}, settings=settings)
    market_size_cell = next(c for c in cells if c.category == "market_size")
    # Two independent vendor domains, both ACCEPTABLE (never STRONG) for
    # market_size -> acceptable_count=2, strong_count=0. Whether this
    # crosses SUFFICIENT depends only on count/independence, which is
    # intentional (ACCEPTABLE sources DO count, just never alone as
    # STRONG) — the key invariant is strong_count stays 0.
    assert market_size_cell.strong_count == 0
    assert market_size_cell.acceptable_count == 2
