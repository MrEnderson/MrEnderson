"""Shared test fixtures. Every test gets an isolated temp-file SQLite database —
tests never touch the developer's jarvis.db, and never require a live OpenAI key."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.agents.providers import MockProvider
from app.agents.registry import AgentRegistry, build_default_registry
from app.config.settings import get_settings
from app.database import connection as db_connection


@pytest.fixture(autouse=True)
def _safe_research_provider_env(monkeypatch):
    """The developer's real .env may select a live ResearchProvider (e.g.
    RESEARCH_PROVIDER=tavily with a real TAVILY_API_KEY) — no test may ever
    depend on that. Force the safe, no-network default for every test in the
    suite; a test that specifically exercises another RESEARCH_PROVIDER value
    (see tests/test_research_provider.py) overrides this itself afterwards,
    same as MODEL_PROVIDER is forced to mock in tests/test_api.py's `client`
    fixture. monkeypatch.delenv() alone is not enough — pydantic-settings
    falls back to reading .env for any key absent from the process
    environment — so this sets an explicit override rather than deleting.
    """
    monkeypatch.setenv("RESEARCH_PROVIDER", "dev")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def session_factory(tmp_path, monkeypatch):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    await db_connection.reset_engine()

    await db_connection.init_db(url)
    factory = db_connection.get_session_factory(url)

    yield factory

    await db_connection.reset_engine()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


@pytest.fixture
def registry() -> AgentRegistry:
    return build_default_registry()


@pytest.fixture
def provider() -> MockProvider:
    return MockProvider()
