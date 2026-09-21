"""Evidence Coverage Matrix (Phase 6). Offline, deterministic."""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.schemas.evidence import EvidenceItem

CANDIDATE = "Notion template marketplace"


def _settings(**overrides) -> Settings:
    base = dict(research_min_independent_sources=2, research_max_evidence_per_requirement=4)
    base.update(overrides)
    return Settings(**base)


def _demand_evidence(url: str, domain_label: str) -> EvidenceItem:
    return EvidenceItem(
        claim=f"{CANDIDATE}: strong demand and growing traction reported by {domain_label}.",
        source_url=url,
    )


def _tagged(evidence_items, settings):
    requirements = generate_requirement_set(candidate_id="c", candidate_label=CANDIDATE, settings=settings)
    tagged = tag_evidence_for_candidate(
        evidence_items, candidate_id="c", candidate_label=CANDIDATE, requirements=requirements
    )
    cells = build_coverage_matrix(requirements, {"c": tagged}, settings=settings)
    return requirements, tagged, cells


def test_evidence_assigned_to_correct_requirement_and_candidate():
    settings = _settings()
    items = [_demand_evidence("https://producthunt.com/posts/1", "Product Hunt")]
    requirements, tagged, cells = _tagged(items, settings)
    demand_cell = next(c for c in cells if c.category == "demand")
    assert demand_cell.candidate_id == "c"
    assert tagged[0].id in demand_cell.evidence_ids


def test_same_domain_evidence_not_counted_as_independent():
    settings = _settings()
    items = [
        _demand_evidence("https://producthunt.com/posts/1", "Product Hunt"),
        _demand_evidence("https://producthunt.com/posts/2", "Product Hunt"),
        _demand_evidence("https://producthunt.com/posts/3", "Product Hunt"),
    ]
    _, _, cells = _tagged(items, settings)
    demand_cell = next(c for c in cells if c.category == "demand")
    assert demand_cell.independent_domain_count == 1
    # Three same-domain items are NOT enough for a requirement that needs
    # independent sources, however many of them there are.
    assert demand_cell.status != "SUFFICIENT"


def test_missing_status_when_no_evidence():
    settings = _settings()
    _, _, cells = _tagged([], settings)
    assert all(c.status == "MISSING" for c in cells)


def test_sufficient_when_count_and_independence_met():
    settings = _settings()
    items = [
        _demand_evidence("https://producthunt.com/posts/1", "Product Hunt"),
        _demand_evidence("https://www.similarweb.com/website/x", "Similarweb"),
    ]
    _, _, cells = _tagged(items, settings)
    demand_cell = next(c for c in cells if c.category == "demand")
    assert demand_cell.status == "SUFFICIENT"
    assert demand_cell.independent_domain_count == 2


def test_partial_when_some_qualifying_evidence_but_below_minimum():
    settings = _settings()
    items = [_demand_evidence("https://producthunt.com/posts/1", "Product Hunt")]
    _, _, cells = _tagged(items, settings)
    demand_cell = next(c for c in cells if c.category == "demand")
    assert demand_cell.status == "PARTIAL"  # 1 strong item, minimum is 2


def test_page_extract_upgrades_best_evidence_depth():
    settings = _settings()
    snippet = _demand_evidence("https://producthunt.com/posts/1", "Product Hunt")
    upgraded = snippet.model_copy(update={"evidence_depth": "PAGE_EXTRACT"})
    _, _, cells = _tagged([upgraded], settings)
    demand_cell = next(c for c in cells if c.category == "demand")
    assert demand_cell.best_evidence_depth == "PAGE_EXTRACT"


def test_requirement_status_mutated_to_match_its_cell():
    settings = _settings()
    items = [
        _demand_evidence("https://producthunt.com/posts/1", "Product Hunt"),
        _demand_evidence("https://www.similarweb.com/website/x", "Similarweb"),
    ]
    requirements, _, cells = _tagged(items, settings)
    demand_req = next(r for r in requirements if r.category == "demand")
    demand_cell = next(c for c in cells if c.category == "demand")
    assert demand_req.status == demand_cell.status == "SUFFICIENT"
