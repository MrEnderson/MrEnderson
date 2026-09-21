"""v0.1.2.5 Phase 14: locks in the v0.1.2.4 Discovery fix against this
checkpoint's changes. DISCOVERY + model QA PASS must still -> final PASS
-> no evidence-gap retry, even now that _gather_evidence runs a
pre-screen step and _run_discovery computes candidate concepts for it.
Offline — fake providers, no network call."""
from __future__ import annotations

from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, ResearchOutput


class _OneShotPassDiscoveryWorker:
    def __init__(self):
        self.calls = 0

    async def run(self, *, title, description, input_data, context):
        self.calls += 1
        return ResearchOutput(
            question=title,
            findings=[],
            insufficient_evidence=False,
            summary="Identified 3 candidate opportunities.",
            research_mode="DISCOVERY",
        )


class _OneShotPassQA:
    def __init__(self):
        self.calls = 0

    async def run(self, **kwargs):
        self.calls += 1
        return QAVerdict(verdict="PASS", score=0.88, feedback="Looks good.")


async def test_discovery_first_attempt_pass_still_terminates_immediately_v0125():
    worker = _OneShotPassDiscoveryWorker()
    qa = _OneShotPassQA()
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=qa, title="Discover candidate opportunities", description="",
        input_data={"research_mode": "DISCOVERY"}, success_criteria=None, max_retries=2,
    )
    assert worker.calls == 1
    assert qa.calls == 1
    assert result.verdict.verdict == "PASS"
    assert result.attempts_used == 0
    # The requirement-driven validation machinery (per-cell gap merging,
    # query planning) must never fire for DISCOVERY — no evidence_gaps at
    # all should have accumulated.
    assert not result.output.evidence_gaps
