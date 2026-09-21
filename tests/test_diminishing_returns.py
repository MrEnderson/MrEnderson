"""Phase 4 diminishing-returns retry policy: direct unit tests of
app/orchestration/evaluator.py::retry_has_expected_value, plus an
integration-level "no infinite retry" guard. All offline, deterministic."""
from __future__ import annotations

from app.orchestration.evaluator import retry_has_expected_value
from app.schemas.evidence import EvidenceGap, EvidenceItem


def _gap(gap_type: str) -> EvidenceGap:
    return EvidenceGap(claim_or_question="q", gap_type=gap_type, resolved=True)


def _weak_evidence() -> EvidenceItem:
    return EvidenceItem(claim="c", source_url="https://example.com/a", evidence_depth="SEARCH_SNIPPET", source_quality="UNKNOWN")


def _strong_evidence(*, depth="PAGE_EXTRACT", quality="UNKNOWN") -> EvidenceItem:
    return EvidenceItem(claim="c", source_url="https://example.com/b", evidence_depth=depth, source_quality=quality)


def test_improving_qa_score_permits_retry():
    assert retry_has_expected_value(
        previous_score=0.5, current_score=0.62, gaps_resolved_this_attempt=[], new_evidence=[]
    ) is True


def test_equal_score_alone_does_not_permit_retry():
    assert retry_has_expected_value(
        previous_score=0.62, current_score=0.62, gaps_resolved_this_attempt=[], new_evidence=[]
    ) is False


def test_regressed_score_alone_does_not_permit_retry():
    assert retry_has_expected_value(
        previous_score=0.62, current_score=0.55, gaps_resolved_this_attempt=[], new_evidence=[]
    ) is False


def test_resolved_high_priority_gap_permits_retry_even_with_stagnant_score():
    assert retry_has_expected_value(
        previous_score=0.62,
        current_score=0.62,
        gaps_resolved_this_attempt=[_gap("market_size")],
        new_evidence=[],
    ) is True


def test_resolved_low_priority_gap_does_not_permit_retry_alone():
    assert retry_has_expected_value(
        previous_score=0.62,
        current_score=0.62,
        gaps_resolved_this_attempt=[_gap("competitor")],
        new_evidence=[],
    ) is False


def test_new_page_extract_evidence_permits_retry_even_with_stagnant_score():
    assert retry_has_expected_value(
        previous_score=0.62,
        current_score=0.62,
        gaps_resolved_this_attempt=[],
        new_evidence=[_strong_evidence(depth="PAGE_EXTRACT", quality="UNKNOWN")],
    ) is True


def test_new_authoritative_evidence_permits_retry_even_with_stagnant_score():
    assert retry_has_expected_value(
        previous_score=0.62,
        current_score=0.62,
        gaps_resolved_this_attempt=[],
        new_evidence=[_strong_evidence(depth="SEARCH_SNIPPET", quality="AUTHORITATIVE")],
    ) is True


def test_new_weak_evidence_alone_does_not_permit_retry():
    assert retry_has_expected_value(
        previous_score=0.62,
        current_score=0.62,
        gaps_resolved_this_attempt=[],
        new_evidence=[_weak_evidence()],
    ) is False


def test_no_signal_at_all_stops_retry():
    """The conservative case this policy exists for: nothing improved,
    nothing resolved, nothing stronger added."""
    assert retry_has_expected_value(
        previous_score=0.62, current_score=0.62, gaps_resolved_this_attempt=[], new_evidence=[]
    ) is False


# --- No infinite retry (integration) -----------------------------------------


async def test_no_infinite_retry_even_with_a_very_high_max_retries_ceiling():
    from app.orchestration.evaluator import run_worker_with_qa
    from app.schemas.agents import QAVerdict, ResearchOutput

    class _StagnantWorker:
        def __init__(self):
            self.calls = 0

        async def run(self, *, title, description, input_data, context):
            self.calls += 1
            return ResearchOutput(
                question="t",
                findings=[],
                evidence=[EvidenceItem(claim="c", source_url="https://example.com/same", query_used="t")],
                unsupported_claims=["No named competitors or pricing found."],
                insufficient_evidence=True,
                summary="s",
            )

    class _AlwaysPassQA:
        async def run(self, **kwargs):
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    worker = _StagnantWorker()
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=50,
    )
    # Same evidence/gaps every time (deduped, never resolved) — the
    # diminishing-returns policy stops this long before max_retries=50.
    assert worker.calls <= 3
    assert result.attempts_used <= 2
