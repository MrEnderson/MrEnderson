"""Candidate Completeness Gate (Phase 7) + cross-candidate gap-query
prioritization (Phase 8). Before Strategy is allowed to rank multiple
candidates, every candidate must meet the configured minimum coverage across
the required core categories. If one candidate has rich evidence and another
has almost none, comparison is refused — Strategy must not manufacture a
winner (see app/agents/strategy.py).
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.requirements import CRITICAL_CATEGORIES
from app.research_intelligence.schemas import (
    CandidateResearchStatus,
    ComparisonReadiness,
    CoverageCell,
    ResearchRequirement,
)

_SUFFICIENT_WEIGHT = 1.0
_PARTIAL_WEIGHT = 0.5
_WEAK_WEIGHT = 0.15
_MISSING_WEIGHT = 0.0

_STATUS_WEIGHT = {
    "SUFFICIENT": _SUFFICIENT_WEIGHT,
    "PARTIAL": _PARTIAL_WEIGHT,
    "WEAK": _WEAK_WEIGHT,
    "MISSING": _MISSING_WEIGHT,
}

# Bounded, per Phase 14 — cross-candidate remediation suggestions are advice
# surfaced in the report/dossier, not automatically executed (this
# architecture plans all tasks up front; see docs/research_intelligence.md).
_MAX_REMEDIATION_QUERIES = 10


def evaluate_completeness(
    requirements: list[ResearchRequirement],
    coverage_cells: list[CoverageCell],
    candidate_labels: dict[str, str],
    *,
    settings: Settings,
) -> ComparisonReadiness:
    cells_by_candidate: dict[str, list[CoverageCell]] = {}
    for cell in coverage_cells:
        cells_by_candidate.setdefault(cell.candidate_id, []).append(cell)

    statuses: list[CandidateResearchStatus] = []
    for candidate_id, cells in cells_by_candidate.items():
        statuses.append(
            _candidate_status(
                candidate_id=candidate_id,
                label=candidate_labels.get(candidate_id, candidate_id),
                cells=cells,
                settings=settings,
            )
        )
    statuses.sort(key=lambda s: s.candidate_id)

    ready = bool(statuses) and all(s.ready_for_comparison for s in statuses)
    missing_requirements = sorted(
        {f"{s.candidate_label}: {req}" for s in statuses for req in s.critical_requirements_missing}
    )
    # v0.1.2.4 Defect 4: every requirement that isn't SUFFICIENT must be
    # visible somewhere in the report — either as a CRITICAL gap (above) or
    # here, as an OTHER MATERIAL gap. Before this fix, a non-critical
    # category (market_size, feasibility, ...) sitting at MISSING, or a
    # CRITICAL category sitting at WEAK/PARTIAL rather than fully MISSING,
    # was silently dropped from both lists — see
    # CandidateResearchStatus.other_material_gaps and docs/research_intelligence.md.
    other_material_gaps = sorted(
        {f"{s.candidate_label}: {req}" for s in statuses for req in s.other_material_gaps}
    )

    remediation = _remediation_queries(statuses, cells_by_candidate, requirements, settings=settings)

    return ComparisonReadiness(
        ready=ready,
        candidate_statuses=statuses,
        missing_requirements=missing_requirements,
        other_material_gaps=other_material_gaps,
        remediation_queries=remediation,
    )


def _candidate_status(
    *, candidate_id: str, label: str, cells: list[CoverageCell], settings: Settings
) -> CandidateResearchStatus:
    if not cells:
        return CandidateResearchStatus(
            candidate_id=candidate_id,
            candidate_label=label,
            coverage_percentage=0.0,
            critical_requirements_missing=sorted(CRITICAL_CATEGORIES),
            ready_for_comparison=False,
        )

    total_weight = sum(_STATUS_WEIGHT[c.status] for c in cells)
    coverage_percentage = total_weight / len(cells)

    critical_missing = sorted(
        c.category for c in cells if c.category in CRITICAL_CATEGORIES and c.status == "MISSING"
    )
    # v0.1.2.4 Defect 4 fix: this used to be `status in ("WEAK", "PARTIAL")`
    # only — a non-critical category sitting at MISSING (e.g. feasibility,
    # market_size) fell through both this and critical_missing above,
    # vanishing from the report entirely even though findings elsewhere
    # described it as absent. Now: every non-SUFFICIENT cell not already
    # counted as critical-missing lands here instead — nothing is dropped.
    other_material_gaps = sorted(
        c.category for c in cells if c.status != "SUFFICIENT" and c.category not in critical_missing
    )

    ready = (
        coverage_percentage >= settings.research_min_comparison_coverage
        and not critical_missing
    )

    return CandidateResearchStatus(
        candidate_id=candidate_id,
        candidate_label=label,
        coverage_percentage=round(coverage_percentage, 4),
        critical_requirements_missing=critical_missing,
        other_material_gaps=other_material_gaps,
        ready_for_comparison=ready,
    )


def _remediation_queries(
    statuses: list[CandidateResearchStatus],
    cells_by_candidate: dict[str, list[CoverageCell]],
    requirements: list[ResearchRequirement],
    *,
    settings: Settings,
) -> list[str]:
    """Prioritizes: (1) critical missing requirement, (2) candidate with the
    lowest coverage, (3) high-importance requirement, (4) requirement with no
    STRONG/ACCEPTABLE evidence at all. Bounded — never an unbounded fan-out."""
    requirement_by_id = {r.id: r for r in requirements}
    ranked_candidates = sorted(statuses, key=lambda s: s.coverage_percentage)

    candidates: list[tuple[int, int, int, str]] = []  # (critical_rank, coverage_rank, -importance, query)
    for coverage_rank, status in enumerate(ranked_candidates):
        for cell in cells_by_candidate.get(status.candidate_id, []):
            if cell.status == "SUFFICIENT":
                continue
            requirement = requirement_by_id.get(cell.requirement_id)
            importance = requirement.importance if requirement else 3
            critical_rank = 0 if cell.category in CRITICAL_CATEGORIES and cell.status == "MISSING" else 1
            query = f"{status.candidate_label} {cell.category.replace('_', ' ')}"
            candidates.append((critical_rank, coverage_rank, -importance, query))

    candidates.sort(key=lambda t: (t[0], t[1], t[2]))
    seen: set[str] = set()
    ordered: list[str] = []
    for _, _, _, query in candidates:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(query)
        if len(ordered) >= min(_MAX_REMEDIATION_QUERIES, settings.research_max_gap_queries_per_attempt * 3):
            break
    return ordered
