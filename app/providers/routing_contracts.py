"""Vendor-neutral Provider Router contracts (v0.2.3 — Provider Router +
Cost / Health / Fallback Policy; `docs/V0_2_3_PROVIDER_ROUTER_SECURITY_CONTRACT.md`).

Central invariant: **the router may select computational capability, it may
never grant authority**. Every routing output type here is `frozen=True,
extra="forbid"` (the same `CompatibleModel` pattern v0.2.2 established):
`permission`/`approval`/`authorization`/`tool_access`/`execute`/`credential`/
`api_key`/`selected`/`recommended`/`priority`/`rank`/`routing_score` cannot
be attached to any of them without an explicit, reviewed field addition.

`ProviderRoutingRequest` is the only routing INPUT that comes from ordinary
trusted calling code and is validated the same way `ProviderRequest` is
(`validate_identifier` on every identifier field, `validate_default=True` so
a left-at-default mutable field is deep-frozen too, exactly like v0.2.1/
v0.2.2's contracts).

`ProviderLocalitySnapshot`/`ProviderHealthSnapshot`/`ProviderCostSnapshot`
are trusted, Jarvis-supplied, per-call routing data — deliberately NOT new
fields on v0.2.2's `ProviderDefinition`/`ModelDefinition` (that promoted,
hostile-reviewed candidate is not touched by this phase at all) and
deliberately NOT Pydantic models (they are small, hand-rolled, frozen
wrappers around a defensively-copied `Mapping`, matching how
`ProviderRegistry` itself -- also a trusted in-memory store -- is a plain
Python class rather than a Pydantic model). Each performs its own
construction-time validation (finite/non-negative cost, valid enum values)
and defends against input aliasing exactly like v0.2.1/v0.2.2's `deep_freeze`
does: the caller's original dict can be freely mutated after construction
without affecting the snapshot.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.providers.contracts import ProviderCapability, validate_identifier

_FROZEN = ConfigDict(frozen=True, extra="forbid", validate_default=True)

_MAX_ID_SET_SIZE = 256


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- enums -------------------------------------------------------------------


class PrivacyRequirement(str, enum.Enum):
    """Exactly two values -- see 'Privacy / locality' in the v0.2.3 contract
    doc for why a third ('ANY') and a separate 'locality_requirement' field
    were both considered and deliberately rejected as redundant/ambiguous.

    CLOUD_ALLOWED: no locality constraint (the default -- also what 'ANY'
    would have meant).
    LOCAL_ONLY: hard constraint -- only a provider with trusted locality
    LOCAL is eligible; unknown locality never satisfies this, and there is
    no cloud fallback."""

    CLOUD_ALLOWED = "CLOUD_ALLOWED"
    LOCAL_ONLY = "LOCAL_ONLY"


class ProviderLocality(str, enum.Enum):
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class HealthState(str, enum.Enum):
    """'Unknown' is deliberately NOT a member here -- it is represented by a
    provider's absence from a `ProviderHealthSnapshot` (see that class), so
    'no trusted health information was supplied' and 'a trusted source
    explicitly reported a value' can never be confused with each other."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class OptimizationPolicy(str, enum.Enum):
    """Deliberately minimal (v0.2.3 contract doc, 'Hard constraints vs.
    optimization') -- no 'BEST'/'SMART'/'QUALITY' without a demonstrated
    need. DETERMINISTIC applies no preference beyond the final tie-break.
    LOWEST_COST prefers the minimum KNOWN trusted cost among eligible
    candidates; if none have a known cost it degrades to DETERMINISTIC over
    the unchanged eligible set (documented, not a silent behavior change)."""

    DETERMINISTIC = "DETERMINISTIC"
    LOWEST_COST = "LOWEST_COST"


class RoutingReasonCode(str, enum.Enum):
    """Machine-readable, exhaustive: every value here corresponds to exactly
    one reachable branch in `router.route_providers`'s hard-constraint
    pipeline -- no placeholder/aspirational codes (v0.2.3 contract doc,
    'no brittle grep-only security theatre' applied to the reason vocabulary
    too)."""

    PROVIDER_DISABLED = "PROVIDER_DISABLED"
    PROVIDER_DENIED = "PROVIDER_DENIED"
    PROVIDER_NOT_ALLOWED = "PROVIDER_NOT_ALLOWED"
    CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
    LOCALITY_MISMATCH = "LOCALITY_MISMATCH"
    HEALTH_UNAVAILABLE = "HEALTH_UNAVAILABLE"
    HEALTH_UNKNOWN = "HEALTH_UNKNOWN"
    HEALTH_DEGRADED_NOT_ALLOWED = "HEALTH_DEGRADED_NOT_ALLOWED"
    COST_EXCEEDED = "COST_EXCEEDED"
    COST_UNKNOWN = "COST_UNKNOWN"


class SelectionStatus(str, enum.Enum):
    SELECTED = "SELECTED"
    NO_ELIGIBLE_PROVIDER = "NO_ELIGIBLE_PROVIDER"


