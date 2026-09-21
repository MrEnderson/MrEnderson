"""v0.1.2.6 Phase 8: source-role classification for vendor sources. The
live benchmark showed obviously-commercial vendor domains (Algolia,
Bloomreach, Voyado, Zylo, ...) printing as Source role: UNKNOWN — this is
correct, conservative behavior for pages that don't look like a vendor's
own official product material. Required semantics:

- An official vendor page about ITS OWN product features/pricing/
  integrations/documentation MAY be PRIMARY.
- A vendor page making claims about overall market size, superiority,
  competitor performance, or industry-wide demand must NOT automatically
  become authoritative for those claims — PRIMARY is never STRONG
  suitability for market_size/growth-type categories, only ACCEPTABLE at
  best (app/research_intelligence/suitability.py's own policy table,
  unchanged this checkpoint).

Offline — no network call.
"""
from __future__ import annotations

from app.research_intelligence.source_roles import classify_source_role
from app.research_intelligence.suitability import evaluate_source_suitability
from app.schemas.evidence import EvidenceItem


# --- 23. official vendor page about its own product -> PRIMARY -------------


def test_vendor_pricing_page_classified_primary():
    assert classify_source_role("https://www.algolia.com/pricing") == "PRIMARY"


def test_vendor_integrations_page_classified_primary():
    assert classify_source_role("https://www.bloomreach.com/integrations") == "PRIMARY"


def test_vendor_documentation_page_classified_primary():
    assert classify_source_role("https://docs.voyado.com/documentation/getting-started") == "PRIMARY"


def test_vendor_product_features_page_classified_primary():
    assert classify_source_role("https://www.zylo.com/product/features") == "PRIMARY"


# --- 24. vendor market-wide claim not automatically authoritative ----------


def test_vendor_blog_post_with_no_recognized_path_stays_unknown_not_authoritative():
    """A vendor's blog post making a market-wide claim, with no
    recognized official-product path segment, stays UNKNOWN — never
    silently promoted to PRIMARY or any authoritative role just because
    the domain is a known commercial vendor."""
    role = classify_source_role("https://www.algolia.com/blog/state-of-search-2026-market-trends")
    assert role == "UNKNOWN"


def test_primary_vendor_source_is_never_strong_for_market_size_claims():
    """Even when a vendor page legitimately IS classified PRIMARY (its
    own pricing/features page), that role is never STRONG suitability for
    a market-size/growth-type claim — only ACCEPTABLE at best. PRIMARY
    being correct for "what does this vendor charge" must never silently
    also mean "this vendor's claim about the WHOLE market is authoritative."
    """
    suitability = evaluate_source_suitability(
        "market_size", EvidenceItem(claim="x", source_role="PRIMARY", source_url="https://www.algolia.com/pricing")
    )
    assert suitability in ("ACCEPTABLE", "WEAK", "UNSUITABLE")
    assert suitability != "STRONG"


def test_primary_vendor_source_is_strong_for_its_own_pricing_claim():
    """The flip side: PRIMARY IS the strongest suitability for pricing —
    a vendor's own pricing page is exactly the right source for "what
    does X charge," unlike market-size claims."""
    suitability = evaluate_source_suitability(
        "pricing", EvidenceItem(claim="x", source_role="PRIMARY", source_url="https://www.algolia.com/pricing")
    )
    assert suitability == "STRONG"


def test_unknown_role_vendor_source_is_unsuitable_for_market_size_not_silently_authoritative():
    """The actual v0.1.2.5 coverage-suppression mechanism (Phase 7's root
    cause): an UNKNOWN-role item (an unrecognized commercial domain with
    no recognized official-product path) is UNSUITABLE for market_size —
    contributes ZERO toward that cell's strong/acceptable/weak counts, not
    merely 'weak'. This is intentionally conservative, not a bug to
    silently paper over by promoting UNKNOWN to authoritative."""
    suitability = evaluate_source_suitability(
        "market_size", EvidenceItem(claim="x", source_role="UNKNOWN", source_url="https://www.example-saas-vendor.com/some-page")
    )
    assert suitability == "UNSUITABLE"
