"""Agent registry and individual agent behavior, all against the MockProvider
so these tests never require a live OpenAI API key."""
from __future__ import annotations

import pytest

from app.database.models import PermissionLevel
from app.schemas.agents import ExecutionOutput, QAVerdict, ResearchOutput, StrategyOutput
from app.schemas.tasks import ExecutionPlan


def test_registry_lists_five_core_agents(registry):
    names = {a.name for a in registry.list_agents()}
    assert names == {"jarvis", "research", "strategy", "execution", "qa"}


def test_registry_permissions_match_spec(registry):
    assert registry.has_permission("research", PermissionLevel.READ)
    assert not registry.has_permission("research", PermissionLevel.WRITE)

    assert registry.has_permission("strategy", PermissionLevel.READ)
    assert not registry.has_permission("strategy", PermissionLevel.WRITE)

    assert registry.has_permission("qa", PermissionLevel.READ)
    assert not registry.has_permission("qa", PermissionLevel.WRITE)

    assert registry.has_permission("execution", PermissionLevel.READ)
    assert registry.has_permission("execution", PermissionLevel.WRITE)

    assert registry.has_permission("jarvis", PermissionLevel.READ)
    assert registry.has_permission("jarvis", PermissionLevel.WRITE)

    for agent_type in ("research", "strategy", "execution", "qa", "jarvis"):
        for elevated in (
            PermissionLevel.EXTERNAL_ACTION,
            PermissionLevel.FINANCIAL_ACTION,
            PermissionLevel.ADMIN,
        ):
            assert not registry.has_permission(agent_type, elevated)


def test_registry_unknown_agent_raises(registry):
    with pytest.raises(KeyError):
        registry.get_descriptor("marketing")


def test_registry_wires_exact_configured_model_ids(monkeypatch):
    """Regression test: each agent's descriptor.model must equal the configured
    *_MODEL env var byte-for-byte. Catches accidental truncation, prefix-stripping,
    or misrouting between agents (e.g. QA_MODEL losing its "claude-" prefix)."""
    from app.agents.registry import build_default_registry
    from app.config.settings import get_settings

    expected = {
        "jarvis": "claude-sonnet-5",
        "research": "claude-haiku-4-5-20251001",
        "strategy": "claude-sonnet-5",
        "qa": "claude-haiku-4-5-20251001",
        "execution": "claude-sonnet-5",
    }
    monkeypatch.setenv("JARVIS_MODEL", expected["jarvis"])
    monkeypatch.setenv("RESEARCH_MODEL", expected["research"])
    monkeypatch.setenv("STRATEGY_MODEL", expected["strategy"])
    monkeypatch.setenv("QA_MODEL", expected["qa"])
    monkeypatch.setenv("EXECUTION_MODEL", expected["execution"])
    get_settings.cache_clear()

    try:
        registry = build_default_registry(get_settings())
        for agent_type, model_id in expected.items():
            assert registry.get_descriptor(agent_type).model == model_id
    finally:
        get_settings.cache_clear()


async def test_research_agent_returns_structured_output_and_labels_dev_data(registry, provider):
    agent = registry.create("research", provider=provider)
    result = await agent.run(
        title="Research: example market", description="", input_data={}, context={}
    )
    assert isinstance(result, ResearchOutput)
    assert result.insufficient_evidence is True
    assert any("DEVELOPMENT/SAMPLE DATA" in f.claim for f in result.findings)


async def test_strategy_agent_returns_structured_output(registry, provider):
    agent = registry.create("strategy", provider=provider)
    result = await agent.run(
        title="Synthesize",
        description="",
        input_data={"research_results": [{"question": "topic a", "findings": []}]},
        context={},
    )
    assert isinstance(result, StrategyOutput)
    assert result.assumptions


async def test_execution_agent_never_claims_external_action(registry, provider):
    agent = registry.create("execution", provider=provider)
    result = await agent.run(title="Draft something", description="", input_data={}, context={})
    assert isinstance(result, ExecutionOutput)
    assert result.blocked_on_approval is False


async def test_qa_agent_flags_missing_assumptions(registry, provider):
    agent = registry.create("qa", provider=provider)
    result = await agent.run(
        title="review",
        description="",
        input_data={"output": {"recommendation": "do X", "assumptions": []}},
        context={},
    )
    assert isinstance(result, QAVerdict)
    assert result.verdict in {"NEEDS_REVIEW", "FAIL"}
    assert result.unsupported_claims


async def test_jarvis_plan_is_structured_execution_plan(registry, provider):
    jarvis = registry.create("jarvis", provider=provider)
    plan = await jarvis.plan("Find three digital product opportunities.")
    assert isinstance(plan, ExecutionPlan)
    assert len(plan.tasks) >= 2
    agent_types = {t.agent_type for t in plan.tasks}
    assert "research" in agent_types
    assert "strategy" in agent_types


async def test_jarvis_run_is_not_a_dispatchable_worker(registry, provider):
    jarvis = registry.create("jarvis", provider=provider)
    with pytest.raises(NotImplementedError):
        await jarvis.run(title="x", description="", input_data={}, context={})
