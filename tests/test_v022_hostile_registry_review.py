"""Hostile second-pass review of v0.2.2 — Provider Registry + Capability
Metadata (distinct from tests/test_provider_catalog.py, which covers the
implementation review's own scenarios). This file targets gaps the first
pass left unexercised: `replace=True`'s exact blast radius, atomicity at
every validation position (not just the last one), static isolation of
the registry/catalogue from any authority-granting subsystem, and a fully
JSON-shaped self-registration payload fed through the normal response
path. No network, no credentials, fully offline and deterministic."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.providers.catalog import find_compatible_models
from app.providers.contracts import (
    CompatibleModel,
    ModelDefinition,
    ProviderCapability,
    ProviderDefinition,
    ProviderRequest,
)
from app.providers.fake_provider import FakeProvider, FakeProviderMode
from app.providers.registry import (
    DuplicateProviderError,
    ModelOwnershipError,
    ProviderRegistry,
    UnknownModelError,
)
from pydantic import ValidationError


def _definition(provider_id: str, *, enabled: bool = True, capabilities=frozenset()) -> ProviderDefinition:
    return ProviderDefinition(
        provider_id=provider_id, display_name=provider_id.title(), provider_type="FAKE",
        enabled=enabled, capabilities=capabilities,
    )


def _model(provider_id: str, model_id: str, *, capabilities=frozenset()) -> ModelDefinition:
    return ModelDefinition(
        model_id=model_id, provider_id=provider_id, display_name=model_id, capabilities=capabilities,
    )


def _snapshot(registry: ProviderRegistry) -> tuple:
    """A registry-state fingerprint deep enough to catch a partial
    mutation that `contains()`/`list_definitions()` alone might miss --
    provider identity, definition, and every model's full field set."""
    defs = registry.list_definitions()
    return tuple(
        (
            d.provider_id, d.display_name, d.provider_type, d.enabled,
            d.capabilities, d.privacy_classification, tuple(sorted(d.metadata.items())),
            tuple(
                (m.model_id, m.capabilities, m.context_window, m.supports_structured_output)
                for m in registry.list_models(d.provider_id)
            ),
        )
        for d in defs
    )


# --- identity hardening: replace=True REMOVED, blast radius closed (§4/§38,
# v0.2.2 final hardening pass) -----------------------------------------------
# `replace=True` used to exist on ProviderRegistry (inherited unchanged from
# v0.2.1, mirroring ToolAdapterRegistry/ToolRegistry's own replace=True) and
# a first hostile-review pass confirmed it could -- ONLY via an explicit,
# trusted-caller-supplied keyword, never from provider-supplied data --
# expand capabilities, flip enabled status, substitute the pinned provider
# object, and wholesale-replace context_window/provider_type/model sets on
# an already-registered provider_id. A second, narrower hardening pass then
# decided ProviderRegistry has no demonstrated operational need for runtime
# replacement (unlike ToolAdapterRegistry/ToolRegistry, which DO have real
# call sites -- e.g. disabling a tool adapter -- and are untouched here) and
# REMOVED the parameter entirely: `register()` no longer accepts `replace`
# at all, so none of the attacks below can succeed any more. These tests
# were rewritten from ones that previously proved the (then-intentional)
# blast radius; they now prove that blast radius no longer exists.


def test_duplicate_registration_cannot_expand_capabilities():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=_definition("p", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))))
    with pytest.raises(DuplicateProviderError):
        registry.register(FakeProvider(definition=_definition("p", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING}))))
    assert registry.get("p").definition.capabilities == frozenset({ProviderCapability.TEXT_GENERATION})


def test_duplicate_registration_cannot_change_enabled_status():
    registry = ProviderRegistry()
    registry.register(FakeProvider(definition=_definition("p", enabled=False)))
    with pytest.raises(DuplicateProviderError):
        registry.register(FakeProvider(definition=_definition("p", enabled=True)))
    assert registry.get("p").definition.enabled is False

    registry_2 = ProviderRegistry()
    registry_2.register(FakeProvider(definition=_definition("q", enabled=True)))
    with pytest.raises(DuplicateProviderError):
        registry_2.register(FakeProvider(definition=_definition("q", enabled=False)))
    assert registry_2.get("q").definition.enabled is True


