"""Persistence bridge for ApprovalRequest (v0.1.3.4, spec sections 16-19).

Deliberately kept separate from both ends it connects:

- approval_engine.py stays exactly as persistence-agnostic as it was in
  v0.1.3.3/v0.1.3.3.1 — it operates purely on the pydantic ApprovalRequest,
  never touches a session.
- app.database.repositories stays domain-agnostic — ActionApprovalRequestRepository
  takes/returns plain ORM rows and keyword fields, never imports
  app.decision_intelligence.

This module is the only place that knows about both, translating between
the pydantic domain object and its durable row.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.database.models import ActionApprovalRequest as ActionApprovalRequestRow
from app.database.models import ActionApprovalStatus
from app.database.repositories import ActionApprovalRequestRepository
from app.decision_intelligence.schemas import ApprovalRequest, ApprovalRequestStatus


def _ensure_utc(value: datetime | None) -> datetime | None:
    """SQLite (via aiosqlite) does not natively preserve tzinfo — a
    `DateTime(timezone=True)` column can round-trip as a naive datetime
    even though every value written into it was always UTC-aware (see
    app.database.models.now_utc / every _now() in this package). Every
    approval_engine.py comparison (`now >= expires_at`, etc.) assumes
    aware datetimes throughout and raises TypeError on a naive/aware
    mismatch otherwise — this is the single place that re-attaches UTC
    rather than trusting the driver's round-trip."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _row_to_domain(row: ActionApprovalRequestRow) -> ApprovalRequest:
    return ApprovalRequest(
        id=row.id,
        action_id=row.action_id,
        requested_by=row.requested_by,
        reason=row.reason or "",
        action_summary=row.action_summary or "",
        risk_summary=row.risk_summary or "",
        permission_level=row.permission_level,
        estimated_cost=row.estimated_cost,
        proposed_inputs=json.loads(row.proposed_inputs) if row.proposed_inputs else {},
        expected_effect=row.expected_effect or "",
        action_hash=row.action_hash,
        status=ApprovalRequestStatus(row.status.value),
        requested_at=_ensure_utc(row.requested_at),
        decided_at=_ensure_utc(row.decided_at),
        decided_by=row.decided_by,
        expires_at=_ensure_utc(row.expires_at),
        consumed=row.consumed,
        consumed_at=_ensure_utc(row.consumed_at),
    )


async def persist_new_approval_request(
    repo: ActionApprovalRequestRepository, approval_request: ApprovalRequest
) -> ApprovalRequest:
    """Creates the durable row for a freshly built (PENDING) ApprovalRequest
    — i.e. the direct output of approval_engine.create_approval_request().
    Caller is responsible for session.commit()."""
    row = await repo.create(
        id=approval_request.id,
        action_id=approval_request.action_id,
        status=ActionApprovalStatus(approval_request.status.value),
        requested_by=approval_request.requested_by,
        reason=approval_request.reason,
        action_summary=approval_request.action_summary,
        risk_summary=approval_request.risk_summary,
        permission_level=approval_request.permission_level,
        estimated_cost=approval_request.estimated_cost,
        proposed_inputs=json.dumps(approval_request.proposed_inputs),
        expected_effect=approval_request.expected_effect,
        action_hash=approval_request.action_hash,
        requested_at=approval_request.requested_at,
        expires_at=approval_request.expires_at,
    )
    return _row_to_domain(row)


async def load_approval_request(
    repo: ActionApprovalRequestRepository, request_id: str
) -> ApprovalRequest | None:
    """Reads back the CURRENT durable state — this is what
    action_executor.py calls immediately before revalidating/consuming, so
    it is never fooled by a stale in-memory copy (spec section 19: "Do not
    rely on a validity result calculated earlier. Do not cache
    authorization.")."""
    row = await repo.get(request_id)
    if row is None:
        return None
    return _row_to_domain(row)


async def sync_decision(
    repo: ActionApprovalRequestRepository, approval_request: ApprovalRequest
) -> ApprovalRequest | None:
    """Persists the output of decide_approval()/expire_approval_request()
    (status/decided_at/decided_by) onto the durable row."""
    row = await repo.update_status(
        approval_request.id,
        status=ActionApprovalStatus(approval_request.status.value),
        decided_at=approval_request.decided_at,
        decided_by=approval_request.decided_by,
    )
    if row is None:
        return None
    return _row_to_domain(row)


async def consume_durable(
    repo: ActionApprovalRequestRepository,
    approval_request_id: str,
    *,
    action_id: str,
    action_hash: str,
    now: datetime,
) -> bool:
    """Thin pass-through to the repository's atomic conditional UPDATE
    (spec sections 18/19) — the actual atomicity boundary lives in
    ActionApprovalRequestRepository.consume_if_valid()."""
    return await repo.consume_if_valid(approval_request_id, action_id=action_id, action_hash=action_hash, now=now)
