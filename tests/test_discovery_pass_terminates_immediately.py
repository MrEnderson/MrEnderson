"""v0.1.2.4 Defect 2: DISCOVERY + QA PASS on the first attempt must
terminate immediately — exactly one Research execution, one Tavily
search, and one QA evaluation, no retry. Root cause of the observed
"PASS retries anyway": DISCOVERY's own honest `insufficient_evidence`
signal (which its system prompt explicitly asks for when it can't find
enough distinct candidates) was feeding the generic keyword-based gap
detector in app/security/evidence_qa.py, manufacturing UNRESOLVABLE gaps
(discovery has no requirement-scoped research to redo) every attempt and
downgrading a correct model PASS to NEEDS_REVIEW until max_agent_retries
was exhausted. Offline."""
from __future__ import annotations

from app.agents.research import ResearchAgent
from app.database.models import PermissionLevel
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import AgentDescriptor, QAVerdict
from app.schemas.research_dto import DiscoveryCandidateProposal, DiscoveryModelOutput
from app.tools.research_tools import SearchResult


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _CountingResearchProvider:
    name = "fake"
    is_live = True

    def __init__(self):
        self.search_calls = 0
        self.extract_calls = 0

    async def search(self, query, *, max_results=5):
        self.search_calls += 1
        return [SearchResult(title="t", url="https://example.com/a", snippet="A digital product idea.")]

    async def fetch(self, url):
        self.extract_calls += 1
        raise NotImplementedError

    async def extract(self, content, question):
        raise NotImplementedError


class _CountingModelProvider:
    """Returns an HONEST DISCOVERY response that sets
    insufficient_evidence=True and mentions pricing/competitor-flavored
    language in open_questions — exactly the shape that used to trigger
    the (now-fixed) unresolvable-gap bug."""

    name = "stub"

    def __init__(self):
        self.calls = 0

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        self.calls += 1
        return DiscoveryModelOutput(
            candidates=[
                DiscoveryCandidateProposal(label="Notion Template Marketplace"),
                DiscoveryCandidateProposal(label="Coda Template Hub"),
                DiscoveryCandidateProposal(label="Airtable Template Pack"),
            ],
            findings=["Identified three candidates."],
            insufficient_evidence=True,  # honest — couldn't fully validate pricing/competitors yet
            open_questions=["What is the competitor pricing landscape for each candidate?"],
            summary="Identified three candidates; pricing/competition still need deeper research.",
        )


class _CountingQAProvider:
    def __init__(self):
        self.calls = 0

    async def run(self, **kwargs):
        self.calls += 1
        return QAVerdict(verdict="PASS", score=0.82, feedback="Three good candidates identified.")


# --- 5/6/7/8. DISCOVERY first-attempt PASS terminates with exactly one ----
#              Research call, one QA call, one Tavily search


async def test_discovery_first_attempt_pass_terminates_immediately():
    research_provider = _CountingResearchProvider()
    model_provider = _CountingModelProvider()
    qa_provider = _CountingQAProvider()

    agent = ResearchAgent(descriptor=_descriptor(), provider=model_provider, research_provider=research_provider)

    result = await run_worker_with_qa(
        worker_agent=agent,
        qa_agent=qa_provider,
        title="Discover candidate digital-product opportunities",
        description="",
        input_data={"research_mode": "DISCOVERY"},
        success_criteria=None,
        max_retries=2,
    )

    # 7. Exactly one Research Anthropic call.
    assert model_provider.calls == 1
    # 8. Exactly one QA evaluation.
    assert qa_provider.calls == 1
    # 6. Exactly one Tavily search (no second search triggered by a retry).
    assert research_provider.search_calls == 1
    # Task completes on the first attempt — no retry.
    assert result.attempts_used == 0
    assert result.verdict.verdict == "PASS"


async def test_discovery_insufficient_evidence_no_longer_manufactures_unresolvable_gaps():
    """Directly proves the root-cause mechanism is disarmed: DISCOVERY's
    own insufficient_evidence=True + gap-keyword-shaped open_questions no
    longer produces structured EvidenceGaps that could drive a pointless
    retry."""
    from app.security.evidence_qa import evaluate_evidence

    output = {
        "question": "q",
        "research_mode": "DISCOVERY",
        "findings": [{"claim": "c", "evidence_type": "ASSUMPTION"}],
        "evidence": [{"id": "e1", "source_url": "https://example.com/a", "claim": "c"}],
        "unsupported_claims": [],
        "open_questions": ["What is the competitor pricing landscape for each candidate?"],
        "assumptions": [],
        "insufficient_evidence": True,
        "summary": "s",
    }
    check = evaluate_evidence(output)
    assert check.gaps == []
    assert not check.needs_review


async def test_general_mode_insufficient_evidence_still_generates_gaps():
    """Contrast case: GENERAL mode's gaps ARE resolvable (a follow-up
    search for "pricing" genuinely can find pricing evidence for a single
    candidate), so gap detection must stay active there — this is not a
    blanket disabling of the mechanism."""
    from app.security.evidence_qa import evaluate_evidence

    output = {
        "question": "q",
        "research_mode": "GENERAL",
        "findings": [{"claim": "c", "evidence_type": "ASSUMPTION"}],
        "evidence": [{"id": "e1", "source_url": "https://example.com/a", "claim": "c"}],
        "unsupported_claims": ["No competitor pricing found."],
        "open_questions": [],
        "assumptions": [],
        "insufficient_evidence": True,
        "summary": "s",
    }
    check = evaluate_evidence(output)
    assert check.gaps  # unchanged behavior for GENERAL
