"""Standalone connectivity check for the Tavily research provider.

Makes exactly ONE minimal real search request to the Tavily API to confirm
that RESEARCH_PROVIDER=tavily is configured correctly end-to-end (key present
and valid, TavilyResearchProvider wired up, results parse correctly). It does
NOT run the Jarvis orchestration pipeline (planner/research/strategy/QA/
execution) and does NOT touch the database — it talks to
TavilyResearchProvider directly, the same way scripts/test_anthropic_connection.py
talks to AnthropicProvider directly.

Bounded by design: one search call, a small max_results, "basic" search
depth. The API key is never printed or logged — only its presence is
checked. Only result titles and URLs are printed, never full content/excerpts.

Usage:
    python scripts/test_tavily_connection.py

Exit code 0 = the real Tavily API request succeeded.
Exit code 1 = misconfiguration or a failed API request (reason printed, key never printed).

NOTE: this script is meant to be run manually by a human when they choose to
spend one real Tavily API call verifying connectivity. It is never invoked
automatically by the test suite (see tests/test_tavily_provider.py, which
mocks the HTTP boundary instead) or by any other script in this project.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config.settings import get_settings  # noqa: E402
from app.tools.research_tools import ResearchUnavailableError, TavilyResearchProvider  # noqa: E402

MAX_RESULTS = 3
QUERY = "Anthropic Claude AI"


async def main() -> int:
    settings = get_settings()

    if settings.research_provider.strip().lower() != "tavily":
        print(
            "FAILURE: RESEARCH_PROVIDER is "
            f"'{settings.research_provider}', not 'tavily'. Set RESEARCH_PROVIDER=tavily in .env."
        )
        return 1

    if not settings.tavily_api_key:
        print("FAILURE: TAVILY_API_KEY is not set. (Key value is never printed.)")
        return 1

    print("RESEARCH_PROVIDER: tavily")
    print("TAVILY_API_KEY: configured (value withheld)")
    print(f"Search depth: {settings.tavily_search_depth}")
    print(f"Query: {QUERY!r} (max_results={MAX_RESULTS})")
    print()

    provider = TavilyResearchProvider(
        api_key=settings.tavily_api_key, search_depth=settings.tavily_search_depth
    )

    try:
        results = await provider.search(QUERY, max_results=MAX_RESULTS)
    except ResearchUnavailableError as e:
        # TavilyResearchProvider already turns authentication failures, rate
        # limits/quota errors, timeouts, and malformed responses into a clear
        # ResearchUnavailableError message — see app/tools/research_tools.py.
        print(f"FAILURE: {e}")
        return 1

    if not results:
        print("FAILURE: Tavily returned zero results for the test query.")
        return 1

    print(f"SUCCESS: Real Tavily API request completed and returned {len(results)} result(s).")
    print()
    for i, r in enumerate(results, start=1):
        print(f"  {i}. {r.title}")
        print(f"     {r.url}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