# --- trusted routing-time snapshots (hand-rolled, not Pydantic) -------------


def _validate_cost_value(value: Decimal) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"cost values must be decimal.Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"cost value must be finite (no NaN/Infinity): {value!r}")
    if value < 0:
        raise ValueError(f"cost value must not be negative: {value!r}")


@dataclass(frozen=True)
class ProviderLocalitySnapshot:
    """Trusted `provider_id -> ProviderLocality` mapping, Jarvis-supplied at
    routing-call time. A provider absent from `values` has unknown locality
    (never satisfies `LOCAL_ONLY`, never matters for `CLOUD_ALLOWED`). The
    constructor defensively copies `values` so a caller mutating their
    original dict afterward cannot affect this snapshot."""

    values: Mapping[str, ProviderLocality] = field(default_factory=dict)

    def __post_init__(self) -> None:
        copied: dict[str, ProviderLocality] = {}
        for key, value in dict(self.values).items():
            if not isinstance(value, ProviderLocality):
                raise TypeError(f"locality value for {key!r} must be a ProviderLocality, got {type(value).__name__}")
            copied[key] = value
        object.__setattr__(self, "values", MappingProxyType(copied))

    def get(self, provider_id: str) -> ProviderLocality | None:
        return self.values.get(provider_id)


@dataclass(frozen=True)
class ProviderHealthSnapshot:
    """Trusted `provider_id -> HealthState` mapping. Absence means unknown
    health (fails closed -- see `HealthState`'s docstring). Never populated
    from `ProviderResponse`/model output/opaque metadata anywhere in this
    codebase; v0.2.3 performs no live health checks -- these are
    deterministic, caller-constructed snapshots."""

    values: Mapping[str, HealthState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        copied: dict[str, HealthState] = {}
        for key, value in dict(self.values).items():
            if not isinstance(value, HealthState):
                raise TypeError(f"health value for {key!r} must be a HealthState, got {type(value).__name__}")
            copied[key] = value
        object.__setattr__(self, "values", MappingProxyType(copied))

    def get(self, provider_id: str) -> HealthState | None:
        return self.values.get(provider_id)


@dataclass(frozen=True)
class ProviderCostSnapshot:
    """Trusted `(provider_id, model_id) -> Decimal` mapping of estimated
    total inference cost (USD). Independent of `app.config.pricing`
    (token-based, `Settings`/environment-dependent -- unusable before a call
    is made) and of any provider-claimed cost in metadata/response content.
    A missing key is unknown cost, distinct from a present `Decimal("0")`
    (a legitimate zero cost). Every value is validated finite and
    non-negative at construction -- `Decimal("NaN")`/`Decimal("Infinity")`/
    negative values raise immediately, never reach a comparison."""

    values: Mapping[tuple[str, str], Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        copied: dict[tuple[str, str], Decimal] = {}
        for key, value in dict(self.values).items():
            _validate_cost_value(value)
            copied[key] = value
        object.__setattr__(self, "values", MappingProxyType(copied))

    def get(self, key: tuple[str, str]) -> Decimal | None:
        return self.values.get(key)


# --- Pydantic contracts (request / evaluation / selection) -----------------


class ProviderRoutingRequest(BaseModel):
    """A vendor-neutral routing request -- requirements, never provider-
    specific preferences (v0.2.3 contract doc). Constructed only by trusted
    calling code, never derived from provider output."""

    model_config = _FROZEN

    routing_request_id: str = Field(default_factory=_new_id)
    required_capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
    privacy_requirement: PrivacyRequirement = PrivacyRequirement.CLOUD_ALLOWED
    max_estimated_cost: Decimal | None = Field(default=None)
    allowed_provider_ids: frozenset[str] | None = None
    denied_provider_ids: frozenset[str] = Field(default_factory=frozenset)
    created_at: datetime = Field(default_factory=_now)

    @field_validator("routing_request_id")
    @classmethod
    def _validate_routing_request_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("allowed_provider_ids", "denied_provider_ids")
    @classmethod
    def _validate_id_set(cls, value: frozenset[str] | None) -> frozenset[str] | None:
        if value is None:
            return None
        if len(value) > _MAX_ID_SET_SIZE:
            raise ValueError(f"must not exceed {_MAX_ID_SET_SIZE} entries, got {len(value)}")
        return frozenset(validate_identifier(v) for v in value)

    @field_validator("max_estimated_cost")
    @classmethod
    def _validate_max_estimated_cost(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if not isinstance(value, Decimal):
            value = Decimal(str(value))
        if not value.is_finite():
            raise ValueError(f"max_estimated_cost must be finite: {value!r}")
        if value < 0:
            raise ValueError(f"max_estimated_cost must not be negative: {value!r}")
        return value


class CandidateEvaluation(BaseModel):
    """One registered `(provider_id, model_id)` pair's routing evaluation --
    ALWAYS present for every registered model, eligible or not, so a
    rejected candidate's reason is auditable (v0.2.3 contract doc,
    'Architecture'). Carries only trusted, non-secret data: `trusted_cost`/
    `trusted_health` are the resolved values FROM the snapshots the router
    was given, never a copy of opaque provider/model metadata.

    `eligible ⟺ reason_codes == ()` is enforced structurally (v0.2.3
    hostile-review finding F-03), not merely by `route_providers()`'s own
    care: a candidate the router marks eligible can never simultaneously
    carry a rejection reason, and a rejected candidate can never claim
    `eligible=True` -- true regardless of how this type is constructed."""

    model_config = _FROZEN

    provider_id: str
    model_id: str
    eligible: bool
    reason_codes: tuple[RoutingReasonCode, ...] = Field(default_factory=tuple)
    effective_capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
    trusted_cost: Decimal | None = None
    trusted_health: HealthState | None = None

    @model_validator(mode="after")
    def _check_eligibility_reason_consistency(self) -> "CandidateEvaluation":
        if self.eligible and self.reason_codes:
            raise ValueError("an eligible candidate must not carry rejection reason_codes")
        if not self.eligible and not self.reason_codes:
            raise ValueError("an ineligible candidate must carry at least one reason code")
        return self


class ProviderSelectionRecord(BaseModel):
    """The single selected candidate, if any -- data only, never authority.
    No `.authorize()`/`.execute()`/`.approve()` method exists on this type
    or on `ProviderSelectionResult`; nothing here converts a selection into
    an action. `reason` is built only from Jarvis-controlled routing facts
    (optimization policy name, candidate counts), never from opaque
    metadata or model output."""

    model_config = _FROZEN

    selection_id: str = Field(default_factory=_new_id)
    routing_request_id: str
    provider_id: str
    model_id: str
    effective_capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
    trusted_health: HealthState | None = None
    trusted_cost: Decimal | None = None
    reason: str
    policy_version: str
    created_at: datetime = Field(default_factory=_now)


class ProviderSelectionResult(BaseModel):
    """The router's complete, immutable output. `evaluations` covers EVERY
    registered `(provider_id, model_id)` pair in deterministic
    `(provider_id, model_id)` order, selected or not -- full auditability,
    never a hidden partial view.

    Internal consistency is enforced structurally (v0.2.3 hostile-review
    finding F-03), not merely by `route_providers()`'s own care -- a future
    consumer (e.g. a durable-persistence layer that deserializes/
    reconstructs this type) must not be able to misrepresent a decision:

    - `status is SELECTED` if and only if `selected is not None`;
    - a non-`None` `selected` must correspond to EXACTLY one entry in
      `evaluations` with a matching `(provider_id, model_id)`, and that
      entry must itself be `eligible`;
    - `evaluations` must not contain two entries for the same
      `(provider_id, model_id)` (audit ambiguity -- which one is
      authoritative?).

    `optimization`/`allow_degraded_health` are the ACTUAL policy inputs
    `route_providers()` applied for this call, always recorded here
    (v0.2.3 hostile-review finding F-05) -- not only when a selection
    succeeds. Before this fix, a `NO_ELIGIBLE_PROVIDER` result carried no
    trace of which optimization policy or degraded-health opt-in was in
    effect (the only place either was recorded was inside a `SELECTED`
    record's free-text `reason`), so two identical requests that produced
    different outcomes purely because of these call-site-only arguments
    could not be told apart after the fact."""

    model_config = _FROZEN

    routing_request_id: str
    status: SelectionStatus
    selected: ProviderSelectionRecord | None = None
    evaluations: tuple[CandidateEvaluation, ...] = Field(default_factory=tuple)
    optimization: OptimizationPolicy
    allow_degraded_health: bool
    policy_version: str
    created_at: datetime = Field(default_factory=_now)

    @model_validator(mode="after")
    def _check_result_consistency(self) -> "ProviderSelectionResult":
        if (self.status is SelectionStatus.SELECTED) != (self.selected is not None):
            raise ValueError(
                "status must be SELECTED if and only if selected is not None "
                f"(status={self.status!r}, selected={self.selected!r})"
            )

        seen: set[tuple[str, str]] = set()
        for evaluation in self.evaluations:
            key = (evaluation.provider_id, evaluation.model_id)
            if key in seen:
                raise ValueError(f"duplicate evaluation for {key!r} -- evaluations must be unique per (provider_id, model_id)")
            seen.add(key)

        if self.selected is not None:
            key = (self.selected.provider_id, self.selected.model_id)
            matching = [e for e in self.evaluations if (e.provider_id, e.model_id) == key]
            if not matching:
                raise ValueError(f"selected {key!r} does not correspond to any entry in evaluations")
            if not matching[0].eligible:
                raise ValueError(f"selected {key!r} corresponds to an evaluation marked ineligible")

        return self
