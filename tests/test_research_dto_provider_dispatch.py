"""Phase 6/9: the exact live-benchmark failure, reproduced offline. Each
research_mode must send the model provider a compact DTO, never the rich
ResearchOutput. Offline — captures output_schema at the point ResearchAgent
calls complete_structured()."""
from __future__ import annotations

from app.agents.research import ResearchAgent
from app.database.models import PermissionLevel
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.schemas.research_dto import (
    DiscoveryCandidateProposal,
    DiscoveryModelOutput,
    GeneralResearchModelOutput,
    ValidationModelOutput,
)
from app.tools.research_tools import DevResearchProvider


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _CapturingProvider:
    name = "stub"

    def __init__(self):
        self.captured_schemas: list = []

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        self.captured_schemas.append(output_schema)
        if output_schema is DiscoveryModelOutput:
            return DiscoveryModelOutput(
                candidates=[
                    DiscoveryCandidateProposal(label="Notion template marketplace"),
                    DiscoveryCandidateProposal(label="Coda template hub"),
                    DiscoveryCandidateProposal(label="Airtable template pack"),
                ],
                summary="Identified three candidates.",
            )
        if output_schema is ValidationModelOutput:
            return ValidationModelOutput(summary="Validated candidates.")
        if output_schema is GeneralResearchModelOutput:
            return GeneralResearchModelOutput(summary="General research summary.")
        raise AssertionError(f"Unexpected output_schema requested: {output_schema}")


async def _run(mode_input_data: dict, *, title: str = "task") -> tuple[ResearchOutput, _CapturingProvider]:
    provider = _CapturingProvider()
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=provider, research_provider=DevResearchProvider()
    )
    result = await agent.run(title=title, description="", input_data=mode_input_data, context={})
    return result, provider


# --- 1/2. DISCOVERY passes the compact DTO, not ResearchOutput -------------


async def test_discovery_passes_compact_dto_to_model_provider():
    _, provider = await _run({"research_mode": "DISCOVERY"}, title="Find three potential digital-product opportunities")
    assert provider.captured_schemas == [DiscoveryModelOutput]


async def test_discovery_does_not_pass_research_output():
    _, provider = await _run({"research_mode": "DISCOVERY"}, title="Find three potential digital-product opportunities")
    assert ResearchOutput not in provider.captured_schemas


# --- 3/4. VALIDATION passes the compact DTO, not ResearchOutput ------------


async def test_validation_passes_compact_dto_to_model_provider():
    _, provider = await _run(
        {"research_mode": "VALIDATION", "candidates": [{"label": "Candidate A"}, {"label": "Candidate B"}]},
        title="Validate and compare candidate opportunities",
    )
    assert provider.captured_schemas == [ValidationModelOutput]


async def test_validation_does_not_pass_research_output():
    _, provider = await _run(
        {"research_mode": "VALIDATION", "candidates": [{"label": "Candidate A"}, {"label": "Candidate B"}]},
        title="Validate and compare candidate opportunities",
    )
    assert ResearchOutput not in provider.captured_schemas


# --- 5. GENERAL uses an appropriately bounded model schema ----------------


async def test_general_research_uses_bounded_model_schema():
    _, provider = await _run({}, title="Research: example market")
    assert provider.captured_schemas == [GeneralResearchModelOutput]
    assert ResearchOutput not in provider.captured_schemas


# --- The full planner shape from the live benchmark, exercised end to end -


async def test_full_discovery_then_validation_shape_never_sends_research_output():
    """Objective: 'Find three potential digital-product opportunities and
    recommend the strongest one.' Planner shape: DISCOVERY research ->
    VALIDATION research (this test covers the two research calls; Strategy/
    QA schema sizes are covered separately in
    tests/test_research_dto_schema_size.py)."""
    discovery_result, discovery_provider = await _run(
        {"research_mode": "DISCOVERY"}, title="Discover candidate digital-product opportunities"
    )
    assert discovery_provider.captured_schemas == [DiscoveryModelOutput]
    assert len(discovery_result.candidates) == 3

    candidates_payload = [c.model_dump(mode="json") for c in discovery_result.candidates]
    validation_result, validation_provider = await _run(
        {"research_mode": "VALIDATION", "candidates": candidates_payload},
        title="Validate and compare candidate opportunities",
    )
    assert validation_provider.captured_schemas == [ValidationModelOutput]
    assert len(validation_result.candidates) == 3
