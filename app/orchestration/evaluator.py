"""QA evaluator loop: Worker -> Output -> QA -> PASS/FAIL/NEEDS_REVIEW, with a
bounded retry budget (MAX_AGENT_RETRIES). Never loops forever.

Also runs the deterministic evidence-quality checks
(app/security/evidence_qa.py) against every worker output and merges them
into the QA verdict, captures per-attempt model usage (app/agents/usage.py)
so retries are individually accounted for, and — for research-shaped outputs
only (anything with an `.evidence` attribute) — accumulates evidence across
retries and tracks structured EvidenceGaps so a retry's follow-up queries
target what's actually missing instead of repeating the original broad
query. See app/agents/research.py::ResearchAgent._build_queries for the
other half of that loop.

If `worker_agent.run()`/`qa_agent.run()` raises (e.g. a structured-output
parse failure — see app/agents/providers.py::ModelOutputParsingError), usage
and evidence gathered by every PRIOR successful attempt in this loop — plus
whatever the failing attempt itself recorded before failing — must not be
silently discarded just because the task is about to fail. See
WorkerExecutionError below and app/orchestration/executor.py's handling of it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from app.agents.qa_context import compact_qa_context
from app.agents.strategy_context import compact_research_results
from app.agents.usage import ModelUsage, collect_request_diagnostics, collect_usage
from app.config.settings import get_settings
from app.database.repositories import UsageTotals
from app.orchestration.budget import check_budget, reserved_totals
from app.research_intelligence.gate import evaluate_comparison_readiness
from app.research_intelligence.prompt_diagnostics import format_diagnostic_summary
from app.schemas.agents import QAVerdict
from app.schemas.evidence import EvidenceGap, EvidenceItem, merge_evidence_items
from app.security.evidence_qa import evaluate_evidence, merge_into_verdict
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class EvaluationResult:
    output: BaseModel
    verdict: QAVerdict
    attempts_used: int
    usage_events: list[ModelUsage] = field(default_factory=list)
    # The FULL accumulated evidence across every attempt, never capped —
    # `output.evidence` (above) is capped to research_max_evidence_items for
    # what gets reported/prompted with; this is what persistence should use
    # instead so the evidence store never loses anything to that cap. Empty
    # for non-research outputs.
    accumulated_evidence: list[EvidenceItem] = field(default_factory=list)
    # Set when a retry was skipped specifically because starting it would
    # have exceeded the mission budget (distinct from exhausting
    # max_retries, and distinct from a task FAILURE) — see
    # app/orchestration/executor.py, which propagates this up to
    # run_objective so the mission stops with STOPPED_BUDGET_LIMIT.
    budget_stopped_reason: str | None = None


class WorkerExecutionError(Exception):
    """Raised instead of letting a worker/QA exception propagate raw — carries
    whatever usage and evidence were already gathered (this attempt's partial
    contribution plus every prior attempt's) so the caller can still account
    for and persist them even though the task itself is about to fail. See
    app/orchestration/executor.py's exception handling."""

    def __init__(
        self,
        *,
        cause: BaseException,
        usage_events: list[ModelUsage],
        accumulated_evidence: list[EvidenceItem],
        attempts_used: int,
    ):
        super().__init__(str(cause))
        self.cause = cause
        self.usage_events = usage_events
        self.accumulated_evidence = accumulated_evidence
        self.attempts_used = attempts_used


async def run_worker_with_qa(
    *,
    worker_agent,
    qa_agent,
    title: str,
    description: str,
    input_data: dict,
    success_criteria: str | None,
    max_retries: int,
    known_evidence_ids: set[str] | None = None,
    mission_usage: UsageTotals | None = None,
) -> EvaluationResult:
    feedback: str | None = None
    attempt = 0
    output: BaseModel
    verdict: QAVerdict
    usage_events: list[ModelUsage] = []
    accumulated_evidence: list[EvidenceItem] = []
    accumulated_gaps: dict[str, EvidenceGap] = {}
    settings = get_settings()
    # VALIDATION-mode research output carries evidence for multiple
    # candidates at once (see app/agents/research.py::_run_validation) — a
    # single-candidate cap would prematurely truncate the authoritative
    # source the Candidate Completeness Gate reads from (see
    # research_max_validation_evidence_items / docs/research_intelligence.md).
    max_evidence_items = (
        settings.research_max_validation_evidence_items
        if input_data.get("research_mode") == "VALIDATION"
        else settings.research_max_evidence_items
    )
    previous_output: BaseModel | None = None
    previous_score: float | None = None
    budget_stopped_reason: str | None = None

    # Candidate Completeness Gate — computed ONCE, from the FULL,
    # pre-compaction `input_data["research_results"]` (each dependency
    # research task's own persisted output), never from the bounded view
    # compact_research_results() builds for the model prompt below. This is
    # the authoritative source: AUTHORITATIVE EVIDENCE -> GATE, separately
    # from AUTHORITATIVE EVIDENCE -> COMPACTOR -> model. Injected into every
    # retry attempt's run_input so it survives compaction untouched — see
    # docs/research_intelligence.md, "Issue 2".
    precomputed_readiness: dict | None = None
    if "research_results" in input_data:
        precomputed_readiness = evaluate_comparison_readiness(
            input_data["research_results"], settings=settings
        ).model_dump(mode="json")

    while True:
        run_input = dict(input_data)
        # Evidence provenance (v0.1.2.3): lets a research worker stamp
        # every EvidenceItem it gathers THIS attempt with the attempt
        # number — see app/schemas/evidence.py::EvidenceItem.attempt_number.
        run_input["attempt_number"] = attempt
        if feedback:
            run_input["qa_feedback"] = feedback
        unresolved_gaps = [g for g in accumulated_gaps.values() if not g.resolved]
        if unresolved_gaps:
            run_input["evidence_gaps"] = [g.model_dump(mode="json") for g in unresolved_gaps]

        compacted_ids: set[str] | None = None
        if "research_results" in input_data:
            previous_dump = previous_output.model_dump(mode="json") if previous_output is not None else None
            compacted_results, compacted_ids, extra = compact_research_results(
                input_data["research_results"],
                qa_feedback=feedback,
                previous_output=previous_dump,
                settings=settings,
            )
            run_input["research_results"] = compacted_results
            run_input.update(extra)
            run_input["comparison_readiness"] = precomputed_readiness

        gaps_resolved_before = {gt for gt, g in accumulated_gaps.items() if g.resolved}
        evidence_count_before = len(accumulated_evidence)

        # v0.1.2.6 Phase 10: usage is collected in TWO separate blocks
        # (worker, then QA) rather than one shared block, so each
        # ModelUsage event can be tagged with WHICH role actually made the
        # call — see ModelUsage.role. Task-level attribution
        # (UsageService.record_many's agent_type=task.agent_type in
        # app/orchestration/executor.py) is UNCHANGED/intentional: usage
        # is still attributed to the parent task, exactly as before — this
        # only ADDS the finer-grained role alongside it, it never changes
        # existing accounting semantics.
        # `worker_events`/`qa_events`/`worker_diagnostics`/`qa_diagnostics`
        # are bound directly by their `with ... as` clauses below (never
        # copied afterward) — a `with X as name:` binds `name` in this
        # ENCLOSING scope immediately on entry, so it stays valid and
        # already holds whatever was collected so far even if an exception
        # propagates out of the block. Pre-declared here only so a name is
        # always defined even if the exception happens before its own
        # `with` block is ever entered (e.g. qa_events when the WORKER
        # itself raises).
        worker_events: list[ModelUsage] = []
        qa_events: list[ModelUsage] = []
        worker_diagnostics: list = []
        qa_diagnostics: list = []
        try:
            with collect_usage() as worker_events, collect_request_diagnostics() as worker_diagnostics:
                output = await worker_agent.run(
                    title=title, description=description, input_data=run_input, context={}
                )

                new_evidence = getattr(output, "evidence", None)
                if new_evidence:
                    _resolve_gaps(accumulated_gaps, new_evidence)
                    accumulated_evidence = merge_evidence_items(accumulated_evidence, new_evidence)
                    # The worker only ever returns what it gathered THIS
                    # attempt; the persisted/downstream-visible output must
                    # carry the running total (bounded — see
                    # _prioritized_evidence), or a later retry's QA/evidence
                    # checks would see fewer sources than actually exist and
                    # evidence already confirmed valid would be discarded for
                    # no reason. The UNBOUNDED total survives separately via
                    # EvaluationResult.accumulated_evidence.
                    output.evidence = _prioritized_evidence(accumulated_evidence, max_evidence_items)

            # v0.1.2.6 Phase 3: computed ONCE here — this IS the
            # authoritative full dump. evaluate_evidence() below reuses
            # this exact same dict (nothing mutates `output`'s pydantic
            # fields in between except evidence_gaps, reassigned only
            # AFTER evidence_check is computed — see below), never a
            # compacted view. Only qa_view (compact_qa_context) is
            # bounded, and only qa_agent.run() ever sees it.
            full_output_dump = output.model_dump(mode="json")
            qa_view = _qa_facing_view(full_output_dump, settings=settings)

            with collect_usage() as qa_events, collect_request_diagnostics() as qa_diagnostics:
                verdict = await qa_agent.run(
                    title=title,
                    description=description,
                    input_data={
                        "output": qa_view,
                        "success_criteria": success_criteria,
                    },
                    context={},
                )
        except Exception as exc:  # noqa: BLE001 - must never lose prior attempts' usage/evidence
            for event in worker_events:
                event.retry_number = attempt
                event.role = "worker"
            for event in qa_events:
                event.retry_number = attempt
                event.role = "qa"
            usage_events.extend(worker_events)
            usage_events.extend(qa_events)
            _log_request_diagnostics(title=title, attempt=attempt, diagnostics=worker_diagnostics + qa_diagnostics)
            raise WorkerExecutionError(
                cause=exc,
                usage_events=usage_events,
                accumulated_evidence=accumulated_evidence,
                attempts_used=attempt,
            ) from exc

        for event in worker_events:
            event.retry_number = attempt
            event.role = "worker"
        for event in qa_events:
            event.retry_number = attempt
            event.role = "qa"
        usage_events.extend(worker_events)
        usage_events.extend(qa_events)
        # v0.1.2.5 Phase 9/11: v0.1.2.4 built ModelRequestDiagnostic but
        # never wired it into the actual mission-execution path — no
        # caller ever wrapped a real worker/QA call in
        # collect_request_diagnostics(), so no historical diagnostic data
        # exists from the v0.1.2.4 live benchmark. This closes that gap:
        # every attempt's diagnostics are now logged (bounded, secret-free
        # — see format_diagnostic_summary) so the NEXT live run captures
        # them.
        _log_request_diagnostics(title=title, attempt=attempt, diagnostics=worker_diagnostics + qa_diagnostics)

        # Restricted to what was actually shown to the worker THIS attempt
        # (run_input, not the stale original input_data) — and, once
        # compaction applied, to exactly the compacted/visible evidence ids
        # rather than the broader project-wide known_evidence_ids, so a
        # real-but-compacted-out id can't accidentally validate. See
        # app/agents/strategy_context.py.
        # Phase 3 architecture invariant: the deterministic evidence check
        # ALWAYS uses full_output_dump — the complete, authoritative worker
        # output — never qa_view. Only the LLM QA prompt above was
        # compacted.
        evidence_check = evaluate_evidence(
            full_output_dump,
            input_data=run_input,
            known_evidence_ids=(None if compacted_ids is not None else known_evidence_ids),
        )
        model_verdict, model_score = verdict.verdict, verdict.score
        verdict = merge_into_verdict(verdict, evidence_check)
        # v0.1.2.5 Phase 7 fix: the WORKER's own gaps (e.g.
        # app/agents/research.py::_run_validation's per-(candidate,
        # requirement_category) cell gaps — richer than evidence_qa.py's
        # generic, candidate-agnostic text-mining gaps) must be merged in
        # too, and merged BEFORE they get overwritten below. Before this
        # fix, only evidence_check.gaps (never candidate-scoped) fed
        # accumulated_gaps, so output.evidence_gaps got unconditionally
        # replaced with that flat set — silently discarding research.py's
        # own richer signal every attempt. See _merge_gaps's (candidate_id,
        # gap_type) keying below, which is what stops candidate B's gap
        # from overwriting candidate A's in the same gap_type.
        worker_gaps = list(getattr(output, "evidence_gaps", None) or [])
        _merge_gaps(accumulated_gaps, worker_gaps)
        _merge_gaps(accumulated_gaps, evidence_check.gaps)
        if hasattr(output, "evidence_gaps"):
            output.evidence_gaps = list(accumulated_gaps.values())

        if verdict.verdict != model_verdict:
            # Visibility fix (v0.1.2.4): app/agents/qa.py's own
            # "qa_agent_completed" log line reports the MODEL's raw
            # verdict, logged BEFORE this deterministic merge runs — a log
            # reader seeing "PASS" there and a retry happening anyway was
            # genuinely confusing (see Defect 2). This makes the override
            # explicit at the point it actually happens.
            logger.info(
                "worker_qa_verdict_overridden_by_evidence_check",
                title=title,
                attempt=attempt,
                model_verdict=model_verdict,
                model_score=model_score,
                final_verdict=verdict.verdict,
                final_score=verdict.score,
                issues=evidence_check.issues,
            )

        if verdict.verdict == "PASS" or attempt >= max_retries:
            break

        # Research-shaped retries only (see _HIGH_PRIORITY_GAP_TYPES/
        # retry_has_expected_value below): once at least one prior attempt's
        # score is known AND there's an active, structured gap signal to
        # judge against, a retry that added nothing of value is skipped
        # rather than blindly consuming another attempt. Never applied to
        # the very first retry (always given a chance) or to workers with no
        # gap-tracking at all (nothing to conservatively judge "no
        # improvement" against).
        is_research_shaped = hasattr(output, "evidence") and hasattr(output, "evidence_gaps")
        if is_research_shaped and previous_score is not None and accumulated_gaps:
            newly_resolved = [
                g for g in accumulated_gaps.values() if g.resolved and g.gap_type not in gaps_resolved_before
            ]
            new_evidence_this_attempt = accumulated_evidence[evidence_count_before:]
            if not retry_has_expected_value(
                previous_score=previous_score,
                current_score=verdict.score,
                gaps_resolved_this_attempt=newly_resolved,
                new_evidence=new_evidence_this_attempt,
            ):
                break

        if mission_usage is not None:
            in_flight_tokens = sum(
                e.total_tokens or ((e.input_tokens or 0) + (e.output_tokens or 0)) for e in usage_events
            )
            projected = reserved_totals(
                mission_usage,
                in_flight_calls=len(usage_events),
                in_flight_tokens=in_flight_tokens,
                settings=settings,
            )
            reason = check_budget(totals=projected, daily_cost_usd=None, settings=settings)
            if reason:
                budget_stopped_reason = reason
                break

        feedback = verdict.feedback
        previous_output = output
        previous_score = verdict.score
        attempt += 1

    return EvaluationResult(
        output=output,
        verdict=verdict,
        attempts_used=attempt,
        usage_events=usage_events,
        accumulated_evidence=accumulated_evidence,
        budget_stopped_reason=budget_stopped_reason,
    )


def _qa_facing_view(output: dict, *, settings) -> dict:
    """v0.1.2.6 Phase 3: dispatches on shape exactly like
    app/security/evidence_qa.py::evaluate_evidence does — only a
    RESEARCH-shaped output (findings + question) goes through the QA
    Context Compactor. A Strategy/Execution output has no large `evidence`
    list to bound in the first place (StrategyOutput carries evidence_used
    ids, not full items) and needs its OWN fields (recommendation,
    reasoning, options_considered, comparison_ready, ...) untouched — a
    Research-shaped compactor would silently drop them. Anything else
    (execution, qa) is passed through unchanged, exactly as before this
    checkpoint."""
    if "findings" in output and "question" in output:
        return compact_qa_context(output, settings=settings)
    return output


def _log_request_diagnostics(*, title: str, attempt: int, diagnostics: list) -> None:
    """v0.1.2.5 Phase 9/11: logs the bounded, secret-free diagnostic
    summary for this attempt's provider call(s) — see
    app/research_intelligence/prompt_diagnostics.py::format_diagnostic_summary
    and app/agents/usage.py::collect_request_diagnostics. Only the
    AnthropicProvider populates these (see app/agents/providers.py); other
    providers simply produce an empty list, which format_diagnostic_summary
    renders as an explicit "no diagnostics recorded" line rather than
    silently saying nothing."""
    if not diagnostics:
        return
    logger.info(
        "research_request_diagnostics",
        title=title,
        attempt=attempt,
        summary=format_diagnostic_summary(diagnostics, title=title),
    )


def retry_has_expected_value(
    *,
    previous_score: float,
    current_score: float,
    gaps_resolved_this_attempt: list[EvidenceGap],
    new_evidence: list[EvidenceItem],
) -> bool:
    """Conservative diminishing-returns policy for research retries: was the
    attempt that just finished worth what it cost? A retry is judged
    worthwhile (True) if ANY of these hold:

    - the QA score materially improved over the previous attempt,
    - a high-priority evidence gap (market_size/growth_rate/pricing/
      financial — see _STRONG_EVIDENCE_REQUIRED_GAP_TYPES) was newly
      resolved this attempt,
    - materially stronger evidence (PAGE_EXTRACT depth, or
      AUTHORITATIVE/PRIMARY quality) was added this attempt.

    Only returns False — i.e. only recommends stopping — when the score did
    NOT improve AND no high-priority gap was resolved AND nothing stronger
    was added: a score merely staying equal is never enough on its own (see
    module docstring / Phase 4 requirements)."""
    if current_score > previous_score:
        return True
    # Reuses the same "high-priority" gap classification as the
    # quantitative-gap-resolution rule below (market_size/growth_rate/
    # pricing/financial) — resolving one of these justifies a further retry
    # even when the raw QA score hasn't moved yet.
    if any(g.gap_type in _STRONG_EVIDENCE_REQUIRED_GAP_TYPES for g in gaps_resolved_this_attempt):
        return True
    if any(
        e.evidence_depth == "PAGE_EXTRACT" or e.source_quality in ("AUTHORITATIVE", "PRIMARY")
        for e in new_evidence
    ):
        return True
    return False


def _prioritized_evidence(evidence: list[EvidenceItem], max_items: int) -> list[EvidenceItem]:
    """Bounds what's reported in the final structured output/prompted to
    downstream tasks — PAGE_EXTRACT and AUTHORITATIVE-quality items first
    (most recently merged items win ties, since those were the ones a retry
    specifically went and got). Never applied to what gets persisted — see
    EvaluationResult.accumulated_evidence."""
    if len(evidence) <= max_items:
        return evidence
    ranked = sorted(
        reversed(evidence),
        key=lambda e: (
            0 if e.evidence_depth == "PAGE_EXTRACT" else 1,
            0 if e.source_quality == "AUTHORITATIVE" else 1,
        ),
    )
    return ranked[:max_items]


# Quantitative gaps are the ones most likely to be wrong if "resolved" just
# means "a search result came back" — a market-size or pricing figure needs
# real source material, not a listicle snippet that happens to mention the
# word. Everything else keeps the weaker (snippet-suffices) rule.
_STRONG_EVIDENCE_REQUIRED_GAP_TYPES = frozenset({"market_size", "growth_rate", "pricing", "financial"})


def _resolve_gaps(gaps: dict[str, EvidenceGap], new_evidence: list[EvidenceItem]) -> None:
    """A gap is resolved deterministically — by a follow-up query that
    targeted it actually returning something — never by the model simply
    stopping to mention it, so resolution can't be faked by a vaguer retry.
    For quantitative gap types, a matching search snippet alone is not
    enough — keyword presence in a snippet doesn't establish the figure is
    correct, so those require at least one PAGE_EXTRACT match (see
    app/agents/research.py::_maybe_upgrade_with_fetch)."""
    for gap in gaps.values():
        if gap.resolved or not gap.suggested_query:
            continue
        matches = [e for e in new_evidence if e.query_used == gap.suggested_query]
        if not matches:
            continue
        if gap.gap_type in _STRONG_EVIDENCE_REQUIRED_GAP_TYPES:
            matches = [e for e in matches if e.evidence_depth == "PAGE_EXTRACT"]
            if not matches:
                continue  # evidence was found but isn't strong enough yet
        gap.resolved = True
        gap.supporting_evidence_ids = [e.id for e in matches]


def _gap_key(gap: EvidenceGap) -> str:
    """v0.1.2.5 Phase 7 fix: keyed by (candidate_id, gap_type), not
    gap_type alone. Before this fix, a VALIDATION-mode mission with three
    candidates all needing "pricing" evidence collapsed into ONE
    accumulated "pricing" gap total — Candidate B's own per-cell gap
    (see app/agents/research.py::_validation_gaps) silently overwrote
    Candidate A's every attempt, so at most one candidate's pricing cell
    could ever get a targeted retry query, no matter how many candidates
    actually needed one. candidate_id is None for evidence_qa.py's own
    generic, candidate-agnostic gaps (GENERAL mode, or the
    insufficient_evidence text-mining check) — those keep colliding on
    gap_type alone exactly as before, which is correct: there is only one
    candidate in that context."""
    return f"{gap.candidate_id or ''}::{gap.gap_type}"


def _merge_gaps(gaps: dict[str, EvidenceGap], new_gaps: list[EvidenceGap]) -> None:
    """Keyed by (candidate_id, gap_type) — see _gap_key — so re-detecting
    "still missing competitor evidence for Candidate A" across attempts
    updates the SAME gap rather than piling up duplicates, while
    Candidate B's own competitor gap is tracked independently. A gap
    already resolved this run is never reopened."""
    for gap in new_gaps:
        key = _gap_key(gap)
        existing = gaps.get(key)
        if existing is None:
            gaps[key] = gap
        elif not existing.resolved:
            existing.claim_or_question = gap.claim_or_question
            existing.related_claim = gap.related_claim
            existing.suggested_query = gap.suggested_query or existing.suggested_query
            existing.requirement_category = gap.requirement_category or existing.requirement_category
