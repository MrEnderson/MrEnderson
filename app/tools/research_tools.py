"""Research provider abstraction (section 19 of the build spec; extended v0.1.1/v0.1.2).

`ResearchProvider` is the seam for real web research (search API, browser
automation, etc.) to be plugged in later without touching the Research Agent.

Implementations shipped today:

- `DevResearchProvider` (default, `RESEARCH_PROVIDER=dev`): makes no network
  calls and always reports the capability as unavailable rather than
  fabricating results. This is the exact v0.1 behavior.
- `MockResearchProvider` (`RESEARCH_PROVIDER=mock`): deterministic, no
  network, returns clearly-labeled placeholder search results so the
  evidence pipeline (Research -> EvidenceItem -> Strategy -> QA -> report)
  can be exercised end-to-end in tests/demos without a live vendor.
- `TavilyResearchProvider` (`RESEARCH_PROVIDER=tavily`): the first live
  backend. Talks to Tavily's REST API (https://docs.tavily.com) directly via
  `httpx` — the same HTTP client already used elsewhere in this project (see
  app/tools/url_safety.py) — rather than adding the `tavily-python` SDK as a
  dependency for what is a thin JSON API.

`RESEARCH_PROVIDER=live` remains reserved for any *other* vendor that isn't
Tavily: no such vendor has been selected, so `get_default_research_provider()`
raises a clear, actionable error instead of silently falling back or
fabricating a provider. See docs/evidence.md.
"""
from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel

from app.agents.usage import ModelUsage, record_usage, timer
from app.config.settings import get_settings
from app.tools.url_safety import validate_url
from app.utils.logging import get_logger

logger = get_logger(__name__)


class SearchResult(BaseModel):
    title: str
    url: str | None = None
    snippet: str


class ResearchProvider(Protocol):
    name: str
    is_live: bool

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]: ...

    async def fetch(self, url: str) -> str: ...

    async def extract(self, content: str, question: str) -> str: ...


class ResearchUnavailableError(Exception):
    pass


class DevResearchProvider:
    """Safe development implementation. Never claims live web access."""

    name = "dev"
    is_live = False

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        raise ResearchUnavailableError(
            "Live web search is not connected in this environment. "
            "Set RESEARCH_PROVIDER=mock for deterministic offline evidence, or "
            "implement a live ResearchProvider once a search vendor is chosen."
        )

    async def fetch(self, url: str) -> str:
        raise ResearchUnavailableError(
            "Live page fetching is not connected in this environment."
        )

    async def extract(self, content: str, question: str) -> str:
        raise ResearchUnavailableError(
            "Live content extraction is not connected in this environment."
        )


class MockResearchProvider:
    """Deterministic, offline, clearly-labeled placeholder research provider.

    Used to exercise the evidence pipeline in tests and local demos without
    any network access or live vendor. Every result is unmistakably labeled
    as mock data — see EvidenceVerificationStatus.MOCK, set by the Research
    Agent for anything this provider returns.
    """

    name = "mock"
    is_live = True

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        count = max(1, min(max_results, 3))
        return [
            SearchResult(
                title=f"[MOCK] Result {i} for: {query}",
                url=f"https://example.com/mock-source-{i}",
                snippet=(
                    f"[MOCK/DEV DATA] Deterministic placeholder snippet {i} for the query "
                    f"'{query}'. Not a real retrieval."
                ),
            )
            for i in range(1, count + 1)
        ]

    async def fetch(self, url: str) -> str:
        return f"[MOCK/DEV DATA] Deterministic placeholder content for {url}."

    async def extract(self, content: str, question: str) -> str:
        return f"[MOCK/DEV DATA] Deterministic placeholder extract answering '{question}'."


