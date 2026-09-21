"""Durable ActionRecord persistence, payload/hash integrity, optimistic
concurrency, and bounded serialization (v0.1.3.5, spec sections 4-6/32).
Every test uses the isolated temp-file SQLite database from conftest.py's
`session`/`session_factory` fixtures."""
from __future__ import annotations

import asyncio

import pytest

from app.database.models import PersistedActionStatus
from app.database.repositories import ActionRecordRepository
from app.decision_intelligence.action_hash import compute_action_hash
from app.decision_intelligence.execution_persistence import (
    MAX_INPUTS_JSON_CHARS,
    PayloadTooLargeForPersistenceError,
    action_to_record_fields,
    bounded_json,
    bounded_text,
    record_to_action,
    safe_inputs_json,
)
from app.decision_intelligence.schemas import Action, ActionStatus


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1",
        action_type="sandbox_create",
        tool_name="file.create_sandboxed",
        title="Write a note",
        description="a test action",
        inputs={"relative_path": "note.txt", "content": "hello"},
        expected_result="a file is created",
        status=ActionStatus.VALIDATED,
    )
    fields.update(overrides)
    return Action(**fields)


# --- Payload/hash integrity (spec section 5) ----------------------------------


def test_action_record_reuses_compute_action_hash_exactly():
    action = _action()
    fields = action_to_record_fields(action)
    assert fields["action_hash"] == compute_action_hash(action)


def test_action_hash_changes_when_inputs_change():
    action = _action()
    other = action.model_copy(update={"inputs": {"relative_path": "note.txt", "content": "different"}})
    fields_a = action_to_record_fields(action)
    fields_b = action_to_record_fields(other)
    assert fields_a["action_hash"] != fields_b["action_hash"]


def test_action_hash_unaffected_by_lifecycle_only_fields():
    action = _action()
    changed = action.model_copy(update={"title": "renamed", "retry_count": 3})
    fields_a = action_to_record_fields(action)
    fields_b = action_to_record_fields(changed)
    assert fields_a["action_hash"] == fields_b["action_hash"]


# --- Round-trip (spec section 5: "add round-trip tests") ---------------------


async def test_action_record_round_trips_through_repository(session):
    action = _action()
    repo = ActionRecordRepository(session)
    fields = action_to_record_fields(action)
    await repo.create(**fields)
    await session.commit()

    row = await repo.get(action.id)
    restored = record_to_action(row)

    assert restored.id == action.id
    assert restored.action_type == action.action_type
    assert restored.tool_name == action.tool_name
    assert restored.inputs == action.inputs
    assert restored.expected_result == action.expected_result
    assert restored.status == action.status
    assert restored.permission_level == action.permission_level
    assert restored.risk_level == action.risk_level


async def test_action_record_round_trip_preserves_action_hash(session):
    action = _action()
    repo = ActionRecordRepository(session)
    await repo.create(**action_to_record_fields(action))
    await session.commit()
    row = await repo.get(action.id)
    restored = record_to_action(row)
    assert compute_action_hash(restored) == compute_action_hash(action)


async def test_action_record_get_unknown_returns_none(session):
    repo = ActionRecordRepository(session)
    assert await repo.get("nonexistent") is None


async def test_action_record_status_persisted_correctly(session):
    action = _action(status=ActionStatus.PERMISSION_CHECKED)
    repo = ActionRecordRepository(session)
    await repo.create(**action_to_record_fields(action))
    await session.commit()
    row = await repo.get(action.id)
    assert row.status == PersistedActionStatus.PERMISSION_CHECKED


def test_persisted_action_status_matches_action_status_values():
    from app.decision_intelligence.schemas import ActionStatus as DomainActionStatus

    assert {m.value for m in PersistedActionStatus} == {m.value for m in DomainActionStatus}


# --- Optimistic concurrency (spec section 6) ----------------------------------


async def test_new_action_record_starts_at_version_one(session):
    action = _action()
    repo = ActionRecordRepository(session)
    row = await repo.create(**action_to_record_fields(action))
    await session.commit()
    assert row.version == 1


async def test_update_if_version_matches_succeeds_and_increments(session):
    action = _action()
    repo = ActionRecordRepository(session)
    await repo.create(**action_to_record_fields(action))
    await session.commit()

    ok = await repo.update_if_version_matches(action.id, expected_version=1, status=PersistedActionStatus.EXECUTING)
    assert ok is True
    row = await repo.get(action.id)
    assert row.version == 2
    assert row.status == PersistedActionStatus.EXECUTING


