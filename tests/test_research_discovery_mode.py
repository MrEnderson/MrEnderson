"""DISCOVERY mode (v0.1.2.1, Issue 1): candidates don't exist yet at mission
start — Research must identify them, structured, before any validation runs.
Discovery evidence establishes a candidate is worth investigating; it never
by itself means the candidate has been validated. Offline."""
from __future__ import annotations

from app.agents.research import ResearchAgent, _resolve_research_mode
from app.config.settings import Settings
from app.database.models import PermissionLevel
from app.research_intelligence.gate import evaluate_comparison_readiness
from app.research_intelligence.schemas import ResearchCandidate
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.tools.research_tools import MockResearchProvider


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _DiscoveryStubProvider:
    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        return ResearchOutput(
            question="q",
            findings=[],
            summary="Identified three candidate digital-product opportunities.",
            insufficient_evidence=False,
            candidates=[
                ResearchCandidate(label="Notion template marketplace", description="Sell Notion templates."),
                ResearchCandidate(label="Coda template hub", description="Sell Coda templates."),
                ResearchCandidate(label="Airtable template pack", description="Sell Airtable templates."),
            ],
        )


def _discovery_agent() -> ResearchAgent:
    return ResearchAgent(
        descriptor=_descriptor(), provider=_DiscoveryStubProvider(), research_provider=MockResearchProvider()
    )


# --- 1. Discovery objective starts with zero known candidates ---------------


def test_discovery_mode_starts_with_zero_known_candidates():
    input_data = {"research_mode": "DISCOVERY"}
    assert not input_data.get("candidates")
    assert _resolve_research_mode(input_data) == "DISCOVERY"


# --- 2. Discovery ResearchOutput returns exactly three structured candidates


async def test_discovery_returns_exactly_three_structured_candidates():
    agent = _discovery_agent()
    result = await agent.run(
        title="Find three potential digital-product opportunities",
        description="",
        input_data={"research_mode": "DISCOVERY"},
        context={},
    )
    assert result.research_mode == "DISCOVERY"
    assert len(result.candidates) == 3
    assert all(isinstance(c, ResearchCandidate) for c in result.candidates)
    assert all(c.status == "DISCOVERED" for c in result.candidates)
    # Discovery never runs the completeness gate or generates per-candidate
    # requirements — there's no validated candidate set yet.
    assert result.requirements == []


# --- 3. Candidates receive stable distinct IDs ------------------------------


async def test_candidates_receive_stable_distinct_ids():
    agent = _discovery_agent()
    result = await agent.run(
        title="Find three potential digital-product opportunities",
        description="",
        input_data={"research_mode": "DISCOVERY"},
        context={},
    )
    ids = [c.id for c in result.candidates]
    assert len(ids) == len(set(ids)) == 3

    # Stable: re-running discovery with the same proposed labels yields the
    # same ids (deterministic normalize_candidate_id, not random uuids).
    result2 = await agent.run(
        title="Find three potential digital-product opportunities",
        description="",
        input_data={"research_mode": "DISCOVERY"},
        context={},
    )
    assert [c.id for c in result2.candidates] == ids


async def test_model_supplied_id_and_status_are_never_trusted():
    """Even if a model tried to claim a candidate is already VALIDATED or
    invent its own id, discovery always recomputes both deterministically."""

    class _UntrustworthyProvider:
        name = "stub"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            return ResearchOutput(
                question="q",
                findings=[],
                summary="s",
                insufficient_evidence=False,
                candidates=[
                    ResearchCandidate(
                        id="fake-id-123",
                        label="Notion template marketplace",
                        status="VALIDATED",
                        discovery_evidence_ids=["nonexistent-evidence-id"],
                    ),
                ],
            )

    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_UntrustworthyProvider(), research_provider=MockResearchProvider()
    )
    result = await agent.run(
        title="Find one candidate", description="", input_data={"research_mode": "DISCOVERY"}, context={}
    )
    candidate = result.candidates[0]
    assert candidate.id != "fake-id-123"
    assert candidate.status == "DISCOVERED"
    assert "nonexistent-evidence-id" not in candidate.discovery_evidence_ids


async def test_candidate_count_is_bounded_per_mission():
    class _TooManyCandidatesProvider:
        name = "stub"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            return ResearchOutput(
                question="q",
                findings=[],
                summary="s",
                insufficient_evidence=False,
                candidates=[ResearchCandidate(label=f"Candidate {i}") for i in range(10)],
            )

    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_TooManyCandidatesProvider(), research_provider=MockResearchProvider()
    )
    result = await agent.run(
        title="Find many candidates", description="", input_data={"research_mode": "DISCOVERY"}, context={}
    )
    assert len(result.candidates) == Settings().research_max_candidates_per_mission


# --- 4. Discovery evidence does not make comparison_ready=true automatically


async def test_discovery_evidence_never_auto_validates_comparison():
    agent = _discovery_agent()
    result = await agent.run(
        title="Find three potential digital-product opportunities",
        description="",
        input_data={"research_mode": "DISCOVERY"},
        context={},
    )

    research_results = [
        {
            "task_id": "discovery-1",
            "title": "Find three potential digital-product opportunities",
            "question": "q",
            "candidates": [c.model_dump(mode="json") for c in result.candidates],
            "evidence": [e.model_dump(mode="json") for e in result.evidence],
        }
    ]
    readiness = evaluate_comparison_readiness(research_results, settings=Settings())
    assert readiness.ready is False
