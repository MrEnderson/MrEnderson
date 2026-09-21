"""Durable ExecutionAttempt, atomic execution claim, idempotency key
uniqueness, and lease-based stale-attempt discovery (v0.1.3.5, spec
sections 7/8/23-25/30/38)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.database.models import ExecutionAttemptStatus
from app.database.repositories import ActionRecordRepository, ExecutionAttemptRepository
from app.decision_intelligence.execution_persistence import action_to_record_fields, compute_idempotency_key
from app.decision_intelligence.schemas import Action, ActionStatus


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1", action_type="sandbox_create", tool_name="file.create_sandboxed",
        title="x", inputs={"relative_path": "a.txt", "content": "hi"}, status=ActionStatus.VALIDATED,
    )
    fields.update(overrides)
    return Action(**fields)


async def _persisted_action(session) -> tuple[Action, str]:
    action = _action()
    fields = action_to_record_fields(action)
    await ActionRecordRepository(session).create(**fields)
    await session.commit()
    return action, fields["action_hash"]


# --- Idempotency key derivation (spec section 23) -----------------------------


def test_idempotency_key_is_deterministic():
    key1 = compute_idempotency_key("action-1", "hash-abc")
    key2 = compute_idempotency_key("action-1", "hash-abc")
    assert key1 == key2


def test_idempotency_key_differs_for_different_action_id():
    assert compute_idempotency_key("action-1", "hash-abc") != compute_idempotency_key("action-2", "hash-abc")


def test_idempotency_key_differs_for_different_hash():
    assert compute_idempotency_key("action-1", "hash-abc") != compute_idempotency_key("action-1", "hash-xyz")


def test_idempotency_key_is_a_sha256_hex_digest():
    key = compute_idempotency_key("a", "b")
    assert len(key) == 64
    int(key, 16)  # must be valid hex


# --- Atomic execution claim (spec sections 8/24) ------------------------------


async def test_claim_succeeds_for_a_fresh_action(session):
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    attempt = await repo.claim(
        action_id=action.id, idempotency_key=key, tool_name="file.create_sandboxed",
        adapter_name="file.create_sandboxed", adapter_version="1.0.0", claimed_by="worker-1",
        now=datetime.now(timezone.utc),
    )
    assert attempt is not None
    assert attempt.status == ExecutionAttemptStatus.CREATED
    assert attempt.idempotency_key == key


async def test_claim_creates_attempt_before_any_adapter_call_conceptually(session):
    # Section 8: attempt identity must be persisted BEFORE adapter
    # execution begins. This test proves the claim alone (no execute())
    # already produces a durable, retrievable row.
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    attempt = await repo.claim(
        action_id=action.id, idempotency_key=key, tool_name="file.create_sandboxed",
        adapter_name="file.create_sandboxed", adapter_version=None, claimed_by="worker-1", now=datetime.now(timezone.utc),
    )
    fetched = await repo.get(attempt.id)
    assert fetched is not None


async def test_second_claim_for_same_idempotency_key_fails(session):
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    now = datetime.now(timezone.utc)
    first = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w1", now=now)
    second = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w2", now=now)
    assert first is not None
    assert second is None


async def test_get_by_idempotency_key_finds_the_claimed_attempt(session):
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    claimed = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w1", now=datetime.now(timezone.utc))
    found = await repo.get_by_idempotency_key(key)
    assert found is not None
    assert found.id == claimed.id


async def test_get_by_idempotency_key_returns_none_when_unclaimed(session):
    repo = ExecutionAttemptRepository(session)
    assert await repo.get_by_idempotency_key("nonexistent-key") is None


# --- Concurrent claims (spec sections 24/38) -----------------------------------


async def test_two_concurrent_claims_exactly_one_succeeds(session_factory):
    async with session_factory() as setup:
        action, action_hash = await _persisted_action(setup)

    key = compute_idempotency_key(action.id, action_hash)
    now = datetime.now(timezone.utc)

    async def attempt(worker):
        async with session_factory() as s:
            return await ExecutionAttemptRepository(s).claim(
                action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a",
                adapter_version=None, claimed_by=worker, now=now,
            )

    results = await asyncio.gather(attempt("worker-a"), attempt("worker-b"))
    outcomes = [r is not None for r in results]
    assert sorted(outcomes) == [False, True]

    async with session_factory() as check:
        rows = await ExecutionAttemptRepository(check).list_for_action(action.id)
        assert len(rows) == 1  # only ONE attempt row ever exists for this key


# --- Attempt field updates ------------------------------------------------------


async def test_update_fields_persists_status_and_result_metadata(session):
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    attempt = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w1", now=datetime.now(timezone.utc))

    updated = await repo.update_fields(
        attempt.id, status=ExecutionAttemptStatus.EXECUTION_SUCCEEDED, side_effect_occurred=True, side_effect_fingerprint="abc123"
    )
    assert updated.status == ExecutionAttemptStatus.EXECUTION_SUCCEEDED
    assert updated.side_effect_occurred is True
    assert updated.side_effect_fingerprint == "abc123"


async def test_update_fields_unknown_id_returns_none(session):
    repo = ExecutionAttemptRepository(session)
    assert await repo.update_fields("nonexistent", status=ExecutionAttemptStatus.STARTED) is None


async def test_list_for_action_returns_only_that_actions_attempts(session):
    a1 = _action()
    a2 = _action(action_plan_id="plan-2")
    action_repo = ActionRecordRepository(session)
    await action_repo.create(**action_to_record_fields(a1))
    await action_repo.create(**action_to_record_fields(a2))
    await session.commit()

    attempt_repo = ExecutionAttemptRepository(session)
    now = datetime.now(timezone.utc)
    await attempt_repo.claim(action_id=a1.id, idempotency_key=compute_idempotency_key(a1.id, "h1"), tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w", now=now)
    await attempt_repo.claim(action_id=a2.id, idempotency_key=compute_idempotency_key(a2.id, "h2"), tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w", now=now)

    a1_attempts = await attempt_repo.list_for_action(a1.id)
    assert len(a1_attempts) == 1
    assert a1_attempts[0].action_id == a1.id


# --- Execution lease (spec section 25) ------------------------------------------


async def test_stale_started_attempt_is_discoverable(session):
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    now = datetime.now(timezone.utc)
    attempt = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w1", now=now)
    past_lease = now - timedelta(minutes=1)
    await repo.update_fields(attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now - timedelta(minutes=30), lease_expires_at=past_lease)

    stale = await repo.list_stale_started(before=now)
    assert any(a.id == attempt.id for a in stale)


async def test_fresh_started_attempt_is_not_stale(session):
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    now = datetime.now(timezone.utc)
    attempt = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w1", now=now)
    future_lease = now + timedelta(minutes=10)
    await repo.update_fields(attempt.id, status=ExecutionAttemptStatus.STARTED, started_at=now, lease_expires_at=future_lease)

    stale = await repo.list_stale_started(before=now)
    assert not any(a.id == attempt.id for a in stale)


async def test_non_started_attempt_never_counted_as_stale(session):
    action, action_hash = await _persisted_action(session)
    repo = ExecutionAttemptRepository(session)
    key = compute_idempotency_key(action.id, action_hash)
    now = datetime.now(timezone.utc)
    attempt = await repo.claim(action_id=action.id, idempotency_key=key, tool_name="t", adapter_name="a", adapter_version=None, claimed_by="w1", now=now)
    # CREATED, not STARTED, with an expired lease field set defensively
    await repo.update_fields(attempt.id, lease_expires_at=now - timedelta(minutes=1))

    stale = await repo.list_stale_started(before=now)
    assert not any(a.id == attempt.id for a in stale)
