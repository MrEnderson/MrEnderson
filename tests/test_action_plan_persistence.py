"""Durable ActionPlan persistence, plan-integrity hash, optimistic
concurrency, and plan-level lease claiming (v0.1.3.6, spec sections 6/24/
25/33/41). Every test uses the isolated temp-file SQLite database from
conftest.py's `session`/`session_factory` fixtures."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import PersistedActionPlanStatus
from app.database.repositories import ActionPlanRecordRepository, ActionRecordRepository
from app.decision_intelligence.action_plan_persistence import (
    compute_plan_hash,
    load_plan,
    normalize_failure_policy,
    persist_new_plan,
    plan_structure_unchanged,
)
from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="internal", title="A", sequence=1,
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    fields.update(overrides)
    return Action(**fields)


def _plan(actions: list[Action] | None = None, **overrides) -> ActionPlan:
    fields = dict(decision_id="dec-1", title="Test plan", actions=actions or [])
    fields.update(overrides)
    plan = ActionPlan(**fields)
    fixed_actions = [a.model_copy(update={"action_plan_id": plan.id}) for a in plan.actions]
    return plan.model_copy(update={"actions": fixed_actions})


# --- Failure policy normalization (spec sections 22/23) -----------------------


def test_normalize_failure_policy_accepts_stop_on_failure():
    assert normalize_failure_policy("STOP_ON_FAILURE") == "STOP_ON_FAILURE"


def test_normalize_failure_policy_accepts_continue_independent():
    assert normalize_failure_policy("continue_independent") == "CONTINUE_INDEPENDENT"


def test_normalize_failure_policy_defaults_to_safer_policy_when_blank():
    assert normalize_failure_policy("") == "STOP_ON_FAILURE"
    assert normalize_failure_policy(None) == "STOP_ON_FAILURE"


def test_normalize_failure_policy_defaults_to_safer_policy_when_unrecognized():
    assert normalize_failure_policy("YOLO_MODE") == "STOP_ON_FAILURE"


# --- Plan hash (spec section 33) -----------------------------------------------


def test_plan_hash_is_deterministic():
    a1 = _action()
    plan = _plan([a1])
    assert compute_plan_hash(plan) == compute_plan_hash(plan)


def test_plan_hash_changes_when_action_inputs_change():
    a1 = _action(action_type="sandbox_create", tool_name="file.create_sandboxed", inputs={"relative_path": "a.txt", "content": "v1"})
    plan = _plan([a1])
    changed = plan.model_copy(update={"actions": [a1.model_copy(update={"inputs": {"relative_path": "a.txt", "content": "v2"}})]})
    assert compute_plan_hash(plan) != compute_plan_hash(changed)


def test_plan_hash_changes_when_dependencies_change():
    a1 = _action()
    a2 = _action(action_type="internal", dependencies=[])
    plan = _plan([a1, a2])
    changed_a2 = plan.actions[1].model_copy(update={"dependencies": [plan.actions[0].id]})
    changed = plan.model_copy(update={"actions": [plan.actions[0], changed_a2]})
    assert compute_plan_hash(plan) != compute_plan_hash(changed)


def test_plan_hash_unaffected_by_permission_level_change():
    """The deliberate divergence from action_hash.py::compute_action_hash
    (spec section 34 rationale) — permission_level/risk_level legitimately
    change once during normal orchestration and must NOT look like plan
    mutation."""
    from app.database.models import PermissionLevel

    a1 = _action(permission_level=PermissionLevel.READ)
    plan = _plan([a1])
    authoritative = plan.actions[0].model_copy(update={"permission_level": PermissionLevel.ADMIN})
    changed = plan.model_copy(update={"actions": [authoritative]})
    assert compute_plan_hash(plan) == compute_plan_hash(changed)


def test_plan_hash_unaffected_by_lifecycle_fields():
    a1 = _action()
    plan = _plan([a1])
    changed = plan.model_copy(update={"title": "renamed", "estimated_cost": 42.0})
    assert compute_plan_hash(plan) == compute_plan_hash(changed)


def test_plan_structure_unchanged_true_for_identical_plans():
    a1 = _action()
    plan = _plan([a1])
    assert plan_structure_unchanged(plan, plan) is True


def test_plan_structure_unchanged_false_for_changed_tool():
    a1 = _action(action_type="sandbox_create", tool_name="file.create_sandboxed", inputs={"relative_path": "a.txt", "content": "x"})
    plan = _plan([a1])
    tampered = plan.model_copy(update={"actions": [plan.actions[0].model_copy(update={"tool_name": "communication.send_email"})]})
    assert plan_structure_unchanged(plan, tampered) is False


# --- Round-trip persistence (spec section 7) -----------------------------------


async def test_persist_and_load_plan_round_trips(session):
    a1 = _action(sequence=1)
    a2 = _action(sequence=2, dependencies=[a1.id], action_type="internal")
    plan = _plan([a1, a2])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)

    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    loaded = await load_plan(plan_repo, action_repo, plan.id)
    assert loaded is not None
    row, loaded_plan = loaded
    assert loaded_plan.id == plan.id
    assert len(loaded_plan.actions) == 2
    assert row.plan_hash == compute_plan_hash(plan)


async def test_persisted_actions_start_at_validated(session):
    a1 = _action()
    plan = _plan([a1])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    rows = await action_repo.list_by_plan(plan.id)
    assert all(r.status.value == "VALIDATED" for r in rows)


async def test_load_plan_returns_none_for_unknown_id(session):
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    assert await load_plan(plan_repo, action_repo, "nonexistent") is None


async def test_load_plan_actions_deterministically_ordered(session):
    a1 = _action(sequence=2, title="second")
    a2 = _action(sequence=1, title="first")
    plan = _plan([a1, a2])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    _, loaded_plan = await load_plan(plan_repo, action_repo, plan.id)
    assert [a.title for a in loaded_plan.actions] == ["first", "second"]


# --- Optimistic concurrency (spec section 41) ----------------------------------


async def test_plan_update_if_version_matches_succeeds_and_increments(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    ok = await plan_repo.update_if_version_matches(plan.id, expected_version=1, status=PersistedActionPlanStatus.EXECUTING)
    assert ok is True
    row = await plan_repo.get(plan.id)
    assert row.version == 2


async def test_plan_update_if_version_matches_fails_on_stale_version(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    await plan_repo.update_if_version_matches(plan.id, expected_version=1, status=PersistedActionPlanStatus.EXECUTING)
    stale = await plan_repo.update_if_version_matches(plan.id, expected_version=1, status=PersistedActionPlanStatus.FAILED)
    assert stale is False
    row = await plan_repo.get(plan.id)
    assert row.status == PersistedActionPlanStatus.EXECUTING


async def test_one_of_two_concurrent_plan_updates_wins(session_factory):
    plan = _plan([_action()])
    async with session_factory() as setup:
        await persist_new_plan(ActionPlanRecordRepository(setup), ActionRecordRepository(setup), plan)
        await setup.commit()

    async def attempt(target):
        async with session_factory() as s:
            return await ActionPlanRecordRepository(s).update_if_version_matches(plan.id, expected_version=1, status=target)

    results = await asyncio.gather(
        attempt(PersistedActionPlanStatus.EXECUTING), attempt(PersistedActionPlanStatus.CANCELLED)
    )
    assert sorted(results) == [False, True]


# --- Plan-level orchestration lease/claim (spec sections 24/25) --------------


async def test_claim_orchestration_succeeds_for_unclaimed_plan(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    now = datetime.now(timezone.utc)
    claimed = await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=now, lease_seconds=300)
    assert claimed is True
    row = await plan_repo.get(plan.id)
    assert row.orchestration_owner == "worker-1"


async def test_second_claim_on_active_lease_fails(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    now = datetime.now(timezone.utc)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=now, lease_seconds=300)
    second = await plan_repo.claim_orchestration(plan.id, owner="worker-2", now=now, lease_seconds=300)
    assert second is False


async def test_claim_on_expired_lease_fails_without_stale_takeover_flag(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=past, lease_seconds=1)  # already expired
    later = datetime.now(timezone.utc)
    second = await plan_repo.claim_orchestration(plan.id, owner="worker-2", now=later, lease_seconds=300)
    assert second is False  # expired lease is NEVER silently stolen


async def test_claim_on_expired_lease_succeeds_with_explicit_stale_takeover(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=past, lease_seconds=1)
    later = datetime.now(timezone.utc)
    second = await plan_repo.claim_orchestration(
        plan.id, owner="worker-2", now=later, lease_seconds=300, allow_stale_takeover=True
    )
    assert second is True


async def test_release_orchestration_clears_owner(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    now = datetime.now(timezone.utc)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=now, lease_seconds=300)
    released = await plan_repo.release_orchestration(plan.id, owner="worker-1")
    assert released is True
    row = await plan_repo.get(plan.id)
    assert row.orchestration_owner is None


async def test_release_orchestration_wrong_owner_fails(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    now = datetime.now(timezone.utc)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=now, lease_seconds=300)
    released = await plan_repo.release_orchestration(plan.id, owner="someone-else")
    assert released is False


async def test_two_concurrent_claims_exactly_one_succeeds(session_factory):
    plan = _plan([_action()])
    async with session_factory() as setup:
        await persist_new_plan(ActionPlanRecordRepository(setup), ActionRecordRepository(setup), plan)
        await setup.commit()

    now = datetime.now(timezone.utc)

    async def attempt(owner):
        async with session_factory() as s:
            return await ActionPlanRecordRepository(s).claim_orchestration(plan.id, owner=owner, now=now, lease_seconds=300)

    results = await asyncio.gather(attempt("worker-a"), attempt("worker-b"))
    assert sorted(results) == [False, True]


async def test_list_stale_leases_finds_expired(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=past, lease_seconds=1)

    stale = await plan_repo.list_stale_leases(before=datetime.now(timezone.utc))
    assert any(r.id == plan.id for r in stale)


async def test_list_stale_leases_excludes_fresh(session):
    plan = _plan([_action()])
    plan_repo = ActionPlanRecordRepository(session)
    action_repo = ActionRecordRepository(session)
    await persist_new_plan(plan_repo, action_repo, plan)
    await session.commit()

    now = datetime.now(timezone.utc)
    await plan_repo.claim_orchestration(plan.id, owner="worker-1", now=now, lease_seconds=300)

    stale = await plan_repo.list_stale_leases(before=now)
    assert not any(r.id == plan.id for r in stale)


# --- Migration table shape ------------------------------------------------------


def test_migration_creates_action_plans_table(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path as _Path

    from alembic import command
    from alembic.config import Config

    from app.config.settings import get_settings

    project_root = _Path(__file__).resolve().parents[1]
    db_path = tmp_path / "fresh_v0136.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()

    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    con = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cols = {r[1] for r in con.execute("PRAGMA table_info(action_plans)")}
    finally:
        con.close()

    assert "action_plans" in tables
    expected = {
        "id", "decision_id", "project_id", "title", "description", "failure_policy",
        "status", "created_by", "plan_hash", "version", "created_at", "updated_at",
        "started_at", "completed_at", "last_error", "pause_reason", "reconciliation_required",
        "orchestration_owner", "orchestration_claimed_at", "orchestration_lease_expires_at",
    }
    assert expected <= cols
    get_settings.cache_clear()


def test_v0136_migration_is_chained_from_v0135():
    # Only checks the link, not the overall head — deliberately
    # forward-compatible with later checkpoints adding their own migration
    # on top (v0.1.3.7 did exactly that; see
    # test_v0137_migration_is_chained_from_v0136 below). The "exactly one
    # head" invariant is checked once, globally, by
    # test_migrations.py::test_migration_chain_has_exactly_one_head.
    from pathlib import Path as _Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    project_root = _Path(__file__).resolve().parents[1]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    revision = script.get_revision("2b3daea54d5c")
    assert revision.down_revision == "1a868c95f4ee"


def test_v0137_migration_is_chained_from_v0136():
    from pathlib import Path as _Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    project_root = _Path(__file__).resolve().parents[1]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["7f2c9a1e4b6d"]
    revision = script.get_revision("7f2c9a1e4b6d")
    assert revision.down_revision == "2b3daea54d5c"
