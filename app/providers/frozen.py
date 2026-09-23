"""Deep-immutability utility (hostile-review remediation, contract §4/§37).

`ConfigDict(frozen=True)` only blocks *reassigning* a Pydantic field; it
does nothing to a mutable object already sitting in that field. A hostile
review of v0.2.1 confirmed this was exploitable: `ProviderRequest.
generation_parameters` and `ProviderResponse.structured_output` are both
part of the canonical hash (`request_hash.py`), so mutating them in place
after construction silently changes what a "validated" request/response
hashes to — exactly the "validated object -> H1 -> nested mutation -> same
object now hashes H2" attack the review asked for.

`deep_freeze()` recursively converts a `dict`/`list`/`tuple`/`set` (and
anything nested inside them) into an immutable equivalent that still
satisfies `isinstance(x, dict)` / `isinstance(x, list)`, so it round-trips
through Pydantic validation, `model_dump()`, and plain `json.dumps()`
exactly like the mutable value it replaces — the only difference is that
mutating it raises `TypeError`."""
from __future__ import annotations

from typing import Any


class FrozenDict(dict):
    """A `dict` whose mutating methods raise. Still a real `dict` for
    `isinstance`, iteration, and (de)serialization purposes. `__ior__`
    (`|=`) is blocked explicitly: dict's in-place union does not route
    through the blocked `update` (hostile review B-11). Explicit base-class
    calls such as `dict.__setitem__(frozen, ...)` are not prevented --
    same-process Python is not a security boundary."""

    def _blocked(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("this mapping is frozen and cannot be mutated after construction")

    __setitem__ = __delitem__ = __ior__ = update = setdefault = pop = popitem = clear = _blocked  # type: ignore[assignment]


class FrozenList(list):
    """A `list` whose mutating methods raise. Still a real `list` for
    `isinstance`, iteration, and (de)serialization purposes. `__imul__`
    (`*=`) is blocked explicitly, like `__iadd__` (hostile review B-11)."""

    def _blocked(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("this sequence is frozen and cannot be mutated after construction")

    __setitem__ = __delitem__ = __iadd__ = __imul__ = append = extend = insert = remove = pop = popitem = clear = sort = reverse = _blocked  # type: ignore[assignment]


def deep_freeze(value: Any) -> Any:
    """Recursively freezes `dict`/`list`/`tuple`/`set` structures. Scalars
    (`str`, `int`, `float`, `bool`, `None`, enum members) and any other
    object type pass through unchanged — this is deliberately narrow: it
    freezes the JSON-shaped containers these contracts actually carry, not
    arbitrary Python objects."""
    if isinstance(value, dict):
        return FrozenDict({key: deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return FrozenList(deep_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(deep_freeze(item) for item in value)
    return value
