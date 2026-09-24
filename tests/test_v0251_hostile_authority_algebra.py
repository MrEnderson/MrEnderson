"""HOSTILE TESTS -- v0.2.5.1 pure authority contracts + algebra.

Written BEFORE `app/authority_contracts` existed (tests-first). They exercise
only the pure, offline contract/algebra layer of the approved v0.2.5 design
(docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md sections 3.2-3.7, 4,
5). They say nothing about delegation issuance, stores, evaluation,
effectiveness at a trusted time, or pipeline integration -- none of which
exists in v0.2.5.1.

Attack IDs A-01..A-54 follow the v0.2.5.1 hostile matrix; X-* are additional
attacks found while writing the contract.
"""
from __future__ import annotations

import ast
import copy
import importlib
import inspect
import itertools
import pickle
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PACKAGE_DIR = _REPO_ROOT / "app" / "authority_contracts"

UTC = timezone.utc
T_EARLY = datetime(2030, 1, 1, tzinfo=UTC)
T_MID = datetime(2030, 6, 1, tzinfo=UTC)
T_LATE = datetime(2031, 1, 1, tzinfo=UTC)

REJECT = (ValueError, TypeError)  # pydantic ValidationError is a ValueError
MUTATE_REJECT = (ValueError, TypeError, AttributeError)

# Design section 3.2 / 3.7 pinned vocabulary v1 and its T_floor.
DESIGN_T_FLOOR = {
    "internal": "P0", "no_op": "P0", "manual": "P0", "decision_only": "P0",
    "read": "P1",
    "internal_create": "P2", "sandbox_create": "P2",
    "external_modify": "P3",
    "send": "P4", "publish": "P4", "delete": "P4",
    "financial": "P5", "install": "P5", "privileged": "P5",
}
EXPECTED_PUBLIC_API = {
    "PrincipalKind", "PrincipalRef", "ObjectiveRef", "PTier", "AuthorityScope",
    "NO_AUTHORITY", "AUTHORITY_SCOPE_SCHEMA_VERSION", "ACTION_VOCABULARY_VERSION",
    "ACTION_TYPE_VOCABULARY", "leq", "meet",
}
SCOPE_FIELDS = {
    "schema_version", "vocabulary_version", "permission_ceiling",
    "action_types", "objective_ref", "expires_at",
}


@pytest.fixture(scope="module")
def ac():
    return importlib.import_module("app.authority_contracts")


def _obj(ac, oid="objective.alpha", version=1):
    return ac.ObjectiveRef(objective_id=oid, objective_version=version)


def _scope(ac, tier="P4", types=("read", "internal_create"), oid="objective.alpha", ov=1, exp=T_MID, **extra):
    return ac.AuthorityScope(
        schema_version=1,
        vocabulary_version=1,
        permission_ceiling=ac.PTier[tier],
        action_types=frozenset(types),
        objective_ref=_obj(ac, oid, ov),
        expires_at=exp,
        **extra,
    )


def _scope_kwargs(ac, **override):
    kwargs = dict(
        schema_version=1, vocabulary_version=1, permission_ceiling=ac.PTier.P4,
        action_types=frozenset({"read"}), objective_ref=_obj(ac), expires_at=T_MID,
    )
    kwargs.update(override)
    return kwargs


def _tampered(ac, field, value, base=None):
    """Simulates an out-of-contract record (e.g. bytes from a tampered store):
    a valid scope whose field is overwritten behind the frozen guard."""
    s = base if base is not None else _scope(ac)
    s = copy.deepcopy(s)
    object.__setattr__(s, field, value)
    return s


def _package_sources():
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(_PACKAGE_DIR.glob("*.py"))}


class _EvilStr(str):
    def __eq__(self, other):  # claims equality with everything
        return True

    def __hash__(self):
        return hash("read")


# --------------------------------------------------------------------------
# Identity attacks A-01..A-06
# --------------------------------------------------------------------------

def test_a01_owner_agent_namespace_collision(ac):
    agent = ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="owner")
    owner = ac.PrincipalRef(kind=ac.PrincipalKind.HUMAN_OWNER, id="owner")
    assert agent != owner
    assert len({agent, owner}) == 2
    assert agent == ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="owner")


def test_a01_principal_kinds_are_exactly_the_design_kinds(ac):
    assert {k.name for k in ac.PrincipalKind} == {"HUMAN_OWNER", "AGENT"}


@pytest.mark.parametrize("kind", ["HUMAN_OWNER", "AGENT", "SYSTEM_POLICY", "ROOT", 0, None])
def test_a02_bare_string_kind_is_not_a_trusted_kind(ac, kind):
    with pytest.raises(REJECT):
        ac.PrincipalRef(kind=kind, id="owner")


def test_a02_bare_string_never_equals_a_principal(ac):
    owner = ac.PrincipalRef(kind=ac.PrincipalKind.HUMAN_OWNER, id="owner")
    for bare in ("owner", "HUMAN_OWNER:owner", ("HUMAN_OWNER", "owner")):
        assert owner != bare
    assert ac.PrincipalKind.HUMAN_OWNER != "HUMAN_OWNER"
    with pytest.raises(REJECT):
        ac.PrincipalRef("owner")


