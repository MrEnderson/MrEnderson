"""Deterministic compaction of research context for the Strategy Agent's
prompt (v0.1.1 efficiency patch).

This only shrinks the copy of `research_results` handed to the model on a
given Strategy attempt — the same pattern already used for Research's own
prompt (see app/agents/research.py::_prompt_evidence). It never touches:

- the persisted Evidence table (full fidelity, unaffected — see
  app/services/evidence_service.py),
- the completed research Task's own stored `output_data` (unaffected),
- evidence ids (never regenerated — the same ids survive compaction so
  citations and validation still line up; see
  app/security/evidence_qa.py::_check_strategy).

The set of evidence ids returned alongside the compacted results is also the
authoritative "what did Strategy actually see this attempt" set — see
app/orchestration/evaluator.py::run_worker_with_qa, which uses it (instead of
the full project-wide evidence pool) to validate `evidence_used` for THIS
call, so a real-but-compacted-out id can't accidentally validate just
because it exists somewhere else in the project.
"""
from __future__ import annotations

import re

# Ranked above plain AUTHORITATIVE/PAGE_EXTRACT preference: an id the
# previous attempt already cited must survive compaction, or a retry that
# re-cites it (entirely reasonably — QA may have flagged something else)
# would spuriously fail evidence-id validation. This is a hard inclusion
# guarantee, not just a sort tiebreaker.
_STRONG_QUALITY = ("PRIMARY", "AUTHORITATIVE")


def compact_research_results(
    research_results: list[dict],
    *,
    qa_feedback: str | None,
    previous_output: dict | None,
    settings,
) -> tuple[list[dict], set[str], dict]:
    """Returns (compacted_research_results, visible_evidence_ids, extra_context).

    `compacted_research_results` has the same shape as the input (one dict
    per research task) so downstream evidence-id collection
    (app/security/evidence_qa.py::_collect_research_evidence_ids) keeps
    working unchanged. `extra_context` carries bounded qa_feedback/previous
    conclusion text for the caller to fold into run_input.
    """
    pinned_ids = set((previous_output or {}).get("evidence_used") or [])

    all_evidence: list[dict] = []
    seen_ids: set[str] = set()
    for r in research_results:
        for e in r.get("evidence", []) or []:
            eid = e.get("id")
            if not eid or eid in seen_ids:
                continue
            seen_ids.add(eid)
            all_evidence.append(e)

    def sort_key(e: dict) -> tuple:
        return (
            0 if e.get("id") in pinned_ids else 1,
            0 if e.get("evidence_depth") == "PAGE_EXTRACT" else 1,
            0 if e.get("source_quality") in _STRONG_QUALITY else 1,
        )

    ranked = sorted(all_evidence, key=sort_key)
    selected = ranked[: settings.strategy_max_evidence_items]
    selected_ids = {e["id"] for e in selected if e.get("id")}

    compacted_results = []
    for r in research_results:
        evidence = [
            _bound_excerpt(e, settings.strategy_max_evidence_excerpt_chars)
            for e in (r.get("evidence") or [])
            if e.get("id") in selected_ids
        ]
        unresolved_gaps = [
            {"gap_type": g.get("gap_type"), "claim_or_question": g.get("claim_or_question")}
            for g in (r.get("evidence_gaps") or [])
            if not g.get("resolved")
        ][: settings.strategy_max_open_questions]
        compacted_results.append(
            {
                "task_id": r.get("task_id"),
                "title": r.get("title"),
                "agent_type": r.get("agent_type"),
                "question": r.get("question"),
                "summary": r.get("summary"),
                "insufficient_evidence": r.get("insufficient_evidence"),
                "findings": (r.get("findings") or [])[: settings.strategy_max_findings],
                "assumptions": (r.get("assumptions") or [])[: settings.strategy_max_assumptions],
                "open_questions": (r.get("open_questions") or [])[: settings.strategy_max_open_questions],
                "unresolved_evidence_gaps": unresolved_gaps,
                "evidence": evidence,
            }
        )

    extra: dict = {}
    if qa_feedback:
        extra["previous_qa_feedback"] = _bound_text(qa_feedback, settings.strategy_max_qa_feedback_chars)
    if previous_output:
        extra["previous_conclusion"] = {
            "recommendation": _bound_text(
                previous_output.get("recommendation", ""), settings.strategy_max_qa_feedback_chars
            ),
            "confidence": previous_output.get("confidence"),
        }

    return compacted_results, selected_ids, extra


def _bound_text(text: str, max_chars: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + " [truncated]"


def _bound_excerpt(evidence: dict, max_chars: int) -> dict:
    if not evidence.get("excerpt"):
        return evidence
    bounded = dict(evidence)
    bounded["excerpt"] = _bound_text(evidence["excerpt"], max_chars)
    return bounded
