"""Research Dossier (Phase 10). Makes the final research state explicit,
built deterministically from ResearchOutput/EvidenceItem/coverage data
already computed elsewhere in this package — never asks a model to reproduce
data Jarvis already has.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.research_intelligence.schemas import (
    CandidateResearchStatus,
    ComparisonReadiness,
    CoverageCell,
    ResearchRequirement,
)


class CandidateDossierEntry(BaseModel):
    candidate_id: str
    candidate_label: str
    supported_findings: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    confidence: str = "LOW"


class ResearchDossier(BaseModel):
    objective: str
    candidates: list[str] = Field(default_factory=list)
    requirements: list[ResearchRequirement] = Field(default_factory=list)
    coverage_matrix: list[CoverageCell] = Field(default_factory=list)
    candidate_entries: list[CandidateDossierEntry] = Field(default_factory=list)
    comparison_readiness: ComparisonReadiness = Field(default_factory=ComparisonReadiness)
    unresolved_gaps: list[str] = Field(default_factory=list)
    recommended_next_research: list[str] = Field(default_factory=list)

    def to_text(self) -> str:
        lines = [f"OBJECTIVE: {self.objective}", f"CANDIDATES: {', '.join(self.candidates) or '(none)'}"]
        lines.append("EVIDENCE COVERAGE MATRIX:")
        for cell in self.coverage_matrix:
            lines.append(
                f"  [{cell.candidate_id}] {cell.category}: {cell.status} "
                f"(strong={cell.strong_count} acceptable={cell.acceptable_count} "
                f"weak={cell.weak_count} independent_domains={cell.independent_domain_count})"
            )
        for entry in self.candidate_entries:
            lines.append(f"{entry.candidate_label.upper()}:")
            lines.append(f"  confidence: {entry.confidence}")
            for f in entry.supported_findings:
                lines.append(f"  + {f}")
            for m in entry.missing_evidence:
                lines.append(f"  - missing: {m}")
        lines.append(f"COMPARISON READINESS: {'READY' if self.comparison_readiness.ready else 'NOT READY'}")
        if self.unresolved_gaps:
            lines.append("UNRESOLVED GAPS:")
            lines.extend(f"  - {g}" for g in self.unresolved_gaps)
        if self.recommended_next_research:
            lines.append("RECOMMENDED NEXT RESEARCH:")
            lines.extend(f"  - {q}" for q in self.recommended_next_research)
        return "\n".join(lines)


def build_research_dossier(
    *,
    objective: str,
    requirements: list[ResearchRequirement],
    coverage_cells: list[CoverageCell],
    comparison_readiness: ComparisonReadiness,
    candidate_labels: dict[str, str],
) -> ResearchDossier:
    entries: list[CandidateDossierEntry] = []
    cells_by_candidate: dict[str, list[CoverageCell]] = {}
    for cell in coverage_cells:
        cells_by_candidate.setdefault(cell.candidate_id, []).append(cell)

    status_by_candidate = {s.candidate_id: s for s in comparison_readiness.candidate_statuses}

    for candidate_id, cells in cells_by_candidate.items():
        label = candidate_labels.get(candidate_id, candidate_id)
        supported = [f"{c.category}: {c.status}" for c in cells if c.status in ("SUFFICIENT", "PARTIAL")]
        missing = [c.category for c in cells if c.status in ("MISSING", "WEAK")]
        status = status_by_candidate.get(candidate_id)
        confidence = "HIGH" if status and status.ready_for_comparison else ("MEDIUM" if supported else "LOW")
        entries.append(
            CandidateDossierEntry(
                candidate_id=candidate_id,
                candidate_label=label,
                supported_findings=supported,
                evidence_ids=[eid for c in cells for eid in c.evidence_ids],
                missing_evidence=missing,
                confidence=confidence,
            )
        )
    entries.sort(key=lambda e: e.candidate_id)

    unresolved_gaps = list(comparison_readiness.missing_requirements)

    return ResearchDossier(
        objective=objective,
        candidates=[candidate_labels.get(cid, cid) for cid in sorted(cells_by_candidate)],
        requirements=requirements,
        coverage_matrix=coverage_cells,
        candidate_entries=entries,
        comparison_readiness=comparison_readiness,
        unresolved_gaps=unresolved_gaps,
        recommended_next_research=comparison_readiness.remediation_queries,
    )