@pytest.mark.parametrize("bad", ["", " ", "\t", "   "])
def test_a03_empty_principal_id_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id=bad)


@pytest.mark.parametrize("bad", [
    "agent\nforged", "agent\r\nINFO granted", "agent\x00", "agent x", "agent x",
    "agent\x1b[31m", " agent", "agent ", "age nt", "jarvis.cеo", "agent​", "-agent", "agent.",
])
def test_a04_log_forging_and_malformed_principal_ids_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id=bad)


def test_a05_overlong_principal_id_rejected(ac):
    ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="a" * 256)
    with pytest.raises(REJECT):
        ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="a" * 257)


@pytest.mark.parametrize("extra", [
    {"authority": "P5"}, {"role": "CEO"}, {"trusted": True}, {"authenticated": True},
    {"permission_ceiling": "P4"}, {"metadata": {}},
])
def test_a06_extra_authority_looking_principal_field_rejected(ac, extra):
    with pytest.raises(REJECT):
        ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="agent.one", **extra)


@pytest.mark.parametrize("bad", [123, b"agent", None, _EvilStr("agent.one")])
def test_a06_principal_id_type_coercion_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id=bad)


# --------------------------------------------------------------------------
# Objective attacks A-07..A-10, A-22, A-23
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["Grow revenue by 10%", "objective.alpha", {"objective_id": "objective.alpha", "objective_version": 1}])
def test_a07_free_text_or_untyped_objective_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, objective_ref=bad))


def test_a07_objective_ref_has_no_free_text_field(ac):
    assert set(ac.ObjectiveRef.model_fields) == {"objective_id", "objective_version"}
    with pytest.raises(REJECT):
        ac.ObjectiveRef(objective_id="Grow revenue by 10%", objective_version=1)
    with pytest.raises(REJECT):
        ac.ObjectiveRef(objective_id="objective.alpha", objective_version=1, text="grow revenue")


def test_a08_objective_version_required(ac):
    with pytest.raises(REJECT):
        ac.ObjectiveRef(objective_id="objective.alpha")


@pytest.mark.parametrize("bad", ["1", 1.0, True, False, 0, -1, None, 2**63])
def test_a09_objective_version_coercion_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.ObjectiveRef(objective_id="objective.alpha", objective_version=bad)


def test_a10_same_objective_id_different_version_is_incomparable(ac):
    v1, v2 = _scope(ac, ov=1), _scope(ac, ov=2)
    assert _obj(ac, version=1) != _obj(ac, version=2)
    assert not ac.leq(v1, v2) and not ac.leq(v2, v1)
    assert ac.meet(v1, v2) is ac.NO_AUTHORITY


def test_a22_different_objectives_meet_is_bottom(ac):
    assert ac.meet(_scope(ac, oid="objective.alpha"), _scope(ac, oid="objective.beta")) is ac.NO_AUTHORITY


def test_a23_objective_ids_are_not_normalized(ac):
    a, b = _scope(ac, oid="objective.alpha"), _scope(ac, oid="Objective.Alpha")
    assert not ac.leq(a, b) and not ac.leq(b, a)
    assert ac.meet(a, b) is ac.NO_AUTHORITY


# --------------------------------------------------------------------------
# P-tier attacks A-11..A-14
# --------------------------------------------------------------------------

def test_a11_p5_not_representable_in_authority_scope(ac):
    with pytest.raises(REJECT):
        _scope(ac, tier="P5", types=("read",))


@pytest.mark.parametrize("p5_type", ["financial", "install", "privileged"])
def test_a11_p5_floor_action_types_not_representable(ac, p5_type):
    with pytest.raises(REJECT):
        _scope(ac, tier="P4", types=(p5_type,))


def test_a12_ptier_values_are_exactly_constitutional_names(ac):
    assert [t.name for t in ac.PTier] == ["P0", "P1", "P2", "P3", "P4", "P5"]
    for bad in ("P6", "P-1", "PX"):
        with pytest.raises(KeyError):
            ac.PTier[bad]


@pytest.mark.parametrize("bad", ["P4", "p4", 4, 4.0, True, None, "P6"])
def test_a13_tier_coercion_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, permission_ceiling=bad))


def test_a13_lookalike_enum_rejected(ac):
    import enum

    class FakeTier(enum.Enum):
        P4 = "P4"

    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, permission_ceiling=FakeTier.P4))


def test_a14_tier_order_is_attenuating(ac):
    p2, p4 = _scope(ac, tier="P2"), _scope(ac, tier="P4")
    assert ac.leq(p2, p4)
    assert not ac.leq(p4, p2)
    assert ac.meet(p2, p4).permission_ceiling is ac.PTier.P2


def test_x11_ptier_has_no_ordering_operators(ac):
    with pytest.raises(TypeError):
        ac.PTier.P1 < ac.PTier.P2
    assert ac.PTier.P4 != "P4"


# --------------------------------------------------------------------------
# Action-type attacks A-15..A-18, X-02, X-03
# --------------------------------------------------------------------------

@pytest.mark.parametrize("wild", ["*", "ALL", "ANY", "UNLIMITED", "all", "any", "", " read", "READ", "tool.shell"])
def test_a15_wildcard_or_unknown_action_type_rejected(ac, wild):
    with pytest.raises(REJECT):
        _scope(ac, types=("read", wild))


