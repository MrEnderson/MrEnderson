"""Durable ApprovalRequest persistence + atomic approval consumption
(v0.1.3.4, spec sections 16-19/26/31/34). Every test uses the isolated
temp-file SQLite database from conftest.py's `session`/`session_factory`
fixtures — never the developer's real jarvis.db."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.database.models import ActionApprovalRequest as ActionApprovalRequestRow
from app.database.models import ActionApprovalStatus
from app.database.repositories import ActionApprovalRequestRepository
from app.decision_intelligence.approval_engine import ApprovalRequestStatus
from app.decision_intelligence.approval_persistence import (
    consume_durable,
    load_approval_request,
    persist_new_approval_request,
    sync_decision,
)
from app.decision_intelligence.schemas import ApprovalRequest
from app.database.models import PermissionLevel


def _domain_request(**overrides) -> ApprovalRequest:
    fields = dict(
        action_id="action-1",
        requested_by="planner-agent",
        permission_level=PermissionLevel.EXTERNAL_ACTION,
        action_hash="a" * 64,
        proposed_inputs={"to": "vendor@example.com"},
        expected_effect="sends an email",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    fields.update(overrides)
    return ApprovalRequest(**fields)


# --- Reconciliation: persisted enum matches domain enum -----------------------


def test_action_approval_status_matches_approval_request_status_values():
    assert {m.value for m in ActionApprovalStatus} == {m.value for m in ApprovalRequestStatus}


# --- Repository CRUD -----------------------------------------------------------


async def test_repository_create_and_get_round_trip(session):
    repo = ActionApprovalRequestRepository(session)
    row = await repo.create(
        action_id="action-1",
        status=ActionApprovalStatus.PENDING,
        requested_by="planner-agent",
        permission_level=PermissionLevel.EXTERNAL_ACTION,
        action_hash="a" * 64,
        requested_at=datetime.now(timezone.utc),
    )
    await session.commit()
    fetched = await repo.get(row.id)
    assert fetched is not None
    assert fetched.action_id == "action-1"
    assert fetched.status == ActionApprovalStatus.PENDING


async def test_repository_get_unknown_returns_none(session):
    repo = ActionApprovalRequestRepository(session)
    assert await repo.get("nonexistent-id") is None


async def test_repository_update_status_persists(session):
    repo = ActionApprovalRequestRepository(session)
    row = await repo.create(
        action_id="action-1", status=ActionApprovalStatus.PENDING, requested_by="planner-agent",
        permission_level=PermissionLevel.EXTERNAL_ACTION, action_hash="a" * 64,
        requested_at=datetime.now(timezone.utc),
    )
    await session.commit()
    now = datetime.now(timezone.utc)
    updated = await repo.update_status(row.id, status=ActionApprovalStatus.APPROVED, decided_at=now, decided_by="human:alice")
    await session.commit()
    assert updated.status == ActionApprovalStatus.APPROVED
    assert updated.decided_by == "human:alice"


async def test_repository_update_status_unknown_returns_none(session):
    repo = ActionApprovalRequestRepository(session)
    result = await repo.update_status("nonexistent", status=ActionApprovalStatus.APPROVED, decided_at=None, decided_by="x")
    assert result is None


# --- approval_persistence.py round trip (spec section 19: no cached auth) ----


async def test_persist_and_load_round_trips_domain_object(session):
    repo = ActionApprovalRequestRepository(session)
    original = _domain_request()
    persisted = await persist_new_approval_request(repo, original)
    await session.commit()

    loaded = await load_approval_request(repo, persisted.id)
    assert loaded is not None
    assert loaded.id == original.id
    assert loaded.action_id == original.action_id
    assert loaded.action_hash == original.action_hash
    assert loaded.proposed_inputs == original.proposed_inputs
    assert loaded.status == ApprovalRequestStatus.PENDING


async def test_load_approval_request_returns_none_for_unknown_id(session):
    repo = ActionApprovalRequestRepository(session)
    assert await load_approval_request(repo, "nonexistent") is None


async def test_loaded_datetimes_are_timezone_aware(session):
    # Regression test for the naive/aware SQLite round-trip bug found while
    # smoke-testing this checkpoint: every datetime on a loaded
    # ApprovalRequest must be comparable against datetime.now(timezone.utc)
    # without raising TypeError.
    repo = ActionApprovalRequestRepository(session)
    persisted = await persist_new_approval_request(repo, _domain_request())
    await session.commit()
    loaded = await load_approval_request(repo, persisted.id)
    assert loaded.requested_at.tzinfo is not None
    assert loaded.expires_at.tzinfo is not None
    # Must not raise:
    assert (datetime.now(timezone.utc) >= loaded.expires_at) in (True, False)


async def test_sync_decision_persists_approval(session):
    repo = ActionApprovalRequestRepository(session)
    persisted = await persist_new_approval_request(repo, _domain_request())
    await session.commit()

    decided = persisted.model_copy(
        update={
            "status": ApprovalRequestStatus.APPROVED,
            "decided_at": datetime.now(timezone.utc),
            "decided_by": "human:alice",
        }
    )
    synced = await sync_decision(repo, decided)
    await session.commit()
    assert synced.status == ApprovalRequestStatus.APPROVED

    reloaded = await load_approval_request(repo, persisted.id)
    assert reloaded.status == ApprovalRequestStatus.APPROVED
    assert reloaded.decided_by == "human:alice"


async def test_sync_decision_unknown_id_returns_none(session):
    repo = ActionApprovalRequestRepository(session)
    fake = _domain_request(id="does-not-exist")
    result = await sync_decision(repo, fake)
    assert result is None


# --- Atomic consumption: consume_if_valid() (spec sections 18/19) ------------


async def _approved_persisted(session, **overrides) -> tuple[ActionApprovalRequestRepository, ApprovalRequest]:
    repo = ActionApprovalRequestRepository(session)
    request = _domain_request(**overrides)
    persisted = await persist_new_approval_request(repo, request)
    await session.commit()
    approved = persisted.model_copy(
        update={"status": ApprovalRequestStatus.APPROVED, "decided_at": datetime.now(timezone.utc), "decided_by": "human:alice"}
    )
    await sync_decision(repo, approved)
    await session.commit()
    return repo, approved


async def test_consume_if_valid_succeeds_for_fresh_approved_request(session):
    repo, approved = await _approved_persisted(session)
    ok = await consume_durable(
        repo, approved.id, action_id=approved.action_id, action_hash=approved.action_hash, now=datetime.now(timezone.utc)
    )
    assert ok is True
    row = await repo.get(approved.id)
    assert row.consumed is True
    assert row.consumed_at is not None


async def test_consume_if_valid_fails_second_time(session):
    repo, approved = await _approved_persisted(session)
    now = datetime.now(timezone.utc)
    first = await consume_durable(repo, approved.id, action_id=approved.action_id, action_hash=approved.action_hash, now=now)
    second = await consume_durable(repo, approved.id, action_id=approved.action_id, action_hash=approved.action_hash, now=now)
    assert first is True
    assert second is False


async def test_consume_if_valid_fails_for_wrong_action_id(session):
    repo, approved = await _approved_persisted(session)
    ok = await consume_durable(repo, approved.id, action_id="some-other-action", action_hash=approved.action_hash, now=datetime.now(timezone.utc))
    assert ok is False
    row = await repo.get(approved.id)
    assert row.consumed is False


async def test_consume_if_valid_fails_for_wrong_hash(session):
    repo, approved = await _approved_persisted(session)
    ok = await consume_durable(repo, approved.id, action_id=approved.action_id, action_hash="b" * 64, now=datetime.now(timezone.utc))
    assert ok is False


async def test_consume_if_valid_fails_for_expired_request(session):
    repo, approved = await _approved_persisted(session, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    ok = await consume_durable(repo, approved.id, action_id=approved.action_id, action_hash=approved.action_hash, now=datetime.now(timezone.utc))
    assert ok is False


async def test_consume_if_valid_fails_for_pending_status(session):
    repo = ActionApprovalRequestRepository(session)
    request = _domain_request()
    persisted = await persist_new_approval_request(repo, request)
    await session.commit()  # still PENDING, never approved
    ok = await consume_durable(repo, persisted.id, action_id=persisted.action_id, action_hash=persisted.action_hash, now=datetime.now(timezone.utc))
    assert ok is False


async def test_consume_if_valid_fails_for_rejected_status(session):
    repo = ActionApprovalRequestRepository(session)
    persisted = await persist_new_approval_request(repo, _domain_request())
    await session.commit()
    rejected = persisted.model_copy(update={"status": ApprovalRequestStatus.REJECTED, "decided_at": datetime.now(timezone.utc), "decided_by": "human:alice"})
    await sync_decision(repo, rejected)
    await session.commit()
    ok = await consume_durable(repo, persisted.id, action_id=persisted.action_id, action_hash=persisted.action_hash, now=datetime.now(timezone.utc))
    assert ok is False


async def test_consume_if_valid_unknown_id_fails(session):
    repo = ActionApprovalRequestRepository(session)
    ok = await consume_durable(repo, "nonexistent", action_id="a1", action_hash="a" * 64, now=datetime.now(timezone.utc))
    assert ok is False


# --- Concurrency: exactly one caller may consume the same approval ----------


async def test_two_sequential_consume_attempts_exactly_one_succeeds(session):
    repo, approved = await _approved_persisted(session)
    now = datetime.now(timezone.utc)
    results = [
        await consume_durable(repo, approved.id, action_id=approved.action_id, action_hash=approved.action_hash, now=now)
        for _ in range(2)
    ]
    assert sorted(results) == [False, True]


async def test_concurrent_consume_attempts_via_two_independent_sessions(session_factory):
    """A more faithful concurrency test: two independent AsyncSessions
    (separate connections) racing to consume the SAME durable row via
    asyncio.gather. Exactly one must win (spec section 31)."""
    async with session_factory() as setup_session:
        repo = ActionApprovalRequestRepository(setup_session)
        persisted = await persist_new_approval_request(repo, _domain_request())
        await setup_session.commit()
        approved = persisted.model_copy(
            update={"status": ApprovalRequestStatus.APPROVED, "decided_at": datetime.now(timezone.utc), "decided_by": "human:alice"}
        )
        await sync_decision(repo, approved)
        await setup_session.commit()

    now = datetime.now(timezone.utc)

    async def attempt():
        async with session_factory() as s:
            r = ActionApprovalRequestRepository(s)
            return await consume_durable(r, approved.id, action_id=approved.action_id, action_hash=approved.action_hash, now=now)

    results = await asyncio.gather(attempt(), attempt())
    assert sorted(results) == [False, True]

    async with session_factory() as check_session:
        row = await ActionApprovalRequestRepository(check_session).get(approved.id)
        assert row.consumed is True


# --- Migration table shape (spec sections 16/17) ------------------------------


def test_migration_creates_action_approval_requests_table(tmp_path, monkeypatch):
    import sqlite3

    from alembic import command
    from alembic.config import Config
    from pathlib import Path as _Path

    from app.config.settings import get_settings

    project_root = _Path(__file__).resolve().parents[1]
    db_path = tmp_path / "fresh_action_approvals.db"
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
        assert "action_approval_requests" in tables
        cols = {r[1] for r in con.execute("PRAGMA table_info(action_approval_requests)")}
    finally:
        con.close()

    expected_cols = {
        "id", "action_id", "status", "requested_by", "reason", "action_summary",
        "risk_summary", "permission_level", "estimated_cost", "proposed_inputs",
        "expected_effect", "action_hash", "requested_at", "decided_at", "decided_by",
        "expires_at", "consumed", "consumed_at",
    }
    assert expected_cols <= cols
    get_settings.cache_clear()
