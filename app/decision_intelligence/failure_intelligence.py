"""Deterministic Failure Intelligence (v0.1.3.7, spec sections 5/6/34/36).
NO LLM. Classifies a failed Action's ExecutionResult into the existing
FailureCategory taxonomy (reused verbatim from schemas.py, not duplicated —
spec section 5), and persists a durable FailureRecord distinct from
`ActionRecord.last_error` (a single mutable field that only ever holds the
MOST RECENT error) so a plan that fails and retries several times keeps a
full history, not just the last attempt.

This module never decides whether to retry/replan/stop — that is
recovery_policy.py's job. This module only answers "what happened, and
what deterministic category does it fall into?"
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from pydantic import BaseModel, Field

from app.database.models import FailureRecord as FailureRecordRow
from app.database.repositories import FailureRecordRepository
from app.decision_intelligence.schemas import (
    EXECUTOR_FAILURE_CATEGORY,
    Action,
    ExecutionResult,
    ExecutorFailureCode,
    FailureCategory,
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())


class FailureRecord(BaseModel):
    """Domain-level, pre-persistence view of one observed failure. See
    app.database.models.FailureRecord for the durable row shape this maps
    to (bridged in this module's own persistence helpers below, same
    pattern as execution_persistence.py's Action<->ActionRecord bridge)."""

    id: str = Field(default_factory=_new_id)
    action_id: str
    plan_id: str
    execution_attempt_id: str | None = None
    category: FailureCategory
    code: str | None = None
    message: str | None = None
    side_effect_occurred: bool = False
    retry_safe: bool = False
    reconciliation_required: bool = False
    retry_count_at_failure: int = 0
    created_at: datetime = Field(default_factory=_default_now)


def classify_failure(
    *,
    execution_result: ExecutionResult | None,
    fallback_category: FailureCategory = FailureCategory.UNKNOWN,
) -> FailureCategory:
    """Deterministic classification (spec section 36) — no string guessing
    when a typed code exists. Priority order:

      1. execution_result.error_code, mapped through the SAME
         EXECUTOR_FAILURE_CATEGORY table action_executor.py/
         durable_action_executor.py already use (spec section 5: "reuse
         this taxonomy") — never a second, competing mapping.
      2. execution_result.error_type, if the code above is absent/unknown.
      3. `fallback_category` (defaults to UNKNOWN — "do not pretend
         certainty", spec section 36).
    """
    if execution_result is not None and execution_result.error_code:
        try:
            code = ExecutorFailureCode(execution_result.error_code)
        except ValueError:
            code = None
        if code is not None:
            return EXECUTOR_FAILURE_CATEGORY[code]
    if execution_result is not None and execution_result.error_type is not None:
        return execution_result.error_type
    return fallback_category


def build_failure_record(
    action: Action,
    *,
    plan_id: str,
    execution_result: ExecutionResult | None,
    retry_safe: bool,
    reconciliation_required: bool = False,
    fallback_category: FailureCategory = FailureCategory.UNKNOWN,
    now: Callable[[], datetime] | None = None,
) -> FailureRecord:
    clock = now or _default_now
    category = classify_failure(execution_result=execution_result, fallback_category=fallback_category)
    return FailureRecord(
        action_id=action.id,
        plan_id=plan_id,
        execution_attempt_id=execution_result.execution_attempt_id if execution_result else None,
        category=category,
        code=execution_result.error_code if execution_result else None,
        message=(execution_result.error_message if execution_result else action.error) or None,
        side_effect_occurred=bool(execution_result.side_effect_occurred) if execution_result else False,
        retry_safe=retry_safe,
        reconciliation_required=reconciliation_required,
        retry_count_at_failure=action.retry_count,
        created_at=clock(),
    )


def failure_record_to_fields(record: FailureRecord) -> dict:
    return dict(
        id=record.id,
        action_id=record.action_id,
        plan_id=record.plan_id,
        execution_attempt_id=record.execution_attempt_id,
        category=record.category.value,
        code=record.code,
        message=record.message,
        side_effect_occurred=record.side_effect_occurred,
        retry_safe=record.retry_safe,
        reconciliation_required=record.reconciliation_required,
        retry_count_at_failure=record.retry_count_at_failure,
        created_at=record.created_at,
    )


def row_to_failure_record(row: FailureRecordRow) -> FailureRecord:
    return FailureRecord(
        id=row.id,
        action_id=row.action_id,
        plan_id=row.plan_id,
        execution_attempt_id=row.execution_attempt_id,
        category=FailureCategory(row.category),
        code=row.code,
        message=row.message,
        side_effect_occurred=row.side_effect_occurred,
        retry_safe=row.retry_safe,
        reconciliation_required=row.reconciliation_required,
        retry_count_at_failure=row.retry_count_at_failure,
        created_at=row.created_at,
    )


async def persist_failure_record(repo: FailureRecordRepository, record: FailureRecord) -> FailureRecordRow:
    return await repo.create(**failure_record_to_fields(record))
