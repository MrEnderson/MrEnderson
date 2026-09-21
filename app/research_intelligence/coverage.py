"""Evidence Coverage Matrix (Phase 6). A deterministic representation of, per
(candidate, requirement) cell: how much evidence exists, how strong it is,
and whether it's independently corroborated. Three pages from the same
domain never count as three independent sources.
"""
from __future__ import annotations

from urllib.parse import urlparse

from app.config.settings import Settings
from app.research_intelligence.schemas import CoverageCell, ResearchRequirement
from app.research_intelligence.suitability import evaluate_source_suitability
from app.schemas.evidence import EvidenceItem

_DEPTH_RANK = {"PAGE_EXTRACT": 1, "SEARCH_SNIPPET": 0}


def canonical_domain(url: str | None) -> str | None:
    if not url:
        return None
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or None


def build_coverage_matrix(
    requirements: list[ResearchRequirement],
    evidence_by_candidate: dict[str, list[EvidenceItem]],
    *,
    settings: Settings,
) -> list[CoverageCell]:
    """One CoverageCell per requirement. `evidence_by_candidate` maps
    candidate_id -> its (already relevance-scored, non-REJECTed) evidence.
    Mutates each requirement's `.status` in place to match its cell — this
    is the ONLY thing requirement.status is ever derived from."""
    cells: list[CoverageCell] = []
    for requirement in requirements:
        candidate_id = requirement.candidate_id or ""
        candidate_evidence = evidence_by_candidate.get(candidate_id, [])
        cell = _build_cell(requirement, candidate_evidence, settings=settings)
        requirement.status = cell.status
        cells.append(cell)
    return cells


def _build_cell(
    requirement: ResearchRequirement, evidence: list[EvidenceItem], *, settings: Settings
) -> CoverageCell:
    relevant = [
        e
        for e in evidence
        if e.requirement_category == requirement.category and e.relevance_label != "REJECT"
    ]
    # Cap how many items count toward one requirement — a flood of near-
    # duplicate snippets should not itself manufacture SUFFICIENT status.
    # Domain-diverse items are preferred among the ones that DO count.
    relevant = _diverse_subset(relevant, settings.research_max_evidence_per_requirement)

    strong = acceptable = weak = 0
    domains: set[str] = set()
    best_depth: str | None = None
    for item in relevant:
        suitability = evaluate_source_suitability(requirement.category, item)
        if suitability == "STRONG":
            strong += 1
        elif suitability == "ACCEPTABLE":
            acceptable += 1
        elif suitability == "WEAK":
            weak += 1
        domain = canonical_domain(item.source_url)
        if domain:
            domains.add(domain)
        if best_depth is None or _DEPTH_RANK.get(item.evidence_depth, 0) > _DEPTH_RANK.get(best_depth, 0):
            best_depth = item.evidence_depth

    status = _status_for(
        requirement=requirement,
        strong=strong,
        acceptable=acceptable,
        weak=weak,
        independent_domains=len(domains),
        settings=settings,
    )

    return CoverageCell(
        requirement_id=requirement.id,
        candidate_id=requirement.candidate_id or "",
        category=requirement.category,
        evidence_ids=[e.id for e in relevant],
        strong_count=strong,
        acceptable_count=acceptable,
        weak_count=weak,
        independent_domain_count=len(domains),
        best_evidence_depth=best_depth,
        status=status,
    )


def _status_for(
    *,
    requirement: ResearchRequirement,
    strong: int,
    acceptable: int,
    weak: int,
    independent_domains: int,
    settings: Settings,
) -> str:
    qualifying = strong + acceptable
    total = qualifying + weak
    if total == 0:
        return "MISSING"

    independence_ok = (
        not requirement.requires_independent_sources
        or independent_domains >= settings.research_min_independent_sources
    )
    count_ok = qualifying >= requirement.minimum_evidence_count

    if count_ok and independence_ok:
        return "SUFFICIENT"
    if qualifying > 0:
        return "PARTIAL"
    return "WEAK"


def _diverse_subset(evidence: list[EvidenceItem], max_count: int) -> list[EvidenceItem]:
    """Prefers domain diversity and higher relevance when trimming to
    max_count — three same-domain items never crowd out a fourth, distinct
    domain (Phase 9: source diversity, preference not an absolute rule)."""
    if max_count <= 0 or len(evidence) <= max_count:
        return evidence

    ranked = sorted(evidence, key=lambda e: -(e.relevance_score or 0.0))
    selected: list[EvidenceItem] = []
    seen_domains: set[str] = set()
    leftover: list[EvidenceItem] = []
    for item in ranked:
        domain = canonical_domain(item.source_url)
        if domain and domain in seen_domains:
            leftover.append(item)
            continue
        if domain:
            seen_domains.add(domain)
        selected.append(item)
        if len(selected) >= max_count:
            return selected
    for item in leftover:
        if len(selected) >= max_count:
            break
        selected.append(item)
    return selected
