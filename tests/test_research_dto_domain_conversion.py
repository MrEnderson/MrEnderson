"""Phase 5: despite the smaller model DTOs, the rest of Jarvis must receive
the same rich ResearchOutput downstream code expects. Offline."""
from __future__ import annotations

from app.agents.research import ResearchAgent
from app.database.models import PermissionLevel
from app.research_intelligence.requirements import CORE_COMPARISON_CATEGORIES
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.schemas.research_dto import DiscoveryCandidateProposal, DiscoveryModelOutput, ValidationModelOutput
from app.tools.research_tools import MockResearchProvider, SearchResult


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _DiscoveryProvider:
    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        return DiscoveryModelOutput(
            candidates=[
                DiscoveryCandidateProposal(label="Notion template marketplace", description="d1"),
                DiscoveryCandidateProposal(label="Coda template hub", description="d2"),
                DiscoveryCandidateProposal(label="Airtable template pack", description="d3"),
            ],
            findings=["Three candidates identified."],
            insufficient_evidence=False,
            summary="Identified three candidates.",
        )


class _ValidationProvider:
    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        return ValidationModelOutput(
            findings=["Validation findings."], insufficient_evidence=False, summary="Validated."
        )


class _FixedResearchProvider:
    name = "fake"
    is_live = True

    async def search(self, query, *, max_results=5):
        return [
            SearchResult(
                title="Fixed result",
                url="https://example.com/fixed",
                snippet=f"Notion template marketplace fixed evidence snippet for query: {query}.",
            )
        ]

    async def fetch(self, url):
        raise NotImplementedError

    async def extract(self, content, question):
        raise NotImplementedError


# --- 12. Compact Discovery result converts to rich ResearchOutput ---------


async def test_discovery_compact_result_converts_to_rich_research_output():
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_DiscoveryProvider(), research_provider=MockResearchProvider()
    )
    result = await agent.run(
        title="Find three potential digital-product opportunities",
        description="",
        input_data={"research_mode": "DISCOVERY"},
        context={},
    )
    assert isinstance(result, ResearchOutput)
    assert result.research_mode == "DISCOVERY"
    ids = [c.id for c in result.candidates]
    assert len(ids) == 3
    assert len(set(ids)) == 3  # exact candidate bound + stable distinct ids
    assert result.requirements == []
    assert result.evidence  # real provider evidence preserved


# --- 13. Compact Validation result converts to rich ResearchOutput --------


async def test_validation_compact_result_converts_to_rich_research_output():
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_ValidationProvider(), research_provider=MockResearchProvider()
    )
    candidates_input = [
        {"id": "candidate-a", "label": "Candidate A"},
        {"id": "candidate-b", "label": "Candidate B"},
    ]
    result = await agent.run(
        title="Validate and compare candidate opportunities",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": candidates_input},
        context={},
    )
    assert isinstance(result, ResearchOutput)
    assert result.research_mode == "VALIDATION"
    assert {c.id for c in result.candidates} == {"candidate-a", "candidate-b"}
    assert result.requirements  # deterministic requirements populated
    assert result.evidence  # real evidence populated


# --- 14. Real evidence IDs survive DTO -> domain conversion unchanged -----


async def test_evidence_ids_survive_discovery_dto_conversion_unchanged():
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_DiscoveryProvider(), research_provider=_FixedResearchProvider()
    )
    result = await agent.run(
        title="Notion template marketplace", description="", input_data={"research_mode": "DISCOVERY"}, context={}
    )
    assert len(result.evidence) == 1
    evidence_item = result.evidence[0]
    assert evidence_item.source_url == "https://example.com/fixed"
    # Discovery evidence links reference the SAME evidence id, unchanged by
    # the DTO round-trip.
    notion_candidate = next(c for c in result.candidates if c.label == "Notion template marketplace")
    assert notion_candidate.discovery_evidence_ids == [evidence_item.id]


# --- 15. Candidate IDs remain deterministic --------------------------------


async def test_candidate_ids_remain_deterministic_via_compact_dto_path():
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_DiscoveryProvider(), research_provider=MockResearchProvider()
    )
    result_a = await agent.run(
        title="Find three potential digital-product opportunities",
        description="", input_data={"research_mode": "DISCOVERY"}, context={},
    )
    result_b = await agent.run(
        title="Find three potential digital-product opportunities",
        description="", input_data={"research_mode": "DISCOVERY"}, context={},
    )
    assert [c.id for c in result_a.candidates] == [c.id for c in result_b.candidates]
    assert "notion-template-marketplace" in [c.id for c in result_a.candidates]


# --- 16. Requirements remain deterministic ----------------------------------


async def test_requirements_remain_deterministic_via_compact_dto_path():
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_ValidationProvider(), research_provider=MockResearchProvider()
    )
    candidates_input = [
        {"id": "candidate-a", "label": "Candidate A"},
        {"id": "candidate-b", "label": "Candidate B"},
    ]
    result = await agent.run(
        title="Validate and compare candidate opportunities",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": candidates_input},
        context={},
    )
    categories_a = {r.category for r in result.requirements if r.candidate_id == "candidate-a"}
    categories_b = {r.category for r in result.requirements if r.candidate_id == "candidate-b"}
    assert categories_a == categories_b == set(CORE_COMPARISON_CATEGORIES)


# --- 17. Evidence gaps remain deterministic --------------------------------


async def test_evidence_gaps_remain_deterministic_via_compact_dto_path():
    from app.config.settings import Settings

    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_ValidationProvider(), research_provider=MockResearchProvider()
    )
    candidates_input = [
        {"id": "candidate-a", "label": "Candidate A"},
        {"id": "candidate-b", "label": "Candidate B"},
    ]
    result = await agent.run(
        title="Validate and compare candidate opportunities",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": candidates_input},
        context={},
    )
    # MockResearchProvider's generic placeholder snippets don't establish
    # SUFFICIENT coverage for either candidate, so gaps are expected — and
    # bounded exactly like every other gap-driven retry.
    assert result.evidence_gaps
    assert len(result.evidence_gaps) <= Settings().research_max_gap_queries_per_attempt
