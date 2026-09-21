"""Model-usage accounting: the contextvar side-channel, provider wiring,
pricing/cost estimation, and DB persistence/aggregation. No live API calls —
MockProvider plus a fake Anthropic SDK response."""
from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from app.agents.providers import AnthropicProvider, MockProvider
from app.agents.usage import ModelUsage, collect_usage, record_usage
from app.config.pricing import estimate_cost_usd, get_pricing_table
from app.config.settings import get_settings


class _Dummy(BaseModel):
    ok: bool = True


# --- collect_usage / record_usage -----------------------------------------


def test_record_usage_outside_collector_is_a_noop():
    record_usage(ModelUsage(provider="p", model="m"))  # must not raise


def test_collect_usage_captures_events():
    with collect_usage() as events:
        record_usage(ModelUsage(provider="p", model="m", api_calls=1))
        record_usage(ModelUsage(provider="p", model="m", api_calls=1))
    assert len(events) == 2


def test_collect_usage_isolated_across_nested_scopes():
    with collect_usage() as outer:
        record_usage(ModelUsage(provider="p", model="outer"))
        with collect_usage() as inner:
            record_usage(ModelUsage(provider="p", model="inner"))
        assert [e.model for e in inner] == ["inner"]
    assert [e.model for e in outer] == ["outer"]


async def test_collect_usage_isolated_across_concurrent_tasks():
    """contextvars must not leak between concurrently-running asyncio Tasks —
    this is what makes usage accounting safe under AgentExecutor's
    asyncio.gather-based concurrent task execution."""

    async def worker(tag: str) -> list[str]:
        with collect_usage() as events:
            record_usage(ModelUsage(provider="p", model=tag))
            await asyncio.sleep(0)
            record_usage(ModelUsage(provider="p", model=tag))
            return [e.model for e in events]

    results = await asyncio.gather(worker("a"), worker("b"), worker("c"))
    assert results == [["a", "a"], ["b", "b"], ["c", "c"]]


# --- MockProvider records usage without guessing tokens ---------------------


async def test_mock_provider_records_usage_with_no_guessed_tokens():
    from app.schemas.tasks import ExecutionPlan

    provider = MockProvider()
    with collect_usage() as events:
        await provider.complete_structured(
            system_prompt="s",
            user_prompt='{"objective": "test objective"}',
            output_schema=ExecutionPlan,
            model="mock-model",
        )
    assert len(events) == 1
    assert events[0].provider == "mock"
    assert events[0].input_tokens is None
    assert events[0].output_tokens is None
    assert events[0].elapsed_ms is not None


# --- Anthropic provider forwards real usage from the SDK response ----------


async def test_anthropic_provider_records_real_token_usage(monkeypatch):
    provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")

    class FakeUsage:
        input_tokens = 123
        output_tokens = 45

    class FakeResponse:
        parsed_output = _Dummy()
        usage = FakeUsage()

    async def fake_parse(**kwargs):
        return FakeResponse()

    monkeypatch.setattr(provider._client.messages, "parse", fake_parse)

    with collect_usage() as events:
        result = await provider.complete_structured(
            system_prompt="s", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001"
        )

    assert isinstance(result, _Dummy)
    assert len(events) == 1
    assert events[0].input_tokens == 123
    assert events[0].output_tokens == 45
    assert events[0].total_tokens == 168


async def test_anthropic_provider_handles_missing_usage_gracefully(monkeypatch):
    provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")

    class FakeResponse:
        parsed_output = _Dummy()
        # no `usage` attribute at all

    async def fake_parse(**kwargs):
        return FakeResponse()

    monkeypatch.setattr(provider._client.messages, "parse", fake_parse)

    with collect_usage() as events:
        await provider.complete_structured(
            system_prompt="s", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001"
        )
    assert events[0].input_tokens is None
    assert events[0].total_tokens is None


# --- Pricing: USAGE and ESTIMATED_COST stay separate ------------------------


@pytest.fixture(autouse=True)
def _clear_pricing_env(monkeypatch):
    monkeypatch.delenv("MODEL_PRICING_JSON", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_estimate_cost_is_none_when_pricing_not_configured():
    assert get_pricing_table() == {}
    assert estimate_cost_usd(model="claude-sonnet-5", input_tokens=1000, output_tokens=1000) is None


def test_estimate_cost_is_none_when_tokens_unknown(monkeypatch):
    monkeypatch.setenv(
        "MODEL_PRICING_JSON",
        '{"claude-sonnet-5": {"input_per_million_usd": 3.0, "output_per_million_usd": 15.0}}',
    )
    get_settings.cache_clear()
    assert estimate_cost_usd(model="claude-sonnet-5", input_tokens=None, output_tokens=100) is None


def test_estimate_cost_computed_when_pricing_and_tokens_present(monkeypatch):
    monkeypatch.setenv(
        "MODEL_PRICING_JSON",
        '{"claude-sonnet-5": {"input_per_million_usd": 3.0, "output_per_million_usd": 15.0}}',
    )
    get_settings.cache_clear()
    cost = estimate_cost_usd(model="claude-sonnet-5", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(18.0)


def test_estimate_cost_none_for_unpriced_model(monkeypatch):
    monkeypatch.setenv(
        "MODEL_PRICING_JSON",
        '{"claude-sonnet-5": {"input_per_million_usd": 3.0, "output_per_million_usd": 15.0}}',
    )
    get_settings.cache_clear()
    assert estimate_cost_usd(model="some-other-model", input_tokens=1000, output_tokens=1000) is None


def test_invalid_pricing_json_falls_back_to_empty_table(monkeypatch):
    monkeypatch.setenv("MODEL_PRICING_JSON", "not valid json")
    get_settings.cache_clear()
    assert get_pricing_table() == {}


# --- UsageService persistence / rollups -------------------------------------


async def test_usage_records_persist_and_aggregate(session_factory):
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.services.project_service import ProjectService
    from app.services.usage_service import UsageService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("u@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        await UsageService(session).record_many(
            workspace_id=workspace_id,
            project_id=project_id,
            task_id=None,
            agent_type="research",
            events=[
                ModelUsage(provider="mock", model="m", input_tokens=100, output_tokens=50, total_tokens=150),
                ModelUsage(provider="mock", model="m", input_tokens=10, output_tokens=5, total_tokens=15, retry_number=1),
            ],
        )
        await session.commit()

    async with session_factory() as session:
        totals = await UsageService(session).totals_for_project(project_id)
        assert totals.api_calls == 2
        assert totals.input_tokens == 110
        assert totals.output_tokens == 55
        assert totals.total_tokens == 165

        by_agent = await UsageService(session).breakdown_by_agent(project_id)
        assert by_agent["research"].api_calls == 2