def test_a16_empty_action_set_rejected(ac):
    with pytest.raises(REJECT):
        _scope(ac, types=())


def test_a17_child_actions_not_subset_is_not_leq(ac):
    parent = _scope(ac, types=("read",))
    child = _scope(ac, types=("read", "internal_create"))
    assert not ac.leq(child, parent)


@pytest.mark.parametrize("container", [set, list, tuple])
def test_a18_mutable_or_non_frozenset_action_container_rejected(ac, container):
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, action_types=container(["read"])))


def test_a18_frozenset_subclass_and_str_subclass_rejected(ac):
    class SneakySet(frozenset):
        def __contains__(self, item):
            return True

    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, action_types=SneakySet({"read"})))
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, action_types=frozenset({_EvilStr("read")})))


def test_x02_action_types_must_be_tier_consistent(ac):
    with pytest.raises(REJECT):
        _scope(ac, tier="P3", types=("publish",))
    with pytest.raises(REJECT):
        _scope(ac, tier="P2", types=("external_modify",))
    with pytest.raises(REJECT):
        _scope(ac, tier="P0", types=("read",))


@pytest.mark.parametrize("action_type,floor", sorted(DESIGN_T_FLOOR.items()))
def test_x03_minimum_ceiling_per_action_type_matches_design_floor(ac, action_type, floor):
    tiers = ["P0", "P1", "P2", "P3", "P4"]
    accepted = []
    for tier in tiers:
        try:
            _scope(ac, tier=tier, types=(action_type,))
            accepted.append(tier)
        except REJECT:
            pass
    if floor == "P5":
        assert accepted == []
    else:
        assert accepted == tiers[tiers.index(floor):]


def test_x03_vocabulary_v1_is_the_design_vocabulary(ac):
    assert ac.ACTION_TYPE_VOCABULARY == frozenset(DESIGN_T_FLOOR)
    assert type(ac.ACTION_TYPE_VOCABULARY) is frozenset
    assert ac.ACTION_VOCABULARY_VERSION == 1 and ac.AUTHORITY_SCOPE_SCHEMA_VERSION == 1


def test_x03_vocabulary_matches_permission_engine_read_only(ac):
    """Drift guard only: the Permission Engine is read, never modified."""
    from app.decision_intelligence import permission_engine, plan_validation

    engine_types = set(permission_engine._ACTION_TYPE_FLOOR) | set(plan_validation._NO_TOOL_ACTION_TYPES)
    assert engine_types == set(ac.ACTION_TYPE_VOCABULARY)


# --------------------------------------------------------------------------
# Version / dimension attacks A-19..A-21
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [2, 0, "1", 1.0, True, None])
def test_a19_unknown_schema_version_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, schema_version=bad))


@pytest.mark.parametrize("bad", [2, 0, -1, "1", 1.0, True, None])
def test_a20_unknown_vocabulary_version_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, vocabulary_version=bad))


@pytest.mark.parametrize("field", sorted(SCOPE_FIELDS))
def test_a21_every_dimension_required(ac, field):
    kwargs = _scope_kwargs(ac)
    kwargs.pop(field)
    with pytest.raises(REJECT):
        ac.AuthorityScope(**kwargs)


@pytest.mark.parametrize("future", [
    {"tenant_scope": "ALL"}, {"resource_scope": frozenset()}, {"data_classification_scope": "ANY"},
    {"budget": 0}, {"redelegation": None},
])
def test_a21_future_dimension_not_accepted(ac, future):
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, **future))


def test_a21_scope_dimension_set_is_exactly_the_design_set(ac):
    assert set(ac.AuthorityScope.model_fields) == SCOPE_FIELDS


# --------------------------------------------------------------------------
# Expiry attacks A-24..A-26
# --------------------------------------------------------------------------

def test_a24_later_child_expiry_is_not_leq(ac):
    assert not ac.leq(_scope(ac, exp=T_LATE), _scope(ac, exp=T_MID))
    assert ac.leq(_scope(ac, exp=T_EARLY), _scope(ac, exp=T_MID))


@pytest.mark.parametrize("bad", [
    datetime(2030, 6, 1),
    datetime(2030, 6, 1, 2, tzinfo=timezone(timedelta(hours=2))),
    "2030-06-01T00:00:00Z",
    1906156800,
    None,
])
def test_a25_naive_non_utc_or_untyped_expiry_rejected(ac, bad):
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, expires_at=bad))


def test_a25_datetime_subclass_rejected(ac):
    class SneakyDatetime(datetime):
        def __le__(self, other):
            return True

    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, expires_at=SneakyDatetime(2099, 1, 1, tzinfo=UTC)))


def test_a26_algebra_is_wall_clock_free(ac):
    past_a = _scope(ac, exp=datetime(2000, 1, 1, tzinfo=UTC))
    past_b = _scope(ac, exp=datetime(2001, 1, 1, tzinfo=UTC))
    results = {(ac.leq(past_a, past_b), ac.meet(past_a, past_b)) for _ in range(5)}
    assert results == {(True, past_a)}
    algebra = (_PACKAGE_DIR / "algebra.py").read_text(encoding="utf-8")
    for token in ("now(", "utcnow", "today(", "time.time", "monotonic", "import time"):
        assert token not in algebra


