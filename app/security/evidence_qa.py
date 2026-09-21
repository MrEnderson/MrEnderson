"""Deterministic evidence-quality checks, layered in front of the QA agent's
LLM verdict — the same defense-in-depth pattern as
app/security/approvals.py::classify_risk sitting in front of the planner.

This runs identically under MockProvider and any live ModelProvider, so
evidence discipline is enforced even if the QA agent's own model misses it,
and the whole check suite stays testable without a live API key.

Also the source of the structured `EvidenceGap`s that drive targeted research
retries (see app/orchestration/evaluator.py and
app/agents/research.py::ResearchAgent._build_queries) — gaps are derived
deterministically from the research output's own unsupported_claims/
open_questions/assumptions text, not parsed from free-text LLM feedback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config.settings import get_settings
from app.research_intelligence.gate import evaluate_comparison_readiness
from app.schemas.agents import QAVerdict
from app.schemas.evidence import EvidenceGap, EvidenceGapType

_QUANT_TERMS = (
    "market size",
    "growth rate",
    "competitor",
    "revenue",
    "cac",
    "customer acquisition cost",
    "conversion rate",
    "market share",
    "user count",
    "users",
    "price",
    "pricing",
)

# Deliberately small, flat taxonomy (see app/schemas/evidence.py::EvidenceGapType).
# Each gap type maps to a set of substrings to look for, and a short phrase
# used to build a bounded follow-up search query.
_GAP_KEYWORDS: tuple[tuple[EvidenceGapType, tuple[str, ...], str], ...] = (
    ("market_size", ("market size", "total addressable market", " tam "), "market size"),
    ("growth_rate", ("growth rate", "growth", "cagr"), "growth rate"),
    ("competitor", ("competitor", "competition", "named competitor"), "competitors"),
    ("pricing", ("pricing", "price point", "competitor pricing"), "pricing"),
    ("demand", ("demand", "conversion", "traction"), "demand and conversion signals"),
    (
        "customer_validation",
        ("customer validation", "customer interview", "user validation", "customer feedback"),
        "customer validation",
    ),
    ("financial", ("revenue", "financial", "funding", "profit margin"), "revenue and financials"),
    ("technical", ("technical feasibility", "implementation complexity"), "technical feasibility"),
)


@dataclass
class EvidenceCheckResult:
    issues: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    needs_review: bool = False
    gaps: list[EvidenceGap] = field(default_factory=list)
    # Set only by the Candidate Completeness Gate's QA readiness contract
    # (v0.1.2.2, Phase 10/12) — when Strategy correctly refuses to rank
    # under comparison_ready=false, this FORCES the merged verdict to PASS
    # regardless of the model QA's own (possibly over-punitive) judgment;
    # when Strategy asserts an unqualified winner despite comparison_ready
    # =false, this forces NEEDS_REVIEW even if the model QA said PASS. See
    # merge_into_verdict and _check_comparison_readiness below.
    verdict_override: str | None = None


def evaluate_evidence(
    output: dict, *, input_data: dict | None = None, known_evidence_ids: set[str] | None = None
) -> EvidenceCheckResult:
    """Dispatches on the shape of `output` (a ResearchOutput or StrategyOutput
    dump). Anything else (execution, qa, unknown) is a no-op."""
    if "recommendation" in output and "options_considered" in output:
        return _check_strategy(output, input_data, known_evidence_ids)
    if "findings" in output and "question" in output:
        return _check_research(output)
    return EvidenceCheckResult()


def merge_into_verdict(verdict: QAVerdict, check: EvidenceCheckResult) -> QAVerdict:
    if check.verdict_override:
        # Readiness-contract override (Phase 10/12): correct handling of
        # insufficient evidence forces PASS even if the model QA itself
        # argued Strategy should have named a winner — PASS here means
        # "correctly handled insufficient evidence," never "business
        # opportunity validated." An unqualified winner claim despite
        # comparison_ready=false forces at least NEEDS_REVIEW even if the
        # model QA said PASS. Takes priority over every other check below.
        issues = list(dict.fromkeys([*verdict.issues, *check.issues]))
        if check.verdict_override == "PASS":
            feedback = (
                "Comparison readiness gate reports insufficient comparable evidence; Strategy "
                "correctly refused to declare a winner and named what's missing — this is "
                "correct handling of insufficient evidence, not a validated business "
                "recommendation."
            )
            score = max(verdict.score, 0.75)
        else:
            feedback = (
                f"{verdict.feedback} Strategy asserted a winner/validated recommendation "
                "without clear provisional qualification despite comparison_ready=false."
            ).strip()
            score = min(verdict.score, 0.4)
        return verdict.model_copy(
            update={"verdict": check.verdict_override, "score": score, "issues": issues, "feedback": feedback}
        )

    if not check.needs_review:
        return verdict

    issues = list(dict.fromkeys([*verdict.issues, *check.issues]))
    unsupported = list(dict.fromkeys([*verdict.unsupported_claims, *check.unsupported_claims]))
    gap_text = "; ".join([*check.issues, *(f"unsupported claim: {c}" for c in check.unsupported_claims)])
    feedback = f"{verdict.feedback} Evidence gap(s) found: {gap_text}".strip()

    new_verdict = "NEEDS_REVIEW" if verdict.verdict == "PASS" else verdict.verdict
    new_score = min(verdict.score, 0.6) if verdict.verdict == "PASS" else verdict.score

    return verdict.model_copy(
        update={
            "verdict": new_verdict,
            "score": new_score,
            "issues": issues,
            "unsupported_claims": unsupported,
            "feedback": feedback,
        }
    )


def _check_research(output: dict) -> EvidenceCheckResult:
    issues: list[str] = []
    unsupported = list(output.get("unsupported_claims") or [])

    findings = output.get("findings") or []
    evidence = output.get("evidence") or []
    fact_findings = [f for f in findings if f.get("evidence_type") == "FACT"]

    if fact_findings and not evidence:
        issues.append(f"{len(fact_findings)} finding(s) labeled FACT but no evidence is attached.")
        for f in fact_findings:
            claim = f.get("claim", "")
            if claim and claim not in unsupported:
                unsupported.append(claim)

    missing_url = [e for e in evidence if not e.get("source_url")]
    if missing_url:
        issues.append(f"{len(missing_url)} evidence item(s) are missing a source URL.")

    urls = [e.get("source_url") for e in evidence if e.get("source_url")]
    if len(urls) >= 3 and (1 - len(set(urls)) / len(urls)) > 0.5:
        issues.append("Evidence sources are duplicated excessively.")

    stale_after_days = get_settings().evidence_stale_after_days
    now = datetime.now(timezone.utc)
    for e in evidence:
        published = _parse_datetime(e.get("published_at"))
        if published is None:
            continue
        if (now - published).days > stale_after_days:
            label = e.get("source_title") or (e.get("claim") or "")[:60]
            issues.append(f"Evidence is stale (> {stale_after_days} days old): {label}")

    # v0.1.2.4 Defect 2 fix: DISCOVERY mode never has requirement-scoped
    # gaps to resolve (result.requirements is always [] — there's no
    # single candidate yet to research categories for), and a retry can
    # only re-run the SAME broad, candidate-agnostic search — it can never
    # actually resolve a "pricing"/"competitor"-type gap. Applying the
    # generic keyword-based gap detector to DISCOVERY's own honest
    # insufficient_evidence signal (which the system prompt explicitly
    # tells it to set when it can't find enough distinct candidates) was
    # manufacturing UNRESOLVABLE gaps every attempt, downgrading a correct
    # model PASS to NEEDS_REVIEW and exhausting max_agent_retries on
    # retries that could never succeed — see
    # tests/test_discovery_pass_terminates_immediately.py and
    # docs/research_intelligence.md, v0.1.2.4.
    gaps: list[EvidenceGap] = []
    if output.get("research_mode") != "DISCOVERY":
        gaps = _detect_evidence_gaps(output)
        if gaps:
            issues.append(
                f"{len(gaps)} evidence gap(s) identified: "
                + ", ".join(g.gap_type for g in gaps)
            )

    return EvidenceCheckResult(
        issues=issues,
        unsupported_claims=unsupported,
        needs_review=bool(issues or unsupported),
        gaps=gaps,
    )


def _detect_evidence_gaps(output: dict) -> list[EvidenceGap]:
    """Scans the research output's own honesty signals (unsupported_claims,
    open_questions, assumptions) for known gap-type keywords, turning free
    text the agent already wrote into structured, retry-actionable gaps.
    Only fires when the task reports it doesn't have enough evidence —
    never invents a gap for a task that's actually fine."""
    if not output.get("insufficient_evidence"):
        return []

    texts: list[str] = [
        *(output.get("unsupported_claims") or []),
        *(output.get("open_questions") or []),
        *(output.get("assumptions") or []),
    ]
    if not texts:
        return []

    topic = (output.get("question") or "").replace("Research:", "").strip()
    combined = " ".join(texts).lower()

    gaps: list[EvidenceGap] = []
    seen_types: set[str] = set()
    for gap_type, keywords, query_phrase in _GAP_KEYWORDS:
        if gap_type in seen_types:
            continue
        matched_text = next((t for t in texts if any(k in t.lower() for k in keywords)), None)
        if matched_text is None and not any(k in combined for k in keywords):
            continue
        seen_types.add(gap_type)
        gaps.append(
            EvidenceGap(
                claim_or_question=matched_text or f"Missing evidence for {query_phrase}",
                gap_type=gap_type,
                related_claim=matched_text,
                suggested_query=f"{topic} {query_phrase}".strip() if topic else query_phrase,
            )
        )
    return gaps