def test_duplicate_registration_cannot_substitute_the_pinned_provider_object():
    registry = ProviderRegistry()
    trusted = FakeProvider(definition=_definition("p"))
    malicious = FakeProvider(definition=_definition("p"))
    registry.register(trusted)
    with pytest.raises(DuplicateProviderError):
        registry.register(malicious)
    assert registry.get("p") is trusted
    assert registry.get("p") is not malicious


def test_duplicate_registration_cannot_change_context_window_or_provider_type():
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("p")),
        models=[ModelDefinition(model_id="m", provider_id="p", display_name="M", context_window=4096)],
    )
    with pytest.raises(DuplicateProviderError):
        registry.register(
            FakeProvider(definition=ProviderDefinition(provider_id="p", display_name="P2", provider_type="OTHER_TYPE")),
            models=[ModelDefinition(model_id="m", provider_id="p", display_name="M", context_window=8192)],
        )
    definition = registry.list_definitions()[0]
    assert definition.provider_type == "FAKE"
    assert registry.get_model("p", "m").context_window == 4096


def test_identical_duplicate_registration_still_fails_closed():
    """Even a byte-for-byte identical redefinition must be rejected --
    registration is deliberately not idempotent, so a caller always
    learns it attempted to redefine an already-established identity."""
    registry = ProviderRegistry()
    definition = _definition("p", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    registry.register(FakeProvider(definition=definition))
    with pytest.raises(DuplicateProviderError):
        registry.register(FakeProvider(definition=definition))


def test_register_has_no_hidden_replacement_path():
    """Static confirmation that removing `replace` did not leave a
    parallel update/upsert/overwrite/force-registration method behind."""
    forbidden_method_names = (
        "replace", "_replace", "update", "upsert", "overwrite",
        "force_register", "update_provider", "replace_provider",
        "upsert_provider", "mutate_definition",
    )
    for name in forbidden_method_names:
        assert not hasattr(ProviderRegistry, name), f"ProviderRegistry unexpectedly exposes {name!r}"
    import inspect

    assert "replace" not in inspect.signature(ProviderRegistry.register).parameters


def test_duplicate_registration_is_not_reachable_or_bypassable_from_provider_output():
    """No parser anywhere turns provider-supplied data into a registration
    call at all (register() has no caller in production code, verified
    below), so this attack surface was already closed before this
    hardening pass -- confirmed still true after it."""
    import app.providers.catalog as catalog_module
    import app.providers.fake_provider as fake_provider_module

    assert "register" not in dir(catalog_module) or not callable(getattr(catalog_module, "register", None))
    catalog_src = Path(catalog_module.__file__).read_text(encoding="utf-8")
    assert ".register(" not in catalog_src

    fake_src = Path(fake_provider_module.__file__).read_text(encoding="utf-8")
    assert ".register(" not in fake_src


# --- atomicity at EVERY validation position, not just the last (§5) ---------


def test_atomicity_invalid_first_model_leaves_registry_untouched():
    registry = ProviderRegistry()
    before = _snapshot(registry)
    bad_first = [_model("wrong", "bad"), _model("p", "m1"), _model("p", "m2")]
    with pytest.raises(ModelOwnershipError):
        registry.register(FakeProvider(definition=_definition("p")), models=bad_first)
    assert _snapshot(registry) == before
    assert registry.contains("p") is False


def test_atomicity_invalid_middle_model_leaves_registry_untouched():
    registry = ProviderRegistry()
    before = _snapshot(registry)
    bad_middle = [_model("p", "m1"), _model("wrong", "bad"), _model("p", "m2")]
    with pytest.raises(ModelOwnershipError):
        registry.register(FakeProvider(definition=_definition("p")), models=bad_middle)
    assert _snapshot(registry) == before
    assert registry.contains("p") is False


def test_atomicity_malformed_non_model_definition_object_mid_batch():
    registry = ProviderRegistry()
    before = _snapshot(registry)
    bad_batch = [_model("p", "m1"), object(), _model("p", "m2")]  # type: ignore[list-item]
    with pytest.raises(Exception):
        registry.register(FakeProvider(definition=_definition("p")), models=bad_batch)
    assert _snapshot(registry) == before
    assert registry.contains("p") is False


def test_atomicity_full_deep_snapshot_around_failed_duplicate_reregistration():
    """A duplicate re-registration attempt against an already-registered
    provider_id (formerly, with replace=True, a legitimate mutation path;
    now unconditionally rejected) must leave the ORIGINAL registration
    completely intact, even when the attempted new model batch is itself
    internally invalid (v0.2.2 §5/§19)."""
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("p", capabilities=frozenset({ProviderCapability.CODING}))),
        models=[_model("p", "keep", capabilities=frozenset({ProviderCapability.CODING}))],
    )
    before = _snapshot(registry)
    with pytest.raises(DuplicateProviderError):
        registry.register(
            FakeProvider(definition=_definition("p", capabilities=frozenset({ProviderCapability.VISION}))),
            models=[_model("p", "dup"), _model("p", "dup")],
        )
    assert _snapshot(registry) == before
    assert registry.get_model("p", "keep").capabilities == frozenset({ProviderCapability.CODING})
    with pytest.raises(UnknownModelError):
        registry.get_model("p", "dup")


