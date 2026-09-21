"""TavilyResearchProvider: construction, factory selection, Tavily JSON ->
EvidenceItem mapping, error/timeout/malformed-response handling, URL safety
on fetch(), usage accounting, and log redaction. Every HTTP call is mocked at
the httpx transport boundary — no test here may reach api.tavily.com."""
from __future__ import annotations

import httpx
import pytest

from app.agents.research import ResearchAgent
from app.agents.usage import collect_usage
from app.config.settings import get_settings
from app.database.models import EvidenceVerificationStatus, PermissionLevel
from app.schemas.agents import AgentDescriptor
from app.tools.research_tools import (
    ResearchUnavailableError,
    TavilyResearchProvider,
    get_default_research_provider,
)
from app.tools.url_safety import UnsafeURLError
from app.utils.logging import _redact_processor

_RealAsyncClient = httpx.AsyncClient
FAKE_KEY = "tvly-test-not-a-real-key"


def _patch_client(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda *a, **kw: _RealAsyncClient(*a, transport=transport, **kw)
    )


def _descriptor(name: str = "research") -> AgentDescriptor:
    return AgentDescriptor(
        name=name, role=name, description=name, capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


# --- Construction / factory selection ---------------------------------------


def test_construction_requires_api_key():
    with pytest.raises(ResearchUnavailableError, match="TAVILY_API_KEY"):
        TavilyResearchProvider(api_key="")


def test_construction_with_key_succeeds_and_is_live():
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    assert provider.name == "tavily"
    assert provider.is_live is True


def test_missing_api_key_error_never_contains_a_key_value():
    with pytest.raises(ResearchUnavailableError) as exc_info:
        TavilyResearchProvider(api_key="")
    assert "tvly-" not in str(exc_info.value)


def test_factory_selects_tavily_provider(monkeypatch):
    monkeypatch.setenv("RESEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", FAKE_KEY)
    get_settings.cache_clear()
    try:
        provider = get_default_research_provider()
        assert isinstance(provider, TavilyResearchProvider)
    finally:
        get_settings.cache_clear()


def test_factory_fails_clearly_when_tavily_selected_without_key(monkeypatch):
    monkeypatch.setenv("RESEARCH_PROVIDER", "tavily")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(ResearchUnavailableError, match="TAVILY_API_KEY"):
            get_default_research_provider()
    finally:
        get_settings.cache_clear()


def test_factory_unknown_provider_fails_clearly(monkeypatch):
    monkeypatch.setenv("RESEARCH_PROVIDER", "duckduckgo-turbo")
    get_settings.cache_clear()
    try:
        with pytest.raises(ResearchUnavailableError, match="Unknown RESEARCH_PROVIDER"):
            get_default_research_provider()
    finally:
        get_settings.cache_clear()


# --- search() -> SearchResult / EvidenceItem mapping -------------------------


async def test_search_maps_tavily_results_preserving_url_title_and_query(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": "children's colouring books market size",
                "results": [
                    {
                        "title": "Colouring Book Market Report 2025",
                        "url": "https://example.com/report",
                        "content": "The global market was valued at ...",
                        "score": 0.91,
                    }
                ],
            },
        )

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    results = await provider.search("children's colouring books market size")

    assert len(results) == 1
    r = results[0]
    assert r.title == "Colouring Book Market Report 2025"
    assert r.url == "https://example.com/report"
    assert r.snippet == "The global market was valued at ..."


async def test_search_results_flow_into_evidence_with_query_preserved(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "T1", "url": "https://example.com/a", "content": "c1"},
                    {"title": "T2", "url": "https://example.org/b", "content": "c2"},
                ]
            },
        )

    _patch_client(monkeypatch, handler)
    agent = ResearchAgent(
        descriptor=_descriptor(),
        provider=_StubModelProvider(),
        research_provider=TavilyResearchProvider(api_key=FAKE_KEY),
    )
    result = await agent.run(title="colouring books", description="", input_data={}, context={})

    assert len(result.evidence) == 2
    urls = {e.source_url for e in result.evidence}
    titles = {e.source_title for e in result.evidence}
    assert urls == {"https://example.com/a", "https://example.org/b"}
    assert titles == {"T1", "T2"}
    for item in result.evidence:
        assert item.query_used == "colouring books"
        assert item.verification_status == EvidenceVerificationStatus.RETRIEVED


