"""Wiring of the Research Intelligence pipeline into ResearchAgent (Phases 2,
3, 5): every research task gets a deterministic requirement set for its own
candidate, and gathered evidence gets tagged with source_role/relevance —
regardless of whether live evidence was available. Offline."""
from __future__ import annotations

from app.database.models import PermissionLevel
from app.research_intelligence.requirements import CORE_COMPARISON_CATEGORIES
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.tools.research_tools import MockResearchProvider


class _StubModelProvider:
    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        return ResearchOutput(question="q", findings=[], summary="s", insufficient_evidence=False)


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


async def test_requirements_generated_even_without_live_evidence(registry, provider):
    """dev mode (the test-suite default — see tests/conftest.py) never
    reaches a live provider, but the candidate still gets a requirement
    set."""
    agent = registry.create("research", provider=provider)
    result = await agent.run(
        title="Notion template marketplace", description="", input_data={}, context={}
    )
    assert result.requirements
    assert {r.category for r in result.requirements} == set(CORE_COMPARISON_CATEGORIES)
    assert all(r.candidate_id == "notion-template-marketplace" for r in result.requirements)


async def test_gathered_evidence_is_tagged_with_source_role_and_relevance():
    from app.agents.research import ResearchAgent

    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_StubModelProvider(), research_provider=MockResearchProvider()
    )
    result = await agent.run(
        title="Notion template marketplace", description="", input_data={}, context={}
    )
    assert result.evidence
    assert all(e.source_role != "" for e in result.evidence)
    assert all(e.relevance_label is not None for e in result.evidence)
    assert all(e.candidate_id == "notion-template-marketplace" for e in result.evidence)


async def test_off_topic_evidence_is_excluded_from_model_prompt_but_still_persisted():
    """Off-topic search results (no mention of the candidate, no category
    signal) should score REJECT and never reach the model prompt, but must
    still survive on result.evidence — never silently discarded (see
    app/research_intelligence/relevance.py)."""
    from app.agents.research import ResearchAgent
    from app.tools.research_tools import SearchResult

    class _OffTopicResearchProvider:
        name = "fake"
        is_live = True

        async def search(self, query, *, max_results=5):
            return [
                SearchResult(
                    title="Chocolate chip cookie recipe",
                    url="https://cooking.example.com/cookies",
                    snippet="A recipe for chocolate chip cookies with step-by-step baking instructions.",
                )
            ]

        async def fetch(self, url):
            raise NotImplementedError

        async def extract(self, content, question):
            raise NotImplementedError

    captured_prompts: list[str] = []

    class _CapturingProvider:
        name = "stub"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            captured_prompts.append(user_prompt)
            return ResearchOutput(question="q", findings=[], summary="s", insufficient_evidence=False)

    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_CapturingProvider(), research_provider=_OffTopicResearchProvider()
    )
    result = await agent.run(
        title="Notion template marketplace", description="", input_data={}, context={}
    )

    assert result.evidence  # never discarded
    rejected = [e for e in result.evidence if e.relevance_label == "REJECT"]
    assert rejected
    for item in rejected:
        assert item.rejection_reason is not None
        assert item.id not in captured_prompts[0]
