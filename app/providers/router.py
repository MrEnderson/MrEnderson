"""Provider Router (v0.2.3 — Provider Router + Cost / Health / Fallback
Policy; `docs/V0_2_3_PROVIDER_ROUTER_SECURITY_CONTRACT.md`).

Central invariant: **the router may select computational capability, it may
never grant authority**. `route_providers()` is a pure, read-only function
of its arguments:

  - it reads `registry.list_definitions()`/`registry.list_models()` only
    (the same catalogue APIs `app.providers.catalog` already uses) and
    never calls `registry.register()` -- v0.2.2's identity hardening
    (no `replace=True`, no hidden update/upsert/overwrite path) is not
    touched, reintroduced, or weakened;
  - it never calls `provider.generate()`, `.stream()`, or any
    hypothetical `health_check()` -- the `AIProvider` protocol has neither
    of the latter two, and this module never even imports anything that
    would let it invoke one;
  - it never mutates the `ProviderRoutingRequest` it receives (frozen
    Pydantic input, and this module builds its own internal working
    values rather than aliasing caller-held collections);
  - it produces an immutable `ProviderSelectionResult` that structurally
    cannot carry an authority/selection-shaped field (see
    `routing_contracts.py`'s `extra="forbid"` types).

Hard constraints (provider enabled, allow/deny, capability intersection,
locality/privacy, health, cost) ELIMINATE a candidate; they are never
scored/weighted/summed. Only after every hard constraint has run does an
explicit, caller-chosen `OptimizationPolicy` operate over what remains,
followed by an explicit, documented, neutral tie-break -- see the
'Hard constraints vs. optimization' and 'Fallback semantics' sections of
the contract doc for why there is no separate "fallback" code path here at
all: every routing call, first attempt or retry-after-failure, runs through
this exact same pipeline."""
from __future__ import annotations

from app.providers.catalog import effective_capabilities
from app.providers.contracts import ProviderDefinition
from app.providers.registry import ProviderRegistry
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

POLICY_VERSION = "v0.2.3-router-policy-1"


def _evaluate_candidate(
    definition: ProviderDefinition,
    model_id: str,
    model_capabilities: frozenset,
    request: ProviderRoutingRequest,
    locality: ProviderLocalitySnapshot,
    health: ProviderHealthSnapshot,
    cost: ProviderCostSnapshot,
    *,
    allow_degraded_health: bool,
) -> CandidateEvaluation:
    provider_id = definition.provider_id
    reason_codes: list[RoutingReasonCode] = []

    if not definition.enabled:
        reason_codes.append(RoutingReasonCode.PROVIDER_DISABLED)

    if provider_id in request.denied_provider_ids:
        reason_codes.append(RoutingReasonCode.PROVIDER_DENIED)
    elif request.allowed_provider_ids is not None and provider_id not in request.allowed_provider_ids:
        reason_codes.append(RoutingReasonCode.PROVIDER_NOT_ALLOWED)

    effective = effective_capabilities(definition.capabilities, model_capabilities)
    if not request.required_capabilities <= effective:
        reason_codes.append(RoutingReasonCode.CAPABILITY_MISMATCH)

    if request.privacy_requirement is PrivacyRequirement.LOCAL_ONLY:
        if locality.get(provider_id) is not ProviderLocality.LOCAL:
            reason_codes.append(RoutingReasonCode.LOCALITY_MISMATCH)

    trusted_health = health.get(provider_id)
    if trusted_health is None:
        reason_codes.append(RoutingReasonCode.HEALTH_UNKNOWN)
    elif trusted_health is HealthState.UNAVAILABLE:
        reason_codes.append(RoutingReasonCode.HEALTH_UNAVAILABLE)
    elif trusted_health is HealthState.DEGRADED and not allow_degraded_health:
        reason_codes.append(RoutingReasonCode.HEALTH_DEGRADED_NOT_ALLOWED)

    trusted_cost = cost.get((provider_id, model_id))
    if request.max_estimated_cost is not None:
        if trusted_cost is None:
            reason_codes.append(RoutingReasonCode.COST_UNKNOWN)
        elif trusted_cost > request.max_estimated_cost:
            reason_codes.append(RoutingReasonCode.COST_EXCEEDED)

    return CandidateEvaluation(
        provider_id=provider_id,
        model_id=model_id,
        eligible=not reason_codes,
        reason_codes=tuple(reason_codes),
        effective_capabilities=effective,
        trusted_cost=trusted_cost,
        trusted_health=trusted_health,
    )


