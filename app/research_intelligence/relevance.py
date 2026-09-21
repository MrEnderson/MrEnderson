"""Evidence relevance scoring (Phase 5). A deterministic RETRIEVAL RELEVANCE
heuristic — never a probabilistic truth score. Filters out generic and
off-topic evidence before it can reach the decision context.

Score in [0.0, 1.0]:
    >= 0.75  HIGH
    0.50-0.74 MEDIUM
    0.30-0.49 LOW
    <  0.30  REJECT (excluded from model-facing evidence/coverage)
"""
from __future__ import annotations

import re

from app.research_intelligence.schemas import ResearchRequirement
from app.research_intelligence.suitability import evaluate_source_suitability
from app.schemas.evidence import EvidenceItem, EvidenceRejectionReason, RelevanceLabel

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "will",
        "have",
        "into",
        "your",
        "about",
        "more",
        "best",
        "what",
        "how",
        "why",
        "digital",
        "product",
        "products",
        "opportunity",
        "opportunities",
        "research",
        "candidate",
    }
)

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "demand": ("demand", "search volume", "interest", "downloads", "installs", "adoption", "traction", "signups"),
    "customer_pain": ("pain point", "frustrat", "complain", "problem", "struggl", "issue", "annoy"),
    "competition": ("competitor", "competition", "alternative", "rival", "market leader"),
    "pricing": ("price", "pricing", "cost", "subscription", "plan", "$", "fee", "tier"),
    "market_size": ("market size", "total addressable market", " tam ", "market value", "industry size"),
    "growth": ("growth", "cagr", "yoy", "year over year", "trend", "forecast"),
    "willingness_to_pay": ("willing to pay", "willingness to pay", "pay for", "would pay", "premium"),
    "feasibility": ("feasib", "technical complexity", "build time", "implementation", "infrastructure"),
    "unit_economics": ("unit economics", "margin", "cac", "ltv", "cost to acquire", "churn"),
    "customer_validation": ("customer interview", "user validation", "beta tester", "waitlist", "survey"),
    "other": (),
}

_GENERIC_MARKERS = (
    "top 10",
    "best ways to",
    "make money online",
    "passive income",
    "side hustle",
    "ultimate guide",
    "everything you need to know",
    "beginner's guide",
)

_SUITABILITY_BONUS = {"STRONG": 1.0, "ACCEPTABLE": 0.6, "WEAK": 0.3, "UNSUITABLE": 0.0}

HIGH_THRESHOLD = 0.75
MEDIUM_THRESHOLD = 0.50
LOW_THRESHOLD = 0.30


def score_relevance(
    requirement: ResearchRequirement,
    candidate_label: str,
    evidence: EvidenceItem,
    *,
    other_candidate_labels: list[str] | None = None,
) -> tuple[float, RelevanceLabel, EvidenceRejectionReason | None]:
    """Returns (score, label, rejection_reason). rejection_reason is only
    set when label == REJECT."""
    text = combined_text(evidence)
    candidate_tokens = significant_tokens(candidate_label)
    candidate_match = overlap_ratio(candidate_tokens, text) if candidate_tokens else 0.5

    keywords = _CATEGORY_KEYWORDS.get(requirement.category, ())
    requirement_match = 1.0 if (keywords and any(k in text for k in keywords)) else (
        0.5 if not keywords else 0.0
    )
    # A requirement's own question text is a secondary relevance signal —
    # catches wording the fixed keyword list doesn't anticipate.
    question_tokens = significant_tokens(requirement.question)
    if question_tokens and overlap_ratio(question_tokens, text) > 0:
        requirement_match = max(requirement_match, 0.5)

    generic = _is_generic(text) and candidate_match < 0.34
    specificity = 0.3 if generic else 0.8

    suitability = evaluate_source_suitability(requirement.category, evidence)
    suitability_bonus = _SUITABILITY_BONUS[suitability]

    score = 0.4 * candidate_match + 0.3 * requirement_match + 0.2 * specificity + 0.1 * suitability_bonus
    score = max(0.0, min(1.0, score))

    # Evidence that clearly belongs to a DIFFERENT candidate is always
    # rejected outright — strong category/source signals must never let a
    # wrong-candidate match through just because it reads like good pricing/
    # market evidence for SOMEONE ELSE'S business.
    if _matches_other_candidate(text, candidate_tokens, other_candidate_labels):
        return min(score, LOW_THRESHOLD - 0.01), "REJECT", "WRONG_CANDIDATE"

    label = _label_for(score)
    reason: EvidenceRejectionReason | None = None
    if label == "REJECT":
        if candidate_match == 0.0:
            reason = "IRRELEVANT_TOPIC"
        elif requirement_match == 0.0:
            reason = "DOES_NOT_ADDRESS_REQUIREMENT"
        elif generic:
            reason = "TOO_GENERIC"
        else:
            reason = "IRRELEVANT_TOPIC"

    return score, label, reason


def _label_for(score: float) -> RelevanceLabel:
    if score >= HIGH_THRESHOLD:
        return "HIGH"
    if score >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    if score >= LOW_THRESHOLD:
        return "LOW"
    return "REJECT"


def combined_text(evidence: EvidenceItem) -> str:
    parts = [evidence.claim or "", evidence.source_title or "", evidence.excerpt or ""]
    return " ".join(parts).lower()


def significant_tokens(label: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", label.lower())
    return {w for w in words if len(w) >= 4 and w not in _STOPWORDS}


def overlap_ratio(tokens: set[str], text: str) -> float:
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in text)
    return hits / len(tokens)


def _is_generic(text: str) -> bool:
    return any(marker in text for marker in _GENERIC_MARKERS)


def _matches_other_candidate(
    text: str, own_tokens: set[str], other_candidate_labels: list[str] | None
) -> bool:
    if not other_candidate_labels:
        return False
    for other in other_candidate_labels:
        other_tokens = significant_tokens(other)
        if not other_tokens:
            continue
        if other_tokens & own_tokens:
            continue  # shares tokens with this candidate's own label — not a clean "other" match
        if overlap_ratio(other_tokens, text) >= 0.5:
            return True
    return False
