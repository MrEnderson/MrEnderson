"""ResearchProvider selection and MockResearchProvider determinism. No test
here makes a network call — DevResearchProvider always raises, and
MockResearchProvider is a pure in-memory stub."""
from __future__ import annotations

import pytest

from app.config.settings import get_settings
from app.tools.research_tools import (
    DevResearchProvider,
    MockResearchProvider,
    ResearchUnavailableError,
    get_default_research_provider,
)


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    # monkeypatch.delenv() alone is NOT enough — pydantic-settings falls back
    # to reading .env for any key absent from the process environment, and a
    # developer's .env may have RESEARCH_PROVIDER=tavily with a real key (as
    # it does in this project's own local .env). Set the default explicitly.
    monkeypatch.setenv("RESEARCH_PROVIDER", "dev")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_to_dev_provider():
    assert isinstance(get_default_research_provider(), DevResearchProvider)


def test_dev_provider_is_not_live():
    assert DevResearchProvider().is_live is False


async def test_dev_provider_search_raises_unavailable():
    provider = DevResearchProvider()
    with pytest.raises(ResearchUnavailableError):
        await provider.search("anything")


def test_mock_provider_selected_when_configured(monkeypatch):
    monkeypatch.setenv("RESEARCH_PROVIDER", "mock")
    get_settings.cache_clear()
    provider = get_default_research_provider()
    assert isinstance(provider, MockResearchProvider)
    assert provider.is_live is True


async def test_mock_provider_search_is_deterministic_and_labeled():
    provider = MockResearchProvider()
    first = await provider.search("children's colouring books market")
    second = await provider.search("children's colouring books market")

    assert [r.model_dump() for r in first] == [r.model_dump() for r in second]
    assert len(first) >= 1
    for result in first:
        assert result.url is not None
        assert "MOCK" in result.snippet


async def test_mock_provider_respects_max_results():
    provider = MockResearchProvider()
    results = await provider.search("q", max_results=1)
    assert len(results) == 1


def test_live_provider_raises_actionable_error_no_vendor_selected(monkeypatch):
    monkeypatch.setenv("RESEARCH_PROVIDER", "live")
    get_settings.cache_clear()
    with pytest.raises(ResearchUnavailableError, match="vendor"):
        get_default_research_provider()


def test_unknown_research_provider_raises(monkeypatch):
    monkeypatch.setenv("RESEARCH_PROVIDER", "not-a-real-provider")
    get_settings.cache_clear()
    with pytest.raises(ResearchUnavailableError):
        get_default_research_provider()
