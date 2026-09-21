"""QA Context Compactor (v0.1.2.6, Phase 3/4).

    AUTHORITATIVE WORKER STATE
      |
      +----> deterministic evidence checks / coverage / gate  (FULL state)
      |
      +----> QA CONTEXT COMPACTOR
      |          |
      |          v
      |       QA MODEL

Root cause traced this checkpoint: `app/agents/qa.py::QAAgent.run()` was
handed `output.model_dump(mode="json")` — the ENTIRE worker output —
completely uncompacted, unlike `app/agents/research.py`'s own model
prompt (already bounded since v0.1.2/v0.1.2.2/v0.1.2.3) or
`app/agents/strategy_context.py`'s equivalent for Strategy. For a
VALIDATION-mode research task, `output.evidence` alone can carry up to
`research_max_validation_evidence_items` (60) full EvidenceItems (every
field — claim, excerpt, provenance, admission metadata, ...), growing on
every retry as `accumulated_evidence` grows — this is exactly why the
live v0.1.2.5 benchmark showed the QA request growing ~2.2x across
retries (71,254 -> 110,274 -> 157,232 chars) while the Research request
(which IS already bounded) shrank.

This module builds a NEW, bounded, QA-facing view of a worker's output.
It NEVER changes what `app/security/evidence_qa.py::evaluate_evidence`,
`app/research_intelligence/coverage.py`, or
`app/research_intelligence/gate.py` see — those all continue to receive
the full, authoritative `output.model_dump(mode="json")`, unchanged. Only
the copy sent to the QA model's prompt is compacted.
"""
from __future__ import annotations

import json
import re

# Evidence with these depths/relevance labels is preferred when the
# bounded evidence budget can't fit everything — mirrors
# app/agents/research.py::_prompt_evidence's own ranking philosophy.
_PREFERRED_DEPTH = "PAGE_EXTRACT"
_PREFERRED_RELEVANCE = "HIGH"

# The only EvidenceItem fields a QA judgment actually needs (Phase 4) —
# never the full ~24-field EvidenceItem (excerpt, publisher, query_used,
# verification_status, confidence, evidence_type, timestamps,
# admission_rejection_reasons, etc. are all audit-only here).
_QA_EVIDENCE_FIELDS = (
    "id",
    "candidate_id",
    "requirement_category",
    "source_role",
    "source_quality",
    "evidence_depth",
    "relevance_label",
)


def compact_qa_context(output: dict, *, settings) -> dict:
    """Returns a NEW, bounded dict built from the full worker `output`
    dump — never mutates `output`, never used for anything but the QA
    model's own prompt. Excludes: full historical ResearchOutput objects
    (this function only ever sees ONE attempt's own output, the current
    one — evaluator.py never hands it a retry history), rejected evidence
    bodies, repeated page extracts (excerpts are dropped entirely here —
    a short claim is enough for a QA relevance/completeness judgment),
    the entire authoritative evidence store (bounded + deduplicated by
    (candidate_id, requirement_category) cell), and full requirement
    objects (reduced to a compact coverage_summary)."""
    compacted: dict = {
        "question": output.get("question"),
        "research_mode": output.get("research_mode"),
        "summary": _bound_text(output.get("summary") or "", settings.qa_prompt_max_finding_chars),
        "insufficient_evidence": output.get("insufficient_evidence"),
    }

    candidates = output.get("candidates") or []
    if candidates:
        compacted["candidates"] = [
            {"id": c.get("id"), "label": c.get("label")} for c in candidates if c.get("id") or c.get("label")
        ]

    compacted["findings"] = _bounded_findings(output.get("findings") or [], settings)
    compacted["assumptions"] = _bounded_texts(
        output.get("assumptions") or [], settings.qa_prompt_max_open_questions, settings.qa_prompt_max_open_question_chars
    )
    compacted["open_questions"] = _bounded_texts(
        output.get("open_questions") or [], settings.qa_prompt_max_open_questions, settings.qa_prompt_max_open_question_chars
    )
    compacted["unsupported_claims"] = _bounded_texts(
        output.get("unsupported_claims") or [], settings.qa_prompt_max_open_questions, settings.qa_prompt_max_open_question_chars
    )

    evidence = output.get("evidence") or []
    qa_visible = [e for e in evidence if _is_qa_visible(e)]
    compacted["evidence"] = _bounded_evidence(qa_visible, settings)
    compacted["evidence_total_count"] = len(evidence)
    compacted["evidence_shown_count"] = len(compacted["evidence"])
    compacted["evidence_excluded_count"] = len(evidence) - len(compacted["evidence"])

    unresolved_gaps = [g for g in (output.get("evidence_gaps") or []) if not g.get("resolved")]
    compacted["unresolved_gaps"] = _bounded_gaps(unresolved_gaps, settings)
    compacted["unresolved_gap_count"] = len(unresolved_gaps)

    coverage_summary = _coverage_summary(output.get("requirements") or [])
    if coverage_summary:
        compacted["coverage_summary"] = coverage_summary

    # Final safety net (Phase 4's QA_PROMPT_MAX_TOTAL_CONTEXT_CHARS):
    # every component above is already individually bounded, but a
    # pathological mix (many candidates, many cells) could still sum past
    # a sane total — trim the evidence list further (the largest, most
    # compressible component) rather than let the whole context balloon.
    _enforce_total_budget(compacted, settings)
    return compacted


