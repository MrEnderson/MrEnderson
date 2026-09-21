"""Regression (Issue 1, requirement #14): plain single-topic research must
keep working exactly as before — no research_mode, no candidates, GENERAL
mode end to end. Offline."""
from __future__ import annotations

from app.agents.research import _resolve_research_mode


def test_no_research_mode_and_no_candidates_defaults_to_general():
    assert _resolve_research_mode({}) == "GENERAL"


def test_explicit_general_stays_general_even_with_stray_keys():
    assert _resolve_research_mode({"research_mode": "GENERAL", "qa_feedback": "x"}) == "GENERAL"


def test_unrecognized_research_mode_value_falls_back_to_general():
    assert _resolve_research_mode({"research_mode": "NOT_A_REAL_MODE"}) == "GENERAL"


async def test_general_research_agent_output_unchanged_shape(registry, provider):
    """Uses the shared registry/provider fixtures exactly as the existing
    v0.1.1/v0.1.2 test suite does — see tests/test_agents.py."""
    agent = registry.create("research", provider=provider)
    result = await agent.run(
        title="Research: example market", description="", input_data={}, context={}
    )
    assert result.research_mode == "GENERAL"
    assert result.candidates == []
    assert result.insufficient_evidence is True
    assert any("DEVELOPMENT/SAMPLE DATA" in f.claim for f in result.findings)


async def test_general_strategy_agent_unaffected_by_gate_when_single_candidate(registry, provider):
    agent = registry.create("strategy", provider=provider)
    result = await agent.run(
        title="Synthesize",
        description="",
        input_data={"research_results": [{"question": "topic a", "findings": []}]},
        context={},
    )
    assert result.comparison_ready is True