# --------------------------------------------------------------------------
# Meet attacks A-27..A-32
# --------------------------------------------------------------------------

def test_a27_disjoint_actions_meet_is_bottom(ac):
    assert ac.meet(_scope(ac, types=("read",)), _scope(ac, types=("internal_create",))) is ac.NO_AUTHORITY


def test_a28_mismatched_objective_meet_is_bottom(ac):
    assert ac.meet(_scope(ac, oid="objective.alpha"), _scope(ac, oid="objective.beta", ov=1)) is ac.NO_AUTHORITY


def test_a29_mismatched_schema_meet_is_bottom(ac):
    foreign = _tampered(ac, "schema_version", 2)
    assert ac.meet(foreign, _scope(ac)) is ac.NO_AUTHORITY
    assert ac.meet(_scope(ac), foreign) is ac.NO_AUTHORITY
    assert not ac.leq(foreign, _scope(ac)) and not ac.leq(_scope(ac), foreign)


def test_a30_mismatched_vocabulary_meet_is_bottom(ac):
    foreign = _tampered(ac, "vocabulary_version", 2)
    assert ac.meet(foreign, _scope(ac)) is ac.NO_AUTHORITY
    assert ac.meet(_scope(ac), foreign) is ac.NO_AUTHORITY
    assert not ac.leq(foreign, _scope(ac)) and not ac.leq(_scope(ac), foreign)


def test_a31_meet_never_raises_the_ceiling(ac):
    m = ac.meet(_scope(ac, tier="P1", types=("read",)), _scope(ac, tier="P4", types=("read",)))
    assert m.permission_ceiling is ac.PTier.P1


def test_a32_meet_intersects_never_unions(ac):
    m = ac.meet(_scope(ac, types=("read", "internal_create")), _scope(ac, types=("read", "sandbox_create")))
    assert m.action_types == frozenset({"read"})


def test_x08_meet_result_is_exact_valid_scope_with_min_expiry(ac):
    m = ac.meet(_scope(ac, exp=T_EARLY), _scope(ac, exp=T_LATE))
    assert type(m) is ac.AuthorityScope
    assert m.expires_at == T_EARLY and m.expires_at.tzinfo is UTC


# --------------------------------------------------------------------------
# Bottom attacks A-33..A-35
# --------------------------------------------------------------------------

def test_a33_bottom_is_not_unlimited_and_not_none(ac):
    bottom = ac.NO_AUTHORITY
    assert bottom is not None
    assert not isinstance(bottom, ac.AuthorityScope)
    assert bottom != _scope(ac)
    assert ac.leq(bottom, _scope(ac))
    assert not ac.leq(_scope(ac), bottom)
    assert ac.leq(bottom, bottom)
    with pytest.raises(TypeError):
        bool(bottom)  # `if meet(...):` must never silently pass or fail


def test_a34_bottom_cannot_become_a_scope(ac):
    bottom = ac.NO_AUTHORITY
    with pytest.raises(REJECT):
        ac.AuthorityScope.model_validate(bottom)
    for attr in ("permission_ceiling", "action_types", "objective_ref", "expires_at"):
        assert not hasattr(bottom, attr)
    with pytest.raises((AttributeError, TypeError)):
        bottom.permission_ceiling = ac.PTier.P4
    assert type(bottom)() is bottom
    assert copy.copy(bottom) is bottom and copy.deepcopy(bottom) is bottom
    assert pickle.loads(pickle.dumps(bottom)) is bottom
    with pytest.raises(TypeError):
        class MoreThanNothing(type(bottom)):
            pass


def test_a35_bottom_absorbs_in_meet(ac):
    s = _scope(ac)
    assert ac.meet(ac.NO_AUTHORITY, s) is ac.NO_AUTHORITY
    assert ac.meet(s, ac.NO_AUTHORITY) is ac.NO_AUTHORITY
    assert ac.meet(ac.NO_AUTHORITY, ac.NO_AUTHORITY) is ac.NO_AUTHORITY


# --------------------------------------------------------------------------
# Mutation attacks A-36..A-39
# --------------------------------------------------------------------------

def test_a36_nested_mutation_rejected(ac):
    s = _scope(ac)
    with pytest.raises(MUTATE_REJECT):
        s.objective_ref.objective_version = 2
    with pytest.raises(MUTATE_REJECT):
        s.objective_ref.objective_id = "objective.beta"
    with pytest.raises(MUTATE_REJECT):
        del s.objective_ref.objective_version
    assert s.objective_ref == _obj(ac)


