"""Tests for app.providers.registry.ProviderRegistry (v0.2.1). Identity/
discovery only — no routing, no fallback, no credentials."""
from __future__ import annotations

import pytest

from app.providers.contracts import ProviderCapability, ProviderDefinition
from app.providers.fake_provider import FakeProvider, default_fake_definition
from app.providers.registry import (
    DisabledProviderError,
    DuplicateProviderError,
    InvalidProviderError,
    ProviderRegistry,
    UnknownProviderError,
)


def test_register_and_get_round_trip():
    registry = ProviderRegistry()
    provider = FakeProvider()
    registry.register(provider)
    assert registry.get("fake") is provider


def test_contains_true_after_register():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    assert registry.contains("fake") is True


def test_contains_false_for_unknown():
    registry = ProviderRegistry()
    assert registry.contains("nope") is False


def test_list_definitions_returns_registered_providers():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    definitions = registry.list_definitions()
    assert len(definitions) == 1
    assert definitions[0].provider_id == "fake"


def test_duplicate_provider_id_rejected():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    with pytest.raises(DuplicateProviderError):
        registry.register(FakeProvider())


def test_duplicate_with_replace_true_succeeds():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    replacement = FakeProvider()
    registry.register(replacement, replace=True)
    assert registry.get("fake") is replacement


def test_unknown_provider_lookup_fails_closed():
    registry = ProviderRegistry()
    with pytest.raises(UnknownProviderError):
        registry.get("nope")


def test_registration_does_not_select_or_route():
    """Registering two distinct providers must not create any notion of
    "best"/"default" provider — get() only ever returns exactly what was
    asked for by id (contract §20)."""
    registry = ProviderRegistry()
    a = FakeProvider(definition=default_fake_definition())
    b_definition = ProviderDefinition(
        provider_id="fake_b",
        display_name="Fake Test Provider B",
        provider_type="FAKE",
        capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
    )
    registry.register(a)
    registry.register(FakeProvider(definition=b_definition))
    assert registry.get("fake") is a
    assert not hasattr(registry, "select_best_provider")
    assert not hasattr(registry, "fallback_to_another_provider")


def test_disabled_provider_not_returned_by_get_enabled():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=default_fake_definition(enabled=False)))
    # get() (identity/discovery) still succeeds:
    registry.get("fake")
    with pytest.raises(DisabledProviderError):
        registry.get_enabled("fake")


def test_enabled_provider_returned_by_get_enabled():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=default_fake_definition(enabled=True)))
    assert registry.get_enabled("fake").definition.enabled is True


def test_register_rejects_object_not_implementing_protocol():
    registry = ProviderRegistry()
    with pytest.raises(InvalidProviderError):
        registry.register(object())