_STRONG_EVIDENCE_DEPTH = frozenset({"PAGE_EXTRACT"})
_STRONG_SOURCE_QUALITY = frozenset({"AUTHORITATIVE", "PRIMARY"})


def _check_strategy(
    output: dict, input_data: dict | None, known_evidence_ids: set[str] | None = None
) -> EvidenceCheckResult:
    issues: list[str] = []
    unsupported = list(output.get("unsupported_claims") or [])
    evidence_used = output.get("evidence_used") or []

    text = f"{output.get('recommendation', '')} {output.get('reasoning', '')}"
    quant_claims = _find_unbacked_quantitative_claims(text)
    for claim in quant_claims:
        if not evidence_used:
            note = f'Quantitative claim stated without cited evidence: "{claim}"'
            if note not in unsupported:
                unsupported.append(note)

    if unsupported and not evidence_used:
        issues.append("Quantitative claims made without any evidence_used citation.")

    # Minimal deterministic guard (not a source-ranking engine): a
    # quantitative/financial claim citing evidence at all must not rely
    # solely on UNKNOWN-quality search-snippet evidence — it needs at least
    # one PAGE_EXTRACT or AUTHORITATIVE/PRIMARY source among what it cites.
    # Weak evidence is never discarded, just prevented from single-handedly
    # backing a high-confidence quantitative conclusion.
    if quant_claims and evidence_used and input_data:
        evidence_by_id = _collect_research_evidence_by_id(input_data)
        cited_items = [evidence_by_id[eid] for eid in evidence_used if eid in evidence_by_id]
        strong = [
            e
            for e in cited_items
            if e.get("evidence_depth") in _STRONG_EVIDENCE_DEPTH
            or e.get("source_quality") in _STRONG_SOURCE_QUALITY
        ]
        if cited_items and not strong:
            issues.append(
                "Quantitative claim(s) backed only by UNKNOWN-quality search-snippet "
                "evidence, no PAGE_EXTRACT or AUTHORITATIVE/PRIMARY source: "
                + "; ".join(quant_claims[:3])
            )

    if evidence_used:
        # `known_evidence_ids` is the authoritative source (e.g. the
        # project's persisted Evidence rows, which now share ids with the
        # EvidenceItems Strategy actually saw — see app/database/repositories.py
        # ::EvidenceRepository.create). input_data's research_results is kept
        # as an additional, narrower source when present (still correct, just
        # scoped to this task's own dependencies) — some call sites (the
        # standalone qa task) don't carry research_results at all, which is
        # exactly the propagation gap known_evidence_ids exists to close.
        available_ids = set(known_evidence_ids or ())
        if input_data:
            available_ids |= _collect_research_evidence_ids(input_data)
        missing = [eid for eid in evidence_used if eid not in available_ids]
        if missing:
            issues.append(f"evidence_used references unknown evidence id(s): {', '.join(missing)}")

    if output.get("recommendation") and not output.get("assumptions") and not evidence_used:
        issues.append("Recommendation given with no stated assumptions and no cited evidence.")

    check_issues, verdict_override = _check_comparison_readiness(output, input_data)
    issues.extend(check_issues)

    return EvidenceCheckResult(
        issues=issues,
        unsupported_claims=unsupported,
        needs_review=bool(issues or unsupported),
        verdict_override=verdict_override,
    )


