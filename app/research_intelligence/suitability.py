"""Claim <-> source policy (Phase 4): deterministic source-role suitability
rules. Different source roles are useful for different claims — DISCOVERY
sources may generate hypotheses but must never, by themselves, establish
high-confidence financial/commercial conclusions.

Small, explicit, testable table. Not a giant ML source-ranking system.
"""
from __future__ import annotations

from app.research_intelligence.schemas import SuitabilityLevel
from app.research_intelligence.source_roles import classify_source_role
from app.schemas.evidence import EvidenceItem, RequirementCategory, SourceRole

# Every category below is explicit for every role — no silent defaulting to
# "whatever seems reasonable." A role/category combination not worth naming
# explicitly still gets a conservative WEAK, applied in evaluate_source_suitability.
_POLICY: dict[RequirementCategory, dict[SourceRole, SuitabilityLevel]] = {
    "market_size": {
        "AUTHORITATIVE": "STRONG",
        "COMMERCIAL_RESEARCH": "STRONG",
        "PRIMARY": "ACCEPTABLE",
        "MARKETPLACE": "WEAK",
        "COMMUNITY": "WEAK",
        "DISCOVERY": "UNSUITABLE",
        "UNKNOWN": "UNSUITABLE",
    },
    "growth": {
        "AUTHORITATIVE": "STRONG",
        "COMMERCIAL_RESEARCH": "STRONG",
        "PRIMARY": "ACCEPTABLE",
        "MARKETPLACE": "WEAK",
        "COMMUNITY": "WEAK",
        "DISCOVERY": "UNSUITABLE",
        "UNKNOWN": "UNSUITABLE",
    },
    "pricing": {
        "PRIMARY": "STRONG",
        "MARKETPLACE": "STRONG",
        "AUTHORITATIVE": "ACCEPTABLE",
        "COMMERCIAL_RESEARCH": "ACCEPTABLE",
        "COMMUNITY": "WEAK",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "UNSUITABLE",
    },
    "customer_pain": {
        "COMMUNITY": "STRONG",
        "PRIMARY": "STRONG",
        "MARKETPLACE": "STRONG",
        "AUTHORITATIVE": "ACCEPTABLE",
        "COMMERCIAL_RESEARCH": "ACCEPTABLE",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "WEAK",
    },
    "demand": {
        "MARKETPLACE": "STRONG",
        "COMMERCIAL_RESEARCH": "STRONG",
        "AUTHORITATIVE": "STRONG",
        "PRIMARY": "ACCEPTABLE",
        "COMMUNITY": "ACCEPTABLE",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "WEAK",
    },
    "willingness_to_pay": {
        "MARKETPLACE": "STRONG",
        "PRIMARY": "STRONG",
        "COMMUNITY": "ACCEPTABLE",
        "COMMERCIAL_RESEARCH": "ACCEPTABLE",
        "AUTHORITATIVE": "WEAK",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "UNSUITABLE",
    },
    "competition": {
        "PRIMARY": "STRONG",
        "MARKETPLACE": "STRONG",
        "COMMERCIAL_RESEARCH": "ACCEPTABLE",
        "AUTHORITATIVE": "ACCEPTABLE",
        "COMMUNITY": "ACCEPTABLE",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "WEAK",
    },
    "unit_economics": {
        "PRIMARY": "STRONG",
        "COMMERCIAL_RESEARCH": "ACCEPTABLE",
        "AUTHORITATIVE": "ACCEPTABLE",
        "MARKETPLACE": "WEAK",
        "COMMUNITY": "WEAK",
        "DISCOVERY": "UNSUITABLE",
        "UNKNOWN": "UNSUITABLE",
    },
    "feasibility": {
        "PRIMARY": "STRONG",
        "AUTHORITATIVE": "STRONG",
        "COMMERCIAL_RESEARCH": "ACCEPTABLE",
        "COMMUNITY": "ACCEPTABLE",
        "MARKETPLACE": "ACCEPTABLE",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "WEAK",
    },
    "customer_validation": {
        "PRIMARY": "STRONG",
        "COMMUNITY": "STRONG",
        "MARKETPLACE": "ACCEPTABLE",
        "COMMERCIAL_RESEARCH": "WEAK",
        "AUTHORITATIVE": "WEAK",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "UNSUITABLE",
    },
    "other": {
        "PRIMARY": "ACCEPTABLE",
        "AUTHORITATIVE": "ACCEPTABLE",
        "COMMERCIAL_RESEARCH": "ACCEPTABLE",
        "MARKETPLACE": "ACCEPTABLE",
        "COMMUNITY": "ACCEPTABLE",
        "DISCOVERY": "WEAK",
        "UNKNOWN": "WEAK",
    },
}


def evaluate_source_suitability(
    requirement_category: RequirementCategory, evidence_item: EvidenceItem
) -> SuitabilityLevel:
    """Looks up (or derives, if the item's source_role hasn't been classified
    yet) how suitable this evidence item's source role is for establishing a
    claim in `requirement_category`. Never proves the claim true — only how
    much weight this KIND of source can carry for this KIND of claim."""
    role = evidence_item.source_role
    if role == "UNKNOWN" and evidence_item.source_url:
        role = classify_source_role(evidence_item.source_url)
    table = _POLICY.get(requirement_category, _POLICY["other"])
    return table.get(role, "WEAK")
