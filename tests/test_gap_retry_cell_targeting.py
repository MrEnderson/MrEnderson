"""v0.1.2.5 Phase 7: a gap retry must target one (candidate_id,
requirement_category) cell, never a cross-candidate/general query.

Root cause found this checkpoint: app/orchestration/evaluator.py's retry
loop unconditionally overwrote `output.evidence_gaps` (research.py's own
freshly-computed, per-cell gaps — see ResearchAgent._validation_gaps) with
`accumulated_gaps`, which was populated ONLY from evidence_qa.py's generic,
candidate-agnostic gap detector, keyed by gap_type ALONE. With three
candidates all needing e.g. "pricing" evidence, that single flat key meant
Candidate B's own gap silently overwrote Candidate A's on every attempt —
at most one candidate's pricing cell could ever receive a targeted retry
query, however many candidates actually needed one. Fixed by (1) merging
the worker's own evidence_gaps into accumulated_gaps too, and (2) keying
_merge_gaps by (candidate_id, gap_type) instead of gap_type alone. Offline
— no network call.
"""
from __future__ import annotations

from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, ResearchOutput
from app.schemas.evidence import EvidenceGap


class _MultiCandidateGapWorker:
    """Every attempt, reports a DISTINCT per-candidate pricing gap — exactly
    what app/agents/research.py::_validation_gaps produces for a real
    multi-candidate VALIDATION mission."""

    def __init__(self):
        self.calls = 0
        self.queries_seen: list[str] = []

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        for gap in input_data.get("evidence_gaps") or []:
            if gap.get("suggested_query"):
                self.queries_seen.append(gap["suggested_query"])
        return ResearchOutput(
            question="Validate candidates",
            findings=[],
            insufficient_evidence=False,
            summary="s",
            research_mode="VALIDATION",
            evidence_gaps=[
                EvidenceGap(
                    claim_or_question="Missing pricing evidence for Candidate A",
                    gap_type="pricing",
                    candidate_id="candidate-a",
                    requirement_category="pricing",
                    importance=5,
                    suggested_query="Candidate A concept pricing competitors",
                ),
                EvidenceGap(
                    claim_or_question="Missing pricing evidence for Candidate B",
                    gap_type="pricing",
                    candidate_id="candidate-b",
                    requirement_category="pricing",
                    importance=5,
                    suggested_query="Candidate B concept pricing competitors",
                ),
                EvidenceGap(
                    claim_or_question="Missing market_size evidence for Candidate A",
                    gap_type="market_size",
                    candidate_id="candidate-a",
                    requirement_category="market_size",
                    importance=3,
                    suggested_query="Candidate A concept market size",
                ),
            ],
        )


class _EventualPassQA:
    def __init__(self, pass_at: int):
        self.calls = 0
        self.pass_at = pass_at

    async def run(self, **kwargs):
        self.calls += 1
        passed = self.calls >= self.pass_at
        return QAVerdict(verdict="PASS" if passed else "NEEDS_REVIEW", score=0.9 if passed else 0.4, feedback="ok")


async def test_gap_retry_preserves_every_candidates_own_cell_in_the_same_category():
    """Both Candidate A's and Candidate B's pricing gaps must survive in
    the accumulated set — neither silently overwrites the other just
    because they share gap_type='pricing'."""
    worker = _MultiCandidateGapWorker()
    result = await run_worker_with_qa(
        worker_agent=worker,
        qa_agent=_EventualPassQA(pass_at=2),
        title="Validate candidates",
        description="",
        input_data={"research_mode": "VALIDATION"},
        success_criteria=None,
        max_retries=3,
    )
    pricing_gaps = [g for g in result.output.evidence_gaps if g.gap_type == "pricing"]
    candidate_ids = {g.candidate_id for g in pricing_gaps}
    assert candidate_ids == {"candidate-a", "candidate-b"}, (
        f"expected both candidates' pricing gaps to survive, got: {candidate_ids}"
    )
    # Each gap keeps ITS OWN suggested_query — proves candidate A's query
    # never became candidate B's (or a generic cross-candidate one).
    by_candidate = {g.candidate_id: g.suggested_query for g in pricing_gaps}
    assert by_candidate["candidate-a"] == "Candidate A concept pricing competitors"
    assert by_candidate["candidate-b"] == "Candidate B concept pricing competitors"


async def test_retry_query_sent_to_worker_identifies_a_single_cell():
    """The query the WORKER actually receives on retry (via
    input_data['evidence_gaps']) must be one of the distinct per-cell
    queries — never a generic 'validate candidates pricing' string, and
    never one candidate's query silently replaced by another's."""
    worker = _MultiCandidateGapWorker()
    await run_worker_with_qa(
        worker_agent=worker,
        qa_agent=_EventualPassQA(pass_at=2),
        title="Validate candidates",
        description="",
        input_data={"research_mode": "VALIDATION"},
        success_criteria=None,
        max_retries=3,
    )
    # queries_seen is populated from input_data on the SECOND call (the
    # retry) — the first call has no accumulated gaps yet.
    assert worker.queries_seen, "retry never received any gap-targeted query"
    for query in worker.queries_seen:
        assert query in (
            "Candidate A concept pricing competitors",
            "Candidate B concept pricing competitors",
            "Candidate A concept market size",
        )
        assert "validate candidates" not in query.lower()


async def test_candidate_a_gap_never_silently_becomes_candidate_b_gap_across_many_attempts():
    """Runs several retry cycles and confirms candidate identity on each
    gap never drifts — a regression guard for the exact collision bug."""
    worker = _MultiCandidateGapWorker()
    result = await run_worker_with_qa(
        worker_agent=worker,
        qa_agent=_EventualPassQA(pass_at=4),
        title="Validate candidates",
        description="",
        input_data={"research_mode": "VALIDATION"},
        success_criteria=None,
        max_retries=5,
    )
    pricing_gaps = {g.candidate_id: g for g in result.output.evidence_gaps if g.gap_type == "pricing"}
    assert pricing_gaps["candidate-a"].suggested_query == "Candidate A concept pricing competitors"
    assert pricing_gaps["candidate-b"].suggested_query == "Candidate B concept pricing competitors"