@pytest.mark.parametrize("op", [
    lambda s: s.action_types.add("delete"),
    lambda s: s.action_types.update({"delete"}),
    lambda s: s.action_types.discard("read"),
    lambda s: s.action_types.remove("read"),
    lambda s: s.action_types.pop(),
    lambda s: s.action_types.clear(),
    lambda s: s.action_types.__ior__({"delete"}),
    lambda s: s.action_types.append("delete"),
    lambda s: s.action_types.extend(["delete"]),
    lambda s: s.action_types.insert(0, "delete"),
    lambda s: s.action_types.reverse(),
    lambda s: s.action_types.sort(),
    lambda s: s.action_types.__setitem__(0, "delete"),
    lambda s: s.action_types.__delitem__(0),
    lambda s: s.action_types.setdefault("delete", 1),
    lambda s: s.action_types.popitem(),
])
def test_a37_in_place_container_mutation_rejected(ac, op):
    s = _scope(ac, types=("read", "internal_create"))
    with pytest.raises(MUTATE_REJECT):
        op(s)
    assert s.action_types == frozenset({"read", "internal_create"})


def _aug_ior(s):
    s.action_types |= {"delete"}


def _aug_iadd(s):
    s.action_types += ("delete",)


def _aug_imul(s):
    s.action_types *= 2


@pytest.mark.parametrize("op", [
    lambda s: setattr(s, "permission_ceiling", s.permission_ceiling),
    lambda s: setattr(s, "action_types", frozenset({"read", "delete"})),
    lambda s: setattr(s, "expires_at", T_LATE),
    lambda s: delattr(s, "expires_at"),
    lambda s: setattr(s, "tenant_scope", "ALL"),
    _aug_ior, _aug_iadd, _aug_imul,
])
def test_a37_field_assignment_and_augmented_assignment_rejected(ac, op):
    s = _scope(ac, types=("read", "internal_create"))
    before = copy.deepcopy(s)
    with pytest.raises(MUTATE_REJECT):
        op(s)
    assert s == before


@pytest.mark.parametrize("name,value", [
    ("__pydantic_extra__", {"approved": True}),
    ("__pydantic_fields_set__", {"schema_version"}),
    ("__pydantic_private__", {"approval": "granted"}),
    ("__pydantic_fields__", {}),
    ("__dict__", {"permission_ceiling": "P5"}),
])
def test_f05_pydantic_internal_attribute_assignment_rejected(ac, name, value):
    """Final hostile review F-05: `frozen` guards declared fields only; plain
    assignment of pydantic internals used to succeed (e.g. an extra dict made
    `scope.approved` true, a fields-set hid expiry from exclude_unset dumps)."""
    objective = _obj(ac)
    principal = ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="agent.alpha")
    for model in (_scope(ac), objective, principal):
        before = copy.deepcopy(model)
        with pytest.raises(TypeError):
            setattr(model, name, value)
        with pytest.raises(TypeError):
            delattr(model, name)
        assert model == before
        assert model.model_dump() == before.model_dump()
        assert not hasattr(model, "approved")


def test_a37_every_field_value_is_immutable(ac):
    s = _scope(ac)
    for name in SCOPE_FIELDS:
        hash(getattr(s, name))
    assert type(s.action_types) is frozenset
    hash(s)


def test_a38_caller_alias_cannot_mutate_scope(ac):
    caller_types = {"read"}
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, action_types=caller_types))
    objective = _obj(ac)
    s = ac.AuthorityScope(**_scope_kwargs(ac, objective_ref=objective))
    with pytest.raises(MUTATE_REJECT):
        objective.objective_version = 9
    assert s.objective_ref.objective_version == 1


@pytest.mark.parametrize("model_name", ["AuthorityScope", "ObjectiveRef", "PrincipalRef"])
def test_a39_model_construct_and_model_copy_bypass_rejected(ac, model_name):
    model = getattr(ac, model_name)
    with pytest.raises(TypeError):
        model.model_construct()
    instance = {
        "AuthorityScope": lambda: _scope(ac),
        "ObjectiveRef": lambda: _obj(ac),
        "PrincipalRef": lambda: ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="agent.one"),
    }[model_name]()
    with pytest.raises(TypeError):
        instance.model_copy()
    with pytest.raises(TypeError):
        instance.model_copy(update={"permission_ceiling": ac.PTier.P5})


@pytest.mark.parametrize("model_name", ["AuthorityScope", "ObjectiveRef", "PrincipalRef"])
def test_a39_subclassing_rejected(ac, model_name):
    base = getattr(ac, model_name)
    with pytest.raises(TypeError):
        type("Widened", (base,), {"__module__": __name__})


def test_a39_copy_and_pickle_preserve_equal_valid_scope(ac):
    s = _scope(ac)
    for clone in (copy.copy(s), copy.deepcopy(s), pickle.loads(pickle.dumps(s))):
        assert clone == s and hash(clone) == hash(s) and type(clone) is ac.AuthorityScope
        assert ac.leq(clone, s) and ac.leq(s, clone)


def test_x09_tampered_p5_scope_never_propagates(ac):
    """An out-of-contract record claiming P5 (same versions, so no early
    bottom) is revalidated by the algebra and refused, never compared."""
    forged = _tampered(ac, "permission_ceiling", ac.PTier.P5)
    honest = _scope(ac)
    for call in (lambda: ac.leq(honest, forged), lambda: ac.leq(forged, honest),
                 lambda: ac.meet(honest, forged), lambda: ac.meet(forged, forged)):
        with pytest.raises(REJECT):
            call()


