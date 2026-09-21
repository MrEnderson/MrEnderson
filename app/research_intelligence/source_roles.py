"""Source-role classification (Phase 3). Extends the existing basic
source_quality concept (app/agents/research.py::_classify_source_quality)
with a role that describes what a source can be USED FOR, not how trustworthy
it universally is. A COMMUNITY source is not automatically weak — it is often
the best evidence for customer pain. A PRIMARY source is not automatically
unbiased — it just means official/first-party.

Deterministic domain/URL heuristics only. Never a machine-learning ranker.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.schemas.evidence import SourceRole

_AUTHORITATIVE_SUFFIXES = (
    ".gov",
    ".gov.uk",
    ".europa.eu",
    ".edu",
    ".ac.uk",
    ".int",
    ".mil",
)

# Recognized market-research / analytics / measurement organizations.
_COMMERCIAL_RESEARCH_DOMAINS = (
    "statista.com",
    "gartner.com",
    "forrester.com",
    "nielsen.com",
    "mckinsey.com",
    "ibisworld.com",
    "similarweb.com",
    "sensortower.com",
    "app.similarweb.com",
    "grandviewresearch.com",
    "marketsandmarkets.com",
    "crunchbase.com",
    "pitchbook.com",
    "cbinsights.com",
)

# Marketplace / product-catalog / app-store / template-store style sources.
_MARKETPLACE_DOMAINS = (
    "amazon.com",
    "etsy.com",
    "ebay.com",
    "shopify.com",
    "apps.shopify.com",
    "gumroad.com",
    "producthunt.com",
    "g2.com",
    "capterra.com",
    "themeforest.net",
    "envato.com",
    "creativemarket.com",
    "chrome.google.com",
    "play.google.com",
    "apps.apple.com",
    "udemy.com",
    "appsumo.com",
    "shopify.app",
    "trustpilot.com",
)

_COMMUNITY_MARKERS = (
    "reddit.com",
    "quora.com",
    "forum.",
    ".forum",
    "community.",
    "news.ycombinator.com",
    "indiehackers.com",
    "stackexchange.com",
    "stackoverflow.com",
    "discourse.",
)

_DISCOVERY_MARKERS = (
    "youtube.com",
    "youtu.be",
    "medium.com",
    "substack.com",
    "tiktok.com",
    "twitter.com",
    "x.com",
    "linkedin.com/pulse",
)

# Path SEGMENTS (not substrings — avoids matching a blog post titled
# something like "pricing-guide-2026") that suggest official first-party
# material: a company's own pricing/plans/docs/product/features/
# integrations/investors/about page. v0.1.2.6 Phase 8: "integrations" was
# missing despite being one of the explicitly-named categories a vendor's
# OWN page can legitimately be PRIMARY for (see
# app/research_intelligence/suitability.py's policy table — PRIMARY is
# never STRONG for market_size/growth-type claims regardless, only
# ACCEPTABLE at best, so this can never make a vendor's market-wide claim
# look authoritative; it only recognizes more of a vendor's own-product
# pages as PRIMARY in the first place).
_PRIMARY_PATH_SEGMENTS = frozenset(
    {"pricing", "plans", "plan", "docs", "documentation", "product", "products", "features", "integrations", "integration", "investors", "about"}
)


def _has_primary_path(path: str) -> bool:
    segments = {s for s in path.strip("/").split("/") if s}
    return bool(segments & _PRIMARY_PATH_SEGMENTS)


def classify_source_role(url: str | None, *, candidate_label: str | None = None) -> SourceRole:
    """Deterministic role classification from the URL alone.

    v0.1.2.3: an unrecognized domain (i.e. not a known government/academic/
    commercial-research/marketplace/community/discovery site) with an
    official-looking path segment is treated as PRIMARY — a company's own
    claim about itself — whether or not that company happens to be the
    candidate being researched or a named competitor mentioned in its
    evidence. This is deliberately broader than requiring the domain to
    match the candidate's own label: "official vendor pricing/features ->
    PRIMARY for that vendor's own claims" applies to ANY vendor, not just
    the one Research happens to be validating right now (see
    docs/research_intelligence.md, "Source quality/coverage"). It never
    means "every company website is independent authoritative market
    evidence" — app/research_intelligence/suitability.py still caps how
    much weight PRIMARY carries for claims a vendor can't independently
    validate (e.g. total market size, unbiased competitive superiority).
    `candidate_label` is accepted for backward compatibility but no longer
    changes the outcome — the path-segment heuristic already generalizes
    it."""
    if not url:
        return "UNKNOWN"
    domain = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if not domain:
        return "UNKNOWN"
    domain = domain[4:] if domain.startswith("www.") else domain

    # Government/academic/commercial-research/marketplace/community/
    # discovery are all unambiguous, explicitly-known classifications —
    # checked first so they're never overridden by the generic "looks like
    # an official page" PRIMARY guess below.
    if any(domain.endswith(suffix) for suffix in _AUTHORITATIVE_SUFFIXES):
        return "AUTHORITATIVE"
    if any(domain == d or domain.endswith("." + d) for d in _COMMERCIAL_RESEARCH_DOMAINS):
        return "COMMERCIAL_RESEARCH"
    if any(domain == d or domain.endswith("." + d) for d in _MARKETPLACE_DOMAINS):
        return "MARKETPLACE"
    if any(marker in domain for marker in _COMMUNITY_MARKERS):
        return "COMMUNITY"
    if any(marker in domain for marker in _DISCOVERY_MARKERS):
        return "DISCOVERY"
    if _has_primary_path(path):
        return "PRIMARY"
    return "UNKNOWN"
