"""v0.2.5.1 pure authority algebra (approved design section 3.3).

Carrier set: `Auth = AuthorityScope ∪ {NO_AUTHORITY}`. `(Auth, leq, meet)`
is a meet-semilattice with bottom. There is deliberately NO join / union
(DI-06), NO total order, and NO issuance helper: issuance is check-not-clip
and belongs to the v0.2.5.2 store, which must use `leq` to *reject* an
over-broad request -- never `meet` to silently narrow it.

`leq` and `meet` are pure and deterministic: no clock, no I/O, no state.
`expires_at` is compared as a stored value; "is this scope expired now?" is
effectiveness at a trusted time and is not answered here.

Fail-closed handling of values that did not come from the validated
constructor (e.g. a tampered record written through `object.__setattr__`):
  - anything that is not exactly `AuthorityScope` or `NO_AUTHORITY` raises
    `TypeError`;
  - a version mismatch yields "not leq" / `NO_AUTHORITY` (design 3.3) --
    this needs no trust in either operand, because it grants nothing;
  - before a scope can make `leq` true or contribute to a non-bottom meet,
    it is rebuilt through the validated constructor; an invalid scope raises
    `ValueError` and never contributes authority.
"""
from __future__ import annotations

from typing import Any, NoReturn, Union

from app.authority_contracts.contracts import AuthorityScope, ObjectiveRef, _tier_leq


class _NoAuthority:
    """The explicit bottom ⊥ (NO_AUTHORITY): zero authority. An algebra
    result only -- never an `AuthorityScope`, never issuable or storable,
    never "unrestricted", never `None`. It has no fields, cannot be
    subclassed, copies/pickles to itself, and refuses truthiness so that
    `if meet(a, b):` cannot silently mean either "yes" or "no"; callers must
    test `result is NO_AUTHORITY`."""

    __slots__ = ()
    _instance: "_NoAuthority | None" = None

    def __new__(cls) -> "_NoAuthority":
        if _NoAuthority._instance is None:
            _NoAuthority._instance = object.__new__(cls)
        return _NoAuthority._instance

    def __init_subclass__(cls, **kwargs: Any) -> NoReturn:
        raise TypeError("NO_AUTHORITY cannot be subclassed")

    def __bool__(self) -> NoReturn:
        raise TypeError("NO_AUTHORITY has no truth value; test `is NO_AUTHORITY` explicitly")

    def __repr__(self) -> str:
        return "NO_AUTHORITY"

    def __reduce__(self) -> str:
        return "NO_AUTHORITY"

    def __copy__(self) -> "_NoAuthority":
        return self

    def __deepcopy__(self, memo: dict) -> "_NoAuthority":
        return self


NO_AUTHORITY = _NoAuthority()

Authority = Union[AuthorityScope, _NoAuthority]


def _carrier(value: Any) -> Authority:
    if value is NO_AUTHORITY or type(value) is AuthorityScope:
        return value
    raise TypeError("authority algebra operands must be exactly AuthorityScope or NO_AUTHORITY")


def _revalidated(scope: AuthorityScope) -> AuthorityScope:
    """Rebuild through the validated constructor, including the nested
    ObjectiveRef, so an out-of-contract instance cannot carry authority."""
    objective = scope.objective_ref
    if type(objective) is not ObjectiveRef:
        raise ValueError("objective_ref must be exactly ObjectiveRef")
    return AuthorityScope(
        schema_version=scope.schema_version,
        vocabulary_version=scope.vocabulary_version,
        permission_ceiling=scope.permission_ceiling,
        action_types=scope.action_types,
        objective_ref=ObjectiveRef(
            objective_id=objective.objective_id,
            objective_version=objective.objective_version,
        ),
        expires_at=scope.expires_at,
    )


def _versions_match(a: AuthorityScope, b: AuthorityScope) -> bool:
    return (
        type(a.schema_version) is int and type(b.schema_version) is int
        and a.schema_version == b.schema_version
        and type(a.vocabulary_version) is int and type(b.vocabulary_version) is int
        and a.vocabulary_version == b.vocabulary_version
    )


def leq(a: Authority, b: Authority, /) -> bool:
    """True iff `a` grants no more than `b` (design 3.3). `NO_AUTHORITY` is
    below everything; nothing but `NO_AUTHORITY` is below it. For scopes:
    same versions, same objective_ref, ceiling(a) <= ceiling(b),
    action_types(a) ⊆ action_types(b), expires_at(a) <= expires_at(b).
    Incomparable scopes return False both ways."""
    a, b = _carrier(a), _carrier(b)
    if a is NO_AUTHORITY:
        return True
    if b is NO_AUTHORITY:
        return False
    if not _versions_match(a, b):
        return False
    a, b = _revalidated(a), _revalidated(b)
    return (
        a.objective_ref == b.objective_ref
        and _tier_leq(a.permission_ceiling, b.permission_ceiling)
        and a.action_types <= b.action_types
        and a.expires_at <= b.expires_at
    )


def meet(a: Authority, b: Authority, /) -> Authority:
    """Greatest lower bound (design 3.3); total on the carrier set.
    NO_AUTHORITY if either side is NO_AUTHORITY, versions differ,
    objective_refs differ, or the action types are disjoint. Otherwise
    (min ceiling, intersection of action types, same objective_ref, earlier
    expires_at, same versions) -- again a valid AuthorityScope."""
    a, b = _carrier(a), _carrier(b)
    if a is NO_AUTHORITY or b is NO_AUTHORITY:
        return NO_AUTHORITY
    if not _versions_match(a, b):
        return NO_AUTHORITY
    a, b = _revalidated(a), _revalidated(b)
    if a.objective_ref != b.objective_ref:
        return NO_AUTHORITY
    action_types = a.action_types & b.action_types
    if not action_types:
        return NO_AUTHORITY
    return AuthorityScope(
        schema_version=a.schema_version,
        vocabulary_version=a.vocabulary_version,
        permission_ceiling=a.permission_ceiling if _tier_leq(a.permission_ceiling, b.permission_ceiling)
        else b.permission_ceiling,
        action_types=action_types,
        objective_ref=a.objective_ref,
        expires_at=min(a.expires_at, b.expires_at),
    )
