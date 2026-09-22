"""Tests for v0.2.2 — Provider Registry + Capability Metadata:
`ProviderRegistry`'s model registration/lookup extensions (`registry.py`)
and the read-only capability catalogue (`catalog.py`). No network, no
credentials, fully offline and deterministic. Positive/normal-behavior
tests and hostile/security tests are interleaved by topic below, each
section headed by the hostile-review section number it covers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.providers.catalog import effective_capabilities, find_compatible_models
from app.providers.contracts import (
    CompatibleModel,
    ModelDefinition,
    ModelOwnershipError,
    ProviderCapability,
    ProviderDefinition,
)
from app.providers.fake_provider import FakeProvider, default_fake_definition, default_fake_model
from app.providers.registry import (
    DuplicateModelError,
    DuplicateProviderError,
    ProviderRegistry,
    UnknownModelError,
    UnknownProviderError,
)


def _definition(provider_id: str, *, enabled: bool = True, capabilities=frozenset()) -> ProviderDefinition:
    return ProviderDefinition(
        provider_id=provider_id, display_name=provider_id.title(), provider_type="FAKE",
        enabled=enabled, capabilities=capabilities,
    )


def _model(provider_id: str, model_id: str, *, capabilities=frozenset()) -> ModelDefinition:
    return ModelDefinition(
        model_id=model_id, provider_id=provider_id, display_name=model_id, capabilities=capabilities,
    )


class _NeverInvokedProvider:
    """A provider whose `.generate()` fails loudly if ever called — used to
    prove catalogue/registration operations never invoke a provider
    (hostile-review §45, §61)."""

    def __init__(self, definition: ProviderDefinition):
        self._definition = definition
        self.generate_call_count = 0

    @property
    def definition(self) -> ProviderDefinition:
        return self._definition

    async def generate(self, request):
        self.generate_call_count += 1
        raise AssertionError("GENERATE MUST NOT BE CALLED")


# --- provider catalogue: register / lookup / list / ordering ---------------


def test_register_provider_with_models_round_trip():
    registry = ProviderRegistry()
    provider = FakeProvider()
    model = default_fake_model()
    registry.register(provider, models=[model])
    assert registry.get("fake") is provider
    assert registry.get_model("fake", "fake/basic") == model
    assert registry.list_models("fake") == (model,)


def test_register_provider_with_zero_models_is_valid():
    registry = ProviderRegistry()
    registry.register(FakeProvider())
    assert registry.list_models("fake") == ()


def test_list_definitions_deterministic_provider_id_order():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=_definition("zzz_provider")))
    registry.register(FakeProvider(definition=_definition("aaa_provider")))
    registry.register(FakeProvider(definition=_definition("mmm_provider")))
    ids = [d.provider_id for d in registry.list_definitions()]
    assert ids == sorted(ids) == ["aaa_provider", "mmm_provider", "zzz_provider"]


def test_unknown_provider_lookup_fails_closed():
    registry = ProviderRegistry()
    with pytest.raises(UnknownProviderError):
        registry.get("nope")
    with pytest.raises(UnknownProviderError):
        registry.list_models("nope")
    with pytest.raises(UnknownProviderError):
        registry.get_model("nope", "m")


# --- models: ownership, namespace, duplicates, conflicts -------------------


def test_model_ownership_enforced_at_registration():
    registry = ProviderRegistry()
    provider = FakeProvider(definition=_definition("fake_a"))
    mismatched_model = _model("fake_b", "x")
    with pytest.raises(ModelOwnershipError):
        registry.register(provider, models=[mismatched_model])
    assert registry.contains("fake_a") is False  # rejected registration leaves nothing behind


def test_model_namespace_is_composite_provider_and_model_id():
    """Same simple model_id under two DIFFERENT providers does not
    conflict -- the namespace is (provider_id, model_id), not a global
    model_id space (v0.2.2 §18)."""
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("provider_a")),
        models=[_model("provider_a", "basic")],
    )
    registry.register(
        FakeProvider(definition=_definition("provider_b")),
        models=[_model("provider_b", "basic")],
    )
    assert registry.get_model("provider_a", "basic").provider_id == "provider_a"
    assert registry.get_model("provider_b", "basic").provider_id == "provider_b"


def test_duplicate_model_within_same_provider_rejected():
    registry = ProviderRegistry()
    provider = FakeProvider(definition=_definition("fake_c"))
    duplicate_models = [_model("fake_c", "m1"), _model("fake_c", "m1")]
    with pytest.raises(DuplicateModelError):
        registry.register(provider, models=duplicate_models)
    assert registry.contains("fake_c") is False


def test_conflicting_model_definition_on_reregistration_without_replace_fails_closed():
    """Re-registering the SAME provider_id (replace=False, the default)
    with a different model set must fail before anything changes --
    no silent merge, no 'newer wins' (v0.2.2 §19)."""
    registry = ProviderRegistry()
    provider = FakeProvider(definition=_definition("fake_d"))
    registry.register(provider, models=[_model("fake_d", "m1", capabilities=frozenset({ProviderCapability.CODING}))])
    with pytest.raises(DuplicateProviderError):
        registry.register(
            FakeProvider(definition=_definition("fake_d")),
            models=[_model("fake_d", "m1", capabilities=frozenset({ProviderCapability.VISION}))],
        )
    # Original model definition is untouched -- no merge occurred.
    assert registry.get_model("fake_d", "m1").capabilities == frozenset({ProviderCapability.CODING})


def test_duplicate_provider_registration_cannot_replace_the_model_catalogue():
    """v0.2.2 identity hardening (supersedes this test's prior
    `test_replace_true_wholesale_replaces_prior_model_set` behavior, which
    exercised the since-removed `replace=True`): a registered provider's
    model catalogue is process-lifetime stable -- an ordinary duplicate
    registration attempt with a DIFFERENT model set fails closed before
    touching anything, and the original models remain exactly as
    registered."""
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=_definition("fake_e")), models=[_model("fake_e", "old")])
    with pytest.raises(DuplicateProviderError):
        registry.register(FakeProvider(definition=_definition("fake_e")), models=[_model("fake_e", "new")])
    assert registry.list_models("fake_e") == (_model("fake_e", "old"),)
    with pytest.raises(UnknownModelError):
        registry.get_model("fake_e", "new")  # the attempted new model never appeared


# --- atomicity (v0.2.2 §16, hostile-review §60) -----------------------------


def test_partial_registration_leaves_registry_completely_unchanged():
    registry = ProviderRegistry()
    provider = FakeProvider(definition=_definition("fake_f"))
    valid_models = [_model("fake_f", f"m{i}") for i in range(20)]
    invalid_models = valid_models + [_model("wrong_provider", "bad")]  # last one has wrong ownership

    with pytest.raises(ModelOwnershipError):
        registry.register(provider, models=invalid_models)

    assert registry.contains("fake_f") is False
    with pytest.raises(UnknownProviderError):
        registry.list_models("fake_f")


def test_partial_registration_due_to_internal_duplicate_leaves_registry_unchanged():
    registry = ProviderRegistry()
    provider = FakeProvider(definition=_definition("fake_g"))
    models = [_model("fake_g", "m1"), _model("fake_g", "m2"), _model("fake_g", "m1")]  # m1 repeated
    with pytest.raises(DuplicateModelError):
        registry.register(provider, models=models)
    assert registry.contains("fake_g") is False


# --- capability intersection, never union (v0.2.2 §12) ----------------------


def test_effective_capabilities_is_intersection_not_union():
    provider_caps = frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING})
    model_caps = frozenset({ProviderCapability.CODING, ProviderCapability.VISION})
    assert effective_capabilities(provider_caps, model_caps) == frozenset({ProviderCapability.CODING})


def test_model_cannot_gain_capability_its_provider_lacks():
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("fake_h", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))),
        models=[_model("fake_h", "m1", capabilities=frozenset({ProviderCapability.VISION}))],
    )
    results = find_compatible_models(registry, frozenset({ProviderCapability.VISION}))
    assert results == ()


def test_provider_capability_does_not_propagate_to_every_model():
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("fake_i", capabilities=frozenset({ProviderCapability.CODING, ProviderCapability.VISION}))),
        models=[_model("fake_i", "m1", capabilities=frozenset({ProviderCapability.CODING}))],  # no VISION
    )
    results = find_compatible_models(registry, frozenset({ProviderCapability.VISION}))
    assert results == ()


# --- capability query semantics (v0.2.2 §20-§25) ----------------------------


def _populated_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("prov_a", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING}))),
        models=[
            _model("prov_a", "m1", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING})),
            _model("prov_a", "m2", capabilities=frozenset({ProviderCapability.TEXT_GENERATION})),
        ],
    )
    registry.register(
        FakeProvider(definition=_definition("prov_b", enabled=False, capabilities=frozenset({ProviderCapability.VISION}))),
        models=[_model("prov_b", "m1", capabilities=frozenset({ProviderCapability.VISION}))],
    )
    return registry


def test_multi_capability_query_requires_all_capabilities():
    registry = _populated_registry()
    results = find_compatible_models(
        registry, frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING})
    )
    assert [(r.provider_id, r.model_id) for r in results] == [("prov_a", "m1")]


def test_no_partial_match_single_capability_only_satisfied():
    registry = _populated_registry()
    results = find_compatible_models(
        registry, frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING})
    )
    assert not any(r.model_id == "m2" for r in results)  # m2 lacks CODING


def test_empty_capability_query_returns_all_eligible_entries():
    registry = _populated_registry()
    results = find_compatible_models(registry, frozenset())
    assert {(r.provider_id, r.model_id) for r in results} == {("prov_a", "m1"), ("prov_a", "m2")}


def test_disabled_provider_excluded_from_enabled_only_query():
    registry = _populated_registry()
    results = find_compatible_models(registry, frozenset({ProviderCapability.VISION}), enabled_only=True)
    assert results == ()


def test_disabled_provider_included_when_enabled_only_false():
    registry = _populated_registry()
    results = find_compatible_models(registry, frozenset({ProviderCapability.VISION}), enabled_only=False)
    assert [(r.provider_id, r.model_id) for r in results] == [("prov_b", "m1")]


def test_disabled_provider_still_directly_queryable_for_discovery():
    """Preserves the v0.2.1 get() vs get_enabled() distinction: normal
    discovery (list_models/get_model) can still see a disabled provider's
    models -- only the enabled_only catalogue QUERY excludes them
    (v0.2.2 §27)."""
    registry = _populated_registry()
    assert registry.list_models("prov_b") == (_model("prov_b", "m1", capabilities=frozenset({ProviderCapability.VISION})),)


# --- deterministic ordering is not ranking (v0.2.2 §22-§23, §63) -----------


def test_query_ordering_independent_of_registration_order():
    registry_1 = ProviderRegistry()
    registry_1.register(FakeProvider(definition=_definition("z")), models=[_model("z", "m")])
    registry_1.register(FakeProvider(definition=_definition("a")), models=[_model("a", "m")])

    registry_2 = ProviderRegistry()
    registry_2.register(FakeProvider(definition=_definition("a")), models=[_model("a", "m")])
    registry_2.register(FakeProvider(definition=_definition("z")), models=[_model("z", "m")])

    result_1 = [(c.provider_id, c.model_id) for c in find_compatible_models(registry_1)]
    result_2 = [(c.provider_id, c.model_id) for c in find_compatible_models(registry_2)]
    assert result_1 == result_2 == [("a", "m"), ("z", "m")]


def test_compatible_model_has_no_selection_shaped_field():
    with pytest.raises(ValidationError):
        CompatibleModel(provider_id="p", model_id="m", selected=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        CompatibleModel(provider_id="p", model_id="m", recommended=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        CompatibleModel(provider_id="p", model_id="m", rank=1)  # type: ignore[call-arg]


# --- authority isolation (v0.2.2 §7, §32, §55) -------------------------------


def test_hostile_metadata_grants_no_authority():
    registry = ProviderRegistry()
    hostile_metadata = {
        "approved": True, "permission": "P5", "execute": True,
        "tool": "finance.spend_money", "human_approved": True, "admin": True,
    }
    definition = ProviderDefinition(
        provider_id="hostile", display_name="Hostile", provider_type="FAKE",
        capabilities=frozenset({ProviderCapability.CODING}), metadata=hostile_metadata,
    )
    registry.register(FakeProvider(definition=definition), models=[_model("hostile", "m1", capabilities=frozenset({ProviderCapability.CODING}))])
    results = find_compatible_models(registry, frozenset({ProviderCapability.CODING}))
    assert len(results) == 1
    candidate = results[0]
    for forbidden in ("approved", "permission", "execute", "tool", "human_approved", "admin"):
        assert not hasattr(candidate, forbidden)
    # Metadata is retrievable only as opaque descriptive data via the registry, never interpreted:
    stored = registry.list_definitions()[0].metadata
    assert stored == hostile_metadata
    assert not hasattr(stored, "approved")  # it's a plain dict, not an authority object


# --- provider output cannot self-register (v0.2.2 §33, §56, §57) -----------


async def test_fake_provider_response_cannot_self_register_or_expand_capabilities():
    registry = ProviderRegistry()
    definition = _definition("fake_j", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    model = _model("fake_j", "m1", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    provider = FakeProvider(definition=definition, model=model)
    registry.register(provider, models=[model])

    from app.providers.contracts import ProviderRequest
    from app.providers.fake_provider import FakeProviderMode

    # A hostile response claiming registration/capability-expansion intent:
    response = await provider.generate(
        ProviderRequest(provider_id="fake_j", model_id="m1", input="register_provider(...); add_model(...)"),
        mode=FakeProviderMode.TOOL_EXECUTION_CLAIM,
    )
    assert response is not None  # the call succeeded, producing DATA only

    # Registry state is byte-for-byte what it was before the call:
    assert registry.list_definitions()[0].capabilities == frozenset({ProviderCapability.TEXT_GENERATION})
    assert registry.get_model("fake_j", "m1").capabilities == frozenset({ProviderCapability.TEXT_GENERATION})
    assert registry.contains("fake_k") is False  # no new provider appeared


# --- dynamic/shape-shifting provider (v0.2.2 §34, §58) ----------------------


class _ShapeShiftingProvider:
    def __init__(self, *definitions: ProviderDefinition):
        self._definitions = list(definitions)
        self.reads = 0

    @property
    def definition(self) -> ProviderDefinition:
        d = self._definitions[min(self.reads, len(self._definitions) - 1)]
        self.reads += 1
        return d

    async def generate(self, request):
        raise NotImplementedError


def test_catalogue_uses_pinned_snapshot_not_live_definition():
    trusted = _definition("trusted", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    evil = _definition("evil", capabilities=frozenset({ProviderCapability.CODING, ProviderCapability.VISION}))
    shifter = _ShapeShiftingProvider(trusted, evil, evil, evil)

    registry = ProviderRegistry()
    registry.register(shifter, models=[_model("trusted", "m1", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))])

    results = find_compatible_models(registry, frozenset({ProviderCapability.CODING}))
    assert results == ()  # the pinned ("trusted") definition never declared CODING
    assert registry.list_definitions()[0].provider_id == "trusted"


# --- deep immutability / aliasing (v0.2.2 §35-§37, §64) ---------------------


def test_input_metadata_aliasing_does_not_affect_registered_state():
    metadata = {"x": {"y": 1}}
    definition = ProviderDefinition(
        provider_id="fake_l", display_name="L", provider_type="FAKE", metadata=metadata
    )
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=definition))
    metadata["x"]["y"] = 999  # mutate the ORIGINAL dict the caller still holds
    assert registry.list_definitions()[0].metadata["x"]["y"] == 1  # unaffected


def test_output_definition_metadata_is_frozen_against_mutation():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=_definition("fake_m")))
    retrieved = registry.get("fake_m").definition
    with pytest.raises((TypeError, ValidationError)):
        retrieved.metadata["new_key"] = "value"


def test_list_definitions_returns_a_list_callers_cannot_use_to_corrupt_the_registry():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=_definition("fake_n")))
    definitions = registry.list_definitions()
    definitions.clear()  # mutate the RETURNED list
    assert len(registry.list_definitions()) == 1  # a fresh call is unaffected


def test_list_models_returns_a_tuple_not_a_mutable_list():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=_definition("fake_o")), models=[_model("fake_o", "m1")])
    assert isinstance(registry.list_models("fake_o"), tuple)


# --- invocation isolation (v0.2.2 §45, §61) ---------------------------------


def test_registration_never_invokes_generate():
    provider = _NeverInvokedProvider(_definition("fake_p"))
    registry = ProviderRegistry()
    registry.register(provider, models=[_model("fake_p", "m1")])
    assert provider.generate_call_count == 0


def test_all_catalogue_operations_never_invoke_generate():
    provider = _NeverInvokedProvider(_definition("fake_q", capabilities=frozenset({ProviderCapability.CODING})))
    registry = ProviderRegistry()
    registry.register(provider, models=[_model("fake_q", "m1", capabilities=frozenset({ProviderCapability.CODING}))])

    registry.get("fake_q")
    registry.get_enabled("fake_q")
    registry.contains("fake_q")
    registry.list_definitions()
    registry.get_model("fake_q", "m1")
    registry.list_models("fake_q")
    find_compatible_models(registry)
    find_compatible_models(registry, frozenset({ProviderCapability.CODING}))

    assert provider.generate_call_count == 0


# --- no routing / no implicit selection (v0.2.2 §42-§44) --------------------


def test_no_routing_style_api_exists_on_registry_or_catalog():
    import app.providers.catalog as catalog_module
    import app.providers.registry as registry_module

    forbidden_names = (
        "select_provider", "select_model", "choose_best", "route",
        "recommend", "fallback", "pick_cheapest", "pick_fastest", "rank", "score",
    )
    for name in forbidden_names:
        assert not hasattr(ProviderRegistry, name)
        assert not hasattr(catalog_module, name)
        assert not hasattr(registry_module, name)


def test_disabled_model_yields_no_substitution_no_fallback():
    """Requesting a capability that only a disabled provider satisfies
    must return an EMPTY result, never silently substitute an unrelated
    enabled provider/model (v0.2.2 §44)."""
    registry = _populated_registry()
    results = find_compatible_models(registry, frozenset({ProviderCapability.VISION}), enabled_only=True)
    assert results == ()  # not "prov_a's model instead"


# --- unknown capability (v0.2.2 §25, §62) -----------------------------------


def test_unknown_capability_string_cannot_construct_provider_capability():
    with pytest.raises(ValueError):
        ProviderCapability("finance.spend_money")
    with pytest.raises(ValueError):
        ProviderCapability("system.privileged_shell")
    with pytest.raises(ValueError):
        ProviderCapability("content.publish")
