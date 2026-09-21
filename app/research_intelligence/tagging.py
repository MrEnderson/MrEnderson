"""Applies source-role classification + relevance scoring to a batch of
evidence for one candidate — the single place both app/agents/research.py
(tagging its own gathered evidence) and app/agents/strategy.py (re-tagging
each research result's evidence for the coverage matrix, independent of
whether research.py already tagged it — idempotent and deterministic) call
into. Never mutates the input items; always returns new copies.
"""
from __future__ import annotations

from app.research_intelligence.relevance import score_relevance
from app.research_intelligence.schemas import ResearchRequirement
from app.research_intelligence.source_roles import classify_source_role
from app.schemas.evidence import EvidenceItem


def tag_evidence_for_candidate(
    evidence_items: list[EvidenceItem],
    *,
    candidate_id: str,
    candidate_label: str,
    requirements: list[ResearchRequirement],
    other_candidate_labels: list[str] | None = None,
) -> list[EvidenceItem]:
    """For each item: classifies source_role, then scores relevance against
    every requirement in this candidate's set and keeps the BEST-matching
    requirement's category/score/label/reason — an item is judged by what it
    is MOST useful for, not penalized for being irrelevant to requirements it
    was never meant to address."""
    tagged: list[EvidenceItem] = []
    for item in evidence_items:
        source_role = classify_source_role(item.source_url, candidate_label=candidate_label)
        working = item.model_copy(update={"source_role": source_role}) if item.source_role != source_role else item

        best_requirement: ResearchRequirement | None = None
        best_score = -1.0
        best_label = "REJECT"
        best_reason = None
        for requirement in requirements:
            score, label, reason = score_relevance(
                requirement, candidate_label, working, other_candidate_labels=other_candidate_labels
            )
            if score > best_score:
                best_score = score
                best_requirement = requirement
                best_label = label
                best_reason = reason

        tagged.append(
            item.model_copy(
                update={
                    "candidate_id": candidate_id,
                    "source_role": source_role,
                    "requirement_category": best_requirement.category if best_requirement else None,
                    "relevance_score": round(best_score, 4) if best_score >= 0 else None,
                    "relevance_label": best_label,
                    "rejection_reason": best_reason,
                }
            )
        )
    return tagged