def _apply_optimization(
    eligible: list[CandidateEvaluation], optimization: OptimizationPolicy
) -> list[CandidateEvaluation]:
    """Narrows `eligible` under an explicit optimization policy. May return
    an EMPTY list -- that is a valid, meaningful outcome (`LOWEST_COST`
    with no known-cost candidate to compare), and the caller
    (`route_providers`) must treat an empty result as `NO_ELIGIBLE_PROVIDER`,
    never fall through to picking an arbitrary candidate anyway.

    LOWEST_COST semantics (v0.2.3 hostile-review finding F-01; see
    'Hard constraints vs. optimization' / 'LOWEST_COST unknown-cost
    semantics' in the contract doc): a candidate with unknown trusted cost
    can never be proven cheapest, so it never wins LOWEST_COST -- not
    "excluded quietly," but structurally: only candidates with a KNOWN
    trusted cost are even considered. If NO eligible candidate has a known
    cost, LOWEST_COST has nothing to compare and returns no candidate at
    all -- it does NOT silently degrade to an arbitrary deterministic pick
    mislabeled as a cost-based decision. `route_providers` reports this as
    `NO_ELIGIBLE_PROVIDER`, never a `SELECTED` result whose `reason` claims
    a cost comparison that never happened."""
    if optimization is OptimizationPolicy.DETERMINISTIC:
        return eligible
    known_cost = [c for c in eligible if c.trusted_cost is not None]
    if not known_cost:
        return []
    minimum = min(c.trusted_cost for c in known_cost)
    return [c for c in known_cost if c.trusted_cost == minimum]


def route_providers(
    registry: ProviderRegistry,
    request: ProviderRoutingRequest,
    *,
    locality: ProviderLocalitySnapshot | None = None,
    health: ProviderHealthSnapshot | None = None,
    cost: ProviderCostSnapshot | None = None,
    optimization: OptimizationPolicy = OptimizationPolicy.DETERMINISTIC,
    allow_degraded_health: bool = False,
) -> ProviderSelectionResult:
    """Read-only, deterministic routing evaluation over `registry`'s
    currently-registered providers/models. Never invokes a provider, never
    mutates `registry` or `request`. `locality`/`health`/`cost` default to
    empty snapshots (every provider unknown-locality/unknown-health/
    unknown-cost) if omitted -- an empty health snapshot alone is enough to
    make every candidate ineligible (`HEALTH_UNKNOWN`, fail closed), so a
    caller must supply real trusted health data to get a `SELECTED` result.

    `optimization` MUST be a genuine `OptimizationPolicy` member -- v0.2.3
    hostile-review finding F-04: `_apply_optimization` branches on
    `optimization is OptimizationPolicy.DETERMINISTIC`, so an unvalidated
    non-member value (a typo string, an int, `None`) would silently fall
    through to the `LOWEST_COST` branch instead of failing loudly, exactly
    the "unrecognized mode falls through toward success" defect
    `fake_provider.py`'s `_require_valid_mode` exists to prevent for
    `FakeProviderMode`. Rejected here, before any branch, the same way."""
    if not isinstance(optimization, OptimizationPolicy):
        raise TypeError(f"optimization must be an OptimizationPolicy member, got {optimization!r}")

    locality = locality if locality is not None else ProviderLocalitySnapshot()
    health = health if health is not None else ProviderHealthSnapshot()
    cost = cost if cost is not None else ProviderCostSnapshot()

    evaluations: list[CandidateEvaluation] = []
    for definition in registry.list_definitions():
        for model in registry.list_models(definition.provider_id):
            evaluations.append(
                _evaluate_candidate(
                    definition, model.model_id, model.capabilities, request,
                    locality, health, cost, allow_degraded_health=allow_degraded_health,
                )
            )

    eligible = [e for e in evaluations if e.eligible]
    if not eligible:
        return ProviderSelectionResult(
            routing_request_id=request.routing_request_id,
            status=SelectionStatus.NO_ELIGIBLE_PROVIDER,
            selected=None,
            evaluations=tuple(evaluations),
            optimization=optimization,
            allow_degraded_health=allow_degraded_health,
            policy_version=POLICY_VERSION,
        )

    narrowed = _apply_optimization(eligible, optimization)
    if not narrowed:
        # LOWEST_COST with no known-cost candidate among the eligible set:
        # there was nothing to compare, so nothing is selected -- never an
        # arbitrary pick mislabeled as a cost-based decision (finding F-01).
        return ProviderSelectionResult(
            routing_request_id=request.routing_request_id,
            status=SelectionStatus.NO_ELIGIBLE_PROVIDER,
            selected=None,
            evaluations=tuple(evaluations),
            optimization=optimization,
            allow_degraded_health=allow_degraded_health,
            policy_version=POLICY_VERSION,
        )
    winner = sorted(narrowed, key=lambda c: (c.provider_id, c.model_id))[0]

    record = ProviderSelectionRecord(
        routing_request_id=request.routing_request_id,
        provider_id=winner.provider_id,
        model_id=winner.model_id,
        effective_capabilities=winner.effective_capabilities,
        trusted_health=winner.trusted_health,
        trusted_cost=winner.trusted_cost,
        reason=(
            f"selected via {optimization.value} policy and deterministic "
            f"(provider_id, model_id) tie-break among {len(narrowed)} candidate(s) "
            f"remaining after optimization (of {len(eligible)} eligible)"
        ),
        policy_version=POLICY_VERSION,
    )
    return ProviderSelectionResult(
        routing_request_id=request.routing_request_id,
        status=SelectionStatus.SELECTED,
        selected=record,
        evaluations=tuple(evaluations),
        optimization=optimization,
        allow_degraded_health=allow_degraded_health,
        policy_version=POLICY_VERSION,
    )
