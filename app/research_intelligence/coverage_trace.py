"""Coverage contribution trace (v0.1.2.6 Phase 7). Deterministic, offline
diagnostic representation of WHY a coverage cell ended up at its status —
for every ACCEPTED validation EvidenceItem:

    evidence_id -> candidate_id -> requirement_category -> source_role
        -> relevance -> coverage cell -> contribution -> resulting status

"contribution" is what app/research_intelligence/coverage.py::_build_cell
actually does with the item: STRONG/ACCEPTABLE/WEAK count it toward
qualifying/weak, or NONE (source suitability UNSUITABLE for this
category — the item is admitted, on-topic evidence, but its source ROLE
cannot carry weight for THIS kind of claim; see
app/research_intelligence/suitability.py). This is the exact mechanism
that silently drops UNSUITABLE items from a cell's status computation
without counting them as WEAK — never a bug, but easy to miss without an
explicit trace. Logging/diagnostic only — never persisted.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.config.settings import Settings
from app.research_intelligence.coverage import canonical_domain
from app.research_intelligence.schemas import CoverageCell
from app.research_intelligence.suitability import evaluate_source_suitability
from app.schemas.evidence import EvidenceItem


class EvidenceContributionTrace(BaseModel):
    evidence_id: str
    candidate_id: str | None
    requirement_category: str | None
    source_role: str
    relevance_label: str | None
    admission_status: str
    domain: str | None
    contribution: str  # "STRONG" | "ACCEPTABLE" | "WEAK" | "NONE" | "NOT_ADMITTED"
    resulting_cell_status: str | None


def trace_evidence_contributions(
    evidence: list[EvidenceItem], coverage_cells: list[CoverageCell], *, settings: Settings
) -> list[EvidenceContributionTrace]:
    """One row per evidence item (ALL items passed in, admitted or not —
    an item never admitted, or admitted but not matching any cell, still
    gets a row explaining why it contributed nothing)."""
    cell_status_by_key = {(c.candidate_id, c.category): c.status for c in coverage_cells}
    cell_evidence_ids = {(c.candidate_id, c.category): set(c.evidence_ids) for c in coverage_cells}

    rows: list[EvidenceContributionTrace] = []
    for item in evidence:
        key = (item.candidate_id, item.requirement_category)
        cell_status = cell_status_by_key.get(key)

        if item.admission_status == "REJECTED":
            contribution = "NOT_ADMITTED"
        elif item.relevance_label == "REJECT":
            contribution = "NOT_ADMITTED"
        elif key not in cell_evidence_ids or item.id not in cell_evidence_ids.get(key, set()):
            # Admitted, on-topic, but not among the (possibly
            # diversity-capped) items the coverage cell actually counted
            # — see coverage.py::_diverse_subset.
            contribution = "NONE"
        elif item.requirement_category is None:
            contribution = "NONE"
        else:
            suitability = evaluate_source_suitability(item.requirement_category, item)
            contribution = suitability if suitability != "UNSUITABLE" else "NONE"

        rows.append(
            EvidenceContributionTrace(
                evidence_id=item.id,
                candidate_id=item.candidate_id,
                requirement_category=item.requirement_category,
                source_role=item.source_role,
                relevance_label=item.relevance_label,
                admission_status=item.admission_status,
                domain=canonical_domain(item.source_url),
                contribution=contribution,
                resulting_cell_status=cell_status,
            )
        )
    return rows


def summarize_contribution_reasons(rows: list[EvidenceContributionTrace]) -> dict[str, int]:
    """Bounded count of WHY evidence didn't contribute — the fastest way
    to see whether low coverage is dominated by NOT_ADMITTED (Admission
    Gate rejecting most of it) vs. NONE (admitted evidence whose source
    role suitability is UNSUITABLE for its category, or evidence that
    lost the diversity cap) vs. genuine STRONG/ACCEPTABLE contribution."""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.contribution] = counts.get(row.contribution, 0) + 1
    return counts
