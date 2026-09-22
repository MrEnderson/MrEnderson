"""Read-only capability catalogue over a `ProviderRegistry` (v0.2.2 —
Provider Registry + Capability Metadata).

```text
Requirement
    |
    v
Capability Catalogue
    |
    +-- candidate A
    +-- candidate B
    +-- candidate C
             |
             X
       NO RANKING
       NO SELECTION
       NO ROUTING
       NO FALLBACK
```

`find_compatible_models` performs zero provider invocation, zero network,
zero ToolAdapter access, zero permission/approval evaluation. It is a pure
function over a `ProviderRegistry`'s already-registered, already-pinned
state: it never calls `.generate()` on anything, and never mutates the
registry it reads. Provider selection/routing/fallback belongs to v0.2.3
(contract §6, §53) — this module returns the full candidate collection and
stops there; see `CompatibleModel` in `contracts.py` for why the result
type cannot structurally carry a selection signal."""
from __future__ import annotations

from app.providers.contracts import CompatibleModel, ProviderCapability
from app.providers.registry import ProviderRegistry


def effective_capabilities(
    provider_capabilities: frozenset[ProviderCapability],
    model_capabilities: frozenset[ProviderCapability],
) -> frozenset[ProviderCapability]:
    """`provider ∩ model` — a capability must be declared at BOTH the
    provider level and the model level to count as effectively available
    (the same rule `FakeProvider.generate()` enforces before invocation;
    see hostile-review §12). Never a union: a model cannot gain a
    capability its provider doesn't declare, and a provider's capability
    does not automatically propagate to every model it hosts."""
    return provider_capabilities & model_capabilities


def find_compatible_models(
    registry: ProviderRegistry,
    required_capabilities: frozenset[ProviderCapability] = frozenset(),
    *,
    enabled_only: bool = True,
) -> tuple[CompatibleModel, ...]:
    """Returns every catalogue entry whose effective capabilities are a
    superset of `required_capabilities` (`required ⊆ effective`, exact
    containment — a candidate satisfying only part of a multi-capability
    requirement is excluded, v0.2.2 §23), in deterministic
    `(provider_id, model_id)` order.

    An empty `required_capabilities` (the default) returns every
    administratively eligible catalogue entry — "all eligible catalogue
    entries," never "recommended models" (v0.2.2 §24).

    `enabled_only=True` (the default) excludes every model belonging to a
    disabled provider — `enabled` is administrative catalogue state only,
    never a stand-in for health/availability/permission (v0.2.2 §26).

    Ordering is deterministic PRESENTATION order, not ranking: registering
    the same definitions in a different order produces the identical
    result order (v0.2.2 §22, §63) — this function never returns
    `candidates[0]` or otherwise treats any position as preferred."""
    candidates: list[CompatibleModel] = []
    for definition in registry.list_definitions():
        if enabled_only and not definition.enabled:
            continue
        for model in registry.list_models(definition.provider_id):
            effective = effective_capabilities(definition.capabilities, model.capabilities)
            if required_capabilities <= effective:
                candidates.append(
                    CompatibleModel(
                        provider_id=definition.provider_id,
                        model_id=model.model_id,
                        effective_capabilities=effective,
                    )
                )
    candidates.sort(key=lambda candidate: (candidate.provider_id, candidate.model_id))
    return tuple(candidates)
