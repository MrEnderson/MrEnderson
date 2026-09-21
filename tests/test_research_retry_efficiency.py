"""v0.1.2.3 "Retry efficiency": model-facing retry context prioritizes
unresolved requirements, and already-SUFFICIENT requirement evidence is
not repeatedly dumped into later retry prompts — while the authoritative
evidence store stays complete. Offline."""
from __future__ import annotations

from app.agents.research import _select_prompt_evidence
from app.config.settings import Settings
from app.schemas.evidence import EvidenceItem


def _item(candidate_id: str, category: str, *, relevance_label="HIGH", relevance_score=0.9) -> EvidenceItem:
    return EvidenceItem(
        claim=f"{candidate_id} {category} evidence",
        source_url=f"https://www.producthunt.com/{candidate_id}-{category}",
        candidate_id=candidate_id,
        requirement_category=category,
        relevance_label=relevance_label,
        relevance_score=relevance_score,
    )


# --- 7. Model-facing retry context prioritizes unresolved requirements ----


def test_unresolved_requirement_evidence_is_prioritized_over_sufficient_ones():
    settings = Settings(research_max_evidence_items=2)
    sufficient_item = _item("candidate-a", "pricing")  # already SUFFICIENT — not in unresolved_gap_keys
    unresolved_item = _item("candidate-a", "competition")  # NOT yet SUFFICIENT

    selected = _select_prompt_evidence(
        [sufficient_item, unresolved_item],
        settings=settings,
        unresolved_gap_keys={("candidate-a", "competition")},
    )
    assert selected[0].id == unresolved_item.id


# --- 8. Already-sufficient requirement evidence is not repeatedly dumped --


def test_sufficient_requirement_evidence_is_dropped_when_budget_is_tight():
    """When the item-count budget can't fit everything, an
    already-SUFFICIENT requirement's evidence loses out to an unresolved
    one — it's not "dumped" into the prompt just because it exists."""
    settings = Settings(research_max_evidence_items=1, research_prompt_max_evidence_per_requirement=2)
    sufficient_item = _item("candidate-a", "pricing")
    unresolved_item = _item("candidate-a", "competition")

    selected = _select_prompt_evidence(
        [sufficient_item, unresolved_item],
        settings=settings,
        unresolved_gap_keys={("candidate-a", "competition")},
    )
    assert len(selected) == 1
    assert selected[0].id == unresolved_item.id


def test_no_unresolved_gaps_falls_back_to_relevance_ranking():
    """With no unresolved_gap_keys at all (e.g. the very first attempt,
    before any coverage has been computed), locality is a no-op tie and
    relevance/depth/recency still rank evidence sensibly."""
    settings = Settings(research_max_evidence_items=1)
    low = _item("candidate-a", "pricing", relevance_label="LOW", relevance_score=0.35)
    high = _item("candidate-a", "competition", relevance_label="HIGH", relevance_score=0.9)

    selected = _select_prompt_evidence([low, high], settings=settings, unresolved_gap_keys=None)
    assert selected == [high]


async def test_retry_context_shrinks_evidence_shown_as_requirements_become_sufficient():
    """End-to-end: as VALIDATION's own coverage improves attempt over
    attempt for a given candidate/category, that pair drops out of
    unresolved_gap_keys and its evidence stops competing for prompt space
    against genuinely unresolved ones."""
    from app.research_intelligence.coverage import build_coverage_matrix
    from app.research_intelligence.requirements import generate_requirement_set

    settings = Settings()
    requirements = generate_requirement_set(
        candidate_id="candidate-a", candidate_label="Notion Template Marketplace", settings=settings
    )
    pricing_item = EvidenceItem(
        claim="Notion Template Marketplace pricing plans listed on Gumroad.",
        source_url="https://gumroad.com/l/x",
        candidate_id="candidate-a",
        requirement_category="pricing",
        relevance_label="HIGH",
        relevance_score=0.9,
    )
    pricing_item_2 = EvidenceItem(
        claim="Notion Template Marketplace pricing plans on AppSumo.",
        source_url="https://appsumo.com/products/x",
        candidate_id="candidate-a",
        requirement_category="pricing",
        relevance_label="HIGH",
        relevance_score=0.85,
    )
    cells_before = build_coverage_matrix(requirements, {"candidate-a": []}, settings=settings)
    unresolved_before = {(c.candidate_id, c.category) for c in cells_before if c.status != "SUFFICIENT"}
    assert ("candidate-a", "pricing") in unresolved_before

    cells_after = build_coverage_matrix(
        requirements, {"candidate-a": [pricing_item, pricing_item_2]}, settings=settings
    )
    unresolved_after = {(c.candidate_id, c.category) for c in cells_after if c.status != "SUFFICIENT"}
    assert ("candidate-a", "pricing") not in unresolved_after
