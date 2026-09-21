"""Deterministic Budget Enforcement for failure recovery (v0.1.3.7, spec
sections 23-33) — app.decision_intelligence.budget. Distinct module from
app.orchestration.budget (the pre-existing mission-level API-call budget;
see tests/test_budget.py), which this checkpoint does not touch."""
from __future__ import annotations

import asyncio

from app.database.models import BudgetAccountStatus, BudgetScope, BudgetType
from app.database.repositories import BudgetAccountRepository, BudgetEventRepository
from app.decision_intelligence.budget import ensure_account, get_remaining, reserve_and_consume


class TestUnconfiguredBudgetIsUnlimited:
    async def test_no_account_means_unlimited_and_creates_no_row(self, session):
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        result = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.MODEL_CALLS,
            amount=5, idempotency_key="k1",
        )
        assert result.granted is True
        assert result.limit == float("inf")
        assert await account_repo.get_by_scope(scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.MODEL_CALLS) is None

    async def test_get_remaining_none_for_unconfigured_scope(self, session):
        account_repo = BudgetAccountRepository(session)
        assert await get_remaining(account_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.MODEL_CALLS) is None


class TestEnsureAccountNeverRaisesLimit:
    async def test_ensure_creates_once(self, session):
        account_repo = BudgetAccountRepository(session)
        account = await ensure_account(account_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES, limit_value=3.0)
        assert account.limit_value == 3.0
        assert account.consumed_value == 0.0
        assert account.status == BudgetAccountStatus.ACTIVE

    async def test_ensure_does_not_change_existing_limit(self, session):
        account_repo = BudgetAccountRepository(session)
        first = await ensure_account(account_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES, limit_value=3.0)
        second = await ensure_account(account_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES, limit_value=999.0)
        assert second.id == first.id
        assert second.limit_value == 3.0  # unchanged — Jarvis cannot raise its own budget (spec section 30)


class TestReserveAndConsume:
    async def test_consumes_up_to_limit(self, session):
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        for i in range(3):
            result = await reserve_and_consume(
                account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES,
                amount=1, idempotency_key=f"attempt-{i}", default_limit=3.0,
            )
            assert result.granted is True
        exhausted = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES,
            amount=1, idempotency_key="attempt-3", default_limit=3.0,
        )
        assert exhausted.granted is False
        assert exhausted.status == BudgetAccountStatus.EXHAUSTED
        assert exhausted.remaining == 0.0

    async def test_exceeding_amount_in_one_call_is_denied(self, session):
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        result = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.ESTIMATED_COST,
            amount=10.0, idempotency_key="k1", default_limit=5.0,
        )
        assert result.granted is False
        assert result.remaining == 5.0  # nothing was consumed

    async def test_idempotency_key_replay_never_double_consumes(self, session):
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        first = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.ACTION, scope_id="a1", budget_type=BudgetType.ACTION_ATTEMPTS,
            amount=1, idempotency_key="same-key", default_limit=2.0,
        )
        second = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.ACTION, scope_id="a1", budget_type=BudgetType.ACTION_ATTEMPTS,
            amount=1, idempotency_key="same-key", default_limit=2.0,
        )
        assert first.granted is True and second.granted is True
        assert second.replayed is True
        account = await account_repo.get_by_scope(scope_type=BudgetScope.ACTION, scope_id="a1", budget_type=BudgetType.ACTION_ATTEMPTS)
        assert account.consumed_value == 1.0  # NOT 2.0

    async def test_replayed_denial_is_also_idempotent(self, session):
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        common = dict(scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.REPLANS, amount=5, idempotency_key="deny-key", default_limit=1.0)
        first = await reserve_and_consume(account_repo, event_repo, **common)
        assert first.granted is False
        second = await reserve_and_consume(account_repo, event_repo, **common)
        assert second.granted is False
        assert second.replayed is True

    async def test_restart_persistence_no_reset(self, session):
        """Simulates a restart: a fresh set of repository instances over
        the SAME session/db must see the durable consumed value unchanged
        (spec sections 43/54)."""
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES,
            amount=1, idempotency_key="k1", default_limit=3.0,
        )
        fresh_account_repo = BudgetAccountRepository(session)
        remaining = await get_remaining(fresh_account_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES)
        assert remaining == 2.0

    async def test_different_budget_types_are_independent(self, session):
        account_repo = BudgetAccountRepository(session)
        event_repo = BudgetEventRepository(session)
        await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.RETRIES,
            amount=1, idempotency_key="retries-1", default_limit=1.0,
        )
        result = await reserve_and_consume(
            account_repo, event_repo, scope_type=BudgetScope.PLAN, scope_id="p1", budget_type=BudgetType.REPLANS,
            amount=1, idempotency_key="replans-1", default_limit=1.0,
        )
        assert result.granted is True  # RETRIES exhaustion does not affect REPLANS


class TestBudgetConcurrency:
    async def test_two_concurrent_consumers_of_the_last_unit_one_wins_one_exhausted(self, session_factory):
        """spec section 53: never both succeed, never remaining goes negative."""
        async with session_factory() as setup_session:
            await ensure_account(
                BudgetAccountRepository(setup_session), scope_type=BudgetScope.PLAN, scope_id="race-plan",
                budget_type=BudgetType.RETRIES, limit_value=1.0,
            )

        async def _attempt(key: str):
            async with session_factory() as s:
                return await reserve_and_consume(
                    BudgetAccountRepository(s), BudgetEventRepository(s), scope_type=BudgetScope.PLAN,
                    scope_id="race-plan", budget_type=BudgetType.RETRIES, amount=1, idempotency_key=key,
                )

        results = await asyncio.gather(_attempt("worker-a"), _attempt("worker-b"))
        granted = [r for r in results if r.granted]
        denied = [r for r in results if not r.granted]
        assert len(granted) == 1
        assert len(denied) == 1
        assert denied[0].remaining == 0.0

        async with session_factory() as check_session:
            final = await BudgetAccountRepository(check_session).get_by_scope(
                scope_type=BudgetScope.PLAN, scope_id="race-plan", budget_type=BudgetType.RETRIES
            )
            assert final.consumed_value == 1.0  # never -1, never 2