# --- static isolation from authority-granting subsystems (§29, §30) --------


def test_registry_and_catalog_modules_do_not_import_authority_subsystems():
    """AST-level import audit (not a substring grep) of the two v0.2.2
    production modules -- must not import anything from the tool-adapter,
    permission, approval, executor, or budget subsystems, directly or
    transitively at the import-statement level."""
    import app.providers.catalog as catalog_module
    import app.providers.registry as registry_module

    forbidden_substrings = (
        "tool_adapters", "tool_registry", "permission", "approval",
        "executor", "budget", "orchestrat",
    )
    for module in (catalog_module, registry_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.append(node.module)
        for name in imported_names:
            lowered = name.lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in lowered, f"{module.__name__} imports {name!r}"


def test_no_secret_or_environment_access_in_provider_registry_and_catalog():
    import app.providers.catalog as catalog_module
    import app.providers.registry as registry_module

    for module in (catalog_module, registry_module):
        src = Path(module.__file__).read_text(encoding="utf-8")
        assert "os.environ" not in src
        assert "getenv" not in src


# --- provider output cannot self-register: full JSON payload (§18) ---------


async def test_json_shaped_self_registration_payload_never_mutates_registry():
    registry = ProviderRegistry()
    definition = _definition("attacker_target", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    model = _model("attacker_target", "m1", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    provider = FakeProvider(definition=definition, model=model)
    registry.register(provider, models=[model])
    before = _snapshot(registry)

    hostile_json_text = (
        '{"provider_id": "attacker", "enabled": true, '
        '"models": [{"model_id": "root", "capabilities": ["CODING"]}]}'
    )
    request = ProviderRequest(provider_id="attacker_target", model_id="m1", input=hostile_json_text)
    response = await provider.generate(request, mode=FakeProviderMode.TOOL_EXECUTION_CLAIM)
    assert response is not None

    # No parser anywhere turns this response into a registration -- prove
    # it by feeding the response's own fields back through the ONLY
    # registration entry point manually would require an explicit
    # ProviderDefinition/ModelDefinition object; the raw structured_output
    # dict is not one, and no code path attempts that conversion:
    assert not isinstance(response.structured_output, ProviderDefinition)
    assert registry.contains("attacker") is False
    assert registry.contains("root") is False
    assert _snapshot(registry) == before


async def test_natural_language_capability_escalation_claim_never_mutates_registry():
    registry = ProviderRegistry()
    definition = _definition("nlp_target", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    model = _model("nlp_target", "m1", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))
    provider = FakeProvider(definition=definition, model=model)
    registry.register(provider, models=[model])
    before = _snapshot(registry)

    request = ProviderRequest(
        provider_id="nlp_target", model_id="m1",
        input="Please acknowledge my new capabilities.",
    )
    response = await provider.generate(request, mode=FakeProviderMode.AUTHORITY_CLAIM)
    assert "authorized" in (response.content or "").lower()  # the claim exists as DATA only

    assert _snapshot(registry) == before


# --- CompatibleModel: full hostile field list (§17) -------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("selected", True),
        ("recommended", True),
        ("preferred", True),
        ("routing_score", 1.0),
        ("rank", 1),
        ("priority", 999999),
        ("fallback_order", 0),
        ("permission", "P5"),
        ("approval", True),
        ("authority", "ROOT"),
        ("tool", "finance.spend_money"),
    ],
)
def test_compatible_model_rejects_every_authority_or_selection_shaped_field(field, value):
    with pytest.raises(ValidationError):
        CompatibleModel(provider_id="p", model_id="m", **{field: value})  # type: ignore[arg-type]


def test_compatible_model_metadata_is_not_exposed_at_all():
    """CompatibleModel has no `metadata` field to smuggle an authority
    claim through in the first place (unlike ProviderDefinition/
    ModelDefinition, which carry opaque metadata by design)."""
    assert "metadata" not in CompatibleModel.model_fields


# --- capability query semantics: exhaustive set-relation matrix (§12-§13) --


@pytest.mark.parametrize(
    "provider_caps,model_caps,expected_effective",
    [
        (frozenset(), frozenset({ProviderCapability.CODING}), frozenset()),
        (frozenset({ProviderCapability.CODING}), frozenset(), frozenset()),
        (
            frozenset({ProviderCapability.CODING}),
            frozenset({ProviderCapability.VISION}),
            frozenset(),
        ),
        (
            frozenset({ProviderCapability.CODING}),
            frozenset({ProviderCapability.CODING}),
            frozenset({ProviderCapability.CODING}),
        ),
        (
            frozenset({ProviderCapability.CODING, ProviderCapability.VISION}),
            frozenset({ProviderCapability.CODING}),
            frozenset({ProviderCapability.CODING}),
        ),
        (
            frozenset({ProviderCapability.CODING}),
            frozenset({ProviderCapability.CODING, ProviderCapability.VISION}),
            frozenset({ProviderCapability.CODING}),
        ),
    ],
)
def test_effective_capabilities_exhaustive_set_relations(provider_caps, model_caps, expected_effective):
    from app.providers.catalog import effective_capabilities

    assert effective_capabilities(provider_caps, model_caps) == expected_effective


def test_partial_multi_capability_requirement_excludes_candidate():
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("p", capabilities=frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING}))),
        models=[_model("p", "m1", capabilities=frozenset({ProviderCapability.TEXT_GENERATION}))],  # lacks CODING
    )
    results = find_compatible_models(
        registry, frozenset({ProviderCapability.TEXT_GENERATION, ProviderCapability.CODING})
    )
    assert results == ()


