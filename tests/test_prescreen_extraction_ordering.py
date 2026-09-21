"""v0.1.2.5 Phase 6: the pre-extraction admission screen.

    SEARCH RESULT -> PRE-SCREEN -> optional PAGE_EXTRACT -> EvidenceItem
        -> ADMISSION GATE -> authoritative evidence

Pre-screen runs BEFORE a SearchResult ever becomes an EvidenceItem —
so a pre-screen-rejected result can structurally never reach PAGE_EXTRACT
(app/agents/research.py::ResearchAgent._maybe_upgrade_with_fetch only ever
sees EvidenceItems). Offline — the ResearchProvider is a fake; no network
call.
"""
from __future__ import annotations

from app.agents.research import ResearchAgent
from app.config.settings import get_settings
from app.database.models import PermissionLevel
from app.schemas.agents import AgentDescriptor
from app.schemas.research_dto import GeneralResearchModelOutput
from app.tools.research_tools import SearchResult


def _agent(research_provider) -> ResearchAgent:
    class _Model:
        name = "stub"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            return GeneralResearchModelOutput(summary="s")

    descriptor = AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )
    return ResearchAgent(descriptor=descriptor, provider=_Model(), research_provider=research_provider)


class _FakeProvider:
    """Returns one on-topic and one HR-noise result on every search;
    fetch() records which URLs it was actually asked to extract."""

    name = "fake"
    is_live = True

    def __init__(self):
        self.fetched_urls: list[str] = []

    async def search(self, query, *, max_results=5):
        return [
            SearchResult(
                title="AI Content Creation Tools Pricing Report",
                url="https://www.g2.com/products/ai-content-tool",
                snippet="AI content creation tool pricing plans start at $29/month for small businesses.",
            ),
            SearchResult(
                title="Candidate Experience Statistics and ATS Market Report",
                url="https://www.grandviewresearch.com/candidate-assessment-market",
                snippet="The global candidate assessment and applicant tracking system market size...",
            ),
        ]

    async def fetch(self, url):
        self.fetched_urls.append(url)
        return "Fetched page content about AI content creation tool pricing plans." * 5

    async def extract(self, content, question):
        raise NotImplementedError


async def _run_general_with_gap_retry():
    provider = _FakeProvider()
    agent = _agent(provider)
    result = await agent.run(
        title="AI-Powered Content Creation Tools & Templates",
        description="A marketplace of AI prompt templates and workflow automation for small businesses.",
        input_data={
            "research_mode": "GENERAL",
            "task_id": "task-1",
            "attempt_number": 1,
            # Non-empty evidence_gaps is what makes `targeted=True` in
            # app/agents/research.py, which is what makes extraction
            # (_maybe_upgrade_with_fetch) run at all.
            "evidence_gaps": [{"gap_type": "pricing", "claim_or_question": "Missing pricing evidence", "resolved": False}],
        },
        context={},
    )
    return provider, result


# --- 13. pre-screen occurs before extract; 14. rejected result never
# extracted; 15. accepted result can be extracted ---------------------------


async def test_prescreen_rejected_result_is_never_extracted():
    provider, result = await _run_general_with_gap_retry()
    assert not any("grandviewresearch" in url for url in provider.fetched_urls), (
        "the HR/candidate-assessment result must be pre-screen-rejected BEFORE it is ever "
        "eligible for extraction"
    )
    # And it must never even become an EvidenceItem at all.
    assert not any("Candidate Experience Statistics" in (e.source_title or "") for e in result.evidence)


async def test_accepted_result_can_be_extracted():
    provider, result = await _run_general_with_gap_retry()
    assert any("g2.com" in url for url in provider.fetched_urls), (
        "the on-topic result must survive pre-screen and remain eligible for extraction"
    )
    upgraded = [e for e in result.evidence if e.evidence_depth == "PAGE_EXTRACT"]
    assert upgraded, "the on-topic result should have been upgraded to PAGE_EXTRACT"


async def test_prescreen_runs_before_any_extraction_attempt():
    """Structural proof, not just behavioral: pre-screen-rejected results
    never become EvidenceItems, and _maybe_upgrade_with_fetch only ever
    operates on EvidenceItems — so it is IMPOSSIBLE for a pre-screen
    rejection to be preceded by an extraction attempt on that same
    result."""
    provider, result = await _run_general_with_gap_retry()
    # Only one EvidenceItem ever entered the pipeline for extraction
    # purposes (the HR one was filtered before construction).
    assert len(result.evidence) == 1
    assert result.evidence[0].source_url and "g2.com" in result.evidence[0].source_url