# Winner/validated-recommendation language that must never appear
# unqualified when comparison_ready=false (Phase 12). Matched against the
# recommendation text lowercased.
_WINNER_LANGUAGE_MARKERS = ("strongest", "winner", "best opportunity", "pursue", "validated recommendation")
# Any of these present alongside winner language counts as an explicit
# provisional qualification, not an unqualified claim. Deliberately does
# NOT include "insufficient comparable evidence" — that's the overall
# DECISION STATUS marker (checked separately below), not a per-claim
# qualifier; a recommendation can carry that marker AND still assert an
# unqualified winner claim elsewhere in the same text.
_PROVISIONAL_MARKERS = ("provisional", "preliminary", "not yet validated")


def _has_unqualified_winner_language(text: str) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _WINNER_LANGUAGE_MARKERS) and not any(
        marker in lowered for marker in _PROVISIONAL_MARKERS
    )


def _check_comparison_readiness(output: dict, input_data: dict | None) -> tuple[list[str], str | None]:
    """Candidate Completeness Gate QA readiness contract (v0.1.2/v0.1.2.2).

    Independently verifies comparison readiness against what Strategy's
    output claims — a model cannot bypass the gate simply by writing
    `comparison_ready: true` or a confident recommendation, because
    app/agents/strategy.py already enforces this deterministically and
    this check verifies that enforcement held.

    Also implements the QA READINESS CONTRACT (Phase 10/12): when
    comparison_ready=false, QA must not penalize Strategy merely for
    refusing to declare a winner — "PASS" there means "correctly handled
    insufficient evidence," not "business opportunity validated." A
    Strategy response that correctly refuses (carries the required marker
    and names what's missing, with no unqualified winner language) gets a
    deterministic verdict_override of "PASS", overriding even an
    over-punitive model QA verdict. Conversely, an unqualified winner claim
    despite comparison_ready=false forces at least "NEEDS_REVIEW".

    Prefers the AUTHORITATIVE readiness the evaluator precomputed from the
    full, pre-compaction research_results (app/orchestration/evaluator.py) —
    the SAME value Strategy itself used — over recomputing from
    `input_data["research_results"]`, which may be the bounded/compacted
    prompt view. Only recomputes as a fallback for direct calls that bypass
    the evaluator. See app/research_intelligence/gate.py and
    docs/research_intelligence.md, "Issue 2".

    v0.1.2.3 fix: the STANDALONE final "qa" task (reviewing an already-
    completed Strategy task's output — see
    app/orchestration/executor.py::AgentExecutor._build_input's qa branch)
    never receives `research_results`/`comparison_readiness` in its
    input_data at all, which used to make this whole readiness contract a
    no-op for exactly that call path — the very case it matters most for.
    Strategy's own `output["comparison_ready"]` is ALREADY the
    deterministic, authoritative value (app/agents/strategy.py sets it
    unconditionally, never left to the model) — trusted directly as a
    last-resort fallback so the contract still applies there."""
    if not input_data and "comparison_ready" not in output:
        return [], None
    precomputed = (input_data or {}).get("comparison_readiness")
    if precomputed is not None:
        expected_ready = bool(precomputed.get("ready"))
    elif input_data and "research_results" in input_data:
        expected_ready = evaluate_comparison_readiness(
            input_data["research_results"], settings=get_settings()
        ).ready
    elif "comparison_ready" in output:
        expected_ready = bool(output.get("comparison_ready"))
    else:
        return [], None

    issues: list[str] = []
    verdict_override: str | None = None
    claimed_ready = output.get("comparison_ready")
    if claimed_ready is not None and bool(claimed_ready) != expected_ready:
        issues.append(
            "comparison_ready does not match the deterministic Candidate Completeness Gate "
            f"recomputed from the research results (expected {expected_ready}, got {claimed_ready})."
        )

    if not expected_ready:
        recommendation_text = output.get("recommendation") or ""
        has_marker = "INSUFFICIENT COMPARABLE EVIDENCE" in recommendation_text.upper()
        unqualified_winner = _has_unqualified_winner_language(recommendation_text)
        if not has_marker:
            issues.append(
                "Strategy recommended/ranked a candidate despite incomplete, non-comparable "
                "evidence across candidates (comparison not ready)."
            )
            verdict_override = "NEEDS_REVIEW"
        elif unqualified_winner:
            issues.append(
                "Strategy's recommendation mixes an insufficient-evidence disclaimer with "
                "unqualified winner/validated language despite comparison_ready=false."
            )
            verdict_override = "NEEDS_REVIEW"
        elif bool(output.get("missing_requirements")) or "MISSING INFORMATION" in recommendation_text.upper():
            # Correctly refused: has the marker, names what's missing, and
            # makes no unqualified winner claim — QA must not penalize this.
            verdict_override = "PASS"

    return issues, verdict_override


def _find_unbacked_quantitative_claims(text: str) -> list[str]:
    flagged = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        lowered = sentence.lower()
        if any(term in lowered for term in _QUANT_TERMS) and re.search(r"\d", sentence):
            flagged.append(sentence.strip())
    return flagged


def _collect_research_evidence_ids(input_data: dict) -> set[str]:
    ids: set[str] = set()
    for r in input_data.get("research_results", []) or []:
        for e in r.get("evidence", []) or []:
            eid = e.get("id")
            if eid:
                ids.add(eid)
    return ids


def _collect_research_evidence_by_id(input_data: dict) -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for r in input_data.get("research_results", []) or []:
        for e in r.get("evidence", []) or []:
            eid = e.get("id")
            if eid:
                by_id[eid] = e
    return by_id


def _parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