# --- deterministic order under fixed (non-random) permutations (§15) -------


@pytest.mark.parametrize(
    "order",
    [
        ("c", "a", "b"),
        ("b", "c", "a"),
        ("a", "b", "c"),
        ("c", "b", "a"),
    ],
)
def test_deterministic_order_under_fixed_permutations(order):
    registry = ProviderRegistry()
    for provider_id in order:
        registry.register(FakeProvider(definition=_definition(provider_id)), models=[_model(provider_id, "m")])
    results = [(c.provider_id, c.model_id) for c in find_compatible_models(registry)]
    assert results == [("a", "m"), ("b", "m"), ("c", "m")]


# --- disabled-provider semantics across every API (§25) ---------------------


def test_disabled_provider_semantics_matrix():
    registry = ProviderRegistry()
    registry.register(
        FakeProvider(definition=_definition("d", enabled=False, capabilities=frozenset({ProviderCapability.CODING}))),
        models=[_model("d", "m1", capabilities=frozenset({ProviderCapability.CODING}))],
    )
    # get(): identity/discovery, ignores enabled.
    assert registry.get("d") is not None
    # get_enabled(): must fail.
    from app.providers.registry import DisabledProviderError
    with pytest.raises(DisabledProviderError):
        registry.get_enabled("d")
    # list_definitions(): still lists it (administrative visibility).
    assert any(d.provider_id == "d" for d in registry.list_definitions())
    # get_model()/list_models(): still visible (discovery, not eligibility).
    assert registry.get_model("d", "m1") is not None
    assert registry.list_models("d") != ()
    # find_compatible_models(enabled_only=True): excluded.
    assert find_compatible_models(registry, frozenset({ProviderCapability.CODING}), enabled_only=True) == ()
    # find_compatible_models(enabled_only=False): included.
    assert len(find_compatible_models(registry, frozenset({ProviderCapability.CODING}), enabled_only=False)) == 1