async def test_missing_metadata_stays_null_not_fabricated(monkeypatch):
    """Tavily's search response has no publisher or published_at field —
    those must stay None, never invented (e.g. from today's date)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"title": "No date here", "url": "https://news.example.com/x", "content": "c"}]},
        )

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    agent = ResearchAgent(descriptor=_descriptor(), provider=_StubModelProvider(), research_provider=provider)
    result = await agent.run(title="q", description="", input_data={}, context={})

    item = result.evidence[0]
    assert item.published_at is None
    assert item.publisher == "news.example.com"  # derived from the URL, not fabricated


async def test_search_result_with_no_title_or_url_handled_safely(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"content": "orphan snippet"}]})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    results = await provider.search("q")
    assert results[0].title == "(untitled)"
    assert results[0].url is None


async def test_empty_search_results(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    results = await provider.search("nothing found")
    assert results == []


async def test_max_results_is_bounded(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"results": []})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    await provider.search("q", max_results=999)
    assert captured["payload"]["max_results"] <= provider._MAX_RESULTS_CEILING


async def test_search_depth_defaults_to_basic(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"results": []})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    await provider.search("q")
    assert captured["payload"]["search_depth"] == "basic"


# --- Error handling -----------------------------------------------------------


async def test_malformed_json_response_raises_research_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with pytest.raises(ResearchUnavailableError, match="malformed"):
        await provider.search("q")


async def test_missing_results_key_raises(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"query": "q"})  # no 'results' key at all

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with pytest.raises(ResearchUnavailableError, match="results"):
        await provider.search("q")


async def test_authentication_failure_raises_clear_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Unauthorized"})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with pytest.raises(ResearchUnavailableError, match="authentication"):
        await provider.search("q")


async def test_rate_limit_raises_clear_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "Too Many Requests"})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with pytest.raises(ResearchUnavailableError, match="rate limit|quota"):
        await provider.search("q")


async def test_server_error_raises_clear_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal error")

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with pytest.raises(ResearchUnavailableError, match="500"):
        await provider.search("q")


async def test_timeout_raises_research_unavailable(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY, timeout_seconds=0.01)
    with pytest.raises(ResearchUnavailableError, match="timed out"):
        await provider.search("q")


async def test_research_agent_treats_tavily_errors_as_no_evidence_not_a_crash(monkeypatch):
    """Matches the existing DevResearchProvider contract: a ResearchUnavailableError
    from the provider must not crash the agent — it falls back to no evidence."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "bad key"})

    _patch_client(monkeypatch, handler)
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_StubModelProvider(),
        research_provider=TavilyResearchProvider(api_key=FAKE_KEY),
    )
    result = await agent.run(title="q", description="", input_data={}, context={})
    assert result.evidence == []


# --- fetch() URL safety -------------------------------------------------------


async def test_fetch_rejects_unsafe_url_before_any_network_call(monkeypatch):
    def _should_not_be_called(*a, **kw):
        raise AssertionError("no HTTP client should be constructed for an unsafe URL")

    monkeypatch.setattr(httpx, "AsyncClient", _should_not_be_called)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with pytest.raises(UnsafeURLError):
        await provider.fetch("http://localhost/admin")


async def test_fetch_returns_extracted_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"url": "https://example.com/p", "raw_content": "full page text"}]})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    content = await provider.fetch("https://example.com/p")
    assert content == "full page text"


# --- Usage accounting ----------------------------------------------------------


async def test_search_records_usage_tagged_as_tavily(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with collect_usage() as events:
        await provider.search("q")

    assert len(events) == 1
    assert events[0].provider == "tavily"
    assert events[0].model == "search"
    assert events[0].elapsed_ms is not None


async def test_failed_call_with_response_still_records_usage(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "bad key"})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with collect_usage() as events:
        with pytest.raises(ResearchUnavailableError):
            await provider.search("q")
    assert len(events) == 1  # a response was received, so it's a completed call


async def test_timeout_records_no_usage(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout", request=request)

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY, timeout_seconds=0.01)
    with collect_usage() as events:
        with pytest.raises(ResearchUnavailableError):
            await provider.search("q")
    assert events == []  # no response ever came back — nothing to account for


# --- Logging / redaction -------------------------------------------------------


def test_tavily_api_key_field_is_redacted():
    redacted = _redact_processor(None, None, {"tavily_api_key": FAKE_KEY, "provider": "tavily"})
    assert redacted["tavily_api_key"] == "***REDACTED***"
    assert redacted["provider"] == "tavily"


async def test_no_log_call_in_provider_ever_includes_the_raw_key(monkeypatch, caplog):
    """Belt-and-suspenders: even without relying on the redaction processor,
    the provider's own code must never pass the key into a log field."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "bad key"})

    _patch_client(monkeypatch, handler)
    provider = TavilyResearchProvider(api_key=FAKE_KEY)
    with pytest.raises(ResearchUnavailableError):
        await provider.search("q")

    assert FAKE_KEY not in caplog.text


class _StubModelProvider:
    """A minimal ModelProvider stand-in that echoes back a valid ResearchOutput
    without needing the real MockProvider's dispatch machinery."""

    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        from app.schemas.agents import ResearchOutput

        return ResearchOutput(question="q", findings=[], summary="s", insufficient_evidence=False)
