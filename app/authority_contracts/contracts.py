"""v0.2.5.1 pure authority contracts (approved design:
`docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md` sections 3.2-3.7,
4 and 5; this phase: `docs/V0_2_5_1_AUTHORITY_CONTRACTS_AND_ALGEBRA.md`).

REPRESENTATION IS NOT POSSESSION. An `AuthorityScope` is an upper-bound
*description*. It is not an approval, a PermissionDecision, a capability
token, a bearer credential, a tool grant or an execution grant, and holding
one proves nothing about what any principal may do. Likewise a
`PrincipalRef` *names* a principal; it does not authenticate one. Trusted
principal establishment (the owner channel, AgentRegistry resolution) is a
future integration dependency, not part of v0.2.5.1.

Hardening (B-11 / v0.2.4 lessons):
  - `frozen=True, extra="forbid", strict=True, hide_input_in_errors=True`;
  - every field value is an immutable, hashable object (enum, int,
    frozenset, datetime, frozen model), so there is no nested container to
    mutate and no caller alias to keep: mutable inputs are rejected, not
    copied;
  - exact types only: `str`/`frozenset`/`datetime`/model subclasses (which
    could override `__eq__`, `__contains__` or `__le__`) are rejected;
  - subclassing, `model_construct()` and `model_copy()` raise `TypeError`,
    so no unvalidated instance can be produced through the model API;
  - assigning or deleting ANY attribute (including pydantic internals such
    as `__pydantic_extra__` or `__dict__` itself) raises `TypeError`.
Explicit base-class calls (`object.__setattr__`, writing into `__dict__`) are out
of contract: same-process Python code is not sandboxed. The algebra
therefore revalidates every scope before it can contribute authority.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, field_serializer, field_validator

from app.agent_identity.contracts import _AGENT_ID_PATTERN, _has_unsafe_chars
from app.providers.contracts import validate_identifier

AUTHORITY_SCOPE_SCHEMA_VERSION = 1
ACTION_VOCABULARY_VERSION = 1

_MAX_VERSION = 2**63 - 1

# revalidate_instances="always" (second hostile review F-01): without it,
# `AuthorityScope.model_validate(instance)` and nesting an ObjectiveRef
# instance return the instance untouched, so a tampered record would pass a
# "revalidation" still claiming P5.
_STRICT_FROZEN = ConfigDict(
    frozen=True, extra="forbid", strict=True, validate_default=True, hide_input_in_errors=True,
    revalidate_instances="always",
)


class PrincipalKind(enum.Enum):
    """Design section 4: exactly two principal namespaces. SYSTEM_POLICY is
    not a principal. A plain `Enum` (not `str, Enum`) so a kind never
    compares equal to a bare string."""

    HUMAN_OWNER = "HUMAN_OWNER"
    AGENT = "AGENT"


class PTier(enum.Enum):
    """Constitutional tier names (v0.2.0 `permission_compatibility.tiers`,
    design section 3.7), not a second taxonomy and not `PermissionLevel`.
    P5 exists as a name so later stages can express a *required* tier; it is
    never a valid `AuthorityScope.permission_ceiling` (DA-03). No ordering
    operators are defined: comparison goes only through `_TIER_RANK`."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"


_TIER_RANK: MappingProxyType[PTier, int] = MappingProxyType({tier: i for i, tier in enumerate(PTier)})

# Design section 3.2 permission_ceiling domain: P5 is not issuable (DA-03).
_ISSUABLE_CEILINGS = frozenset({PTier.P0, PTier.P1, PTier.P2, PTier.P3, PTier.P4})