async def test_update_if_version_matches_fails_on_stale_version(session):
    action = _action()
    repo = ActionRecordRepository(session)
    await repo.create(**action_to_record_fields(action))
    await session.commit()

    await repo.update_if_version_matches(action.id, expected_version=1, status=PersistedActionStatus.EXECUTING)
    stale = await repo.update_if_version_matches(action.id, expected_version=1, status=PersistedActionStatus.FAILED)
    assert stale is False
    row = await repo.get(action.id)
    assert row.status == PersistedActionStatus.EXECUTING  # unaffected by the stale write


async def test_update_if_version_matches_unknown_id_fails(session):
    repo = ActionRecordRepository(session)
    ok = await repo.update_if_version_matches("nonexistent", expected_version=1, status=PersistedActionStatus.FAILED)
    assert ok is False


async def test_one_of_two_concurrent_updates_wins(session_factory):
    """Two independent sessions racing on the same expected_version — the
    database's conditional UPDATE guarantees exactly one wins (spec
    sections 6/38)."""
    action = _action()
    async with session_factory() as setup:
        await ActionRecordRepository(setup).create(**action_to_record_fields(action))
        await setup.commit()

    async def attempt(target_status):
        async with session_factory() as s:
            return await ActionRecordRepository(s).update_if_version_matches(action.id, expected_version=1, status=target_status)

    results = await asyncio.gather(
        attempt(PersistedActionStatus.EXECUTING), attempt(PersistedActionStatus.CANCELLED)
    )
    assert sorted(results) == [False, True]


async def test_list_by_status_filters_correctly(session):
    a1 = _action()
    a2 = _action(action_plan_id="plan-2")
    repo = ActionRecordRepository(session)
    await repo.create(**action_to_record_fields(a1))
    await repo.create(**{**action_to_record_fields(a2), "status": PersistedActionStatus.EXECUTING})
    await session.commit()

    executing = await repo.list_by_status([PersistedActionStatus.EXECUTING])
    assert {r.id for r in executing} == {a2.id}


# --- Bounded serialization (spec section 32) ----------------------------------


def test_bounded_text_passes_through_short_values():
    assert bounded_text("short") == "short"


def test_bounded_text_truncates_oversized_values_with_marker():
    long_value = "x" * 5000
    result = bounded_text(long_value, max_chars=100)
    assert len(result) <= 100
    assert result.endswith("...[truncated]")


def test_bounded_text_handles_none():
    assert bounded_text(None) is None


def test_bounded_json_passes_through_small_values():
    import json

    result = bounded_json(["a", "b"])
    assert json.loads(result) == ["a", "b"]


def test_bounded_json_marks_oversized_values_truncated():
    huge = {"data": "x" * 20000}
    result = bounded_json(huge, max_chars=100)
    assert "_truncated" in result


def test_safe_inputs_json_passes_through_normal_inputs():
    dumped = safe_inputs_json({"relative_path": "a.txt", "content": "hi"})
    assert "relative_path" in dumped


def test_safe_inputs_json_fails_closed_for_oversized_security_relevant_payload():
    oversized = {"content": "x" * (MAX_INPUTS_JSON_CHARS + 1)}
    with pytest.raises(PayloadTooLargeForPersistenceError):
        safe_inputs_json(oversized)


async def test_action_record_creation_fails_closed_for_oversized_inputs(session):
    action = _action(inputs={"relative_path": "a.txt", "content": "x" * (MAX_INPUTS_JSON_CHARS + 1)})
    with pytest.raises(PayloadTooLargeForPersistenceError):
        action_to_record_fields(action)


# --- Migration table shape -----------------------------------------------------


def test_migration_creates_all_v0135_tables(tmp_path, monkeypatch):
    import sqlite3
    from pathlib import Path as _Path

    from alembic import command
    from alembic.config import Config

    from app.config.settings import get_settings

    project_root = _Path(__file__).resolve().parents[1]
    db_path = tmp_path / "fresh_v0135.db"
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
    finally:
        con.close()

    assert {"action_records", "execution_attempts", "execution_results", "verification_results"} <= tables
    get_settings.cache_clear()


def test_v0135_migration_is_chained_from_v0134():
    """Narrower, forward-compatible regression guard than asserting the
    overall chain HEAD (which legitimately moves every time a later
    checkpoint adds a migration — see test_migrations.py's own
    test_migration_chain_has_exactly_one_head for that invariant): this
    only pins that the v0.1.3.5 revision itself is still correctly linked
    to its v0.1.3.4 parent, regardless of what has been appended since."""
    from pathlib import Path as _Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    project_root = _Path(__file__).resolve().parents[1]
    cfg = Config(str(project_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(project_root / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    revision = script.get_revision("1a868c95f4ee")
    assert revision.down_revision == "b0a3e6d998fc"
