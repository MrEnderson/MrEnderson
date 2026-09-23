"""Agent identity contract (v0.2.4 — Agent Identity + Agent Registry;
`docs/V0_2_4_AGENT_IDENTITY_AND_REGISTRY_SECURITY_CONTRACT.md`).

`AgentDefinition` is a `frozen=True, extra="forbid", validate_default=True`
Pydantic object (the `_FROZEN` pattern `app.providers.contracts`/
`app.providers.failures`/`app.providers.routing_contracts` already
established), plus `hide_input_in_errors=True` so a rejected value (e.g. a
secret a trusted caller mistakenly put in metadata) is never echoed into a
`ValidationError` message/log line. An unexpected constructor field (e.g.
`permission="P5"`) raises `ValidationError` immediately.

`metadata` is stricter than v0.2.1-2.3's provider/router metadata (contract
doc, "Metadata policy"): JSON-shaped values only (no arbitrary/mutable/
callable objects), bounded in depth/size, reserved security-shaped and
canonical-field-shadowing keys rejected at any depth under a normalized
(case/separator/camelCase-insensitive) comparison, and frozen into the
shared `app.providers.frozen` containers (which block `|=`/`*=` since the
B-11 fix; B-03 originally worked around that gap locally)."""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.contracts import ProviderCapability, validate_display_name, validate_identifier
from app.providers.frozen import FrozenDict, FrozenList

_AGENT_CONFIG = ConfigDict(frozen=True, extra="forbid", validate_default=True, hide_input_in_errors=True)

# agent_id: validate_identifier (shared v0.2.1 policy) PLUS a conservative
# ASCII charset -- an agent_id is an audit identity, so homoglyphs
# ("jarvis.cеo" with Cyrillic е), zero-width and line-separator characters
# must not be able to impersonate another identity in a log (B-05).
_AGENT_ID_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:-]*[A-Za-z0-9])?")

_MAX_PREFERRED_PROVIDER_IDS = 256
_MAX_METADATA_DEPTH = 8
_MAX_METADATA_NODES = 1024
_MAX_METADATA_KEY_LENGTH = 256
_MAX_METADATA_STRING_LENGTH = 4096

# Security-shaped terms. A metadata key is rejected when its normalized
# token sequence CONTAINS any of these as a contiguous run, so `Permission`,
# `PERMISSIONS`, `apiKey`, `OPENAI_API_KEY`, `access_token`, `tool-access`
# are all caught (B-04). Deliberately fail-closed: a benign key such as
# `max_tokens` is also rejected -- an identity record has no need for it.
_RESERVED_METADATA_TERMS: frozenset[tuple[str, ...]] = frozenset(
    tuple(term.split("_")) for term in (
        "permission", "permissions", "approval", "approvals", "approve", "approved", "approver",
        "authority", "authorities", "authorize", "authorized", "authorization",
        "admin", "superuser", "execute", "executable",
        "can_spend", "business_spend", "tool_access", "delegation", "delegate",
        "credential", "credentials", "secret", "secrets", "token", "tokens",
        "api_key", "apikey", "access_key", "private_key", "password", "passwords", "passwd", "bearer",
    )
)

# Keys that would shadow a canonical AgentDefinition field (§76/§77): rejected
# on exact normalized match so no consumer can ever read `metadata["enabled"]`
# or `metadata["role"]` in place of the canonical value.
_CANONICAL_FIELD_SHADOWS: frozenset[tuple[str, ...]] = frozenset(
    tuple(name.split("_")) for name in (
        "agent_id", "display_name", "role", "description", "enabled", "active", "disabled",
        "preferred_provider_ids", "required_capabilities", "metadata", "created_at",
    )
)

_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key_tokens(key: str) -> tuple[str, ...]:
    return tuple(t for t in _NON_ALNUM.split(_CAMEL_BOUNDARY.sub(r"\1_\2", key).lower()) if t)


def _contains_run(tokens: tuple[str, ...], term: tuple[str, ...]) -> bool:
    width = len(term)
    return any(tokens[i:i + width] == term for i in range(len(tokens) - width + 1))


def _has_unsafe_chars(value: str, allowed: str = "") -> bool:
    """Control characters (Cc) and Unicode line/paragraph separators --
    anything that can forge a new line in an audit log (B-06)."""
    return any(ch not in allowed and unicodedata.category(ch) in ("Cc", "Zl", "Zp") for ch in value)


