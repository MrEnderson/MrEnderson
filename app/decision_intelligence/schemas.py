"""Domain contracts for Decision & Action Intelligence (v0.1.3.1).

All models here are plain Pydantic domain objects, deliberately NOT
SQLAlchemy-backed yet — see docs/decision_intelligence.md, "Persistence",
for why. They follow the same conventions as app/schemas/evidence.py's
EvidenceItem/EvidenceGap (which also started as pydantic-only domain
objects before the `evidence` table existed): a `str` uuid4 `id` via
`default_factory`, timezone-aware UTC timestamps via `default_factory`,
and reuse of existing enums (`RiskLevel`, `PermissionLevel`) rather than
duplicating them.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.database.models import PermissionLevel, RiskLevel


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Status enums
# --------------------------------------------------------------------------


class DecisionStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    READY_FOR_ACTION = "READY_FOR_ACTION"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class ActionPlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    EXECUTING = "EXECUTING"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ActionStatus(str, enum.Enum):
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    PERMISSION_CHECKED = "PERMISSION_CHECKED"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    BLOCKED = "BLOCKED"


class ApprovalRequestStatus(str, enum.Enum):
    """Distinct from app.database.models.ApprovalStatus (PENDING/APPROVED/
    REJECTED only), which is Task-scoped and already persisted. This
    contract is Action-scoped and needs EXPIRED/CANCELLED as well (an
    approval request can go stale, or its action can be cancelled out from
    under it, independent of a human ever deciding it) — a genuinely
    different lifecycle, not a duplicate of the existing one."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class FailureCategory(str, enum.Enum):
    TRANSIENT = "TRANSIENT"
    VALIDATION = "VALIDATION"
    PERMISSION = "PERMISSION"
    APPROVAL = "APPROVAL"
    TOOL = "TOOL"
    VERIFICATION = "VERIFICATION"
    BUDGET = "BUDGET"
    SECURITY = "SECURITY"
    UNKNOWN = "UNKNOWN"


class ExecutorFailureCode(str, enum.Enum):
    """Finer-grained ActionExecutor failure classification (v0.1.3.4, spec
    section 22) than FailureCategory alone can express. Every
    ExecutionResult.error_code is one of these; ExecutionResult.error_type
    is always the corresponding, coarser, REUSED FailureCategory below —
    see EXECUTOR_FAILURE_CATEGORY. No LLM ever classifies a failure; every
    code here is assigned by deterministic code in action_executor.py /
    tool_adapters.py."""

    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    APPROVAL_FAILURE = "APPROVAL_FAILURE"
    ADAPTER_NOT_FOUND = "ADAPTER_NOT_FOUND"
    SANDBOX_VIOLATION = "SANDBOX_VIOLATION"
    TOOL_EXECUTION_FAILURE = "TOOL_EXECUTION_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    INTERNAL_FAILURE = "INTERNAL_FAILURE"


# The single authoritative mapping from the fine-grained ExecutorFailureCode
# to the reused, coarser FailureCategory (spec section 22: "Reuse existing
# FailureCategory where semantically appropriate"). SANDBOX_VIOLATION maps
# to SECURITY (never auto-retryable — see retry_policy.py) rather than TOOL,
# since a path-escape/traversal attempt is a security boundary violation,
# not an ordinary tool failure.
EXECUTOR_FAILURE_CATEGORY: dict[ExecutorFailureCode, FailureCategory] = {
    ExecutorFailureCode.VALIDATION_FAILURE: FailureCategory.VALIDATION,
    ExecutorFailureCode.PERMISSION_FAILURE: FailureCategory.PERMISSION,
    ExecutorFailureCode.APPROVAL_FAILURE: FailureCategory.APPROVAL,
    ExecutorFailureCode.ADAPTER_NOT_FOUND: FailureCategory.TOOL,
    ExecutorFailureCode.SANDBOX_VIOLATION: FailureCategory.SECURITY,
    ExecutorFailureCode.TOOL_EXECUTION_FAILURE: FailureCategory.TOOL,
    ExecutorFailureCode.VERIFICATION_FAILURE: FailureCategory.VERIFICATION,
    ExecutorFailureCode.INTERNAL_FAILURE: FailureCategory.UNKNOWN,
}


# --------------------------------------------------------------------------
# Domain models
# --------------------------------------------------------------------------


class Decision(BaseModel):
    """A single, evaluable decision reached from research evidence.

    `actionable` and `status` are both writable fields (an LLM-driven
    decision-writer agent, once built, will set them), but neither is
    trusted at face value — see
    decision_rules.py::compute_actionable/enforce_actionable_flag and
    assert_transition, which are the only deterministic sources of truth
    for whether a Decision may actually be treated as ready to act on.
    """

    id: str = Field(default_factory=_new_id)
    project_id: str
    title: str
    statement: str
    status: DecisionStatus = DecisionStatus.PROPOSED
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    alternatives_considered: list[str] = Field(default_factory=list)
    rationale: str = ""
    # Whether the evidence behind this decision passed the v0.1.2 Research
    # Intelligence comparison-readiness gate (or an equivalent deterministic
    # check) — see app/research_intelligence/gate.py::evaluate_comparison_readiness.
    comparison_ready: bool = False
    # Raw, possibly LLM-set claim of actionability. NEVER read directly by
    # anything that gates real work — always go through
    # decision_rules.compute_actionable(decision) instead.
    actionable: bool = False
    recommended_next_step: str | None = None
    created_by: str = "system"
    created_at: datetime = Field(default_factory=_now)


