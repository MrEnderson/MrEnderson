"""Canonical audit event type constants and a thin recording helper."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import AuditRepository


class AuditEventType:
    OBJECTIVE_CREATED = "OBJECTIVE_CREATED"
    PLAN_CREATED = "PLAN_CREATED"
    TASK_CREATED = "TASK_CREATED"
    TASK_STARTED = "TASK_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"
    TASK_CANCELLED = "TASK_CANCELLED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    TOOL_CALLED = "TOOL_CALLED"
    MEMORY_CREATED = "MEMORY_CREATED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    REPORT_GENERATED = "REPORT_GENERATED"
    EVIDENCE_STORED = "EVIDENCE_STORED"
    BUDGET_LIMIT_REACHED = "BUDGET_LIMIT_REACHED"
    # v0.1.3.4 — Action Executor. Recorded only when a workspace_id/session
    # is supplied to action_executor.execute_action(); Action/ApprovalRequest
    # are workspace-agnostic domain objects, so a caller with no natural
    # workspace to attribute the event to simply gets no audit trail for
    # that run (documented limitation, not a silent failure).
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFICATION_STARTED = "VERIFICATION_STARTED"
    VERIFICATION_SUCCEEDED = "VERIFICATION_SUCCEEDED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    APPROVAL_CONSUMED = "APPROVAL_CONSUMED"
    # v0.1.3.5 — durable execution + reconciliation. Same best-effort,
    # workspace-gated wiring as the v0.1.3.4 events above.
    EXECUTION_ATTEMPT_CREATED = "EXECUTION_ATTEMPT_CREATED"
    EXECUTION_CLAIMED = "EXECUTION_CLAIMED"
    EXECUTION_INTERRUPTED = "EXECUTION_INTERRUPTED"
    RECONCILIATION_STARTED = "RECONCILIATION_STARTED"
    RECONCILIATION_CLASSIFIED = "RECONCILIATION_CLASSIFIED"
    RECONCILIATION_RECOVERED = "RECONCILIATION_RECOVERED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"
    DUPLICATE_EXECUTION_BLOCKED = "DUPLICATE_EXECUTION_BLOCKED"
    # v0.1.3.6 — durable ActionPlan orchestration. Same best-effort,
    # workspace-gated wiring as the v0.1.3.4/.5 events above.
    ACTION_PLAN_CREATED = "ACTION_PLAN_CREATED"
    ACTION_PLAN_VALIDATED = "ACTION_PLAN_VALIDATED"
    ACTION_PLAN_READY = "ACTION_PLAN_READY"
    ACTION_PLAN_CLAIMED = "ACTION_PLAN_CLAIMED"
    ACTION_PLAN_STARTED = "ACTION_PLAN_STARTED"
    ACTION_PLAN_ACTION_READY = "ACTION_PLAN_ACTION_READY"
    ACTION_PLAN_ACTION_DISPATCHED = "ACTION_PLAN_ACTION_DISPATCHED"
    ACTION_PLAN_ACTION_COMPLETED = "ACTION_PLAN_ACTION_COMPLETED"
    ACTION_PLAN_WAITING_FOR_APPROVAL = "ACTION_PLAN_WAITING_FOR_APPROVAL"
    ACTION_PLAN_RESUMED = "ACTION_PLAN_RESUMED"
    ACTION_PLAN_PARTIALLY_COMPLETED = "ACTION_PLAN_PARTIALLY_COMPLETED"
    ACTION_PLAN_COMPLETED = "ACTION_PLAN_COMPLETED"
    ACTION_PLAN_FAILED = "ACTION_PLAN_FAILED"
    ACTION_PLAN_CANCELLED = "ACTION_PLAN_CANCELLED"
    ACTION_PLAN_RECONCILIATION_STARTED = "ACTION_PLAN_RECONCILIATION_STARTED"
    ACTION_PLAN_RECONCILIATION_COMPLETED = "ACTION_PLAN_RECONCILIATION_COMPLETED"
    ACTION_PLAN_RECONCILIATION_BLOCKED = "ACTION_PLAN_RECONCILIATION_BLOCKED"
    ACTION_PLAN_DUPLICATE_CLAIM_BLOCKED = "ACTION_PLAN_DUPLICATE_CLAIM_BLOCKED"
    ACTION_PLAN_STALE_LEASE_DETECTED = "ACTION_PLAN_STALE_LEASE_DETECTED"
    # v0.1.3.7 — failure intelligence, bounded retry, replan, budgets. Same
    # best-effort, workspace-gated wiring as every event above; audit never
    # grants authority and audit failure never changes a security decision.
    ACTION_FAILURE_CLASSIFIED = "ACTION_FAILURE_CLASSIFIED"
    RECOVERY_DECISION_CREATED = "RECOVERY_DECISION_CREATED"
    ACTION_RETRY_AUTHORIZED = "ACTION_RETRY_AUTHORIZED"
    ACTION_RETRY_EXHAUSTED = "ACTION_RETRY_EXHAUSTED"
    REPLAN_PROPOSED = "REPLAN_PROPOSED"
    REPLAN_APPLIED = "REPLAN_APPLIED"
    REPLAN_REJECTED = "REPLAN_REJECTED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    SECURITY_RECOVERY_BLOCKED = "SECURITY_RECOVERY_BLOCKED"


async def record_event(
    session: AsyncSession,
    *,
    workspace_id: str,
    actor_type: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    actor_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    repo = AuditRepository(session)
    await repo.record(
        workspace_id=workspace_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=metadata,
    )
