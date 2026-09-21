"""Candidate Completeness Gate entry point (Phase 7/11/12). The single
function both app/agents/strategy.py (to gate its own output) and
app/security/evidence_qa.py (to independently verify Strategy respected that
gate) call — kept here, not in either of those modules, so neither depends
on the other.

Supports TWO research_results shapes (v0.1.2.1):

- Legacy / GENERAL: each research_results entry IS one candidate (this
  architecture assigns one research task per candidate for a comparison
  objective — see app/research_intelligence/candidates.py).
- Discovery/Validation (v0.1.2.1): a SINGLE research_results entry (a
  VALIDATION-mode research task's output) carries MULTIPLE candidates via
  its own `candidates` field, with each evidence item already tagged with
  the candidate_id it belongs to (see app/agents/research.py::_run_validation).
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.admission import admitted_only, apply_admission_gate
from app.research_intelligence.candidates import normalize_candidate_id
from app.research_intelligence.completeness import evaluate_completeness
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.schemas import ComparisonReadiness, ResearchRequirement
from app.research_intelligence.tagging import tag_evidence_for_candidate
from app.schemas.evidence import EvidenceItem

# A comparison objective needs at least this many distinct candidates before
# the completeness gate applies at all — a single-candidate research task
# (not a comparison) is never gated.
MIN_CANDIDATES_FOR_GATE = 2


def evaluate_comparison_readiness(research_results: list[dict], *, settings: Settings) -> ComparisonReadiness:
    embedded = _collect_embedded_candidates(research_results)
    if embedded:
        return _evaluate_embedded_candidates(research_results, embedded, settings=settings)
    return _evaluate_legacy_shape(research_results, settings=settings)


def _collect_embedded_candidates(research_results: list[dict]) -> list[tuple[str, str]]:
    """Candidates carried directly on a research_results entry's own
    `candidates` field (a DISCOVERY task's output, or a VALIDATION task's
    output which just echoes them back) — see
    app/schemas/agents.py::ResearchOutput.candidates."""
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in research_results:
        for c in r.get("candidates") or []:
            if not isinstance(c, dict):
                continue
            label = (c.get("label") or "").strip()
            if not label:
                continue
            candidate_id = normalize_candidate_id(label)
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            candidates.append((candidate_id, label))
    return candidates


def _evaluate_embedded_candidates(
    research_results: list[dict], candidates: list[tuple[str, str]], *, settings: Settings
) -> ComparisonReadiness:
    if len(candidates) < MIN_CANDIDATES_FOR_GATE:
        return ComparisonReadiness(ready=True)

    candidate_labels = dict(candidates)
    requirements: list[ResearchRequirement] = []
    requirements_by_candidate: dict[str, list[ResearchRequirement]] = {}
    for candidate_id, label in candidates:
        reqs = generate_requirement_set(candidate_id=candidate_id, candidate_label=label, settings=settings)
        requirements_by_candidate[candidate_id] = reqs
        requirements.extend(reqs)

    evidence_by_candidate: dict[str, list[EvidenceItem]] = {cid: [] for cid, _ in candidates}
    for r in research_results:
        for item in _safe_parse_evidence(r.get("evidence") or []):
            # v0.1.2.3 Defect 1 fix: evidence explicitly tagged as having
            # come from a DISCOVERY (or any other non-VALIDATION) research
            # task must NEVER count toward VALIDATION coverage, even via
            # the defensive fallback below — discovery evidence establishes
            # a candidate is worth investigating, it does not validate it
            # (see app/research_intelligence/completeness.py and
            # docs/research_intelligence.md, "Evidence provenance").
            # Untagged evidence (research_mode is None — legacy data, hand-
            # built test fixtures) is still allowed through for backward
            # compatibility.
            if item.research_mode is not None and item.research_mode != "VALIDATION":
                continue
            if item.candidate_id in evidence_by_candidate:
                evidence_by_candidate[item.candidate_id].append(item)
                continue
            # Defensive fallback for evidence that arrives without a valid
            # candidate_id tag (e.g. hand-built test fixtures) — re-tag
            # against every embedded candidate and keep the best match, so
            # evidence for Candidate A can never satisfy Candidate B's
            # requirement just because it arrived untagged.
            best_id, best_item, best_score = None, None, -1.0
            for candidate_id, label in candidates:
                other_labels = [lbl for cid, lbl in candidates if cid != candidate_id]
                tagged = tag_evidence_for_candidate(
                    [item],
                    candidate_id=candidate_id,
                    candidate_label=label,
                    requirements=requirements_by_candidate[candidate_id],
                    other_candidate_labels=other_labels,
                )[0]
                score = tagged.relevance_score if tagged.relevance_label != "REJECT" else -1.0
                score = score if score is not None else -1.0
                if score > best_score:
                    best_score, best_id, best_item = score, candidate_id, tagged
            if best_id is not None:
                evidence_by_candidate[best_id].append(best_item)

    # Evidence Admission Gate (v0.1.2.4 Defect 3): Strategy's own
    # completeness re-verification must apply the SAME gate research.py
    # already applied when it gathered this evidence — never trust that
    # upstream tagging alone (relevance/suitability) was enough, since this
    # is precisely the independent check the gate exists to enforce even
    # if research.py's own gate were ever bypassed or fed stale data. See
    # app/research_intelligence/admission.py.
    candidates_by_id = {cid: (label, None) for cid, label in candidates}
    for candidate_id, items in list(evidence_by_candidate.items()):
        stamped = apply_admission_gate(items, candidates_by_id=candidates_by_id, settings=settings)
        evidence_by_candidate[candidate_id] = admitted_only(stamped)

    coverage_cells = build_coverage_matrix(requirements, evidence_by_candidate, settings=settings)
    return evaluate_completeness(requirements, coverage_cells, candidate_labels, settings=settings)


def _evaluate_legacy_shape(research_results: list[dict], *, settings: Settings) -> ComparisonReadiness:
    """Treats each research_results entry as one candidate — the
    unchanged v0.1.2 behavior for a plan shaped as one research task per
    candidate, with no explicit DISCOVERY/VALIDATION split. Re-tags each
    candidate's evidence independently of whatever app/agents/research.py
    already tagged, so this works even when fed raw/hand-built evidence
    (e.g. in tests)."""
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for r in research_results:
        label = (r.get("title") or r.get("question") or "candidate").strip()
        candidate_id = normalize_candidate_id(label)
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        candidates.append((candidate_id, label))

    if len(candidates) < MIN_CANDIDATES_FOR_GATE:
        return ComparisonReadiness(ready=True)

    candidate_labels = dict(candidates)
    requirements: list[ResearchRequirement] = []
    evidence_by_candidate: dict[str, list[EvidenceItem]] = {}

    for r in research_results:
        label = (r.get("title") or r.get("question") or "candidate").strip()
        candidate_id = normalize_candidate_id(label)
        if candidate_id in evidence_by_candidate:
            continue  # duplicate research_results entry for the same candidate
        other_labels = [lbl for cid, lbl in candidates if cid != candidate_id]
        candidate_requirements = generate_requirement_set(
            candidate_id=candidate_id, candidate_label=label, settings=settings
        )
        requirements.extend(candidate_requirements)
        parsed = _safe_parse_evidence(r.get("evidence") or [])
        evidence_by_candidate[candidate_id] = tag_evidence_for_candidate(
            parsed,
            candidate_id=candidate_id,
            candidate_label=label,
            requirements=candidate_requirements,
            other_candidate_labels=other_labels,
        )

    coverage_cells = build_coverage_matrix(requirements, evidence_by_candidate, settings=settings)
    return evaluate_completeness(requirements, coverage_cells, candidate_labels, settings=settings)


def _safe_parse_evidence(raw_items: list) -> list[EvidenceItem]:
    parsed: list[EvidenceItem] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            parsed.append(EvidenceItem.model_validate(item))
        except Exception:  # noqa: BLE001 - a malformed record must never break the gate
            continue
    return parsed