def test_x09_tampered_wildcard_or_empty_scope_never_propagates(ac):
    for field, value in (("action_types", frozenset({"*"})), ("action_types", frozenset()),
                         ("expires_at", datetime(2030, 1, 1)), ("objective_ref", "free text")):
        forged = _tampered(ac, field, value)
        with pytest.raises(REJECT):
            ac.meet(_scope(ac), forged)
        with pytest.raises(REJECT):
            ac.leq(_scope(ac), forged)


def test_f01_model_validate_revalidates_tampered_instances(ac):
    """Second hostile review F-01 (MEDIUM): model_validate(instance) used to
    return a tampered instance untouched."""
    with pytest.raises(REJECT):
        ac.AuthorityScope.model_validate(_tampered(ac, "permission_ceiling", ac.PTier.P5))
    with pytest.raises(REJECT):
        ac.AuthorityScope.model_validate(_tampered(ac, "action_types", frozenset({"*"})))
    forged_objective = copy.deepcopy(_obj(ac))
    object.__setattr__(forged_objective, "objective_version", True)
    with pytest.raises(REJECT):
        ac.ObjectiveRef.model_validate(forged_objective)
    with pytest.raises(REJECT):
        ac.AuthorityScope(**_scope_kwargs(ac, objective_ref=forged_objective))
    forged_principal = ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id="agent.one")
    object.__setattr__(forged_principal, "id", "agent\nforged")
    with pytest.raises(REJECT):
        ac.PrincipalRef.model_validate(forged_principal)


def test_f01_honest_instances_still_validate(ac):
    s = _scope(ac)
    assert ac.AuthorityScope.model_validate(s) == s


def test_x15_copy_replace_and_lax_validation_rejected(ac):
    s = _scope(ac)
    if hasattr(copy, "replace"):
        with pytest.raises(TypeError):
            copy.replace(s, permission_ceiling=ac.PTier.P5)
    with pytest.raises(REJECT):
        ac.AuthorityScope.model_validate(dict(s) | {"permission_ceiling": "P4"}, strict=False)
    with pytest.raises(REJECT):
        ac.AuthorityScope.model_validate_json(s.model_dump_json())  # no deserialization path


@pytest.mark.parametrize("bad", [None, {}, "P4", 4, object()])
def test_x04_algebra_rejects_values_outside_the_carrier_set(ac, bad):
    s = _scope(ac)
    for call in (lambda: ac.leq(bad, s), lambda: ac.leq(s, bad), lambda: ac.meet(bad, s), lambda: ac.meet(s, bad)):
        with pytest.raises(TypeError):
            call()


def test_x04_algebra_rejects_principal_and_objective_values(ac):
    s = _scope(ac)
    with pytest.raises(TypeError):
        ac.leq(ac.PrincipalRef(kind=ac.PrincipalKind.HUMAN_OWNER, id="owner"), s)
    with pytest.raises(TypeError):
        ac.meet(_obj(ac), s)


# --------------------------------------------------------------------------
# Authority-confusion attacks A-40..A-44
# --------------------------------------------------------------------------

_FORBIDDEN_FIELD_TOKENS = (
    "approv", "tool", "adapter", "execut", "budget", "spend", "financ", "role", "title",
    "provider", "model", "metadata", "delegat", "credential", "secret", "token", "grant",
)


@pytest.mark.parametrize("model_name", ["AuthorityScope", "ObjectiveRef", "PrincipalRef"])
def test_a40_no_approval_tool_or_budget_shaped_field(ac, model_name):
    for name in getattr(ac, model_name).model_fields:
        assert not any(tok in name.lower() for tok in _FORBIDDEN_FIELD_TOKENS), name


def test_a40_scope_is_not_an_approval_or_permission_decision(ac):
    from app.decision_intelligence.permission_engine import PermissionDecision
    from app.decision_intelligence.schemas import ApprovalRequest

    s = _scope(ac)
    assert not isinstance(s, (PermissionDecision, ApprovalRequest))
    assert not issubclass(ac.AuthorityScope, (PermissionDecision, ApprovalRequest))


_PROHIBITED_IMPORT_PREFIXES = (
    "app.providers.registry", "app.providers.router", "app.decision_intelligence",
    "app.agents", "app.security", "app.orchestration", "app.database", "app.tools",
    "app.services", "app.api", "app.memory", "app.research_intelligence", "app.config",
    "sqlalchemy", "alembic", "requests", "httpx", "urllib", "socket", "subprocess",
    "anthropic", "openai", "dotenv", "os", "time",
)


def test_a41_package_imports_no_capability_pipeline_or_io_module(ac):
    for name, source in _package_sources().items():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                for prefix in _PROHIBITED_IMPORT_PREFIXES:
                    assert not (module == prefix or module.startswith(prefix + ".")), (name, module)


def test_a41_package_source_has_no_io_or_environment_access(ac):
    for name, source in _package_sources().items():
        for token in ("open(", "environ", "getenv", ".env", "ToolAdapter", "execute(", "sqlite"):
            assert token not in source, (name, token)


@pytest.mark.parametrize("extra", [
    {"role": "CEO"}, {"title": "CFO"}, {"provider_id": "anthropic"}, {"model_id": "claude"},
    {"agent_type": "finance"}, {"display_name": "Owner"},
])
def test_a42_role_title_provider_model_rejected(ac, extra):
    with pytest.raises(REJECT):
        _scope(ac, **extra)


