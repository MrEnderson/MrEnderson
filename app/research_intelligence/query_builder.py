"""Structured external search query builder (v0.1.2.2, Defect 1). Jarvis's
own orchestration vocabulary — "candidate", "opportunity", "validation
task", "comparison task", "research task", "discovery task" — must never
leak into an external search query just because Jarvis internally calls a
business idea a `ResearchCandidate`. A live benchmark reproduced this
exactly: retrieval for "candidate opportunities" pulled in political-
candidate and HR-recruitment content instead of the actual digital-product
concepts.

Deterministic only — never an LLM call to normalize a label (that would
reintroduce cost and non-determinism for something string manipulation
already solves).
"""
from __future__ import annotations

import re

from app.research_intelligence.schemas import ResearchQueryPlan, ResearchRequirement

# Orchestration-only vocabulary, stripped from any text before it becomes
# (or contributes to) an external search string. Multi-word phrases first,
# so "validation task" is removed as a phrase rather than leaving a
# dangling "task". Word-boundary matched, case-insensitive — never touches
# a legitimate business term merely because it shares a substring.
_ORCHESTRATION_PHRASES: tuple[str, ...] = (
    "candidate opportunities",
    "candidate opportunity",
    "candidate comparison",
    "validation task",
    "comparison task",
    "research task",
    "discovery task",
)
_ORCHESTRATION_WORDS: tuple[str, ...] = ("candidates", "candidate", "opportunities", "opportunity")


def build_external_search_concept(label: str, description: str = "") -> str:
    """Normalizes an internal candidate label (+ optional description) into
    an external-search-safe concept string: strips Jarvis's own
    orchestration vocabulary, flattens punctuation/parentheses (keeping
    their contents, since "(Courses/Templates)" is meaningful business
    content), and collapses whitespace. Never calls a model."""
    text = f"{label} {description}".strip()
    for phrase in _ORCHESTRATION_PHRASES:
        text = re.sub(re.escape(phrase), " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[()/&,-]", " ", text)
    for word in _ORCHESTRATION_WORDS:
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


# Small, deterministic, per-category search-intent templates (Phase 3).
# Deliberately concise — one template per category, not "dozens". Every
# template embeds ONLY the search-safe concept, never a category name or
# any orchestration term.
_REQUIREMENT_QUERY_TEMPLATES: dict[str, str] = {
    "pricing": "{concept} pricing competitors",
    "competition": "{concept} competitors marketplace",
    "demand": "{concept} demand sales search trends",
    "customer_pain": "{concept} customer reviews problems complaints",
    "market_size": "{concept} market size",
    "growth": "{concept} growth rate",
    "willingness_to_pay": "{concept} pricing purchases customer willingness to pay",
    "feasibility": "{concept} creator setup costs requirements",
    "unit_economics": "{concept} creator revenue costs margins",
    "customer_validation": "{concept} customer validation reviews",
    "other": "{concept} overview",
}

# Bounded — an external query is never allowed to grow unboundedly long
# just because a label/description was verbose.
_MAX_QUERY_CHARS = 200


# v0.1.2.5 Phase 3: a candidate LABEL is a display name, not necessarily an
# optimal search concept — "AI-Powered Content Creation Tools & Templates"
# is really at least two distinct searchable concepts ("AI content creation
# tools", "templates"). Splits on these separators to surface each
# meaningful phrase as its own concept, in addition to the whole
# label+description as the primary concept (unchanged legacy behavior —
# see build_external_research_query). Deterministic string manipulation
# only, never a model call.
_CONCEPT_SPLIT_PATTERN = re.compile(r"&|/|,| and |\s-\s")

# Bounded — a candidate's concept set is a small, fixed handful of phrases,
# never an unbounded fan-out of every possible substring.
_MAX_CANDIDATE_CONCEPTS = 4


def build_candidate_concepts(label: str, description: str = "", *, max_concepts: int = _MAX_CANDIDATE_CONCEPTS) -> list[str]:
    """Bounded, deterministic set of searchable concepts derived from a
    candidate's own label + description — never from Jarvis's own
    orchestration wording (each candidate phrase is passed through the
    same build_external_search_concept() normalization). The FIRST entry
    is always the whole label+description as one concept (matching
    build_external_research_query's existing primary-concept behavior);
    the rest are meaningful (2+ word) phrases split out of the label, then
    the description's first sentence — deduplicated, case-insensitive."""
    concepts: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        normalized = build_external_search_concept(raw)
        if not normalized:
            return
        key = normalized.lower()
        if key in seen:
            return
        seen.add(key)
        concepts.append(normalized)

    _add(f"{label} {description}".strip())
    for segment in _CONCEPT_SPLIT_PATTERN.split(label or ""):
        segment = segment.strip(" -")
        if segment and len(segment.split()) >= 2:
            _add(segment)
    if description and description.strip():
        first_sentence = re.split(r"(?<=[.!?])\s+", description.strip())[0]
        for segment in re.split(r",| and ", first_sentence):
            segment = segment.strip(" -")
            if segment and len(segment.split()) >= 2:
                _add(segment)
    return concepts[:max_concepts]


def build_external_research_query(
    *, candidate_label: str, candidate_description: str = "", category: str | None = None
) -> str:
    """The single deterministic query builder every query-generating call
    site should use (initial validation search, gap retries, remediation
    queries). Returns CANDIDATE LABEL + CANDIDATE DESCRIPTION/DOMAIN
    CONTEXT (normalized) + REQUIREMENT-SPECIFIC SEARCH INTENT — never a
    bare orchestration phrase like "candidate opportunity pricing"."""
    concept = build_external_search_concept(candidate_label, candidate_description)
    if not concept:
        concept = "digital product"  # never send an empty/orchestration-only query
    if category is None:
        query = concept
    else:
        template = _REQUIREMENT_QUERY_TEMPLATES.get(category, _REQUIREMENT_QUERY_TEMPLATES["other"])
        query = template.format(concept=concept)
    if len(query) > _MAX_QUERY_CHARS:
        query = query[:_MAX_QUERY_CHARS].rstrip()
    return query


def build_query_plan(
    *,
    candidate_id: str,
    candidate_label: str,
    candidate_description: str = "",
    requirement: ResearchRequirement | None = None,
    max_results: int,
) -> ResearchQueryPlan:
    """v0.1.2.5 Phase 2: the single deterministic assembly point for a
    ResearchQueryPlan — every query-generating call site (initial
    validation search, gap retries) should build one of these rather than
    a bare string, so candidate_id/requirement_category/source-role
    preference/exclusions travel with the query instead of being
    re-derived ad hoc. The query TEXT itself is unchanged from
    build_external_research_query (already CANDIDATE CONCEPT +
    REQUIREMENT-SPECIFIC INTENT, never orchestration wording) — this adds
    the rest of the plan around it."""
    from app.research_intelligence.prescreen import negative_terms_for_candidate

    concepts = build_candidate_concepts(candidate_label, candidate_description)
    concept = concepts[0] if concepts else "digital product"
    category = requirement.category if requirement else None
    query = build_external_research_query(
        candidate_label=candidate_label, candidate_description=candidate_description, category=category,
    )
    return ResearchQueryPlan(
        candidate_id=candidate_id,
        candidate_label=candidate_label,
        candidate_concept=concept,
        requirement_category=category,
        search_intent=category or "general_discovery",
        query=query,
        preferred_source_roles=list(requirement.preferred_source_roles) if requirement else [],
        excluded_terms=negative_terms_for_candidate(concepts),
        max_results=max_results,
    )
