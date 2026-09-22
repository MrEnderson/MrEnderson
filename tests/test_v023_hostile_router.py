"""Hostile-first tests for v0.2.3 -- Provider Router + Cost / Health /
Fallback Policy. Written BEFORE `app/providers/router.py`/
`routing_contracts.py` exist (mandatory phase order: hostile scenarios
shape the implementation, not the reverse). Every test here initially
fails with an ImportError; `router.py`/`routing_contracts.py` are then
implemented to make them pass, and no further "invent security rules
afterward" retrofitting occurs. No network, no credentials, fully offline
and deterministic.

Central invariant under test throughout: the router may select
computational capability; it may never grant authority."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.providers.catalog import find_compatible_models
from app.providers.contracts import ModelDefinition, ProviderCapability, ProviderDefinition
from app.providers.fake_provider import FakeProvider
from app.providers.registry import ProviderRegistry
from app.providers.router import route_providers
from app.providers.routing_contracts import (
    CandidateEvaluation,
    HealthState,
    OptimizationPolicy,
    PrivacyRequirement,
    ProviderCostSnapshot,
    ProviderHealthSnapshot,
    ProviderLocality,
    ProviderLocalitySnapshot,
    ProviderRoutingRequest,
    ProviderSelectionRecord,
    ProviderSelectionResult,
    RoutingReasonCode,
    SelectionStatus,
)


# --- fixtures / builders -----------------------------------------------------


def _definition(
    provider_id: str, *, enabled: bool = True, capabilities: frozenset = frozenset()
) -> ProviderDefinition:
    return ProviderDefinition(
        provider_id=provider_id, display_name=provider_id.title(), provider_type="FAKE",
        enabled=enabled, capabilities=capabilities,
    )


def _model(provider_id: str, model_id: str, *, capabilities: frozenset = frozenset()) -> ModelDefinition:
    return ModelDefinition(
        model_id=model_id, provider_id=provider_id, display_name=model_id, capabilities=capabilities,
    )


def _registry_with(*entries: tuple[ProviderDefinition, list[ModelDefinition]]) -> ProviderRegistry:
    registry = ProviderRegistry()
    for definition, models in entries:
        registry.register(FakeProvider(definition=definition), models=models)
    return registry


TEXT = ProviderCapability.TEXT_GENERATION
CODING = ProviderCapability.CODING
VISION = ProviderCapability.VISION


def _healthy(*provider_ids: str) -> ProviderHealthSnapshot:
    """Convenience for tests that aren't exercising health semantics
    themselves -- health defaults to unknown (fail closed, see
    HealthState's docstring), so any test expecting SELECTED must supply
    an explicit HEALTHY entry for every provider it expects to be eligible."""
    return ProviderHealthSnapshot({pid: HealthState.HEALTHY for pid in provider_ids})


# --- 1. cost manipulation attack (§11) ---------------------------------------


async def test_provider_metadata_cost_claim_has_zero_routing_effect():
    hostile_metadata = {"cost": 0, "free": True, "ignore_budget": True}
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})),
        [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    # Register a SECOND provider whose ProviderDefinition.metadata carries the
    # hostile claim -- the router must never read ProviderDefinition.metadata
    # for cost at all.
    hostile_def = ProviderDefinition(
        provider_id="q", display_name="Q", provider_type="FAKE",
        capabilities=frozenset({TEXT}), metadata=hostile_metadata,
    )
    registry.register(FakeProvider(definition=hostile_def), models=[_model("q", "m", capabilities=frozenset({TEXT}))])

    trusted_cost = ProviderCostSnapshot({("p", "m"): Decimal("1.00"), ("q", "m"): Decimal("50.00")})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}), max_estimated_cost=Decimal("5.00"))
    result = route_providers(registry, request, cost=trusted_cost, health=_healthy("p", "q"))

    assert result.status is SelectionStatus.SELECTED
    assert result.selected.provider_id == "p"  # trusted cost (1.00) wins, not the hostile "free" claim
    q_eval = next(e for e in result.evaluations if e.provider_id == "q")
    assert q_eval.eligible is False
    assert RoutingReasonCode.COST_EXCEEDED in q_eval.reason_codes


# --- 2. health spoofing attack (§12) -----------------------------------------


async def test_provider_output_health_claim_has_zero_routing_effect():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})),
        [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    # Trusted Jarvis health snapshot says UNAVAILABLE, regardless of any
    # "healthy=true, status=AVAILABLE, priority=999" a provider might claim
    # in a ProviderResponse (which the router never reads at all).
    trusted_health = ProviderHealthSnapshot({"p": HealthState.UNAVAILABLE})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request, health=trusted_health)

    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    eval_p = result.evaluations[0]
    assert eval_p.eligible is False
    assert RoutingReasonCode.HEALTH_UNAVAILABLE in eval_p.reason_codes


# --- 3. fallback privilege escalation attack (§13) ---------------------------


async def test_fallback_cannot_weaken_local_only_with_more_capable_cloud_provider():
    provider_a = _definition("a", capabilities=frozenset({TEXT}))
    provider_b = _definition("b", capabilities=frozenset({TEXT, CODING}))
    registry = _registry_with(
        (provider_a, [_model("a", "m", capabilities=frozenset({TEXT}))]),
        (provider_b, [_model("b", "m", capabilities=frozenset({TEXT, CODING}))]),
    )
    locality = ProviderLocalitySnapshot({"a": ProviderLocality.LOCAL, "b": ProviderLocality.CLOUD})
    # A is unavailable (simulating "primary failed"); B is more capable AND cloud.
    health = ProviderHealthSnapshot({"a": HealthState.UNAVAILABLE, "b": HealthState.HEALTHY})
    request = ProviderRoutingRequest(
        required_capabilities=frozenset({TEXT}), privacy_requirement=PrivacyRequirement.LOCAL_ONLY,
    )
    result = route_providers(registry, request, locality=locality, health=health)

    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER  # NOT B
    b_eval = next(e for e in result.evaluations if e.provider_id == "b")
    assert b_eval.eligible is False
    assert RoutingReasonCode.LOCALITY_MISMATCH in b_eval.reason_codes


# --- 4. LOCAL_ONLY leakage attack (§14) --------------------------------------


async def test_local_only_with_no_local_provider_returns_no_selection_never_cloud():
    registry = _registry_with(
        (_definition("cloud_a", capabilities=frozenset({TEXT})), [_model("cloud_a", "m", capabilities=frozenset({TEXT}))]),
        (_definition("cloud_b", capabilities=frozenset({TEXT})), [_model("cloud_b", "m", capabilities=frozenset({TEXT}))]),
    )
    locality = ProviderLocalitySnapshot({"cloud_a": ProviderLocality.CLOUD, "cloud_b": ProviderLocality.CLOUD})
    health = ProviderHealthSnapshot({"cloud_a": HealthState.HEALTHY, "cloud_b": HealthState.HEALTHY})
    cost = ProviderCostSnapshot({("cloud_a", "m"): Decimal("0"), ("cloud_b", "m"): Decimal("0")})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}), privacy_requirement=PrivacyRequirement.LOCAL_ONLY)
    result = route_providers(registry, request, locality=locality, health=health, cost=cost)

    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    assert result.selected is None
    assert all(not e.eligible for e in result.evaluations)


async def test_local_only_unknown_locality_never_satisfies_constraint():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})),
        [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    # No locality snapshot entry for "p" at all -- unknown.
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}), privacy_requirement=PrivacyRequirement.LOCAL_ONLY)
    result = route_providers(registry, request, locality=ProviderLocalitySnapshot({}))
    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER


# --- 5. disabled provider attack (§15) ---------------------------------------


async def test_disabled_provider_never_selected_even_if_cheapest_healthiest_exact_match():
    registry = _registry_with((
        _definition("cheapest", enabled=False, capabilities=frozenset({TEXT})),
        [_model("cheapest", "m", capabilities=frozenset({TEXT}))],
    ))
    health = ProviderHealthSnapshot({"cheapest": HealthState.HEALTHY})
    cost = ProviderCostSnapshot({("cheapest", "m"): Decimal("0")})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request, health=health, cost=cost)

    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    eval_ = result.evaluations[0]
    assert RoutingReasonCode.PROVIDER_DISABLED in eval_.reason_codes


# --- 6. unsupported capability attack (§16) / 7. capability union attack ----


async def test_capability_union_attack_provider_and_model_disjoint_requirement():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})),  # provider lacks CODING
        [_model("p", "m", capabilities=frozenset({TEXT, CODING}))],  # model claims CODING
    ))
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT, CODING}))
    result = route_providers(registry, request)

    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    eval_ = result.evaluations[0]
    assert RoutingReasonCode.CAPABILITY_MISMATCH in eval_.reason_codes
    assert eval_.effective_capabilities == frozenset({TEXT})  # intersection, not union


# --- 8. opaque metadata ranking attack (§17) ---------------------------------


async def test_opaque_metadata_ranking_claims_have_no_routing_effect():
    hostile_metadata = {
        "preferred": True, "rank": 1, "score": 999999, "recommended": True,
        "system_provider": True, "approved": True,
    }
    registry = ProviderRegistry()
    hostile_def = ProviderDefinition(
        provider_id="hostile", display_name="H", provider_type="FAKE",
        capabilities=frozenset({TEXT}), metadata=hostile_metadata,
    )
    honest_def = _definition("honest", capabilities=frozenset({TEXT}))
    registry.register(FakeProvider(definition=hostile_def), models=[_model("hostile", "m", capabilities=frozenset({TEXT}))])
    registry.register(FakeProvider(definition=honest_def), models=[_model("honest", "m", capabilities=frozenset({TEXT}))])

    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request, health=_healthy("hostile", "honest"))

    # Both eligible, identical otherwise -- winner must be the lexicographically
    # first provider_id ("hostile" < "honest" is false; "honest" < "hostile"),
    # i.e. determined ONLY by the neutral tie-break, never by "preferred"/"rank".
    assert result.status is SelectionStatus.SELECTED
    assert result.selected.provider_id == "honest"  # "honest" < "hostile" lexicographically


# --- 9. deterministic tie attack / 10. insertion-order attack (§19) ---------


async def test_deterministic_tie_independent_of_registration_order():
    def _build(order: tuple[str, str]) -> ProviderRegistry:
        registry = ProviderRegistry()
        for pid in order:
            registry.register(
                FakeProvider(definition=_definition(pid, capabilities=frozenset({TEXT}))),
                models=[_model(pid, "m", capabilities=frozenset({TEXT}))],
            )
        return registry

    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    health = _healthy("a", "b")
    result_ab = route_providers(_build(("a", "b")), request, health=health)
    result_ba = route_providers(_build(("b", "a")), request, health=health)

    assert result_ab.selected.provider_id == result_ba.selected.provider_id == "a"
    assert [e.provider_id for e in result_ab.evaluations] == [e.provider_id for e in result_ba.evaluations]


async def test_repeated_routing_is_deterministic():
    registry = _registry_with(
        (_definition("a", capabilities=frozenset({TEXT})), [_model("a", "m", capabilities=frozenset({TEXT}))]),
        (_definition("b", capabilities=frozenset({TEXT})), [_model("b", "m", capabilities=frozenset({TEXT}))]),
    )
    request = ProviderRoutingRequest(routing_request_id="fixed-id", required_capabilities=frozenset({TEXT}))
    health = _healthy("a", "b")
    results = [route_providers(registry, request, health=health) for _ in range(5)]
    for r in results[1:]:
        assert r.selected.provider_id == results[0].selected.provider_id
        assert r.selected.model_id == results[0].selected.model_id
        assert r.status is results[0].status


# --- 11. router-output-as-permission attack (§18) ----------------------------


async def test_selection_record_has_no_authority_fields_or_methods():
    with pytest.raises(ValidationError):
        ProviderSelectionRecord(
            selection_id="s1", routing_request_id="r1", provider_id="p", model_id="m",
            effective_capabilities=frozenset(), trusted_health=HealthState.HEALTHY,
            trusted_cost=None, reason="x", policy_version="v0.2.3",
            permission="P5",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError):
        ProviderSelectionRecord(
            selection_id="s1", routing_request_id="r1", provider_id="p", model_id="m",
            effective_capabilities=frozenset(), trusted_health=HealthState.HEALTHY,
            trusted_cost=None, reason="x", policy_version="v0.2.3",
            execute=True,  # type: ignore[call-arg]
        )

    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request)
    record = result.selected
    for forbidden in ("authorize", "execute", "approve"):
        assert not hasattr(record, forbidden)
        assert not hasattr(result, forbidden)


# --- 12. provider invocation attack (§30) ------------------------------------


class _NeverInvokedProvider:
    def __init__(self, definition: ProviderDefinition):
        self._definition = definition
        self.generate_call_count = 0

    @property
    def definition(self) -> ProviderDefinition:
        return self._definition

    async def generate(self, request):
        self.generate_call_count += 1
        raise AssertionError("ROUTER MUST NEVER INVOKE PROVIDER")


async def test_router_never_invokes_provider_generate():
    provider = _NeverInvokedProvider(_definition("p", capabilities=frozenset({TEXT})))
    registry = ProviderRegistry()
    registry.register(provider, models=[_model("p", "m", capabilities=frozenset({TEXT}))])

    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    for _ in range(3):
        route_providers(registry, request)
    assert provider.generate_call_count == 0


# --- 13. registry mutation attack (§32) --------------------------------------


def _registry_snapshot(registry: ProviderRegistry) -> tuple:
    defs = registry.list_definitions()
    return tuple(
        (d.provider_id, d.enabled, d.capabilities, tuple(m.model_id for m in registry.list_models(d.provider_id)))
        for d in defs
    )


async def test_router_never_mutates_registry():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    before = _registry_snapshot(registry)
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    for _ in range(5):
        route_providers(registry, request)
    assert _registry_snapshot(registry) == before


# --- 14. request mutation attack (§33) ---------------------------------------


async def test_router_never_mutates_routing_request():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    before = request.model_dump()
    route_providers(registry, request)
    assert request.model_dump() == before
    with pytest.raises(ValidationError):
        request.required_capabilities = frozenset()  # frozen -- reassignment must fail


# --- 15/16/17. unknown privacy / health / fallback enum attacks (§34) -------


def test_unknown_privacy_requirement_string_rejected():
    with pytest.raises(ValidationError):
        ProviderRoutingRequest(privacy_requirement="SUPER_PRIVATE")  # type: ignore[arg-type]


def test_unknown_health_state_string_rejected():
    with pytest.raises(ValueError):
        HealthState("TOTALLY_HEALTHY")


def test_unknown_capability_string_in_required_capabilities_rejected():
    with pytest.raises(ValidationError):
        ProviderRoutingRequest(required_capabilities=frozenset({"finance.spend_money"}))  # type: ignore[arg-type]


# --- 18. invalid cost attacks (§35) ------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_invalid_cost_values_rejected_at_snapshot_construction(bad_value):
    with pytest.raises(ValueError):
        ProviderCostSnapshot({("p", "m"): bad_value})


def test_negative_max_estimated_cost_rejected():
    with pytest.raises(ValidationError):
        ProviderRoutingRequest(max_estimated_cost=Decimal("-5"))


def test_zero_cost_is_legitimate_not_missing():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    cost = ProviderCostSnapshot({("p", "m"): Decimal("0")})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}), max_estimated_cost=Decimal("0"))
    result = route_providers(registry, request, cost=cost, health=_healthy("p"))
    assert result.status is SelectionStatus.SELECTED
    assert result.selected.trusted_cost == Decimal("0")


def test_unknown_cost_with_ceiling_set_fails_closed():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}), max_estimated_cost=Decimal("1"))
    result = route_providers(registry, request, cost=ProviderCostSnapshot({}))
    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    assert RoutingReasonCode.COST_UNKNOWN in result.evaluations[0].reason_codes


def test_unknown_cost_without_ceiling_is_eligible():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))  # no max_estimated_cost
    result = route_providers(registry, request, cost=ProviderCostSnapshot({}), health=_healthy("p"))
    assert result.status is SelectionStatus.SELECTED


# --- 19. denied-provider override attack (§22) -------------------------------


async def test_denied_provider_ineligible_even_if_also_allowed():
    registry = _registry_with(
        (_definition("a", capabilities=frozenset({TEXT})), [_model("a", "m", capabilities=frozenset({TEXT}))]),
        (_definition("b", capabilities=frozenset({TEXT})), [_model("b", "m", capabilities=frozenset({TEXT}))]),
    )
    request = ProviderRoutingRequest(
        required_capabilities=frozenset({TEXT}),
        allowed_provider_ids=frozenset({"a", "b"}),
        denied_provider_ids=frozenset({"b"}),
    )
    result = route_providers(registry, request, health=_healthy("a", "b"))
    assert result.status is SelectionStatus.SELECTED
    assert result.selected.provider_id == "a"
    b_eval = next(e for e in result.evaluations if e.provider_id == "b")
    assert RoutingReasonCode.PROVIDER_DENIED in b_eval.reason_codes


async def test_unknown_id_in_allowed_list_does_not_broaden_eligibility():
    registry = _registry_with((
        _definition("a", capabilities=frozenset({TEXT})), [_model("a", "m", capabilities=frozenset({TEXT}))],
    ))
    request = ProviderRoutingRequest(
        required_capabilities=frozenset({TEXT}),
        allowed_provider_ids=frozenset({"nonexistent_provider"}),
    )
    result = route_providers(registry, request)
    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    a_eval = next(e for e in result.evaluations if e.provider_id == "a")
    assert RoutingReasonCode.PROVIDER_NOT_ALLOWED in a_eval.reason_codes


# --- 20. provider shape-shifting attack (§31) --------------------------------


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


async def test_router_uses_registry_pinned_definition_not_live_reread():
    trusted = _definition("trusted", capabilities=frozenset({TEXT}))
    evil = _definition("evil", capabilities=frozenset({TEXT, CODING}))
    shifter = _ShapeShiftingProvider(trusted, evil, evil, evil)
    registry = ProviderRegistry()
    registry.register(shifter, models=[_model("trusted", "m", capabilities=frozenset({TEXT}))])

    reads_before = shifter.reads
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT, CODING}))
    result = route_providers(registry, request)

    assert shifter.reads == reads_before  # router never touched .definition again
    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER  # pinned "trusted" never declared CODING


# --- 21. no eligible provider result shape (§24) -----------------------------


async def test_no_eligible_provider_result_explains_every_candidate():
    registry = _registry_with(
        (_definition("a", enabled=False, capabilities=frozenset({TEXT})), [_model("a", "m", capabilities=frozenset({TEXT}))]),
        (_definition("b", capabilities=frozenset({VISION})), [_model("b", "m", capabilities=frozenset({VISION}))]),
    )
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request)

    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    assert result.selected is None
    assert len(result.evaluations) == 2
    a_eval = next(e for e in result.evaluations if e.provider_id == "a")
    b_eval = next(e for e in result.evaluations if e.provider_id == "b")
    assert RoutingReasonCode.PROVIDER_DISABLED in a_eval.reason_codes
    assert RoutingReasonCode.CAPABILITY_MISMATCH in b_eval.reason_codes


# --- deterministic tie-break lexicographic, and NO router-style helper -----


def test_no_ranking_or_selection_helper_names_exist():
    import app.providers.router as router_module
    import app.providers.routing_contracts as routing_contracts_module

    forbidden_names = (
        "select_best_provider", "choose_best", "recommend", "pick_cheapest",
        "pick_fastest", "rank_providers", "score_providers",
    )
    for name in forbidden_names:
        assert not hasattr(router_module, name)
        assert not hasattr(routing_contracts_module, name)


# --- malformed optimization policy (F-04) -----------------------------------


@pytest.mark.parametrize("bad_optimization", ["BEST", "CHEAPEST_IGNORE_RULES", 1, None, object()])
def test_unrecognized_optimization_policy_rejected_not_silently_lowest_cost(bad_optimization):
    """v0.2.3 hostile-review finding F-04: an unrecognized `optimization`
    value must fail loudly, before any branch -- NOT silently fall through
    to the LOWEST_COST branch (the old `is OptimizationPolicy.DETERMINISTIC`
    check treated anything non-DETERMINISTIC as LOWEST_COST)."""
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    with pytest.raises(TypeError):
        route_providers(registry, request, optimization=bad_optimization, health=_healthy("p"))


# --- optimization policy: LOWEST_COST ----------------------------------------


async def test_lowest_cost_optimization_prefers_cheaper_eligible_candidate():
    registry = _registry_with(
        (_definition("expensive", capabilities=frozenset({TEXT})), [_model("expensive", "m", capabilities=frozenset({TEXT}))]),
        (_definition("cheap", capabilities=frozenset({TEXT})), [_model("cheap", "m", capabilities=frozenset({TEXT}))]),
    )
    cost = ProviderCostSnapshot({("expensive", "m"): Decimal("9.99"), ("cheap", "m"): Decimal("0.01")})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(
        registry, request, cost=cost, optimization=OptimizationPolicy.LOWEST_COST,
        health=_healthy("expensive", "cheap"),
    )
    assert result.selected.provider_id == "cheap"


async def test_lowest_cost_with_no_known_cost_at_all_returns_no_eligible_provider():
    """v0.2.3 hostile-review finding F-01: LOWEST_COST must never silently
    degrade to an arbitrary deterministic pick mislabeled as a cost-based
    decision when NO eligible candidate has a known trusted cost -- that
    would let `ProviderSelectionResult.selected.reason` claim a cost
    comparison that never happened. The correct, fail-closed outcome is
    NO_ELIGIBLE_PROVIDER: LOWEST_COST had nothing to compare."""
    registry = _registry_with(
        (_definition("a", capabilities=frozenset({TEXT})), [_model("a", "m", capabilities=frozenset({TEXT}))]),
        (_definition("b", capabilities=frozenset({TEXT})), [_model("b", "m", capabilities=frozenset({TEXT}))]),
    )
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(
        registry, request, optimization=OptimizationPolicy.LOWEST_COST, health=_healthy("a", "b"),
    )
    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    assert result.selected is None


async def test_lowest_cost_unknown_cost_never_wins_against_any_known_cost():
    """F-01, case 2: an unknown-cost candidate can never be proven cheapest,
    so it never wins LOWEST_COST against a candidate with ANY known cost --
    even an expensive one. This is intentional (documented in the contract
    doc): LOWEST_COST only compares proven costs."""
    registry = _registry_with(
        (_definition("unknown_cost", capabilities=frozenset({TEXT})), [_model("unknown_cost", "m", capabilities=frozenset({TEXT}))]),
        (_definition("known_expensive", capabilities=frozenset({TEXT})), [_model("known_expensive", "m", capabilities=frozenset({TEXT}))]),
    )
    cost = ProviderCostSnapshot({("known_expensive", "m"): Decimal("100.00")})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(
        registry, request, cost=cost, optimization=OptimizationPolicy.LOWEST_COST,
        health=_healthy("unknown_cost", "known_expensive"),
    )
    assert result.status is SelectionStatus.SELECTED
    assert result.selected.provider_id == "known_expensive"
    assert result.selected.trusted_cost == Decimal("100.00")


async def test_lowest_cost_known_equal_costs_use_neutral_tie_break():
    """F-01 related: Decimal("1") and Decimal("1.00") must compare equal
    and the neutral (provider_id, model_id) tie-break must decide, not
    decimal representation."""
    registry = _registry_with(
        (_definition("b", capabilities=frozenset({TEXT})), [_model("b", "m", capabilities=frozenset({TEXT}))]),
        (_definition("a", capabilities=frozenset({TEXT})), [_model("a", "m", capabilities=frozenset({TEXT}))]),
    )
    cost = ProviderCostSnapshot({("a", "m"): Decimal("1"), ("b", "m"): Decimal("1.00")})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(
        registry, request, cost=cost, optimization=OptimizationPolicy.LOWEST_COST,
        health=_healthy("a", "b"),
    )
    assert result.selected.provider_id == "a"


# --- degraded health opt-in -----------------------------------------------


async def test_degraded_health_ineligible_by_default():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    health = ProviderHealthSnapshot({"p": HealthState.DEGRADED})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request, health=health)
    assert result.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    assert RoutingReasonCode.HEALTH_DEGRADED_NOT_ALLOWED in result.evaluations[0].reason_codes


async def test_degraded_health_eligible_when_explicitly_allowed():
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    health = ProviderHealthSnapshot({"p": HealthState.DEGRADED})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request, health=health, allow_degraded_health=True)
    assert result.status is SelectionStatus.SELECTED


# --- policy-input auditability (F-05) ----------------------------------------


async def test_no_eligible_provider_result_still_records_policy_inputs_used():
    """v0.2.3 hostile-review finding F-05: before this fix, a
    NO_ELIGIBLE_PROVIDER result carried no trace of what `optimization`/
    `allow_degraded_health` were actually passed to route_providers() --
    two calls with identical requests that differed only in these
    call-site-only arguments were indistinguishable after the fact."""
    registry = _registry_with((
        _definition("p", capabilities=frozenset({TEXT})), [_model("p", "m", capabilities=frozenset({TEXT}))],
    ))
    health = ProviderHealthSnapshot({"p": HealthState.DEGRADED})
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))

    result_denied = route_providers(registry, request, health=health, allow_degraded_health=False)
    assert result_denied.status is SelectionStatus.NO_ELIGIBLE_PROVIDER
    assert result_denied.allow_degraded_health is False
    assert result_denied.optimization is OptimizationPolicy.DETERMINISTIC

    cost = ProviderCostSnapshot({("p", "m"): Decimal("1.00")})
    result_allowed = route_providers(
        registry, request, health=health, cost=cost, allow_degraded_health=True,
        optimization=OptimizationPolicy.LOWEST_COST,
    )
    assert result_allowed.status is SelectionStatus.SELECTED
    assert result_allowed.allow_degraded_health is True
    assert result_allowed.optimization is OptimizationPolicy.LOWEST_COST


# --- snapshot input aliasing --------------------------------------------------


def test_health_snapshot_input_aliasing_does_not_affect_snapshot():
    values = {"p": HealthState.HEALTHY}
    snapshot = ProviderHealthSnapshot(values)
    values["p"] = HealthState.UNAVAILABLE  # mutate the caller's original dict
    assert snapshot.get("p") == HealthState.HEALTHY  # unaffected


def test_cost_snapshot_input_aliasing_does_not_affect_snapshot():
    values = {("p", "m"): Decimal("1.00")}
    snapshot = ProviderCostSnapshot(values)
    values[("p", "m")] = Decimal("999.00")
    assert snapshot.get(("p", "m")) == Decimal("1.00")


# --- CandidateEvaluation shape ------------------------------------------------


def test_candidate_evaluation_rejects_authority_fields():
    with pytest.raises(ValidationError):
        CandidateEvaluation(
            provider_id="p", model_id="m", eligible=True, reason_codes=(),
            effective_capabilities=frozenset(), trusted_cost=None, trusted_health=None,
            permission="P5",  # type: ignore[call-arg]
        )


# --- structural integrity of routing output contracts (F-03) ----------------


def _record(provider_id: str = "p", model_id: str = "m") -> ProviderSelectionRecord:
    return ProviderSelectionRecord(
        routing_request_id="r1", provider_id=provider_id, model_id=model_id,
        effective_capabilities=frozenset(), trusted_health=HealthState.HEALTHY,
        trusted_cost=None, reason="x", policy_version="v0.2.3",
    )


def _eval(provider_id: str = "p", model_id: str = "m", *, eligible: bool = True) -> CandidateEvaluation:
    return CandidateEvaluation(
        provider_id=provider_id, model_id=model_id, eligible=eligible,
        reason_codes=() if eligible else (RoutingReasonCode.PROVIDER_DISABLED,),
        effective_capabilities=frozenset(), trusted_cost=None, trusted_health=None,
    )


def test_candidate_evaluation_eligible_cannot_carry_reason_codes():
    with pytest.raises(ValidationError):
        CandidateEvaluation(
            provider_id="p", model_id="m", eligible=True,
            reason_codes=(RoutingReasonCode.PROVIDER_DISABLED,),
            effective_capabilities=frozenset(), trusted_cost=None, trusted_health=None,
        )


def test_candidate_evaluation_ineligible_must_carry_reason_codes():
    with pytest.raises(ValidationError):
        CandidateEvaluation(
            provider_id="p", model_id="m", eligible=False, reason_codes=(),
            effective_capabilities=frozenset(), trusted_cost=None, trusted_health=None,
        )


def _result_kwargs(**overrides) -> dict:
    base = dict(
        routing_request_id="r1", status=SelectionStatus.NO_ELIGIBLE_PROVIDER, selected=None,
        evaluations=(), optimization=OptimizationPolicy.DETERMINISTIC,
        allow_degraded_health=False, policy_version="v0.2.3",
    )
    base.update(overrides)
    return base


def test_selection_result_fully_valid_construction_succeeds():
    """Positive control for the five negative tests below -- proves they
    reject on the INTENDED structural-consistency violation, not merely
    because a required field (optimization/allow_degraded_health, added
    for finding F-05) was left out."""
    result = ProviderSelectionResult(**_result_kwargs(
        status=SelectionStatus.SELECTED, selected=_record(), evaluations=(_eval(),),
    ))
    assert result.status is SelectionStatus.SELECTED


def test_selection_result_status_selected_requires_a_record():
    with pytest.raises(ValidationError):
        ProviderSelectionResult(**_result_kwargs(status=SelectionStatus.SELECTED, selected=None))


def test_selection_result_no_eligible_provider_forbids_a_record():
    with pytest.raises(ValidationError):
        ProviderSelectionResult(**_result_kwargs(
            status=SelectionStatus.NO_ELIGIBLE_PROVIDER, selected=_record(),
        ))


def test_selection_result_selected_must_match_an_evaluation():
    with pytest.raises(ValidationError):
        ProviderSelectionResult(**_result_kwargs(
            status=SelectionStatus.SELECTED, selected=_record(), evaluations=(),
        ))


def test_selection_result_selected_cannot_match_an_ineligible_evaluation():
    with pytest.raises(ValidationError):
        ProviderSelectionResult(**_result_kwargs(
            status=SelectionStatus.SELECTED, selected=_record(), evaluations=(_eval(eligible=False),),
        ))


def test_selection_result_rejects_duplicate_evaluations():
    with pytest.raises(ValidationError):
        ProviderSelectionResult(**_result_kwargs(
            status=SelectionStatus.SELECTED, selected=_record(), evaluations=(_eval(), _eval()),
        ))


async def test_router_never_produces_a_structurally_inconsistent_result():
    """Every result `route_providers()` actually produces satisfies the
    F-03 validators -- construction never raises for router output."""
    registry = _registry_with(
        (_definition("a", capabilities=frozenset({TEXT})), [_model("a", "m", capabilities=frozenset({TEXT}))]),
        (_definition("b", enabled=False, capabilities=frozenset({TEXT})), [_model("b", "m", capabilities=frozenset({TEXT}))]),
    )
    request = ProviderRoutingRequest(required_capabilities=frozenset({TEXT}))
    result = route_providers(registry, request, health=_healthy("a", "b"))
    assert result.status is SelectionStatus.SELECTED  # already validated at construction by the model_validator
