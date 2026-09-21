"""Research Requirement Planner (Phase 2). Before broad research begins,
builds a deterministic, structured representation of WHAT must be
established for a candidate — reusable across SaaS, ecommerce, services,
affiliate, digital products, software, marketplaces, and future business
types. Never hard-codes a specific vertical.

For an opportunity-comparison objective, every candidate gets the SAME core
requirement categories so coverage stays comparable (see
app/research_intelligence/completeness.py).
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.schemas import ResearchRequirement
from app.schemas.evidence import RequirementCategory, SourceRole

# The common minimum core for a candidate-comparison objective (Phase 2's
# example: Demand / Competition / Pricing / Customer pain / Market-growth /
# Feasibility). Order also doubles as a stable priority ordering.
CORE_COMPARISON_CATEGORIES: tuple[RequirementCategory, ...] = (
    "demand",
    "competition",
    "pricing",
    "customer_pain",
    "market_size",
    "feasibility",
)

# (importance, preferred_source_roles, minimum_evidence_count,
#  requires_independent_sources, quantitative, question_template)
_CATEGORY_SPEC: dict[RequirementCategory, tuple[int, tuple[SourceRole, ...], int, bool, bool, str]] = {
    "demand": (4, ("MARKETPLACE", "COMMERCIAL_RESEARCH", "AUTHORITATIVE"), 2, True, False, "Is there real, evidenced demand for {candidate}?"),
    "customer_pain": (4, ("COMMUNITY", "PRIMARY", "MARKETPLACE"), 2, False, False, "What specific pain points do customers report for {candidate}?"),
    "competition": (5, ("PRIMARY", "MARKETPLACE"), 2, True, False, "Who are {candidate}'s named competitors?"),
    "pricing": (5, ("PRIMARY", "MARKETPLACE"), 2, True, True, "What do {candidate}'s competitors charge?"),
    "market_size": (3, ("AUTHORITATIVE", "COMMERCIAL_RESEARCH"), 2, True, True, "How large is the addressable market for {candidate}?"),
    "growth": (3, ("AUTHORITATIVE", "COMMERCIAL_RESEARCH", "PRIMARY"), 2, True, True, "Is the market for {candidate} growing?"),
    "willingness_to_pay": (4, ("MARKETPLACE", "PRIMARY"), 2, False, False, "Is there evidence customers will pay for {candidate}?"),
    "feasibility": (2, ("PRIMARY", "AUTHORITATIVE"), 1, False, False, "Is {candidate} technically/operationally feasible to build?"),
    "unit_economics": (3, ("PRIMARY",), 2, False, True, "What do the unit economics of {candidate} look like?"),
    "customer_validation": (3, ("PRIMARY", "COMMUNITY"), 2, False, False, "Has demand for {candidate} been directly validated with customers?"),
    "other": (2, (), 1, False, False, "{candidate}: other supporting evidence."),
}

# A requirement in these categories is treated as a "critical" blocker for
# comparison readiness if missing entirely — see
# app/research_intelligence/completeness.py.
CRITICAL_CATEGORIES: frozenset[RequirementCategory] = frozenset({"demand", "competition", "pricing"})


def generate_requirement_set(
    *,
    candidate_id: str,
    candidate_label: str,
    categories: tuple[RequirementCategory, ...] | None = None,
    settings: Settings | None = None,
) -> list[ResearchRequirement]:
    """Builds the requirement set for ONE candidate. `categories` defaults to
    CORE_COMPARISON_CATEGORIES — the common minimum for a comparison task.
    Bounded by settings.research_max_requirements_per_candidate."""
    chosen = categories or CORE_COMPARISON_CATEGORIES
    max_count = settings.research_max_requirements_per_candidate if settings else len(chosen)
    chosen = chosen[:max_count]

    requirements: list[ResearchRequirement] = []
    for category in chosen:
        importance, preferred_roles, min_count, needs_independent, quantitative, template = _CATEGORY_SPEC.get(
            category, _CATEGORY_SPEC["other"]
        )
        requirements.append(
            ResearchRequirement(
                candidate_id=candidate_id,
                category=category,
                question=template.format(candidate=candidate_label),
                importance=importance,
                preferred_source_roles=list(preferred_roles),
                minimum_evidence_count=min_count,
                requires_independent_sources=needs_independent,
                quantitative=quantitative,
            )
        )
    return requirements


def generate_candidate_requirement_sets(
    candidates: list[tuple[str, str]],
    *,
    categories: tuple[RequirementCategory, ...] | None = None,
    settings: Settings | None = None,
) -> dict[str, list[ResearchRequirement]]:
    """Generates a COMPARABLE requirement set for each (candidate_id,
    candidate_label) pair — every candidate gets the same categories, so
    coverage stays comparable across candidates (Phase 2's requirement)."""
    return {
        candidate_id: generate_requirement_set(
            candidate_id=candidate_id, candidate_label=label, categories=categories, settings=settings
        )
        for candidate_id, label in candidates
    }