def test_a42_algebra_takes_exactly_two_operands(ac):
    for fn in (ac.leq, ac.meet):
        params = list(inspect.signature(fn).parameters.values())
        assert len(params) == 2
        assert all(p.kind is inspect.Parameter.POSITIONAL_ONLY for p in params)


@pytest.mark.parametrize("extra", [
    {"metadata": {"approval": "granted"}}, {"approved": True}, {"approval_id": "a-1"},
    {"approved_by": "owner"}, {"notes": "owner approved"},
])
def test_a43_approval_smuggling_rejected(ac, extra):
    with pytest.raises(REJECT):
        _scope(ac, **extra)


@pytest.mark.parametrize("extra", [
    {"budget": 1000}, {"business_spend": True}, {"financial_authority": "P5"},
    {"can_spend": True}, {"spend_limit": 10**9},
])
def test_a44_budget_or_financial_smuggling_rejected(ac, extra):
    with pytest.raises(REJECT):
        _scope(ac, **extra)


# --------------------------------------------------------------------------
# Vocabulary attacks A-45, A-46 and no-issuance API X-07
# --------------------------------------------------------------------------

@pytest.mark.parametrize("alias", ["OUTSIDE_CEILING", "LINEAGE_DISCONTINUOUS"])
def test_a45_a46_dangling_reason_aliases_not_reintroduced(ac, alias):
    for name, source in _package_sources().items():
        assert alias not in source, name


def test_x07_public_api_is_exactly_contracts_and_algebra(ac):
    assert set(ac.__all__) == EXPECTED_PUBLIC_API


_ISSUANCE_WORDS = ("attenuate", "issue", "delegat", "grant", "clip", "join", "union", "authorize",
                   "approve", "execute", "revoke", "evaluate", "store", "persist", "upgrade", "migrate")


def test_x07_no_issuance_join_or_runtime_callable_anywhere_in_package(ac):
    for name, source in _package_sources().items():
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                lowered = node.name.lower()
                assert not any(w in lowered for w in _ISSUANCE_WORDS), (name, node.name)


def test_x07_no_later_stage_contract_defined(ac):
    later = {"DelegationRecord", "RootAuthorization", "DelegationStore", "RevocationRecord",
             "DelegationEvaluator", "DelegationLineage", "DelegationService", "DelegationRequest",
             "RedelegationPolicy", "AuthorityEvaluation", "SystemPolicyCeiling", "DelegationParentRef"}
    for name, source in _package_sources().items():
        defined = {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ClassDef)}
        assert not (defined & later), (name, defined & later)


# --------------------------------------------------------------------------
# Hygiene / determinism X-05, X-06, X-13
# --------------------------------------------------------------------------

def test_x05_json_serialization_is_deterministic(ac):
    types = ["read", "internal_create", "sandbox_create", "no_op", "manual"]
    a = _scope(ac, types=types)
    b = _scope(ac, types=list(reversed(types)))
    assert a.model_dump_json() == b.model_dump_json()
    assert '"action_types":["internal_create","manual","no_op","read","sandbox_create"]' in a.model_dump_json()


def test_x06_validation_errors_do_not_echo_hostile_input(ac):
    secret = "sk-ant-THISISNOTAREALKEY0123456789"
    for build in (
        lambda: ac.PrincipalRef(kind=ac.PrincipalKind.AGENT, id=secret + "\n"),
        lambda: ac.ObjectiveRef(objective_id=secret + " x", objective_version=1),
        lambda: _scope(ac, types=("read", secret)),
        lambda: _scope(ac, notes=secret),
    ):
        with pytest.raises(REJECT) as info:
            build()
        assert secret not in str(info.value)


def test_x13_equality_and_hash_are_consistent(ac):
    a, b = _scope(ac), _scope(ac)
    assert a == b and hash(a) == hash(b) and a is not b
    assert _scope(ac, ov=2) != a
    assert len({a, b, _scope(ac, ov=2)}) == 2


def test_x13_scopes_have_no_total_order(ac):
    a, b = _scope(ac, types=("read",)), _scope(ac, types=("internal_create",))
    assert not ac.leq(a, b) and not ac.leq(b, a)
    with pytest.raises(TypeError):
        a < b
    with pytest.raises(TypeError):
        sorted([a, b])


# --------------------------------------------------------------------------
# Section 41 representative examples
# --------------------------------------------------------------------------

def test_s41_representative_examples(ac):
    a = _scope(ac)
    assert ac.leq(a, a)
    assert ac.leq(_scope(ac, tier="P2"), _scope(ac, tier="P4"))
    assert not ac.leq(_scope(ac, tier="P4"), _scope(ac, tier="P2"))
    narrow = _scope(ac, types=("internal_create",))
    wide = _scope(ac, types=("internal_create", "external_modify"))
    assert ac.leq(narrow, wide) and not ac.leq(wide, narrow)
    assert not ac.leq(_scope(ac, ov=2), a) and ac.meet(_scope(ac, ov=2), a) is ac.NO_AUTHORITY
    assert not ac.leq(_scope(ac, exp=T_LATE), a)
    assert ac.leq(_scope(ac, exp=T_EARLY), a)
    assert ac.meet(_scope(ac, types=("read",)), _scope(ac, types=("sandbox_create",))) is ac.NO_AUTHORITY
    assert ac.meet(_tampered(ac, "schema_version", 2), a) is ac.NO_AUTHORITY
    assert ac.meet(_tampered(ac, "vocabulary_version", 2), a) is ac.NO_AUTHORITY
    assert ac.leq(ac.NO_AUTHORITY, a)
    assert not ac.leq(a, ac.NO_AUTHORITY)


