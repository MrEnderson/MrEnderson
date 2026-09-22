"""Normalized provider failure taxonomy (contract §17-§18, §51-§52).

`app/agents/providers.py` already has its own `ModelProviderError` hierarchy
(`ModelAuthenticationError`, `ModelRateLimitError`, ...) tightly coupled to
the OpenAI/Anthropic SDKs it wraps. This module defines the VENDOR-NEUTRAL
target those (and any future real provider) would eventually normalize
into — see contract §51's `Anthropic exception / OpenAI exception / Local
exception -> ProviderFailure` diagram. v0.2.1 does not implement that
mapping (no existing provider code is touched); it only defines the target
shape and exercises it via `FakeProvider`.

`ProviderFailure.retryable` is purely descriptive (contract §52): it means
"this failure category may be technically suitable for a retry," never
"retry now." It is derived deterministically from `category` (see
`ProviderFailure`), not caller-supplied, so it can never contradict its
own category. Nothing in this package retries automatically.
"""
from __future__ import annotations

import enum
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.contracts import validate_identifier
from app.providers.frozen import deep_freeze

_FROZEN = ConfigDict(frozen=True, extra="forbid", validate_default=True)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProviderFailureCategory(str, enum.Enum):
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    MALFORMED_STRUCTURED_OUTPUT = "MALFORMED_STRUCTURED_OUTPUT"
    CONTEXT_LIMIT_EXCEEDED = "CONTEXT_LIMIT_EXCEEDED"
    CONTENT_REJECTED = "CONTENT_REJECTED"
    SAFETY_REJECTED = "SAFETY_REJECTED"
    TRANSIENT_PROVIDER_ERROR = "TRANSIENT_PROVIDER_ERROR"
    PERMANENT_PROVIDER_ERROR = "PERMANENT_PROVIDER_ERROR"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


# Categories where a retry is at least technically plausible. Used only to
# fill ProviderFailure.retryable's default; never consulted by an automatic
# retry loop, because there isn't one in this package (contract §52).
RETRYABLE_CATEGORIES = frozenset(
    {
        ProviderFailureCategory.PROVIDER_UNAVAILABLE,
        ProviderFailureCategory.RATE_LIMITED,
        ProviderFailureCategory.TIMEOUT,
        ProviderFailureCategory.TRANSIENT_PROVIDER_ERROR,
    }
)

_MAX_MESSAGE_CHARS = 500

# Secret-shaped substrings a provider error/exception might echo back
# (contract §18: "provider error text is untrusted; secrets must be
# redacted"). Deliberately pattern-based, not a fixed marker list, so a
# real vendor key shape (e.g. `sk-ant-...`, `sk-...`) is caught the same
# way a `key=value`-style leak is.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{6,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"tvly-[A-Za-z0-9_-]{6,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE),
    re.compile(
        r"(api[_-]?key|password|passwd|secret|token)"
        r"[\"']?\s*[:=]\s*"
        r"[\"']?[^\s\"',}]{4,}",
        re.IGNORECASE,
    ),
)


def redact_secrets(text: str) -> str:
    """Best-effort, pattern-based redaction of secret-shaped substrings.
    Not a guarantee against every possible leak shape — a defense-in-depth
    layer, not the only one; callers must still avoid putting raw
    credentials into any string that reaches this function. See
    `tests/test_provider_security.py` for the fake-marker leak test this
    exists to satisfy (contract §29)."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _sanitize_message(text: str) -> str:
    redacted = redact_secrets(text)
    if len(redacted) > _MAX_MESSAGE_CHARS:
        return redacted[:_MAX_MESSAGE_CHARS] + "... [message truncated]"
    return redacted


class ProviderFailure(BaseModel):
    """A normalized, sanitized provider failure (contract §18). `message`
    is redacted and length-bounded on construction — there is no way to
    build a `ProviderFailure` whose `message` still contains a raw
    secret-shaped substring the redactor recognizes. Carries no authority:
    `retryable` never triggers a retry on its own (see module docstring).

    `retryable` is NOT a constructor field — a hostile review confirmed
    that accepting it as caller-supplied allowed a contradictory state
    (e.g. `category=PERMANENT_PROVIDER_ERROR` with `retryable=True`).
    Instead it is a read-only property derived deterministically from
    `category` via `RETRYABLE_CATEGORIES`, the same pattern
    `ProviderResponse.trusted` uses to make its invariant unconditional
    rather than merely validated."""

    model_config = _FROZEN

    category: ProviderFailureCategory
    message: str
    provider_id: str = Field(min_length=1)
    model_id: str | None = None
    request_id: str | None = None
    provider_code: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=_now)

    @field_validator("message", mode="before")
    @classmethod
    def _sanitize(cls, value: Any) -> str:
        return _sanitize_message(str(value))

    @field_validator("provider_id")
    @classmethod
    def _validate_provider_id(cls, value: str) -> str:
        return validate_identifier(value)

    @field_validator("model_id", "request_id")
    @classmethod
    def _validate_optional_id(cls, value: str | None) -> str | None:
        return validate_identifier(value) if value is not None else None

    @field_validator("details", mode="after")
    @classmethod
    def _freeze_details(cls, value: dict[str, Any]) -> dict[str, Any]:
        return deep_freeze(value)

    @property
    def retryable(self) -> bool:
        return self.category in RETRYABLE_CATEGORIES


class ProviderFailureError(Exception):
    """Raised by `AIProvider.generate()` on failure. Carries a structured,
    already-sanitized `ProviderFailure` — never a raw vendor exception or
    unsanitized text. Mirrors `app.agents.providers.ModelProviderError`'s
    role for the vendor-neutral abstraction."""

    def __init__(self, failure: ProviderFailure):
        super().__init__(failure.message)
        self.failure = failure