def _is_qa_visible(item: dict) -> bool:
    """Excludes REJECTED (Evidence Admission Gate, VALIDATION mode) and
    REJECT-relevance (the older, coarser signal — still the only one
    available for DISCOVERY/GENERAL evidence, which never goes through
    the admission gate) evidence from what QA sees. This mirrors, and
    must stay consistent with, app/orchestration/executor.py::build_report's
    identical exclusion — see docs/research_intelligence.md."""
    if item.get("admission_status") == "REJECTED":
        return False
    if item.get("relevance_label") == "REJECT":
        return False
    return True


def _bounded_evidence(items: list[dict], settings) -> list[dict]:
    def sort_key(item: dict) -> tuple:
        return (
            0 if item.get("evidence_depth") == _PREFERRED_DEPTH else 1,
            0 if item.get("relevance_label") == _PREFERRED_RELEVANCE else 1,
        )

    ranked = sorted(items, key=sort_key)

    selected: list[dict] = []
    per_cell_counts: dict[tuple, int] = {}
    total_chars = 0
    for item in ranked:
        if len(selected) >= settings.qa_prompt_max_evidence_items:
            break
        cell = (item.get("candidate_id"), item.get("requirement_category"))
        count = per_cell_counts.get(cell, 0)
        if count >= settings.qa_prompt_max_evidence_per_requirement:
            continue
        compact_item = _compact_evidence_item(item, settings)
        item_chars = len(json.dumps(compact_item))
        if selected and total_chars + item_chars > settings.qa_prompt_max_evidence_chars:
            continue
        selected.append(compact_item)
        per_cell_counts[cell] = count + 1
        total_chars += item_chars
    return selected


def _compact_evidence_item(item: dict, settings) -> dict:
    compact = {field: item[field] for field in _QA_EVIDENCE_FIELDS if item.get(field) is not None}
    claim = item.get("claim")
    if claim:
        compact["claim"] = _bound_text(claim, settings.qa_prompt_max_evidence_claim_chars)
    return compact


def _bounded_findings(findings: list[dict], settings) -> list[dict]:
    out = []
    for f in findings[: settings.qa_prompt_max_findings]:
        out.append(
            {
                "claim": _bound_text(f.get("claim") or "", settings.qa_prompt_max_finding_chars),
                "evidence_type": f.get("evidence_type"),
            }
        )
    return out


def _bounded_gaps(gaps: list[dict], settings) -> list[dict]:
    ranked = sorted(gaps, key=lambda g: -(g.get("importance") or 3))
    out = []
    for g in ranked[: settings.qa_prompt_max_gaps]:
        out.append(
            {
                "candidate_id": g.get("candidate_id"),
                "gap_type": g.get("gap_type"),
                "claim_or_question": _bound_text(g.get("claim_or_question") or "", settings.qa_prompt_max_gap_chars),
            }
        )
    return out


def _coverage_summary(requirements: list[dict]) -> dict:
    """Built from `.status`, already computed deterministically by
    app/research_intelligence/coverage.py::build_coverage_matrix (which
    mutates each ResearchRequirement in place) BEFORE this function ever
    runs — never re-derived, never estimated."""
    summary: dict[str, dict[str, str]] = {}
    for r in requirements:
        category = r.get("category")
        status = r.get("status")
        if not category or not status:
            continue
        candidate_id = r.get("candidate_id") or "?"
        summary.setdefault(candidate_id, {})[category] = status
    return summary


def _enforce_total_budget(compacted: dict, settings) -> None:
    """Last-resort trim if the sum of already-bounded components still
    exceeds qa_prompt_max_total_context_chars — repeatedly halves the
    evidence list (the largest, most compressible component) rather than
    silently exceeding the configured bound."""
    limit = settings.qa_prompt_max_total_context_chars
    while len(json.dumps(compacted)) > limit and compacted.get("evidence"):
        keep = max(1, len(compacted["evidence"]) // 2)
        if keep == len(compacted["evidence"]):
            break
        compacted["evidence"] = compacted["evidence"][:keep]
        compacted["evidence_shown_count"] = len(compacted["evidence"])


def _bound_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + " [truncated]"


def _bounded_texts(texts: list[str], max_items: int, max_chars: int) -> list[str]:
    return [_bound_text(t, max_chars) for t in (texts or [])[:max_items] if t]
