"""ProviderRegistry — identity/discovery only (contract §20). Same shape as
`app.decision_intelligence.tool_adapters.ToolAdapterRegistry`:
register/get/contains/list, duplicate registration fails deterministically
(no "last provider wins" identity substitution), unknown lookup fails
closed. Registering a provider grants zero execution authority and
performs zero selection/routing/fallback — see contract §5, §20; routing
is out of scope until v0.2.3 (contract §6, §53).

`.definition` on `AIProvider` is an ordinary Python property, not something
Pydantic can force to be idempotent — nothing in the `AIProvider` protocol
itself prevents a provider object from returning a *different*
`ProviderDefinition` on each read. A hostile review confirmed this was
exploitable: calling `.definition` more than once per operation (as an
earlier version of this file did, via `hasattr()` plus a separate
attribute read) let a shape-shifting provider register under one identity
and be reported under another. This registry now reads `provider.
definition` **exactly once**, at registration time, and pins that snapshot
as the provider's identity for every subsequent `get_enabled`/
`list_definitions` call — later reads of the live `.definition` property
are never consulted again for this registry's own bookkeeping."""
from __future__ import annotations

from dataclasses import dataclass

from app.providers.contracts import ProviderDefinition
from app.providers.protocol import AIProvider


class ProviderRegistrationError(Exception):
    """Base class for all typed ProviderRegistry errors."""


class DuplicateProviderError(ProviderRegistrationError):
    def __init__(self, provider_id: str):
        super().__init__(
            f"A provider is already registered for '{provider_id}' (pass replace=True to replace it)"
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


@dataclass(frozen=True)
class _RegisteredProvider:
    """The provider object plus the ONE `ProviderDefinition` snapshot taken
    of it at registration time — see module docstring."""

    provider: AIProvider
    definition: ProviderDefinition


class ProviderRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _RegisteredProvider] = {}

    def register(self, provider: AIProvider, *, replace: bool = False) -> None:
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
        if provider_id in self._entries and not replace:
            raise DuplicateProviderError(provider_id)
        self._entries[provider_id] = _RegisteredProvider(provider=provider, definition=definition)

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
        return [entry.definition for entry in self._entries.values()]
