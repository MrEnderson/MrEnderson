"""Regression tests for the v0.2.1 hostile IMPLEMENTATION review (distinct
from tests/test_provider_security.py, which covers the earlier hostile
CONTRACT/DESIGN review's scenarios). Each test here pins a specific
production-code finding from that review and its remediation — see
docs/V0_2_1_PROVIDER_ABSTRACTION.md's "Deep immutability" and "Trust
model" sections. No network, no credentials."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.providers.contracts import (
    ModelDefinition,
    ProviderCapability,
    ProviderDefinition,
    ProviderRequest,
    ProviderResponse,
    validate_identifier,
)
from app.providers.correlation import validate_failure_correlation, validate_response_correlation
from app.providers.failures import (
    ProviderFailure,
    ProviderFailureCategory,
    ProviderFailureError,
    RETRYABLE_CATEGORIES,
)
from app.providers.fake_provider import FakeProvider, FakeProviderMode, ModelOwnershipError, default_fake_model
from app.providers.registry import ProviderRegistry
from app.providers.request_hash import compute_request_hash, compute_response_hash


def _request(**overrides) -> ProviderRequest:
    fields = dict(provider_id="fake", model_id="fake/basic", input="hello")
    fields.update(overrides)
    return ProviderRequest(**fields)


# --- deep immutability (hostile review §4/§41) ------------------------------


def test_nested_generation_parameters_mutation_raises_and_hash_is_stable():
    request = _request(generation_parameters={"temperature": 0.5, "nested": {"a": [1, 2, 3]}})
    hash_before = compute_request_hash(request)

    with pytest.raises(TypeError):
        request.generation_parameters["temperature"] = 999.0
    with pytest.raises(TypeError):
        request.generation_parameters["nested"]["a"].append(4)

    assert compute_request_hash(request) == hash_before


def test_nested_structured_output_mutation_raises_and_hash_is_stable():
    response = ProviderResponse(
        request_id="r1", provider_id="fake", model_id="fake/basic",
        structured_output={"a": {"b": [1, 2]}},
    )
    hash_before = compute_response_hash(response)

    with pytest.raises(TypeError):
        response.structured_output["a"]["b"].append(3)
    with pytest.raises(TypeError):
        response.structured_output["a"]["b"] = "replaced"

    assert compute_response_hash(response) == hash_before


def test_nested_metadata_and_provider_metadata_are_frozen():
    request = _request(metadata={"trace": {"nested": ["x"]}})
    with pytest.raises(TypeError):
        request.metadata["trace"]["nested"].append("y")

    response = ProviderResponse(
        request_id="r1", provider_id="fake", model_id="fake/basic",
        provider_metadata={"tags": ["a", "b"]},
    )
    with pytest.raises(TypeError):
        response.provider_metadata["tags"].append("c")


def test_default_valued_dict_fields_are_also_frozen_not_only_explicit_ones():
    """v0.2.2 discovery: Pydantic does NOT run field_validator on a field's
    default_factory value unless the model sets validate_default=True — so
    every dict field above was ONLY frozen when a caller explicitly passed
    a value; the (far more common) case of leaving metadata/
    generation_parameters/details at their empty-dict default was silently
    still mutable. Fixed by adding validate_default=True to the shared
    _FROZEN ConfigDict in both contracts.py and failures.py. This test
    constructs every affected type with ZERO explicit dict arguments."""
    definition = ProviderDefinition(provider_id="x", display_name="X", provider_type="FAKE")
    with pytest.raises(TypeError):
        definition.metadata["k"] = "v"

    model = ModelDefinition(model_id="m", provider_id="x", display_name="M")
    with pytest.raises(TypeError):
        model.metadata["k"] = "v"

    request = ProviderRequest(provider_id="x", model_id="m", input="hi")
    with pytest.raises(TypeError):
        request.generation_parameters["k"] = "v"
    with pytest.raises(TypeError):
        request.metadata["k"] = "v"

    response = ProviderResponse(request_id="r1", provider_id="x", model_id="m")
    with pytest.raises(TypeError):
        response.provider_metadata["k"] = "v"

    failure = ProviderFailure(category=ProviderFailureCategory.TIMEOUT, message="x", provider_id="x")
    with pytest.raises(TypeError):
        failure.details["k"] = "v"


def test_provider_failure_details_are_frozen():
    failure = ProviderFailure(
        category=ProviderFailureCategory.PERMANENT_PROVIDER_ERROR,
        message="x",
        provider_id="fake",
        details={"nested": {"list": [1, 2]}},
    )
    with pytest.raises(TypeError):
        failure.details["nested"]["list"].append(3)


# --- B-11: inherited in-place operators (|= on dict, *= on list) ------------


def test_b11_in_place_operators_cannot_mutate_request_at_any_depth_and_hash_is_stable():
    """B-11 (found during the v0.2.4 hostile review): `dict.__ior__` and
    `list.__imul__` do not route through the blocked `update`/`extend`, so
    `|=` / `*=` silently mutated "frozen" generation_parameters and changed
    compute_request_hash. Every reachable frozen level is attacked."""
    request = _request(
        generation_parameters={"temperature": 0.0, "stop": ["x"], "nested": {"inner": [1, 2], "k": "v"}},
    )
    twin = request.model_copy()
    hash_before = compute_request_hash(request)
    dump_before = request.model_dump(mode="json")

    top = request.generation_parameters
    with pytest.raises(TypeError):
        top |= {"temperature": 2.0}
    nested = request.generation_parameters["nested"]
    with pytest.raises(TypeError):
        nested |= {"k": "hijacked"}
    stop = request.generation_parameters["stop"]
    with pytest.raises(TypeError):
        stop *= 2
    inner = request.generation_parameters["nested"]["inner"]
    with pytest.raises(TypeError):
        inner *= 3
    with pytest.raises(TypeError):
        inner += [3]

    assert request.generation_parameters == {"temperature": 0.0, "stop": ["x"], "nested": {"inner": [1, 2], "k": "v"}}
    assert compute_request_hash(request) == hash_before
    assert request.model_dump(mode="json") == dump_before
    assert request == twin


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.__setitem__("x", 1), lambda d: d.__delitem__("a"), lambda d: d.update(x=1),
        lambda d: d.setdefault("x", 1), lambda d: d.pop("a"), lambda d: d.popitem(),
        lambda d: d.clear(), lambda d: d.__ior__({"x": 1}),
    ],
    ids=["setitem", "delitem", "update", "setdefault", "pop", "popitem", "clear", "ior"],
)
def test_b11_frozen_dict_mutation_matrix(mutate):
    request = _request(generation_parameters={"a": 1})
    with pytest.raises(TypeError):
        mutate(request.generation_parameters)
    assert request.generation_parameters == {"a": 1}


@pytest.mark.parametrize(
    "mutate",
    [
        lambda l: l.__setitem__(0, 9), lambda l: l.__setitem__(slice(0, 1), [9, 9]), lambda l: l.__delitem__(0),
        lambda l: l.append(9), lambda l: l.extend([9]), lambda l: l.insert(0, 9), lambda l: l.pop(),
        lambda l: l.remove(2), lambda l: l.clear(), lambda l: l.reverse(), lambda l: l.sort(),
        lambda l: l.__iadd__([9]), lambda l: l.__imul__(2),
    ],
    ids=["setitem", "setslice", "delitem", "append", "extend", "insert", "pop", "remove", "clear",
         "reverse", "sort", "iadd", "imul"],
)
def test_b11_frozen_list_mutation_matrix(mutate):
    request = _request(generation_parameters={"items": [2, 1]})
    with pytest.raises(TypeError):
        mutate(request.generation_parameters["items"])
    assert request.generation_parameters["items"] == [2, 1]


def test_b11_in_place_operators_blocked_on_every_deep_frozen_contract():
    definition = ProviderDefinition(provider_id="x", display_name="X", provider_type="FAKE", metadata={"t": [1]})
    model = ModelDefinition(model_id="m", provider_id="x", display_name="M", metadata={"t": [1]})
    response = ProviderResponse(
        request_id="r1", provider_id="x", model_id="m",
        structured_output={"items": [1]}, provider_metadata={"t": [1]},
    )
    failure = ProviderFailure(
        category=ProviderFailureCategory.TIMEOUT, message="x", provider_id="x", details={"t": [1]},
    )
    response_hash = compute_response_hash(response)
    for frozen_mapping in (
        definition.metadata, model.metadata, response.structured_output, response.provider_metadata, failure.details,
    ):
        with pytest.raises(TypeError):
            frozen_mapping |= {"injected": True}
        items = next(iter(frozen_mapping.values()))
        with pytest.raises(TypeError):
            items *= 2
        assert "injected" not in frozen_mapping
        assert len(items) == 1
    assert compute_response_hash(response) == response_hash


def test_b11_non_mutating_operators_and_deep_freeze_behavior_unchanged():
    request = _request(generation_parameters={"a": 1, "items": [1], "nested": {"b": (2, 3)}})
    params = request.generation_parameters
    assert isinstance(params, dict) and isinstance(params["items"], list)
    assert params | {"c": 3} == {"a": 1, "items": [1], "nested": {"b": [2, 3]}, "c": 3}  # new plain dict
    assert params["items"] * 2 == [1, 1] and params["items"] + [2] == [1, 2]  # new plain lists
    assert params == {"a": 1, "items": [1], "nested": {"b": [2, 3]}}
    assert ProviderRequest.model_validate_json(request.model_dump_json()) == request


def test_b11_caller_owned_input_mutation_after_construction_has_no_effect():
    source = {"nested": {"inner": [1]}, "stop": ["x"]}
    request = _request(generation_parameters=source)
    hash_before = compute_request_hash(request)
    source["nested"]["inner"].append(2)
    source["stop"] *= 2
    source |= {"new": 1}
    assert request.generation_parameters == {"nested": {"inner": [1]}, "stop": ["x"]}
    assert compute_request_hash(request) == hash_before


def test_b11_explicit_base_class_calls_are_outside_the_contract():
    """Documents the trust boundary honestly: the frozen containers block
    every ordinary mutation API and operator, but same-process code that
    deliberately calls the base implementation still succeeds. This is
    NOT a protected path; the test pins the documented limitation."""
    from app.providers.frozen import FrozenDict, FrozenList

    mapping = FrozenDict({"a": 1})
    dict.__setitem__(mapping, "a", 2)
    assert mapping["a"] == 2
    sequence = FrozenList([1])
    list.append(sequence, 2)
    assert sequence == [1, 2]


# --- model_copy / model_construct bypass (hostile review §18/§41) ----------


def test_model_copy_bypasses_field_validators_but_stays_frozen():
    """Documents a real, if currently unused, Pydantic-level risk (see
    docs/V0_2_1_PROVIDER_ABSTRACTION.md, "Deep immutability"): `.model_copy
    (update=...)` does NOT re-run field validators. Future code MUST use
    the normal constructor for these types, never model_copy."""
    request = _request()
    copy = request.model_copy(update={"provider_id": ""})
    assert copy.provider_id == ""  # validator was skipped -- an invalid instance exists
    with pytest.raises(ValidationError):
        copy.provider_id = "x"  # the copy is still frozen, at least


def test_model_construct_skips_validation_of_recognized_fields():
    """`.model_construct()` skips field validators for RECOGNIZED fields —
    it can produce an instance with a blank/control-character `request_id`/
    `provider_id` that the normal constructor would reject. (Empirically
    verified this pydantic version's `extra="forbid"` config does at least
    discard a genuinely UNRECOGNIZED kwarg passed to model_construct rather
    than exposing it as a live attribute — see
    test_model_construct_discards_unrecognized_extra_kwarg below — so the
    risk here is narrower than for model_copy: recognized-field validation
    bypass only, not arbitrary attribute injection.)"""
    constructed = ProviderResponse.model_construct(
        request_id="", provider_id="bad\x00id", model_id="fake/basic"
    )
    assert constructed.request_id == ""
    assert constructed.provider_id == "bad\x00id"


def test_model_construct_discards_unrecognized_extra_kwarg():
    """On this Pydantic version, `extra="forbid"` causes model_construct to
    silently discard a kwarg for a field that doesn't exist, rather than
    storing it as a retrievable attribute — do not assume otherwise without
    re-verifying against the Pydantic version in use."""
    constructed = ProviderResponse.model_construct(
        request_id="r1", provider_id="fake", model_id="fake/basic", approved=True
    )
    assert not hasattr(constructed, "approved")
    assert constructed.model_extra is None


# --- registry identity pinning (hostile review §9/§10/§35) -----------------


class _ShapeShiftingProvider:
    """A malicious/buggy AIProvider whose `.definition` returns a
    DIFFERENT ProviderDefinition on every read."""

    def __init__(self, *definitions: ProviderDefinition):
        self._definitions = list(definitions)
        self.reads = 0

    @property
    def definition(self) -> ProviderDefinition:
        d = self._definitions[min(self.reads, len(self._definitions) - 1)]
        self.reads += 1
        return d

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError


def test_registry_pins_identity_at_registration_not_on_every_read():
    trusted = ProviderDefinition(provider_id="trusted", display_name="T", provider_type="FAKE")
    evil = ProviderDefinition(provider_id="evil", display_name="E", provider_type="FAKE")
    shifter = _ShapeShiftingProvider(trusted, evil, evil, evil)

    registry = ProviderRegistry()
    registry.register(shifter)

    assert shifter.reads == 1  # exactly one live read consumed by register()
    assert registry.contains("trusted") is True
    assert registry.contains("evil") is False
    assert registry.get("trusted") is shifter
    assert [d.provider_id for d in registry.list_definitions()] == ["trusted"]
    assert registry.get_enabled("trusted") is shifter  # uses the PINNED definition, not a fresh read


def test_registry_rejects_object_whose_definition_property_raises():
    class Broken:
        @property
        def definition(self):
            raise RuntimeError("boom")

        async def generate(self, request):
            raise NotImplementedError

    registry = ProviderRegistry()
    with pytest.raises(RuntimeError):
        registry.register(Broken())
    assert registry.contains("anything") is False


# --- model ownership (hostile review §13) -----------------------------------


def test_fake_provider_rejects_model_belonging_to_a_different_provider():
    definition = ProviderDefinition(provider_id="fake_a", display_name="A", provider_type="FAKE")
    mismatched_model = ModelDefinition(
        model_id="x", provider_id="fake_b", display_name="X",
        capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
    )
    with pytest.raises(ModelOwnershipError):
        FakeProvider(definition=definition, model=mismatched_model)


def test_fake_provider_default_model_matches_a_custom_definitions_provider_id():
    definition = ProviderDefinition(provider_id="fake_c", display_name="C", provider_type="FAKE")
    provider = FakeProvider(definition=definition)  # no explicit model -- must not raise
    assert provider._model.provider_id == "fake_c"  # noqa: SLF001 (test-only introspection)


# --- capability intersection, never union (hostile review §12) ------------


async def test_capability_must_be_declared_at_both_provider_and_model_level():
    # Model advertises VISION, provider does not.
    definition = ProviderDefinition(
        provider_id="fake", display_name="F", provider_type="FAKE",
        capabilities=frozenset({ProviderCapability.TEXT_GENERATION}),
    )
    model = default_fake_model(capabilities=frozenset({ProviderCapability.VISION}))
    provider = FakeProvider(definition=definition, model=model)
    with pytest.raises(ProviderFailureError) as exc_info:
        await provider.generate(_request(required_capabilities=frozenset({ProviderCapability.VISION})))
    assert exc_info.value.failure.category == ProviderFailureCategory.UNSUPPORTED_CAPABILITY


async def test_capability_declared_by_provider_but_not_model_is_still_unsupported():
    # Inverse: provider advertises CODING, model does not.
    definition = ProviderDefinition(
        provider_id="fake", display_name="F", provider_type="FAKE",
        capabilities=frozenset({ProviderCapability.CODING, ProviderCapability.TEXT_GENERATION}),
    )
    model = default_fake_model(capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    provider = FakeProvider(definition=definition, model=model)
    with pytest.raises(ProviderFailureError) as exc_info:
        await provider.generate(_request(required_capabilities=frozenset({ProviderCapability.CODING})))
    assert exc_info.value.failure.category == ProviderFailureCategory.UNSUPPORTED_CAPABILITY


# --- retryable is derived, not caller-supplied (hostile review §21) --------


def test_retryable_cannot_be_passed_at_construction():
    with pytest.raises(ValidationError):
        ProviderFailure(
            category=ProviderFailureCategory.PERMANENT_PROVIDER_ERROR,
            message="x", provider_id="fake", retryable=True,  # type: ignore[call-arg]
        )


def test_retryable_matches_category_deterministically():
    permanent = ProviderFailure(
        category=ProviderFailureCategory.PERMANENT_PROVIDER_ERROR, message="x", provider_id="fake"
    )
    transient = ProviderFailure(
        category=ProviderFailureCategory.TRANSIENT_PROVIDER_ERROR, message="x", provider_id="fake"
    )
    assert permanent.retryable is False
    assert transient.retryable is True
    assert transient.category in RETRYABLE_CATEGORIES
    assert permanent.category not in RETRYABLE_CATEGORIES


# --- failure-path correlation (hostile review §16) --------------------------


async def test_failure_correlation_catches_spoofed_provider_id():
    request = _request()
    spoofed_failure = ProviderFailureError(
        ProviderFailure(
            category=ProviderFailureCategory.PERMANENT_PROVIDER_ERROR,
            message="x", provider_id="a_different_provider",
        )
    )
    with pytest.raises(ProviderFailureError) as exc_info:
        validate_failure_correlation(request, spoofed_failure)
    assert exc_info.value.failure.category == ProviderFailureCategory.INVALID_RESPONSE


async def test_failure_correlation_allows_none_model_and_request_id():
    """A failure that doesn't ASSERT a model_id/request_id (both are
    optional on ProviderFailure) must not be treated as a mismatch --
    only an explicit, different value should fail closed."""
    request = _request()
    failure = ProviderFailureError(
        ProviderFailure(category=ProviderFailureCategory.TIMEOUT, message="x", provider_id="fake")
    )
    validate_failure_correlation(request, failure)  # must not raise


async def test_failure_correlation_catches_spoofed_model_id():
    request = _request()
    failure = ProviderFailureError(
        ProviderFailure(
            category=ProviderFailureCategory.TIMEOUT, message="x",
            provider_id="fake", model_id="anthropic/claude-privileged",
        )
    )
    with pytest.raises(ProviderFailureError):
        validate_failure_correlation(request, failure)


# --- identifier policy: control chars, whitespace, length (§7/§8/§38) -------


@pytest.mark.parametrize(
    "hostile_id",
    [
        "fake\n",
        "fake\r",
        "fake\x00",
        "fake\x7f",
        "  fake",
        "fake  ",
        "x" * 257,
        "   ",
    ],
)
def test_hostile_identifiers_rejected(hostile_id):
    with pytest.raises(ValidationError):
        ProviderRequest(provider_id=hostile_id, model_id="m", input="hi")


def test_validate_identifier_accepts_a_normal_id():
    assert validate_identifier("fake-provider_1.2") == "fake-provider_1.2"


# --- FakeProviderMode exhaustiveness (hostile review §26) -------------------


async def test_unrecognized_mode_value_fails_loudly_not_silently_success():
    provider = FakeProvider()
    with pytest.raises(TypeError):
        await provider.generate(_request(), mode="NOT_A_REAL_MODE")  # type: ignore[arg-type]


def test_constructing_fake_provider_with_invalid_default_mode_fails_loudly():
    with pytest.raises(TypeError):
        FakeProvider(mode="NOT_A_REAL_MODE")  # type: ignore[arg-type]


@pytest.mark.parametrize("mode", list(FakeProviderMode))
async def test_every_declared_mode_produces_a_deterministic_outcome(mode):
    provider = FakeProvider(mode=mode)
    request = _request()
    # Every mode either raises ProviderFailureError or returns a
    # ProviderResponse -- never anything else, never silently no-ops.
    try:
        response = await provider.generate(request)
        assert isinstance(response, ProviderResponse)
    except ProviderFailureError as exc:
        assert isinstance(exc.failure, ProviderFailure)


# --- redaction: JSON-shaped key:value (hostile review §22) -----------------


@pytest.mark.parametrize(
    "sample",
    [
        '{"api_key": "FAKE_TEST_SECRET_DO_NOT_USE_json"}',
        '{"anthropic_api_key":"FAKE_TEST_SECRET_DO_NOT_USE_vendor"}',
        'PASSWORD:"FAKE_TEST_SECRET_DO_NOT_USE_pw"',
    ],
)
def test_redact_secrets_covers_json_shaped_leaks(sample):
    from app.providers.failures import redact_secrets

    assert "FAKE_TEST_SECRET_DO_NOT_USE" not in redact_secrets(sample)


# --- serialization round-trip preserves identity (hostile review §19) ------


def test_provider_request_round_trips_through_json():
    import json

    request = _request(required_capabilities=frozenset({ProviderCapability.VISION}))
    dumped = json.loads(json.dumps(request.model_dump(mode="json")))
    restored = ProviderRequest.model_validate(dumped)
    assert restored.provider_id == request.provider_id
    assert restored.model_id == request.model_id
    assert restored.required_capabilities == request.required_capabilities
