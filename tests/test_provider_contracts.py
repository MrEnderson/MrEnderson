"""Positive contract tests for app.providers.contracts / request_hash
(v0.2.1). No network, no credentials — see app/providers/__init__.py."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.providers.contracts import (
    ModelDefinition,
    ProviderCapability,
    ProviderDefinition,
    ProviderRequest,
    ProviderResponse,
    UsageInfo,
)
from app.providers.request_hash import (
    canonical_request_payload,
    canonical_response_payload,
    compute_request_hash,
    compute_response_hash,
)


def test_valid_provider_definition():
    definition = ProviderDefinition(
        provider_id="fake",
        display_name="Fake Test Provider",
        provider_type="FAKE",
        capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
    )
    assert definition.provider_id == "fake"
    assert definition.enabled is True
    assert definition.privacy_classification == "INTERNAL"


def test_valid_model_definition():
    model = ModelDefinition(
        model_id="fake/basic",
        provider_id="fake",
        display_name="Fake Basic Model",
        capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.STRUCTURED_OUTPUT}),
        supports_structured_output=True,
    )
    assert ProviderCapability.STRUCTURED_OUTPUT in model.capabilities


def test_capabilities_represented_consistently_as_enum_members():
    model = ModelDefinition(
        model_id="fake/basic", provider_id="fake", display_name="Fake",
        capabilities=frozenset({ProviderCapability.CODING, "VISION"}),
    )
    assert model.capabilities == frozenset({ProviderCapability.CODING, ProviderCapability.VISION})


def test_valid_provider_request():
    request = ProviderRequest(provider_id="fake", model_id="fake/basic", input="hello")
    assert request.request_id
    assert request.task_class == "general"


def test_valid_provider_response():
    response = ProviderResponse(
        request_id="req-1", provider_id="fake", model_id="fake/basic", content="hi"
    )
    assert response.content == "hi"
    assert response.trusted is False


def test_usage_metadata_distinguishes_provider_vs_jarvis_cost():
    usage = UsageInfo(provider_reported_input_tokens=10, provider_reported_output_tokens=5)
    assert usage.provider_reported_total_tokens is None
    assert usage.jarvis_calculated_cost is None


def test_blank_identity_fields_rejected():
    with pytest.raises(ValidationError):
        ProviderDefinition(provider_id="   ", display_name="x", provider_type="FAKE")
    with pytest.raises(ValidationError):
        ProviderRequest(provider_id="fake", model_id="", input="hi")


def test_request_hash_deterministic_for_same_semantic_content():
    a = ProviderRequest(provider_id="fake", model_id="fake/basic", input="same input")
    b = ProviderRequest(provider_id="fake", model_id="fake/basic", input="same input")
    # request_id/created_at differ, but the semantic content is identical.
    assert a.request_id != b.request_id
    assert compute_request_hash(a) == compute_request_hash(b)


def test_request_hash_changes_when_semantic_content_changes():
    a = ProviderRequest(provider_id="fake", model_id="fake/basic", input="input A")
    b = ProviderRequest(provider_id="fake", model_id="fake/basic", input="input B")
    assert compute_request_hash(a) != compute_request_hash(b)


def test_request_hash_excludes_volatile_fields():
    payload = canonical_request_payload(
        ProviderRequest(provider_id="fake", model_id="fake/basic", input="hi", metadata={"trace": "x"})
    )
    assert "request_id" not in payload
    assert "created_at" not in payload
    assert "metadata" not in payload


def test_response_hash_deterministic_and_sensitive_to_content():
    a = ProviderResponse(request_id="r1", provider_id="fake", model_id="fake/basic", content="X")
    b = ProviderResponse(request_id="r1", provider_id="fake", model_id="fake/basic", content="X")
    c = ProviderResponse(request_id="r1", provider_id="fake", model_id="fake/basic", content="Y")
    assert compute_response_hash(a) == compute_response_hash(b)
    assert compute_response_hash(a) != compute_response_hash(c)
    payload = canonical_response_payload(a)
    assert "created_at" not in payload
    assert "provider_metadata" not in payload
