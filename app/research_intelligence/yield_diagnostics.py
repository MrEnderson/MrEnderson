"""Evidence yield diagnostics (v0.1.2.5 Phase 8). Deterministic, per-query
metrics for how much of what retrieval returns actually survives to
become authoritative evidence — logging/report diagnostics only, never
persisted to the database (no migration). Operates purely on already-
computed EvidenceItem fields (query_used, admission_status,
evidence_depth) plus plain counts supplied by the caller — never touches
prompt content or secrets.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.evidence import EvidenceItem


class QueryYieldMetrics(BaseModel):
    query: str
    candidate_id: str | None = None
    requirement_category: str | None = None
    results_returned: int = 0
    pre_screen_rejected: int = 0
    evidence_created: int = 0
    admission_accepted: int = 0
    admission_rejected: int = 0
    extracted_count: int = 0

    @property
    def accepted_evidence_yield(self) -> float:
        """accepted / max(results_returned, 1) — see checkpoint Phase 8."""
        return self.admission_accepted / max(self.results_returned, 1)

    def to_text(self) -> str:
        return (
            f"query={self.query!r} candidate_id={self.candidate_id} "
            f"category={self.requirement_category} results_returned={self.results_returned} "
            f"pre_screen_rejected={self.pre_screen_rejected} evidence_created={self.evidence_created} "
            f"admission_accepted={self.admission_accepted} admission_rejected={self.admission_rejected} "
            f"extracted_count={self.extracted_count} "
            f"accepted_evidence_yield={self.accepted_evidence_yield:.2f}"
        )


def compute_query_yield_metrics(
    evidence: list[EvidenceItem],
    *,
    results_returned_by_query: dict[str, int] | None = None,
    pre_screen_rejected_by_query: dict[str, int] | None = None,
) -> list[QueryYieldMetrics]:
    """Groups already-tagged, already-admission-stamped evidence by the
    query that produced it (EvidenceItem.query_used). `results_returned_by_query`
    / `pre_screen_rejected_by_query` come from app/agents/research.py::
    _gather_evidence, which is the only place that still has the raw,
    pre-EvidenceItem counts (a pre-screen-rejected result never becomes an
    EvidenceItem at all, so it can't be recovered from `evidence` alone)."""
    results_returned_by_query = results_returned_by_query or {}
    pre_screen_rejected_by_query = pre_screen_rejected_by_query or {}

    by_query: dict[str, QueryYieldMetrics] = {}
    for item in evidence:
        query = item.query_used or "(unknown query)"
        metrics = by_query.get(query)
        if metrics is None:
            metrics = QueryYieldMetrics(
                query=query,
                candidate_id=item.candidate_id,
                requirement_category=item.requirement_category,
                results_returned=results_returned_by_query.get(query, 0),
                pre_screen_rejected=pre_screen_rejected_by_query.get(query, 0),
            )
            by_query[query] = metrics
        metrics.evidence_created += 1
        if item.evidence_depth == "PAGE_EXTRACT":
            metrics.extracted_count += 1
        if item.admission_status == "ACCEPTED":
            metrics.admission_accepted += 1
        elif item.admission_status == "REJECTED":
            metrics.admission_rejected += 1

    # A query whose every result was pre-screen-rejected never produced any
    # EvidenceItem, so it would otherwise be invisible here entirely.
    for query, rejected in pre_screen_rejected_by_query.items():
        if query not in by_query:
            by_query[query] = QueryYieldMetrics(
                query=query,
                results_returned=results_returned_by_query.get(query, rejected),
                pre_screen_rejected=rejected,
            )

    return list(by_query.values())