def _check_metadata_key(key: Any) -> None:
    if not isinstance(key, str):
        raise ValueError("metadata keys must be strings")
    if not key.strip() or len(key) > _MAX_METADATA_KEY_LENGTH or _has_unsafe_chars(key):
        raise ValueError("metadata keys must be non-blank, bounded, and free of control characters")
    tokens = _key_tokens(key)
    if tokens in _CANONICAL_FIELD_SHADOWS:
        raise ValueError(
            f"metadata key {key!r} shadows a canonical AgentDefinition field -- metadata can never "
            f"override role/enabled/identity"
        )
    if any(_contains_run(tokens, term) for term in _RESERVED_METADATA_TERMS):
        raise ValueError(
            f"metadata key {key!r} is security-shaped -- AgentDefinition metadata is opaque "
            f"descriptive data only and can never carry authority, approvals, tool access, or secrets"
        )


def _freeze_metadata_value(value: Any, depth: int, budget: list[int]) -> Any:
    """Validates AND freezes in one bounded walk. JSON-shaped values only:
    anything else (bytearray, arbitrary objects, callables, live
    ToolAdapters, sets) is rejected, because it could be mutable after
    construction (breaking A11) or executable (A16) (B-02)."""
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError(f"metadata must not exceed {_MAX_METADATA_NODES} total entries")
    if depth > _MAX_METADATA_DEPTH:
        raise ValueError(f"metadata must not nest deeper than {_MAX_METADATA_DEPTH} levels")
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata floats must be finite")
        return value
    if isinstance(value, str):
        if len(value) > _MAX_METADATA_STRING_LENGTH:
            raise ValueError(f"metadata strings must not exceed {_MAX_METADATA_STRING_LENGTH} characters")
        return value
    if isinstance(value, dict):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            _check_metadata_key(key)
            frozen[key] = _freeze_metadata_value(item, depth + 1, budget)
        return FrozenDict(frozen)
    if isinstance(value, (list, tuple)):
        return FrozenList(_freeze_metadata_value(item, depth + 1, budget) for item in value)
    raise ValueError(
        f"metadata values must be JSON-shaped (str/int/float/bool/None/dict/list) -- got {type(value).__name__}"
    )


class AgentDefinition(BaseModel):
    """Jarvis-controlled logical agent identity record. Registration in an
    `AgentRegistry` is identity/discovery only — it grants zero execution
    authority, zero permission, zero approval, and zero tool access
    (central invariant: "agent identity is not authority"). Never carries a
    secret: no field here may hold an API key or other credential.

    `display_name`/`role` are plain, validated strings with ZERO authority
    semantics — no enum, no mapping to a permission tier, and no code
    anywhere that branches on their value. `role="CEO"` and `role="Intern"`
    are equally inert strings.

    `enabled` is strict (`True`/`False` only, no `"yes"`/`1` coercion) and
    means "eligible for future active orchestration" — never a permission."""

    model_config = _AGENT_CONFIG

    agent_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    description: str | None = None
    enabled: bool = Field(default=True, strict=True)
    preferred_provider_ids: frozenset[str] = Field(default_factory=frozenset)
    required_capabilities: frozenset[ProviderCapability] = Field(default_factory=frozenset)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)

    @field_validator("agent_id")
    @classmethod
    def _validate_agent_id(cls, value: str) -> str:
        validate_identifier(value)
        if not _AGENT_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "agent_id must be ASCII letters/digits separated by '.', '_', ':' or '-', "
                "starting and ending with a letter or digit"
            )
        return value

    @field_validator("display_name", "role")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        validate_display_name(value)
        if _has_unsafe_chars(value):
            raise ValueError("must not contain control or line-separator characters")
        return value

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        validate_display_name(value)
        if _has_unsafe_chars(value, allowed="\n\t"):
            raise ValueError("must not contain control characters other than newline/tab")
        return value

    @field_validator("preferred_provider_ids")
    @classmethod
    def _validate_preferred_provider_ids(cls, value: frozenset[str]) -> frozenset[str]:
        if len(value) > _MAX_PREFERRED_PROVIDER_IDS:
            raise ValueError(f"must not exceed {_MAX_PREFERRED_PROVIDER_IDS} entries")
        return frozenset(validate_identifier(v) for v in value)

    @field_validator("metadata", mode="after")
    @classmethod
    def _freeze_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _freeze_metadata_value(value, 0, [_MAX_METADATA_NODES + 1])
