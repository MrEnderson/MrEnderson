"""ProviderRegistry — Jarvis-controlled provider/model catalogue, identity/
discovery/capability-query only (contract §20; v0.2.2 — Provider Registry +
Capability Metadata). Same shape as
`app.decision_intelligence.tool_adapters.ToolAdapterRegistry`:
register/get/contains/list, duplicate registration fails deterministically
(no "last provider wins" identity substitution), unknown lookup fails
closed. Registering a provider (and, as of v0.2.2, its models) grants zero
execution authority and performs zero selection/routing/fallback — see
contract §5, §20; routing is out of scope until v0.2.3 (contract §6, §53).

`.definition` on `AIProvider` is an ordinary Python property, not something
Pydantic can force to be idempotent — nothing in the `AIProvider` protocol
itself prevents a provider object from returning a *different*
`ProviderDefinition` on each read. A hostile review confirmed this was
exploitable: calling `.definition` more than once per operation (as an
earlier version of this file did, via `hasattr()` plus a separate
attribute read) let a shape-shifting provider register under one identity
and be reported under another. This registry reads `provider.definition`
**exactly once**, at registration time, and pins that snapshot as the
provider's identity for every subsequent `get_enabled`/`list_definitions`
call — later reads of the live `.definition` property are never consulted
again for this registry's own bookkeeping.

v0.2.2 model registration is deliberately NOT read from the live provider
object at all (the `AIProvider` protocol has no `.models` property to
misread in the first place) — models are explicit `ModelDefinition` value
objects passed directly to `register()`, so there is no live-re-read risk
for them to begin with; they are pinned by construction, not by a
snapshot-taking mechanism.

Model identity namespace (v0.2.2 §18): composite `(provider_id, model_id)`
— a model's simple `model_id` need only be unique WITHIN its own provider,
mirroring how real vendor model ids already look in this codebase (e.g.
`FAKE_MODEL_ID = "fake/basic"`). Two different providers may each register
a model_id `"basic"` without conflict; the same provider registering
`"basic"` twice does conflict.

v0.2.2 identity hardening: `register()` originally accepted a `replace:
bool = False` escape hatch (inherited from v0.2.1, itself mirroring
`ToolAdapterRegistry`/`ToolRegistry`'s administrative-replacement
pattern) that let trusted calling code wholesale-replace an
already-registered provider's object, enabled status, capabilities,
metadata, and entire model set. A hostile review confirmed `replace=True`
was never reachable from provider-supplied data and had no production
caller, but also found v0.2.2 has no demonstrated operational need for
runtime provider replacement — and `ProviderRegistry`'s purpose is to
establish STABLE Jarvis-controlled computational identities, not a
mutable configuration store. `replace` has therefore been REMOVED (not
merely defaulted off): once a provider identity is registered in a given
`ProviderRegistry` instance, no ordinary call can redefine it, its
enabled status, its capabilities, its metadata, or its model catalogue —
`DuplicateProviderError` is unconditional. This is scoped to
`ProviderRegistry` only; `ToolAdapterRegistry` and `ToolRegistry` keep
their own `replace=True`, which the hostile review found IS exercised by
real production/test call sites (e.g. disabling a tool adapter) and is
unaffected by this change. A future provider-configuration lifecycle, if
one is ever needed, must be designed explicitly as its own mechanism —
this registry deliberately provides no `update_provider`/
`replace_provider`/`upsert_provider`/`force_register` alternate path."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.providers.contracts import ModelDefinition, ModelOwnershipError, ProviderDefinition
from app.providers.protocol import AIProvider


class ProviderRegistrationError(Exception):
    """Base class for all typed ProviderRegistry errors."""


class DuplicateProviderError(ProviderRegistrationError):
    """Raised on ANY re-registration attempt for an already-registered
    `provider_id` — identical, different enabled status, expanded/reduced
    capabilities, different metadata, different `provider_type`, a
    different provider object, or a different model set. v0.2.2 identity
    hardening (superseding v0.2.1's `replace=True` escape hatch, see
    module docstring): once registered, a provider identity is
    process-lifetime stable. There is no ordinary path to redefine it."""

    def __init__(self, provider_id: str):
        super().__init__(
            f"A provider is already registered for '{provider_id}'; "
            f"provider identity is process-lifetime stable and cannot be "
            f"redefined by ordinary registration (v0.2.2 identity hardening)"
        )
        self.provider_id = provider_id


class UnknownProviderError(ProviderRegistrationError):
    def __init__(self, provider_id: str):
        super().__init__(f"No provider registered for '{provider_id}'")
        self.provider_id = provider_id


class DisabledProviderError(ProviderRegistrationError):
    """Registered, but not eligible for invocation — see
    `ProviderRegistry.get_enabled`. Deliberately a distinct error from
    `UnknownProviderError` so a caller/test can tell "doesn't exist" apart
    from "exists but is disabled," while both still fail closed."""

    def __init__(self, provider_id: str):
        super().__init__(f"Provider '{provider_id}' is registered but disabled")
        self.provider_id = provider_id


class InvalidProviderError(ProviderRegistrationError):
    pass


class DuplicateModelError(ProviderRegistrationError):
    """Raised when the SAME registration call's `models` batch names the
    same `model_id` twice for the same provider. (A model catalogue
    conflict against an ALREADY-registered provider's models is instead a
    `DuplicateProviderError`, raised before any model in the new batch is
    even considered — see module docstring: v0.2.2 identity hardening
    means a registered provider's model catalogue is equally
    process-lifetime stable.)"""

    def __init__(self, provider_id: str, model_id: str):
        super().__init__(
            f"Model '{model_id}' is registered twice for provider "
            f"'{provider_id}' within the same registration call"
        )
        self.provider_id = provider_id
        self.model_id = model_id


class UnknownModelError(ProviderRegistrationError):
    def __init__(self, provider_id: str, model_id: str):
        super().__init__(f"No model registered for ('{provider_id}', '{model_id}')")
        self.provider_id = provider_id
        self.model_id = model_id


@dataclass(frozen=True)
class _RegisteredProvider:
    """The provider object plus the ONE `ProviderDefinition` snapshot taken
    of it at registration time, plus its pinned model set — see module
    docstring. `models` is stored in registration order here; callers get
    a deterministic `(provider_id, model_id)`-sorted view via
    `list_models()`, never this internal order directly."""

    provider: AIProvider
    definition: ProviderDefinition
    models: tuple[ModelDefinition, ...]


class ProviderRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _RegisteredProvider] = {}
        self._models: dict[tuple[str, str], ModelDefinition] = {}

    def register(
        self,
        provider: AIProvider,
        *,
        models: Sequence[ModelDefinition] = (),
    ) -> None:
        """Registers `provider` and, atomically, its `models`. Every check
        below runs and every exception it can raise is raised BEFORE this
        method touches `self._entries`/`self._models` at all — a failed
        call leaves the registry in EXACTLY the state it was in before the
        call (v0.2.2 §16: no partial/half registration is ever visible,
        not even to a concurrent reader on the same thread mid-call, since
        nothing is mutated until every check below has already passed).

        There is no `replace` parameter (v0.2.2 identity hardening — see
        module docstring): an already-registered `provider_id` ALWAYS
        raises `DuplicateProviderError`, unconditionally, whether the new
        definition/models are identical, disjoint, a strict superset, or
        anything else. Provider identity, once registered in a given
        registry instance, is process-lifetime stable."""
        if not isinstance(provider, AIProvider):
            raise InvalidProviderError(
                f"Object does not implement the AIProvider protocol "
                f"(definition/generate) — got {type(provider).__name__}"
            )

        # Exactly one read of the live `.definition` property, ever, for
        # this registration — see module docstring.
        definition = provider.definition
        if not isinstance(definition, ProviderDefinition):
            raise InvalidProviderError(
                f"provider.definition did not return a ProviderDefinition — "
                f"got {type(definition).__name__}"
            )

        provider_id = definition.provider_id
        if provider_id in self._entries:
            raise DuplicateProviderError(provider_id)

        # Validate the ENTIRE models batch before mutating any state.
        validated_models: list[ModelDefinition] = []
        seen_model_ids: set[str] = set()
        for model in models:
            if not isinstance(model, ModelDefinition):
                raise InvalidProviderError(
                    f"models must all be ModelDefinition instances — got {type(model).__name__}"
                )
            if model.provider_id != provider_id:
                raise ModelOwnershipError(
                    f"Model '{model.model_id}' belongs to provider "
                    f"'{model.provider_id}', not '{provider_id}'"
                )
            if model.model_id in seen_model_ids:
                raise DuplicateModelError(provider_id, model.model_id)
            seen_model_ids.add(model.model_id)
            validated_models.append(model)

        # All validation passed -- commit. `provider_id` is guaranteed NOT
        # already in self._entries at this point (checked above,
        # unconditionally), so there is never prior model state to
        # reconcile or delete here.
        self._entries[provider_id] = _RegisteredProvider(
            provider=provider, definition=definition, models=tuple(validated_models)
        )
        for model in validated_models:
            self._models[(provider_id, model.model_id)] = model

    def get(self, provider_id: str) -> AIProvider:
        """Identity/discovery lookup only — does NOT check `enabled`. Use
        `get_enabled` when the caller intends to actually invoke the
        provider (contract §20: "registered" and "eligible for invocation"
        must be an explicit distinction, never implicit)."""
        entry = self._entries.get(provider_id)
        if entry is None:
            raise UnknownProviderError(provider_id)
        return entry.provider

    def get_enabled(self, provider_id: str) -> AIProvider:
        entry = self._entries.get(provider_id)
        if entry is None:
            raise UnknownProviderError(provider_id)
        if not entry.definition.enabled:
            raise DisabledProviderError(provider_id)
        return entry.provider

    def contains(self, provider_id: str) -> bool:
        return provider_id in self._entries

    def list_definitions(self) -> list[ProviderDefinition]:
        """Deterministic `provider_id`-sorted order — presentation order,
        not preference (v0.2.2 §22-§24)."""
        return sorted(
            (entry.definition for entry in self._entries.values()),
            key=lambda d: d.provider_id,
        )

    def get_model(self, provider_id: str, model_id: str) -> ModelDefinition:
        """Fails closed with `UnknownProviderError` if the provider itself
        isn't registered, or `UnknownModelError` if the provider exists but
        has no such model — two distinct, informative reasons, same
        fail-closed outcome (v0.2.2 §40)."""
        if provider_id not in self._entries:
            raise UnknownProviderError(provider_id)
        model = self._models.get((provider_id, model_id))
        if model is None:
            raise UnknownModelError(provider_id, model_id)
        return model

    def list_models(self, provider_id: str) -> tuple[ModelDefinition, ...]:
        """Deterministic `model_id`-sorted order — presentation order, not
        preference. Raises `UnknownProviderError` for an unregistered
        provider_id (never silently returns an empty tuple for "doesn't
        exist" — that would be indistinguishable from "exists, has no
        models yet")."""
        if provider_id not in self._entries:
            raise UnknownProviderError(provider_id)
        return tuple(sorted(self._entries[provider_id].models, key=lambda m: m.model_id))