class Action(BaseModel):
    """One concrete, individually verifiable step within an ActionPlan.
    Never executed by anything in this checkpoint — see
    action_state_machine.py for the lifecycle it is restricted to."""

    id: str = Field(default_factory=_new_id)
    action_plan_id: str
    sequence: int = 0
    action_type: str
    title: str
    description: str = ""
    agent_type: str = "execution"
    tool_name: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    permission_level: PermissionLevel = PermissionLevel.WRITE
    approval_required: bool = False
    approval_id: str | None = None
    estimated_cost: float | None = None
    # IDs of other Actions in the same ActionPlan that must complete first.
    dependencies: list[str] = Field(default_factory=list)
    expected_result: str = ""
    success_criteria: str = ""
    verification_method: str = ""
    status: ActionStatus = ActionStatus.PLANNED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 0
    # v0.1.3.7: set when a ReplanProposal replaces this (terminally FAILED)
    # Action with a new one — the id of the replacement, never the reverse.
    # This Action's own status/history is never erased or overwritten (spec
    # section 21) — see replan.py.
    superseded_by: str | None = None


class ActionPlan(BaseModel):
    """A structured, ordered set of Actions intended to realize one Decision.
    Never auto-promoted to READY — see plan_validation.py::evaluate_plan_readiness."""

    id: str = Field(default_factory=_new_id)
    decision_id: str
    project_id: str | None = None
    title: str
    description: str = ""
    actions: list[Action] = Field(default_factory=list)
    estimated_cost: float | None = None
    estimated_model_calls: int | None = None
    success_criteria: str = ""
    failure_policy: str = ""
    status: ActionPlanStatus = ActionPlanStatus.DRAFT
    created_by: str = "system"
    created_at: datetime = Field(default_factory=_now)
    # v0.1.3.7: a durable structural version, incremented by exactly one
    # each time an applied ReplanProposal rewrites the plan's Action
    # membership/dependency graph (spec sections 19/20). Never incremented
    # by ordinary execution progress (status changes, permission/approval
    # evaluation) — only by an authorized structural mutation.
    revision: int = 1


class ApprovalRequest(BaseModel):
    """The contract a future Approval Engine will persist/serve. Binds to
    the EXACT action payload it approved via `action_hash` — see
    action_hash.py::compute_action_hash. Not interactively handled yet."""

    id: str = Field(default_factory=_new_id)
    action_id: str
    requested_by: str = "system"
    reason: str = ""
    action_summary: str = ""
    risk_summary: str = ""
    permission_level: PermissionLevel
    estimated_cost: float | None = None
    proposed_inputs: dict[str, Any] = Field(default_factory=dict)
    expected_effect: str = ""
    action_hash: str
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING
    requested_at: datetime = Field(default_factory=_now)
    decided_at: datetime | None = None
    decided_by: str | None = None
    # v0.1.3.2: bounded expiration (see approval_engine.py) — None means no
    # deterministic auto-expiration policy applies to this request (the
    # engine's own create_approval_request() factory always sets a bounded
    # default rather than leaving this None, so a blanket unbounded approval
    # is never created through the normal path).
    expires_at: datetime | None = None
    # v0.1.3.2: distinguishes APPROVED-but-unused from APPROVED-and-consumed
    # (spec section 12/13) — set only via approval_engine.py::consume_approval,
    # never by execution itself (no execution exists yet).
    consumed: bool = False
    consumed_at: datetime | None = None


class ExecutionResult(BaseModel):
    """What a tool execution adapter reports. As of v0.1.3.4, exactly ONE
    real adapter exists (file.create_sandboxed — see
    app/decision_intelligence/tool_adapters.py); every other tool remains
    a non-executing definition."""

    action_id: str
    tool_name: str | None = None
    started_at: datetime
    completed_at: datetime
    success: bool
    provider_status: str | None = None
    output: dict[str, Any] | None = None
    side_effects: list[str] = Field(default_factory=list)
    cost: float | None = None
    error_type: FailureCategory | None = None
    error_message: str | None = None
    # v0.1.3.4 additions — additive/backward-compatible, all optional.
    execution_attempt_id: str | None = None
    # Finer-grained failure classification than error_type/FailureCategory
    # (spec section 22) — one of ActionExecutor's ExecutorFailureCode
    # values (VALIDATION_FAILURE/PERMISSION_FAILURE/APPROVAL_FAILURE/
    # ADAPTER_NOT_FOUND/SANDBOX_VIOLATION/TOOL_EXECUTION_FAILURE/
    # VERIFICATION_FAILURE/INTERNAL_FAILURE). error_type stays the reused,
    # coarser FailureCategory; this is the exact reason within it.
    error_code: str | None = None
    # Whether a real external/filesystem effect actually occurred, even if
    # the overall attempt is ultimately reported as a failure (spec section
    # 25 — e.g. the sandbox file WAS created but verification then failed).
    # Independent of `side_effects` (a descriptive list) — this is the
    # single authoritative boolean a future rollback/reconciliation process
    # would key off of.
    side_effect_occurred: bool = False
    adapter_version: str | None = None


class VerificationResult(BaseModel):
    """What a (future) verification adapter would report. No real
    verification is ever performed in this checkpoint."""

    action_id: str
    method: str
    expected: str | None = None
    observed: str | None = None
    passed: bool
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    issues: list[str] = Field(default_factory=list)
    verified_at: datetime = Field(default_factory=_now)


class PlanReadinessResult(BaseModel):
    """Structured result of plan_validation.py::evaluate_plan_readiness —
    mirrors app/research_intelligence/schemas.py::ComparisonReadiness's
    shape (ready + structured reasons, never a bare bool)."""

    ready: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
