"""Deterministic-behavior tests for FakeProvider (v0.2.1). Hostile/security
scenarios live in tests/test_provider_security.py; this file covers normal
success/failure/interface-conformance behavior only."""
from __future__ import annotations

import pytest

from app.providers.contracts import ProviderRequest
from app.providers.failures import ProviderFailureCategory, ProviderFailureError
from app.providers.fake_provider import FakeProvider, FakeProviderMode
from app.providers.protocol import AIProvider


def _request(**overrides) -> ProviderRequest:
    fields = dict(provider_id="fake", model_id="fake/basic", input="hello")
    fields.update(overrides)
    return ProviderRequest(**fields)


async def test_fake_provider_deterministic_success():
    provider = FakeProvider()
    response = await provider.generate(_request())
    assert response.provider_id == "fake"
    assert response.model_id == "fake/basic"
    assert response.content == "FakeProvider deterministic response."
    assert response.trusted is False


async def test_fake_provider_repeated_calls_are_identical_in_shape():
    provider = FakeProvider()
    r1 = await provider.generate(_request())
    r2 = await provider.generate(_request())
    assert r1.content == r2.content
    assert r1.provider_metadata == r2.provider_metadata


async def test_fake_provider_deterministic_transient_failure():
    provider = FakeProvider(mode=FakeProviderMode.TRANSIENT_FAILURE)
    with pytest.raises(ProviderFailureError) as exc_info:
        await provider.generate(_request())
    assert exc_info.value.failure.category == ProviderFailureCategory.TRANSIENT_PROVIDER_ERROR
    assert exc_info.value.failure.retryable is True


async def test_fake_provider_deterministic_permanent_failure():
    provider = FakeProvider(mode=FakeProviderMode.PERMANENT_FAILURE)
    with pytest.raises(ProviderFailureError) as exc_info:
        await provider.generate(_request())
    assert exc_info.value.failure.category == ProviderFailureCategory.PERMANENT_PROVIDER_ERROR
    assert exc_info.value.failure.retryable is False


async def test_fake_provider_mode_override_per_call():
    provider = FakeProvider(mode=FakeProviderMode.SUCCESS)
    with pytest.raises(ProviderFailureError):
        await provider.generate(_request(), mode=FakeProviderMode.TIMEOUT)
    # Default mode is unaffected by the per-call override.
    response = await provider.generate(_request())
    assert response.content is not None


def test_fake_provider_satisfies_ai_provider_protocol():
    provider = FakeProvider()
    assert isinstance(provider, AIProvider)


async def test_fake_provider_tracks_invocation_history():
    provider = FakeProvider()
    request = _request()
    await provider.generate(request)
    assert provider.invocations == [request]


async def test_fake_provider_unknown_model_fails_closed():
    provider = FakeProvider()
    with pytest.raises(ProviderFailureError) as exc_info:
        await provider.generate(_request(model_id="some/other-model"))
    assert exc_info.value.failure.category == ProviderFailureCategory.UNSUPPORTED_MODEL