# Pinned action-type vocabulary v1 with the design section 3.7 T_floor.
# Mirrors the Permission Engine's current vocabulary (`_ACTION_TYPE_FLOOR`
# plus `_NO_TOOL_ACTION_TYPES`) without importing or changing it; a test
# guards the drift. Publishing a versioned vocabulary from the Permission
# Engine is CR-02 (not authorized).
_ACTION_TYPE_FLOOR_V1: MappingProxyType[str, PTier] = MappingProxyType({
    "internal": PTier.P0, "no_op": PTier.P0, "manual": PTier.P0, "decision_only": PTier.P0,
    "read": PTier.P1,
    "internal_create": PTier.P2, "sandbox_create": PTier.P2,
    "external_modify": PTier.P3,
    "send": PTier.P4, "publish": PTier.P4, "delete": PTier.P4,
    "financial": PTier.P5, "install": PTier.P5, "privileged": PTier.P5,
})
ACTION_TYPE_VOCABULARY: frozenset[str] = frozenset(_ACTION_TYPE_FLOOR_V1)


def _tier_leq(a: PTier, b: PTier) -> bool:
    return _TIER_RANK[a] <= _TIER_RANK[b]


def _require_exact(value: Any, expected: type, what: str) -> None:
    if type(value) is not expected:
        raise ValueError(f"{what} must be exactly {expected.__name__}")


def _validate_id(value: Any, what: str) -> str:
    """v0.2.4 agent_id rules (shared identifier policy plus the conservative
    ASCII charset): no blank, whitespace, control/line-separator characters,
    homoglyphs or over-long values. Messages never echo the input."""
    _require_exact(value, str, what)
    try:
        validate_identifier(value)
    except ValueError:
        raise ValueError(f"{what} is blank, too long, padded or contains control characters") from None
    if _has_unsafe_chars(value) or not _AGENT_ID_PATTERN.fullmatch(value):
        raise ValueError(
            f"{what} must be ASCII letters/digits separated by '.', '_', ':' or '-', "
            f"starting and ending with a letter or digit"
        )
    return value


def _validate_version(value: Any, what: str) -> int:
    _require_exact(value, int, what)
    if not 1 <= value <= _MAX_VERSION:
        raise ValueError(f"{what} must be a positive integer")
    return value