# --------------------------------------------------------------------------
# Algebra properties A-47..A-54 over a deterministic finite universe
# --------------------------------------------------------------------------

_UNIVERSE_TYPES = ("no_op", "read", "internal_create", "external_modify", "send")
_UNIVERSE_OBJECTIVES = (("objective.alpha", 1), ("objective.alpha", 2), ("objective.beta", 1))
_UNIVERSE_EXPIRIES = (T_EARLY, T_MID, T_LATE)


@pytest.fixture(scope="module")
def universe(ac):
    scopes = []
    for tier in ("P0", "P1", "P2", "P3", "P4"):
        for r in range(1, len(_UNIVERSE_TYPES) + 1):
            for types in itertools.combinations(_UNIVERSE_TYPES, r):
                if any(DESIGN_T_FLOOR[t] > tier for t in types):
                    continue
                for (oid, ov), exp in itertools.product(_UNIVERSE_OBJECTIVES, _UNIVERSE_EXPIRIES):
                    scopes.append(_scope(ac, tier=tier, types=types, oid=oid, ov=ov, exp=exp))
    assert len(scopes) == 57 * 9
    return scopes + [ac.NO_AUTHORITY]


@pytest.fixture(scope="module")
def triples(universe):
    rng = random.Random(20260924)
    return [tuple(rng.choice(universe) for _ in range(3)) for _ in range(6000)]


def _eq(ac, a, b):
    if a is ac.NO_AUTHORITY or b is ac.NO_AUTHORITY:
        return a is b
    return a == b


def test_a47_reflexive(ac, universe):
    assert all(ac.leq(a, a) for a in universe)


def test_a48_antisymmetric(ac, universe):
    sample = universe[::3]
    for a in sample:
        for b in sample:
            if ac.leq(a, b) and ac.leq(b, a):
                assert _eq(ac, a, b)


def test_a49_transitive(ac, universe, triples):
    checked = 0
    for a, b, c in triples:
        if ac.leq(a, b) and ac.leq(b, c):
            checked += 1
            assert ac.leq(a, c)
    # also along explicit chains so the property is not vacuous
    for c in universe[::7]:
        for b in universe:
            if ac.leq(b, c):
                a = ac.meet(b, b)
                checked += 1
                assert ac.leq(a, c)
    assert checked > 100


def test_a50_meet_commutative(ac, universe):
    sample = universe[::4]
    for a in sample:
        for b in sample:
            assert _eq(ac, ac.meet(a, b), ac.meet(b, a))


def test_a51_meet_associative(ac, triples):
    for a, b, c in triples:
        assert _eq(ac, ac.meet(ac.meet(a, b), c), ac.meet(a, ac.meet(b, c)))


def test_a52_meet_idempotent(ac, universe):
    assert all(_eq(ac, ac.meet(a, a), a) for a in universe)


def test_a53_meet_is_a_lower_bound(ac, universe):
    sample = universe[::4]
    non_bottom = 0
    for a in sample:
        for b in sample:
            m = ac.meet(a, b)
            assert ac.leq(m, a) and ac.leq(m, b)
            non_bottom += m is not ac.NO_AUTHORITY
    assert non_bottom > 0


def test_a54_meet_is_the_greatest_lower_bound(ac, universe, triples):
    checked = 0
    for x, a, b in triples:
        if ac.leq(x, a) and ac.leq(x, b):
            checked += 1
            assert ac.leq(x, ac.meet(a, b))
    small = universe[::11]
    for a in small:
        for b in small:
            m = ac.meet(a, b)
            for x in universe:
                if ac.leq(x, a) and ac.leq(x, b):
                    checked += 1
                    assert ac.leq(x, m)
    assert checked > 100


def test_a47_order_is_partial_not_total(ac, universe):
    sample = universe[::5]
    incomparable = sum(1 for a in sample for b in sample if not ac.leq(a, b) and not ac.leq(b, a))
    assert incomparable > 0


def test_po01_leq_accepted_children_never_exceed_parent_in_any_dimension(ac, universe):
    """PO-01 expressed without issuance (attenuate() is deferred to v0.2.5.2):
    whenever leq(child, parent) holds, every dimension is attenuated."""
    rank = {f"P{i}": i for i in range(6)}
    scopes = [s for s in universe if s is not ac.NO_AUTHORITY][::2]
    for child in scopes:
        for parent in scopes:
            if ac.leq(child, parent):
                assert rank[child.permission_ceiling.name] <= rank[parent.permission_ceiling.name]
                assert child.action_types <= parent.action_types
                assert child.objective_ref == parent.objective_ref
                assert child.expires_at <= parent.expires_at
