"""Candidate Completeness Gate (Phase 7) + remediation prioritization
(Phase 8). Offline, deterministic."""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.completeness import evaluate_completeness
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.requirements import CRITICAL_CATEGORIES, generate_requirement_set
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.schemas.evidence import EvidenceItem


def _settings() -> Settings:
    return Settings(research_min_comparison_coverage=0.70, research_min_independent_sources=2)


def _full_coverage_evidence(label: str) -> list[EvidenceItem]:
    """Two independent, on-topic, role-appropriate sources per core
    category — enough to make every cell SUFFICIENT."""

    def item(url: str, claim: str) -> EvidenceItem:
        return EvidenceItem(claim=claim, source_url=url, excerpt=claim)

    return [
        item("https://www.producthunt.com/posts/x", f"{label}: strong demand with growing traction on Product Hunt."),
        item("https://www.similarweb.com/website/x", f"Similarweb traffic data shows strong demand and traction for {label}."),
        item("https://www.producthunt.com/posts/y", f"{label}: named competitors identified among similar launches."),
        item("https://www.g2.com/products/x", f"G2 reviews list several competitors to {label}."),
        item("https://gumroad.com/l/x", f"Gumroad marketplace pricing for {label} listed clearly."),
        item("https://appsumo.com/products/x", f"AppSumo pricing deal for {label} shows plan tiers."),
        item("https://reddit.com/r/x/comments/1", f"Reddit users report a common pain point and complain about {label}."),
        item("https://www.indiehackers.com/post/1", f"Indie Hackers discussion: customers complain about a pain point with {label}."),
        item("https://www.statista.com/statistics/x", f"Statista data on market size and total addressable market for {label}."),
        item("https://www.gartner.com/reports/x", f"Gartner report on market size for {label}."),
        item("https://www.g2.com/products/y", f"G2 reviews discuss technical feasibility of building {label}."),
    ]


def _weak_evidence(label: str) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            claim="Top 10 best ways to make money online with digital products.",
            source_url="https://random-blog.example.com/top10",
        )
    ]


def _build(candidates: dict[str, list[EvidenceItem]], *, settings: Settings):
    requirements = []
    evidence_by_candidate = {}
    for candidate_id, items in candidates.items():
        label = candidate_id
        reqs = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
        requirements.extend(reqs)
        evidence_by_candidate[candidate_id] = tag_evidence_for_candidate(
            items, candidate_id=candidate_id, candidate_label=label, requirements=reqs
        )
    cells = build_coverage_matrix(requirements, evidence_by_candidate, settings=settings)
    labels = {cid: cid for cid in candidates}
    return requirements, cells, labels


def test_balanced_sufficient_candidates_are_ready():
    settings = _settings()
    candidates = {
        "Notion template marketplace": _full_coverage_evidence("Notion template marketplace"),
        "Coda template hub": _full_coverage_evidence("Coda template hub"),
    }
    requirements, cells, labels = _build(candidates, settings=settings)
    readiness = evaluate_completeness(requirements, cells, labels, settings=settings)
    assert readiness.ready is True
    assert all(s.ready_for_comparison for s in readiness.candidate_statuses)


def test_one_under_researched_candidate_blocks_readiness():
    settings = _settings()
    candidates = {
        "Notion template marketplace": _full_coverage_evidence("Notion template marketplace"),
        "Coda template hub": _weak_evidence("Coda template hub"),
    }
    requirements, cells, labels = _build(candidates, settings=settings)
    readiness = evaluate_completeness(requirements, cells, labels, settings=settings)
    assert readiness.ready is False
    statuses_by_id = {s.candidate_id: s for s in readiness.candidate_statuses}
    assert statuses_by_id["Notion template marketplace"].ready_for_comparison is True
    assert statuses_by_id["Coda template hub"].ready_for_comparison is False


def test_critical_missing_requirement_blocks_readiness_even_with_decent_coverage_elsewhere():
    settings = _settings()

    def items_missing_pricing(label: str) -> list[EvidenceItem]:
        full = _full_coverage_evidence(label)
        return [e for e in full if "pricing" not in e.claim.lower() and "gumroad" not in (e.source_url or "") and "appsumo" not in (e.source_url or "")]

    candidates = {
        "Notion template marketplace": items_missing_pricing("Notion template marketplace"),
        "Coda template hub": _full_coverage_evidence("Coda template hub"),
    }
    requirements, cells, labels = _build(candidates, settings=settings)
    readiness = evaluate_completeness(requirements, cells, labels, settings=settings)
    assert readiness.ready is False
    status = next(s for s in readiness.candidate_statuses if s.candidate_id == "Notion template marketplace")
    assert "pricing" in status.critical_requirements_missing


def test_remediation_queries_prioritize_lowest_coverage_candidate_first():
    settings = _settings()
    candidates = {
        "Notion template marketplace": _full_coverage_evidence("Notion template marketplace"),
        "Coda template hub": _weak_evidence("Coda template hub"),
    }
    requirements, cells, labels = _build(candidates, settings=settings)
    readiness = evaluate_completeness(requirements, cells, labels, settings=settings)
    assert readiness.remediation_queries
    assert readiness.remediation_queries[0].startswith("Coda template hub")


def test_remediation_queries_are_bounded():
    settings = _settings()
    candidates = {
        "A": _weak_evidence("A"),
        "B": _weak_evidence("B"),
        "C": _weak_evidence("C"),
    }
    requirements, cells, labels = _build(candidates, settings=settings)
    readiness = evaluate_completeness(requirements, cells, labels, settings=settings)
    assert len(readiness.remediation_queries) <= min(10, settings.research_max_gap_queries_per_attempt * 3)


def test_no_remediation_queries_needed_when_fully_covered():
    settings = _settings()
    candidates = {
        "Notion template marketplace": _full_coverage_evidence("Notion template marketplace"),
        "Coda template hub": _full_coverage_evidence("Coda template hub"),
    }
    requirements, cells, labels = _build(candidates, settings=settings)
    readiness = evaluate_completeness(requirements, cells, labels, settings=settings)
    assert readiness.remediation_queries == []


def test_critical_categories_are_the_expected_set():
    assert CRITICAL_CATEGORIES == frozenset({"demand", "competition", "pricing"})