class TavilyResearchProvider:
    """Live search/extract via the Tavily REST API.

    Sends the API key only in the POST body (never in a URL query string, so
    it can never end up in a log line or proxy access log that only captures
    the request line), and never includes it in any exception message or log
    field. See app/utils/logging.py::_REDACT_KEYS for the defense-in-depth
    redaction backstop on the `tavily_api_key` field name.

    Records one ModelUsage event per completed HTTP response (success or
    Tavily-reported error) via app.agents.usage.record_usage — tagged
    provider="tavily", model="search"/"extract" so it stays distinguishable
    from LLM token usage in mission reporting. No request is recorded for
    network/timeout failures where no response was ever received.
    """

    name = "tavily"
    is_live = True

    _SEARCH_URL = "https://api.tavily.com/search"
    _EXTRACT_URL = "https://api.tavily.com/extract"
    _MAX_RESULTS_CEILING = 10  # hard safety cap, independent of caller/config

    def __init__(
        self,
        api_key: str,
        *,
        search_depth: str = "basic",
        timeout_seconds: float | None = None,
    ):
        if not api_key:
            raise ResearchUnavailableError(
                "RESEARCH_PROVIDER=tavily but TAVILY_API_KEY is not set. Set TAVILY_API_KEY "
                "in your environment/.env to use the live Tavily provider."
            )
        self._api_key = api_key
        self._search_depth = search_depth
        self._timeout_seconds = timeout_seconds or get_settings().research_fetch_timeout_seconds

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        bounded_max_results = max(1, min(max_results, self._MAX_RESULTS_CEILING))
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": bounded_max_results,
            "search_depth": self._search_depth,
            "include_answer": False,
            "include_raw_content": False,
        }

        response = await self._post(self._SEARCH_URL, payload, operation="search")
        data = self._parse_json(response, operation="search")

        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise ResearchUnavailableError("Tavily search response was missing a 'results' list.")

        results: list[SearchResult] = []
        for item in raw_results[:bounded_max_results]:
            if not isinstance(item, dict):
                continue
            results.append(
                SearchResult(
                    title=item.get("title") or "(untitled)",
                    url=item.get("url"),
                    snippet=item.get("content") or "",
                )
            )
        return results

    async def fetch(self, url: str) -> str:
        # Tavily performs the actual retrieval server-side, but we still
        # reject obviously-unsafe targets locally before asking it to (defense
        # in depth, and consistent with every other fetch path in this project).
        validate_url(url)

        payload = {"api_key": self._api_key, "urls": [url]}
        response = await self._post(self._EXTRACT_URL, payload, operation="extract")
        data = self._parse_json(response, operation="extract")

        raw_results = data.get("results")
        if isinstance(raw_results, list) and raw_results and isinstance(raw_results[0], dict):
            content = raw_results[0].get("raw_content")
            if content:
                return content

        raise ResearchUnavailableError("Tavily could not extract content for the given URL.")

    async def extract(self, content: str, question: str) -> str:
        raise ResearchUnavailableError(
            "TavilyResearchProvider has no standalone extract() over already-fetched content; "
            "use fetch(url) to retrieve page content via Tavily's own extract endpoint."
        )

    async def _post(self, url: str, payload: dict, *, operation: str) -> httpx.Response:
        with timer() as elapsed:
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(url, json=payload)
            except httpx.TimeoutException as exc:
                raise ResearchUnavailableError(
                    f"Tavily {operation} timed out after {self._timeout_seconds}s."
                ) from exc
            except httpx.HTTPError as exc:
                raise ResearchUnavailableError(
                    f"Tavily {operation} failed due to a network error ({type(exc).__name__})."
                ) from exc

        # A response was received (whether success or a Tavily-side error) —
        # that's a completed API call, so it's accounted for either way.
        # is_model_call=False (v0.1.2.7 Phase 8): a Tavily search/extract is
        # a retrieval call, never an LLM completion — it must never be
        # counted toward worker_model_calls in app/orchestration/executor.py.
        record_usage(
            ModelUsage(provider=self.name, model=operation, elapsed_ms=elapsed(), is_model_call=False)
        )
        self._raise_for_status(response, operation=operation)
        return response

    def _raise_for_status(self, response: httpx.Response, *, operation: str) -> None:
        if response.status_code == 401:
            logger.warning("tavily_auth_failed", operation=operation, status_code=401)
            raise ResearchUnavailableError("Tavily authentication failed: check TAVILY_API_KEY.")
        if response.status_code == 429:
            logger.warning("tavily_rate_limited", operation=operation, status_code=429)
            raise ResearchUnavailableError("Tavily rate limit or quota exceeded.")
        if response.status_code >= 400:
            logger.warning("tavily_request_failed", operation=operation, status_code=response.status_code)
            raise ResearchUnavailableError(
                f"Tavily {operation} request failed with status {response.status_code}."
            )

    def _parse_json(self, response: httpx.Response, *, operation: str) -> dict:
        try:
            data = response.json()
        except ValueError as exc:
            raise ResearchUnavailableError(f"Tavily {operation} returned a malformed response.") from exc
        if not isinstance(data, dict):
            raise ResearchUnavailableError(f"Tavily {operation} returned an unexpected response shape.")
        return data


def get_default_research_provider() -> ResearchProvider:
    settings = get_settings()
    mode = settings.research_provider.strip().lower()

    if mode == "dev":
        return DevResearchProvider()
    if mode == "mock":
        return MockResearchProvider()
    if mode == "tavily":
        if not settings.tavily_api_key:
            raise ResearchUnavailableError(
                "RESEARCH_PROVIDER=tavily but TAVILY_API_KEY is not set. Set TAVILY_API_KEY "
                "in your environment/.env to use the live Tavily provider."
            )
        return TavilyResearchProvider(
            api_key=settings.tavily_api_key, search_depth=settings.tavily_search_depth
        )
    if mode == "live":
        raise ResearchUnavailableError(
            "RESEARCH_PROVIDER=live but no live web-search vendor is wired up yet. "
            "Choose a vendor (e.g. Tavily — set RESEARCH_PROVIDER=tavily, Brave Search API, "
            "Bing Web Search, SerpAPI, or You.com), implement it against "
            "app.tools.research_tools.ResearchProvider using app.tools.url_safety for "
            "fetch()'s safety checks, then set RESEARCH_PROVIDER accordingly."
        )
    raise ResearchUnavailableError(
        f"Unknown RESEARCH_PROVIDER '{settings.research_provider}'. "
        "Expected 'dev', 'mock', 'tavily', or 'live'."
    )