class _SealedModel(BaseModel):
    """No subclass, no `model_construct`, no `model_copy`: every instance of a
    sealed contract went through full validation."""

    model_config = _STRICT_FROZEN
    _sealed: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        if any(getattr(base, "_sealed", False) for base in cls.__mro__[1:]):
            raise TypeError("authority contracts cannot be subclassed")
        super().__init_subclass__(**kwargs)

    @classmethod
    def model_construct(cls, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("model_construct() bypasses validation and is not supported for authority contracts")

    def model_copy(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("model_copy() bypasses validation and is not supported for authority contracts")

    # Final hostile review F-05: pydantic's `frozen` guards declared fields
    # only, so plain assignment of `__pydantic_extra__`,
    # `__pydantic_fields_set__`, `__pydantic_private__` or `__dict__` used to
    # succeed (e.g. `scope.__pydantic_extra__ = {"approved": True}` made
    # `scope.approved` true). No attribute of a sealed contract is assignable
    # or deletable. Pydantic's own init/copy/pickle paths bypass these hooks.
    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("authority contracts are immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("authority contracts are immutable")


class PrincipalRef(_SealedModel):
    """A principal name `(kind, id)` (design section 4, HR-17). Identity,
    equality and hashing always include `kind`: `AGENT:"owner"` is never
    `HUMAN_OWNER:"owner"`. Represents; does NOT authenticate."""

    _sealed: ClassVar[bool] = True

    kind: PrincipalKind
    id: str

    @field_validator("id", mode="before")
    @classmethod
    def _check_id(cls, value: Any) -> str:
        return _validate_id(value, "principal id")


class ObjectiveRef(_SealedModel):
    """Durable, versioned objective identity (design HR-10). Never free
    text; changing an objective means a new version. The objective store is
    not part of v0.2.5.1."""

    _sealed: ClassVar[bool] = True

    objective_id: str
    objective_version: int

    @field_validator("objective_id", mode="before")
    @classmethod
    def _check_objective_id(cls, value: Any) -> str:
        return _validate_id(value, "objective_id")

    @field_validator("objective_version", mode="before")
    @classmethod
    def _check_objective_version(cls, value: Any) -> int:
        return _validate_version(value, "objective_version")


class AuthorityScope(_SealedModel):
    """The six v0.2.5 dimensions (design section 3.2), all required, none
    defaulted. An upper-bound description only (see module docstring).

    Invariants checked at construction:
      - `schema_version` / `vocabulary_version` are exactly the supported
        versions (no upgrade, downgrade or best-effort compatibility);
      - `permission_ceiling` is P0..P4 (P5 is not issuable, DA-03);
      - `action_types` is a non-empty frozenset over vocabulary v1, with no
        wildcard, and every type's T_floor is at or below the ceiling
        (tier-consistent; so P5-floor types are unrepresentable);
      - `expires_at` is an exact `datetime` whose tzinfo is UTC (naive and
        non-UTC offsets rejected; nothing is converted).
    Expiry is a stored bound only. Whether a scope is *currently* expired is
    effectiveness at a trusted time -- a later evaluator, not this type."""

    _sealed: ClassVar[bool] = True

    schema_version: int
    vocabulary_version: int
    permission_ceiling: PTier
    action_types: frozenset[str]
    objective_ref: ObjectiveRef
    expires_at: datetime

    @field_validator("schema_version", mode="before")
    @classmethod
    def _check_schema_version(cls, value: Any) -> int:
        _require_exact(value, int, "schema_version")
        if value != AUTHORITY_SCOPE_SCHEMA_VERSION:
            raise ValueError("unsupported schema_version")
        return value

    @field_validator("vocabulary_version", mode="before")
    @classmethod
    def _check_vocabulary_version(cls, value: Any) -> int:
        _require_exact(value, int, "vocabulary_version")
        if value != ACTION_VOCABULARY_VERSION:
            raise ValueError("unsupported vocabulary_version")
        return value

    @field_validator("permission_ceiling", mode="before")
    @classmethod
    def _check_ceiling(cls, value: Any) -> PTier:
        _require_exact(value, PTier, "permission_ceiling")
        if value not in _ISSUABLE_CEILINGS:
            raise ValueError("P5 is not issuable as an AuthorityScope ceiling in v0.2.5 (DA-03)")
        return value

    @field_validator("action_types", mode="before")
    @classmethod
    def _check_action_types(cls, value: Any) -> frozenset[str]:
        _require_exact(value, frozenset, "action_types")
        if not value:
            raise ValueError("action_types must not be empty")
        for item in value:
            if type(item) is not str or item not in ACTION_TYPE_VOCABULARY:
                raise ValueError("action_types contains a value outside the pinned vocabulary")
        return value

    @field_validator("objective_ref", mode="before")
    @classmethod
    def _check_objective_ref(cls, value: Any) -> ObjectiveRef:
        _require_exact(value, ObjectiveRef, "objective_ref")
        return value

    @field_validator("expires_at", mode="before")
    @classmethod
    def _check_expires_at(cls, value: Any) -> datetime:
        _require_exact(value, datetime, "expires_at")
        if value.tzinfo is not timezone.utc:
            raise ValueError("expires_at must be timezone-aware UTC (datetime.timezone.utc)")
        return value

    @field_validator("action_types", mode="after")
    @classmethod
    def _check_tier_consistency(cls, value: frozenset[str], info: Any) -> frozenset[str]:
        ceiling = info.data.get("permission_ceiling")
        if ceiling is None:
            return value  # the ceiling already failed validation
        if any(not _tier_leq(_ACTION_TYPE_FLOOR_V1[t], ceiling) for t in value):
            raise ValueError("an action type requires a higher tier than permission_ceiling")
        return value

    @field_serializer("action_types", when_used="json")
    def _serialize_action_types(self, value: frozenset[str]) -> list[str]:
        return sorted(value)
