"""Evidence Admission Gate (v0.1.2.4 Defect 3).

    Tavily result -> EvidenceItem -> candidate/requirement tagging ->
    relevance + suitability -> EVIDENCE ADMISSION GATE
        |-- ACCEPT -> authoritative validation evidence
        `-- REJECT -> audit/rejected evidence only

Provenance (research_mode/research_task_id, see docs/research_intelligence.md)
answers WHERE did this evidence come from. Relevance scoring
(app/research_intelligence/relevance.py) answers how well it matches a
requirement's KEYWORDS. Neither answers the question this gate exists for:
SHOULD THIS EVIDENCE BE ADMITTED into a candidate's authoritative
validation evidence? An authoritative, well-matched-on-keywords source
about the WRONG topic — e.g. an authoritative page about the HR "candidate
skills assessment market size" scored MEDIUM relevance for a
data-analytics-dashboard candidate's own market_size requirement purely
because both mention "market size" — must still be rejected here. Source
authority is not topic relevance: an authoritative page about the wrong
market is still irrelevant (Phase 6).

All rules below must hold for ACCEPT (Phase 4) — deterministic, no model
call. REJECT is never a deletion: a rejected item keeps
admission_status=REJECTED with its reasons for audit, but must be excluded
by every caller from coverage/completeness, Strategy's evidence context,
prompt-facing (model-context) evidence, and report citation — see
admitted_only() below, and its callers in app/agents/research.py and
app/research_intelligence/gate.py.
"""
from __future__ import annotations

from app.config.settings import Settings
from app.research_intelligence.relevance import combined_text, overlap_ratio, significant_tokens
from app.research_intelligence.suitability import evaluate_source_suitability
from app.schemas.evidence import AdmissionRejectionReason, EvidenceItem


def evaluate_admission(
    item: EvidenceItem,
    *,
    candidate_label: str | None,
    candidate_description: str | None = None,
    settings: Settings,
) -> tuple[bool, list[AdmissionRejectionReason]]:
    """Returns (accepted, reasons). `reasons` is empty iff accepted. Never
    mutates `item` — callers apply the result via model_copy (see
    apply_admission_gate)."""
    reasons: list[AdmissionRejectionReason] = []

    # Rule 1: research_mode == VALIDATION. Untagged (None) is allowed
    # through for backward compatibility with hand-built fixtures/legacy
    # data that never set research_mode — mirrors the identical carve-out
    # already established in app/research_intelligence/gate.py.
    if item.research_mode is not None and item.research_mode != "VALIDATION":
        reasons.append("NOT_VALIDATION_MODE")

    # Rule 2: candidate_id present and valid.
    if not item.candidate_id:
        reasons.append("NO_CANDIDATE_ID")

    # Rule 3: requirement_category present.
    if not item.requirement_category:
        reasons.append("NO_REQUIREMENT_CATEGORY")

    # Rule 4: relevance_label != REJECT.
    if item.relevance_label is None or item.relevance_label == "REJECT":
        reasons.append("RELEVANCE_REJECTED")

    # Rule 5: relevance_score >= configured threshold (MEDIUM+, stricter
    # than the LOW+ bar relevance.py itself already enforces).
    if item.relevance_score is None or item.relevance_score < settings.research_admission_min_relevance_score:
        reasons.append("BELOW_RELEVANCE_THRESHOLD")

    # Rule 6: candidate-specific semantic overlap exceeds a deterministic
    # minimum — the actual fix for the leaked off-topic-evidence bug.
    # score_relevance's own candidate-match term is only a 40% weight, so a
    # strong keyword hit elsewhere in the formula can carry a zero-overlap
    # item past LOW/MEDIUM; this is a hard, independent floor.
    if _candidate_overlap(item, candidate_label, candidate_description) < settings.research_admission_min_candidate_overlap:
        reasons.append("INSUFFICIENT_CANDIDATE_OVERLAP")

    # Rule 7: source suitability != UNSUITABLE for the requirement.
    if item.requirement_category and evaluate_source_suitability(item.requirement_category, item) == "UNSUITABLE":
        reasons.append("SOURCE_UNSUITABLE_FOR_REQUIREMENT")

    return (len(reasons) == 0, reasons)


def _candidate_overlap(
    item: EvidenceItem, candidate_label: str | None, candidate_description: str | None
) -> float:
    """Fraction of the candidate's own significant label+description
    tokens that appear in the evidence text. No candidate topic tokens at
    all (a degenerate/very short label) never blocks admission — there's
    nothing to check overlap against, so this rule is vacuously satisfied,
    matching relevance.py's own fallback for the same edge case."""
    topic_tokens = significant_tokens(candidate_label or "")
    if candidate_description:
        topic_tokens |= significant_tokens(candidate_description)
    if not topic_tokens:
        return 1.0
    return overlap_ratio(topic_tokens, combined_text(item))


def apply_admission_gate(
    evidence: list[EvidenceItem],
    *,
    candidates_by_id: dict[str, tuple[str, str]],
    settings: Settings,
) -> list[EvidenceItem]:
    """Stamps admission_status/admission_rejection_reasons on every item —
    returns a NEW list, same length, nothing dropped (rejected items are
    marked, never removed; see apply_admission_gate's callers for where
    ACCEPTED-only filtering actually happens). `candidates_by_id` maps
    candidate_id -> (label, description); an item whose candidate_id isn't
    in that map can never pass rule 2/6 (no valid candidate to check
    overlap against) and is rejected accordingly."""
    stamped: list[EvidenceItem] = []
    for item in evidence:
        label, description = candidates_by_id.get(item.candidate_id or "", (None, None))
        accepted, reasons = evaluate_admission(
            item, candidate_label=label, candidate_description=description, settings=settings
        )
        stamped.append(
            item.model_copy(
                update={
                    "admission_status": "ACCEPTED" if accepted else "REJECTED",
                    "admission_rejection_reasons": reasons,
                }
            )
        )
    return stamped


def admitted_only(evidence: list[EvidenceItem]) -> list[EvidenceItem]:
    """The single filter every downstream consumer (coverage/completeness,
    Strategy evidence context, prompt-facing evidence, report citation)
    must apply — never re-derive admission independently. NOT_EVALUATED
    items (evidence that never went through the gate at all — DISCOVERY/
    GENERAL mode, or legacy data from before this gate existed) are passed
    through unchanged rather than silently excluded, to avoid breaking
    every pre-v0.1.2.4 code path that already applies its OWN relevance
    filtering (relevance_label != REJECT)."""
    return [e for e in evidence if e.admission_status != "REJECTED"]
