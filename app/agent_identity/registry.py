"""AgentRegistry — Jarvis-controlled agent identity catalogue, identity/
discovery only (v0.2.4; `docs/V0_2_4_AGENT_IDENTITY_AND_REGISTRY_SECURITY_CONTRACT.md`).
Same shape as `app.providers.registry.ProviderRegistry` (post-v0.2.2
identity hardening) and `app.decision_intelligence.tool_adapters.ToolAdapterRegistry`:
register/get/contains/list, duplicate registration fails deterministically
and UNCONDITIONALLY (no `replace` parameter at all — this phase starts at
the destination v0.2.2's hardening pass arrived at, not at its original
`replace=True` starting point), unknown lookup fails closed. Registering an
agent identity grants zero execution authority, zero permission, and
performs zero provider/model invocation or routing.

This module does not import `app.providers.registry.ProviderRegistry` (no
agent-registry operation ever looks up, mutates, or reasons about a
provider/model registration) and does not import anything from
`app.agents` (the pre-existing, unrelated, executable v0.1.3 agent-dispatch
package — see the contract doc for why that module boundary is
deliberate)."""
from __future__ import annotations

from dataclasses import dataclass

from app.agent_identity.contracts import AgentDefinition


class AgentRegistrationError(Exception):
    """Base class for all typed AgentRegistry errors."""


class DuplicateAgentError(AgentRegistrationError):
    """Raised on ANY re-registration attempt for an already-registered
    `agent_id` — identical, different role, different enabled status,
    different metadata, different provider preferences, anything.
    Unconditional: once registered, an agent identity is process-lifetime
    stable. There is no ordinary (or extraordinary) path to redefine it in
    v0.2.4 — see the contract doc for why this phase starts where v0.2.2's
    hardening pass ended rather than reintroducing `replace=True`."""

    def __init__(self, agent_id: str):
        super().__init__(
            f"An agent is already registered for '{agent_id}'; agent identity is "
            f"process-lifetime stable and cannot be redefined by ordinary registration"
        )
        self.agent_id = agent_id


class UnknownAgentError(AgentRegistrationError):
    def __init__(self, agent_id: str):
        super().__init__(f"No agent registered for '{agent_id}'")
        self.agent_id = agent_id


class DisabledAgentError(AgentRegistrationError):
    """Registered, but not eligible for active orchestration — see
    `AgentRegistry.get_active`. Deliberately a distinct error from
    `UnknownAgentError` so a caller/test can tell "doesn't exist" apart
    from "exists but is disabled," while both still fail closed."""

    def __init__(self, agent_id: str):
        super().__init__(f"Agent '{agent_id}' is registered but disabled")
        self.agent_id = agent_id


class InvalidAgentError(AgentRegistrationError):
    pass


@dataclass(frozen=True)
class _RegisteredAgent:
    """Internal storage for the registry's OWN re-validated snapshot of a
    registered `AgentDefinition` (see `_pin_snapshot`)."""

    definition: AgentDefinition


def _pin_snapshot(agent: object) -> AgentDefinition:
    """The registry is the trust boundary (hostile review B-01), so it does
    not store the caller's object. It accepts only the exact
    `AgentDefinition` type -- a subclass could loosen `extra`/`frozen` and
    carry e.g. `permission="P5"` -- and rebuilds a fresh instance through
    full validation, so a record produced by Pydantic's validation-
    skipping construct/copy-with-update paths cannot be registered
    with unvalidated fields."""
    if type(agent) is not AgentDefinition:
        raise InvalidAgentError(
            f"register() requires an exact AgentDefinition instance — got {type(agent).__name__}"
        )
    try:
        fields = {name: getattr(agent, name) for name in AgentDefinition.model_fields}
        return AgentDefinition.model_validate(fields)
    except (AttributeError, ValueError) as exc:
        raise InvalidAgentError(
            "register() rejected an AgentDefinition that fails re-validation "
            "(constructed via a validation-bypassing path)"
        ) from exc


class AgentRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, _RegisteredAgent] = {}

    def register(self, agent: AgentDefinition) -> None:
        """Registers a re-validated snapshot of `agent`. Validates before
        mutating: an already-registered `agent_id` raises
        `DuplicateAgentError` unconditionally, before `self._entries` is
        touched at all."""
        snapshot = _pin_snapshot(agent)
        if snapshot.agent_id in self._entries:
            raise DuplicateAgentError(snapshot.agent_id)
        self._entries[snapshot.agent_id] = _RegisteredAgent(definition=snapshot)

    def get(self, agent_id: str) -> AgentDefinition:
        """Identity/discovery lookup only — does NOT check `enabled`. Use
        `get_active` when the caller intends to treat the identity as
        eligible for active orchestration (contract: "registered" and
        "eligible for active orchestration" must be an explicit
        distinction, never implicit)."""
        return self._lookup(agent_id).definition

    def get_active(self, agent_id: str) -> AgentDefinition:
        definition = self._lookup(agent_id).definition
        if not definition.enabled:
            raise DisabledAgentError(agent_id)
        return definition

    def contains(self, agent_id: str) -> bool:
        return isinstance(agent_id, str) and agent_id in self._entries

    def _lookup(self, agent_id: str) -> _RegisteredAgent:
        # A non-str key (e.g. an unhashable list) fails closed with the same
        # typed error as any unknown id, never a raw TypeError (B-10).
        entry = self._entries.get(agent_id) if isinstance(agent_id, str) else None
        if entry is None:
            raise UnknownAgentError(agent_id)
        return entry

    def list_definitions(self) -> list[AgentDefinition]:
        """Deterministic `agent_id`-sorted order — presentation order, not
        preference."""
        return sorted((entry.definition for entry in self._entries.values()), key=lambda a: a.agent_id)

    def list_enabled(self) -> list[AgentDefinition]:
        """Deterministic `agent_id`-sorted order, excluding disabled
        identities."""
        return [a for a in self.list_definitions() if a.enabled]
