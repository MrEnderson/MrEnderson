"""v0.1.2.6: end-to-end proof that app/orchestration/evaluator.py::
run_worker_with_qa actually wires the QA Context Compactor correctly —
the QA AGENT receives the small, bounded view, while the deterministic
evidence check (app/security/evidence_qa.py::evaluate_evidence) continues
to see the FULL, authoritative worker output. Offline — fake agents, no
network call.
"""
from __future__ import annotations

from app.config.settings import get_settings
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, ResearchOutput
from app.schemas.evidence import EvidenceItem


def _many_evidence_items(n: int) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            claim=f"Claim {i} with substantial supporting detail text repeated for size. " * 3,
            source_url=f"https://www.example-vendor-{i}.com/report",
            excerpt="Long excerpt text repeated for realistic size. " * 10,
            candidate_id="candidate-a",
            requirement_category="pricing",
            relevance_label="HIGH",
            relevance_score=0.8,
            admission_status="ACCEPTED",
            research_mode="VALIDATION",
        )
        for i in range(n)
    ]


class _ManyEvidenceWorker:
    async def run(self, *, title, description, input_data, context):
        return ResearchOutput(
            question=title, findings=[], insufficient_evidence=False, summary="s",
            research_mode="VALIDATION", evidence=_many_evidence_items(20),
        )


class _RecordingQA:
    def __init__(self):
        self.received_outputs: list[dict] = []

    async def run(self, *, title, description, input_data, context):
        self.received_outputs.append(input_data.get("output", {}))
        return QAVerdict(verdict="PASS", score=0.9, feedback="ok")


async def test_qa_agent_receives_the_compacted_view_not_the_full_dump():
    qa = _RecordingQA()
    result = await run_worker_with_qa(
        worker_agent=_ManyEvidenceWorker(), qa_agent=qa, title="t", description="",
        input_data={"research_mode": "VALIDATION"}, success_criteria=None, max_retries=0,
    )
    assert qa.received_outputs
    seen = qa.received_outputs[0]
    settings = get_settings()
    assert len(seen.get("evidence", [])) <= settings.qa_prompt_max_evidence_items
    # The FULL, authoritative evidence still made it to the persisted
    # output / accumulated_evidence — compaction only affected what the
    # QA MODEL prompt saw.
    assert len(result.accumulated_evidence) == 20


class _UnsupportedClaimWorker:
    """Reports a FACT-labeled finding with NO evidence at all — the exact
    shape app/security/evidence_qa.py::_check_research flags
    deterministically, regardless of what the QA model itself says."""

    async def run(self, *, title, description, input_data, context):
        from app.schemas.agents import ResearchFinding

        return ResearchOutput(
            question=title,
            findings=[ResearchFinding(claim="A confident factual claim with no backing.", evidence_type="FACT")],
            insufficient_evidence=False, summary="s", research_mode="GENERAL", evidence=[],
        )


class _AlwaysPassQA:
    async def run(self, **kwargs):
        return QAVerdict(verdict="PASS", score=0.95, feedback="Looks fine to me.")


async def test_deterministic_evidence_check_still_catches_issues_the_compacted_view_might_hide():
    """Even though the QA MODEL says PASS, the deterministic evidence
    check (which must see the FULL output, not qa_view) still catches the
    unsupported FACT claim and downgrades the verdict — proving
    evaluate_evidence is not accidentally operating on the compacted
    view (which would still show this, since findings aren't dropped by
    compaction, but confirms the full pipeline still enforces this
    invariant end-to-end)."""
    result = await run_worker_with_qa(
        worker_agent=_UnsupportedClaimWorker(), qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=0,
    )
    assert result.verdict.verdict != "PASS"
    assert any("FACT" in issue or "evidence" in issue.lower() for issue in result.verdict.issues)
