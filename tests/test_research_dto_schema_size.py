"""Schema-size regression guard (v0.1.2.1 grammar-size patch, Phase 4/7).
Offline — measures Model.model_json_schema() directly, never depends on
Anthropic's undocumented exact grammar-size limit. A conservative,
project-owned budget instead."""
from __future__ import annotations

import json

from app.schemas.agents import QAVerdict, ResearchOutput, StrategyOutput
from app.schemas.research_dto import (
    DiscoveryModelOutput,
    GeneralResearchModelOutput,
    ValidationModelOutput,
)
from app.schemas.tasks import ExecutionPlan

# Generous headroom over the largest actual compact DTO measured (~1400
# chars for DiscoveryModelOutput) — chosen from the compact schemas
# actually produced, not from Anthropic's own (undocumented) limit.
RESEARCH_DTO_SIZE_BUDGET_CHARS = 2500

# A model-facing research schema must never re-embed these deterministic,
# Jarvis-owned domain structures — see app/schemas/research_dto.py.
DOMAIN_ONLY_DEFS = {
    "EvidenceItem",
    "ResearchRequirement",
    "CandidateResearchStatus",
    "CoverageCell",
    "ComparisonReadiness",
}


def _schema_size(model) -> int:
    return len(json.dumps(model.model_json_schema()))


def _schema_defs(model) -> set[str]:
    return set(model.model_json_schema().get("$defs", {}).keys())


# --- 6/7/8. Compact DTOs stay under the internal complexity budget ---------


def test_discovery_dto_within_budget():
    assert _schema_size(DiscoveryModelOutput) < RESEARCH_DTO_SIZE_BUDGET_CHARS


def test_validation_dto_within_budget():
    assert _schema_size(ValidationModelOutput) < RESEARCH_DTO_SIZE_BUDGET_CHARS


def test_general_dto_within_budget():
    assert _schema_size(GeneralResearchModelOutput) < RESEARCH_DTO_SIZE_BUDGET_CHARS


# --- 9/10/11. No domain-only structures embedded ----------------------------


def test_discovery_dto_contains_no_evidence_item_definition():
    assert "EvidenceItem" not in _schema_defs(DiscoveryModelOutput)
    assert not (_schema_defs(DiscoveryModelOutput) & DOMAIN_ONLY_DEFS)


def test_validation_dto_contains_no_research_requirement_definition():
    assert "ResearchRequirement" not in _schema_defs(ValidationModelOutput)


def test_validation_dto_contains_no_coverage_or_completeness_structures():
    defs = _schema_defs(ValidationModelOutput)
    assert "CoverageCell" not in defs
    assert "ComparisonReadiness" not in defs
    assert "CandidateResearchStatus" not in defs
    assert not (defs & DOMAIN_ONLY_DEFS)


def test_general_dto_contains_no_domain_only_structures():
    assert not (_schema_defs(GeneralResearchModelOutput) & DOMAIN_ONLY_DEFS)


def test_discovery_dto_never_embeds_full_research_candidate():
    """Discovery uses the deliberately slim DiscoveryCandidateProposal
    (label/description only) — never the rich ResearchCandidate."""
    defs = _schema_defs(DiscoveryModelOutput)
    assert "DiscoveryCandidateProposal" in defs
    assert "ResearchCandidate" not in defs


# --- Dramatic reduction vs. the rich domain ResearchOutput ------------------


def test_discovery_dto_is_dramatically_smaller_than_research_output():
    assert _schema_size(DiscoveryModelOutput) < _schema_size(ResearchOutput) / 3


def test_validation_dto_is_dramatically_smaller_than_research_output():
    assert _schema_size(ValidationModelOutput) < _schema_size(ResearchOutput) / 3


def test_general_dto_is_dramatically_smaller_than_research_output():
    assert _schema_size(GeneralResearchModelOutput) < _schema_size(ResearchOutput) / 3


# --- 21/22/23. Strategy / QA / Jarvis planner schema sizes measured --------
# Root-caused failure was specific to Research's schema. Per Phase 7: if
# these are comfortably small, leave them alone — do not redesign.


def test_strategy_output_schema_size_is_comfortably_small():
    assert _schema_size(StrategyOutput) < 5000


def test_qa_verdict_schema_size_is_comfortably_small():
    assert _schema_size(QAVerdict) < 5000


def test_execution_plan_schema_size_is_comfortably_small():
    assert _schema_size(ExecutionPlan) < 5000
