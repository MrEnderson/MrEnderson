"""Provider selection tests. These must never make a real network call — they only
verify that MODEL_PROVIDER + the matching API key select the right ModelProvider
class, and that missing credentials fall back to MockProvider.

Constructing OpenAIProvider/AnthropicProvider only builds an SDK client object; the
SDKs do not perform any I/O until a request method is actually called, so it is safe
to instantiate them here with fake keys.
"""
from __future__ import annotations

import pytest

from app.agents.providers import (
    AnthropicProvider,
    MockProvider,
    ModelProviderError,
    OpenAIProvider,
    get_default_provider,
)
from app.config.settings import get_settings


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    """Every test here starts from a clean slate, independent of the real .env —
    pydantic-settings falls back to .env for any key not present in the process
    environment, so we must explicitly set (not just delete) each key we care about.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_defaults_to_mock_when_no_credentials(monkeypatch):
    # MODEL_PROVIDER unset -> defaults to "openai"; no key configured -> falls back.
    get_settings.cache_clear()
    assert isinstance(get_default_provider(), MockProvider)


def test_openai_provider_selected_when_configured(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-key")
    get_settings.cache_clear()

    provider = get_default_provider()

    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"


def test_falls_back_to_mock_when_openai_selected_without_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    get_settings.cache_clear()

    assert isinstance(get_default_provider(), MockProvider)


def test_anthropic_provider_selected_when_configured(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    get_settings.cache_clear()

    provider = get_default_provider()

    assert isinstance(provider, AnthropicProvider)
    assert provider.name == "anthropic"


def test_falls_back_to_mock_when_anthropic_selected_without_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    get_settings.cache_clear()

    assert isinstance(get_default_provider(), MockProvider)


def test_model_provider_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ANTHROPIC")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    get_settings.cache_clear()

    assert isinstance(get_default_provider(), AnthropicProvider)


def test_explicit_mock_provider_ignores_configured_keys(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    get_settings.cache_clear()

    assert isinstance(get_default_provider(), MockProvider)


def test_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "not-a-real-provider")
    get_settings.cache_clear()

    with pytest.raises(ModelProviderError):
        get_default_provider()


def test_anthropic_provider_construction_makes_no_network_call():
    provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")
    assert provider.name == "anthropic"


def test_openai_provider_construction_makes_no_network_call():
    provider = OpenAIProvider(api_key="sk-not-a-real-key")
    assert provider.name == "openai"


async def test_anthropic_provider_forwards_model_id_unmodified(monkeypatch):
    """Regression test: AnthropicProvider must send the exact model id it was given
    to the SDK, with no normalization/truncation (e.g. stripping the "claude-"
    prefix or a date suffix) between the caller and the API request."""
    from pydantic import BaseModel

    class Dummy(BaseModel):
        ok: bool

    provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")

    captured: dict = {}

    class FakeResponse:
        parsed_output = Dummy(ok=True)

    async def fake_parse(**kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(provider._client.messages, "parse", fake_parse)

    model_id = "claude-haiku-4-5-20251001"
    result = await provider.complete_structured(
        system_prompt="sys", user_prompt="{}", output_schema=Dummy, model=model_id
    )

    assert isinstance(result, Dummy)
    assert captured["model"] == model_id
