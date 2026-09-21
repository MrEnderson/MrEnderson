"""Phase 2 regression tests: QA PASS must be terminal. Traced in code
(app/orchestration/evaluator.py::run_worker_with_qa) — the retry loop already
breaks immediately on the first PASS verdict, before this patch; these tests
lock that behavior in so it can't silently regress. All offline, deterministic
stub agents — no network, no live API key."""
from __future__ import annotations

from app.agents.usage import ModelUsage, record_usage
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import ExecutionOutput, QAVerdict


class _CountingWorker:
    def __init__(self):
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        record_usage(ModelUsage(provider="mock", model="m", api_calls=1))
        return ExecutionOutput(actions_performed=[f"attempt {self.calls}"])


class _ScriptedQA:
    """Returns verdicts in order; asserts it is never called more times than
    the script provides — a call beyond the script means PASS failed to stop
    the loop."""

    def __init__(self, verdicts: list[tuple[str, float]]):
        self._verdicts = verdicts
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        assert self.calls < len(self._verdicts), "QA called more times than PASS should have allowed"
        verdict, score = self._verdicts[self.calls]
        self.calls += 1
        return QAVerdict(verdict=verdict, score=score, feedback=f"verdict {self.calls}")


async def test_pass_on_attempt_one_means_exactly_one_worker_attempt():
    worker = _CountingWorker()
    qa = _ScriptedQA([("PASS", 0.9)])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=3,
    )

    assert worker.calls == 1
    assert qa.calls == 1
    assert result.attempts_used == 0
    assert result.verdict.verdict == "PASS"


async def test_pass_on_attempt_two_means_exactly_two_worker_attempts():
    worker = _CountingWorker()
    qa = _ScriptedQA([("NEEDS_REVIEW", 0.5), ("PASS", 0.9)])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=3,
    )

    assert worker.calls == 2
    assert qa.calls == 2
    assert result.attempts_used == 1
    assert result.verdict.verdict == "PASS"


async def test_pass_result_cannot_be_overwritten_by_a_later_needs_review():
    """The QA stub has a NEEDS_REVIEW queued right after the PASS — if the
    loop ever called the worker/QA again after a PASS, that NEEDS_REVIEW
    would be consumed and this test would fail on the assert inside
    _ScriptedQA (or the final verdict would flip)."""
    worker = _CountingWorker()
    qa = _ScriptedQA([("PASS", 0.9), ("NEEDS_REVIEW", 0.3)])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=3,
    )

    assert worker.calls == 1
    assert qa.calls == 1
    assert result.verdict.verdict == "PASS"
    assert result.verdict.score == 0.9


async def test_fail_and_needs_review_still_retry_within_configured_limits():
    worker = _CountingWorker()
    qa = _ScriptedQA([("FAIL", 0.2), ("NEEDS_REVIEW", 0.4), ("PASS", 0.9)])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=3,
    )

    assert worker.calls == 3
    assert result.attempts_used == 2
    assert result.verdict.verdict == "PASS"


async def test_usage_reflects_only_calls_actually_made():
    worker = _CountingWorker()
    qa = _ScriptedQA([("NEEDS_REVIEW", 0.5), ("PASS", 0.9)])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=3,
    )

    # One ModelUsage event per worker call (QA calls don't go through
    # record_usage in this stub) — exactly matching worker.calls, never more.
    assert len(result.usage_events) == worker.calls == 2
    assert [e.retry_number for e in result.usage_events] == [0, 1]


async def test_retry_count_matches_attempts_used_not_total_calls():
    worker = _CountingWorker()
    qa = _ScriptedQA([("FAIL", 0.2), ("PASS", 0.9)])

    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="t", description="", input_data={},
        success_criteria=None, max_retries=3,
    )

    # attempts_used counts RETRIES (0 = passed first try), not total calls.
    assert result.attempts_used == 1
    assert worker.calls == 2
