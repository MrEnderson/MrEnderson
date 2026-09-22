"""Vendor-neutral provider/model/request/response contracts (contract §4, §9-§16).

Every model here is a frozen (`ConfigDict(frozen=True)`), `extra="forbid"`
Pydantic object: identity/security fields cannot be reassigned after
construction, and an unexpected constructor field (e.g. a field named
`approved` smuggled onto `ProviderResponse`) raises `ValidationError`
immediately rather than being silently ignored — see contract §37
(mutability) and §14 (a response must never be able to masquerade as
authority). Every dict/list/set-valued field (`metadata`,
`provider_metadata`, `generation_parameters`, `structured_output`, ...) is
recursively deep-frozen via `app.providers.frozen.deep_freeze` on
construction: a hostile review confirmed that `ConfigDict(frozen=True)`
alone only blocks reassigning the field, not mutating a dict already
sitting in it, and `generation_parameters`/`structured_output` are both
part of the canonical request/response hash (`request_hash.py`) — an
in-place mutation there would have silently changed what an already-
"validated" object hashes to. Every identity field (`provider_id`,
`model_id`, `request_id`) is a validated, non-empty `str`, never inferred
from provider-supplied content (contract §7, §26)."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.frozen import deep_freeze

_FROZEN = ConfigDict(frozen=True, extra="forbid", validate_default=True)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


_MAX_IDENTIFIER_LENGTH = 256
_MAX_DISPLAY_NAME_LENGTH = 512
_CONTROL_CHARS = frozenset(chr(c) for c in range(0x20)) | {chr(0x7F)}


def validate_identifier(value: str) -> str:
    """Deterministic policy for machine identifiers (`provider_id`,
    `model_id`, `request_id`, `provider_type`, `task_class`,
    `structured_output_schema_name`) — hostile-review §8/§38. These are
    dict-keyed and exact-matched (by `ProviderRegistry`, by correlation
    checks); a control character or stray leading/trailing whitespace must
    never silently create two identifiers Jarvis treats as different, or
    corrupt a downstream log line. Chosen policy, deliberately narrow (not
    a full Unicode-confusable defense): reject blank, reject longer than
    256 characters, reject leading/trailing whitespace, reject any ASCII
    control character (0x00-0x1F, 0x7F) anywhere in the string. Broader
    Unicode normalization/confusable-character handling is out of scope
    for v0.2.1."""
    if not value.strip():
        raise ValueError("must not be blank")
    if len(value) > _MAX_IDENTIFIER_LENGTH:
        raise ValueError(f"must not exceed {_MAX_IDENTIFIER_LENGTH} characters")
    if value != value.strip():
        raise ValueError("must not have leading/trailing whitespace")
    if any(char in _CONTROL_CHARS for char in value):
        raise ValueError("must not contain control characters")
    return value


def validate_display_name(value: str) -> str:
    """More lenient than `validate_identifier`: display names are
    user-facing text, never dict-keyed or exact-matched for security
    decisions, so only blank/length are enforced."""
    if not value.strip():
        raise ValueError("must not be blank")
    if len(value) > _MAX_DISPLAY_NAME_LENGTH:
        raise ValueError(f"must not exceed {_MAX_DISPLAY_NAME_LENGTH} characters")
    return value


class ModelOwnershipError(ValueError):
    """Raised whenever a `ModelDefinition` claims a `provider_id` different
    from the provider it is being associated with — a provider must not
    invoke/claim a model belonging to another provider (hostile-review
    v0.2.1 §13, v0.2.2 §13). Lives here (not in `fake_provider.py`, where
    it originated) because both `FakeProvider` construction (a single
    provider/model pair) and `ProviderRegistry.register` (a provider with
    a whole batch of models, v0.2.2) need to raise the exact same error for
    the exact same invariant; `registry.py` must not depend on
    `fake_provider.py`, a test-only leaf module, to get at it. Re-exported
    from `app.providers.fake_provider` unchanged for backward
    compatibility with existing imports."""


class ProviderCapability(str, enum.Enum):
    """A model capability is descriptive metadata about what a model can
    compute — it is never a Jarvis permission. A model advertising CODING
    does not authorize repository writes; a model advertising TOOL_USE does
    not authorize invoking a Jarvis ToolAdapter (contract §11, §34). Only
    the existing v0.1.3 Permission/Approval Engines grant those."""

    TEXT_GENERATION = "TEXT_GENERATION"
    STRUCTURED_OUTPUT = "STRUCTURED_OUTPUT"
    REASONING = "REASONING"
    CODING = "CODING"
    VISION = "VISION"
    EMBEDDING = "EMBEDDING"
    RERANKING = "RERANKING"
    STREAMING = "STREAMING"
    TOOL_USE = "TOOL_USE"


class ProviderDefinition(BaseModel):
    """Jarvis-controlled identity record for an AI provider (contract §9).
    Registration in a `ProviderRegistry` is identity/discovery only — it
    grants zero execution authority (contract §5, §20). Never carries a
    secret: no field here may hold an API key or other credential (contract
    §38) — the one live-provider seam that currently resolves credentials
    (`app/agents/providers.py::get_default_provider`, via
    `app.config.settings`) is untouched by and independent of this
    abstraction."""

    model_config = _FROZEN

    provider_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    provider_type: str = Field(min_length=1)
    enabled: bool = True
    capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
    privacy_classification: str = "INTERNAL"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("provider_id", "provider_type")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("display_name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_display_name(value)

    @field_validator("metadata", mode="after")
    @classmethod
    def _freeze_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return deep_freeze(value)


class ModelDefinition(BaseModel):
    """Jarvis-controlled identity record for a specific model behind a
    provider (contract §10). `capabilities` here is the precise, per-model
    set used for capability-mismatch checks (contract §33-§34); it need not
    equal `ProviderDefinition.capabilities`, which is the coarser set the
    provider can support across all of its models."""

    model_config = _FROZEN

    model_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
    context_window: int | None = Field(default=None, gt=0)
    supports_structured_output: bool = False
    supports_streaming: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model_id", "provider_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("display_name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_display_name(value)

    @field_validator("metadata", mode="after")
    @classmethod
    def _freeze_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return deep_freeze(value)


class UsageInfo(BaseModel):
    """Vendor-neutral usage/cost telemetry (contract §16). Provider-reported
    values are untrusted telemetry, kept separate from any future
    Jarvis-calculated figure; a `None` cost means "unknown", never "zero"
    — mirrors the existing v0.1.3 convention of never guessing a price (see
    `app/config/pricing.py`, `Settings.model_pricing_json`). Full AI budget
    accounting (reservation, ceilings) is v0.2.7, not implemented here."""

    model_config = _FROZEN

    provider_reported_input_tokens: int | None = Field(default=None, ge=0)
    provider_reported_output_tokens: int | None = Field(default=None, ge=0)
    provider_reported_total_tokens: int | None = Field(default=None, ge=0)
    provider_reported_cost: float | None = Field(default=None, ge=0)
    jarvis_calculated_cost: float | None = Field(default=None, ge=0)


class ProviderRequest(BaseModel):
    """A vendor-neutral inference request — it asks a model to compute, and
    represents nothing else (contract §12). It MUST NOT and structurally
    CANNOT (via `extra="forbid"`) carry a Jarvis approval object, a
    ToolAdapter, a raw credential, a DB session, or any other
    authority-granting structure. `required_capabilities` lets a caller
    declare what the request needs so `FakeProvider`/future real providers
    can fail deterministically on a mismatch (contract §33) rather than
    silently proceeding. `structured_output_schema_name` is a NAME, not a
    live Python type/class — keeping the request a plain, hashable,
    JSON-serializable value object (contract §13) that does not import-
    couple this package to arbitrary Pydantic schema classes."""

    model_config = _FROZEN

    request_id: str = Field(default_factory=_new_id)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    system_instructions: str | None = None
    task_class: str = "general"
    required_capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
    structured_output_schema_name: str | None = None
    generation_parameters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)

    @field_validator("provider_id", "model_id", "request_id", "task_class")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("structured_output_schema_name")
    @classmethod
    def _validate_optional_id(cls, value: str | None) -> str | None:
        return validate_identifier(value) if value is not None else None

    @field_validator("generation_parameters", "metadata", mode="after")
    @classmethod
    def _freeze_dict_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        return deep_freeze(value)


class ProviderResponse(BaseModel):
    """A vendor-neutral inference response — DATA, never authority (contract
    §14). `trusted` is not a constructor field: it is a fixed, computed
    property that always reads `False`, so no caller (and no malicious
    provider payload smuggled through `metadata`) can ever construct a
    `ProviderResponse` that claims to be trusted. `structured_output` is
    intentionally untyped (`Any`) at this layer — schema validation against
    a real Pydantic schema is a later-layer responsibility (contract §15),
    not implemented in v0.2.1, so this layer must not pretend a shape it
    hasn't checked. `provider_metadata` is opaque, untrusted, and never
    inspected for keys like `approved`/`authority`/`permission` (contract
    §36) — see `tests/test_provider_security.py`."""

    model_config = _FROZEN

    request_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    content: str | None = None
    structured_output: Any | None = None
    usage: UsageInfo | None = None
    finish_reason: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)

    @field_validator("request_id", "provider_id", "model_id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("structured_output", "provider_metadata", mode="after")
    @classmethod
    def _freeze_dict_fields(cls, value: Any) -> Any:
        return deep_freeze(value)

    @property
    def trusted(self) -> bool:
        """Always False. See class docstring — this is deliberately a
        read-only property, not a field, so it can never be set to True by
        any caller or any provider-supplied content."""
        return False


class CompatibleModel(BaseModel):
    """A single descriptive catalogue-query result (v0.2.2 — Provider
    Registry + Capability Metadata). A candidate description ONLY:
    `frozen=True, extra="forbid"` means there is no way to attach
    `selected`/`recommended`/`preferred`/`routing_score`/`rank`/`priority`/
    `fallback_order` to this type without an explicit field addition to
    this class — a future v0.2.3 router cannot smuggle a selection signal
    through this type by construction. `effective_capabilities` is the
    already-computed `provider ∩ model` intersection (never a union) —
    see `app.providers.catalog.effective_capabilities`."""

    model_config = _FROZEN

    provider_id: str
    model_id: str
    effective_capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
