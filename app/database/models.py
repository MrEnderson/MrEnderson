"""SQLAlchemy ORM models — the system-of-record schema for Jarvis OS."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    PLANNED = "PLANNED"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskPriority(str, enum.Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProjectStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class AgentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class AgentRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class MemoryType(str, enum.Enum):
    FACT = "FACT"
    DECISION = "DECISION"
    PREFERENCE = "PREFERENCE"
    PROJECT_KNOWLEDGE = "PROJECT_KNOWLEDGE"
    LESSON = "LESSON"
    RESEARCH = "RESEARCH"
    INSTRUCTION = "INSTRUCTION"


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ActionApprovalStatus(str, enum.Enum):
    """Persisted mirror of app.decision_intelligence.schemas.ApprovalRequestStatus
    (v0.1.3.1/.3). Deliberately a SEPARATE enum, not an import of that pydantic
    module's enum — this module must not depend on app.decision_intelligence
    (which itself imports PermissionLevel/RiskLevel FROM here; importing the
    other way would be circular). Kept byte-for-byte identical in values by a
    dedicated regression test (test_action_approval_persistence.py)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PersistedActionStatus(str, enum.Enum):
    """Persisted mirror of app.decision_intelligence.schemas.ActionStatus
    (v0.1.3.1, v0.1.3.5 durability). Same separate-enum reasoning as
    ActionApprovalStatus above — kept byte-for-byte identical in values by
    a dedicated regression test."""

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


class ExecutionAttemptStatus(str, enum.Enum):
    """v0.1.3.5. Durable ExecutionAttempt lifecycle — deliberately distinct
    from PersistedActionStatus: an Action's status is the AUTHORIZATION/
    lifecycle view; an attempt's status is the EXECUTOR'S OWN bookkeeping
    for one specific try at running the adapter, including recovery-only
    states (INTERRUPTED/RECONCILIATION_REQUIRED/RECONCILED/BLOCKED) that
    have no ActionStatus equivalent."""

    CREATED = "CREATED"
    STARTED = "STARTED"
    SIDE_EFFECT_REPORTED = "SIDE_EFFECT_REPORTED"
    EXECUTION_SUCCEEDED = "EXECUTION_SUCCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    INTERRUPTED = "INTERRUPTED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    RECONCILED = "RECONCILED"
    BLOCKED = "BLOCKED"


class ResultProvenance(str, enum.Enum):
    """v0.1.3.5 spec sections 34/35: never let a recovered/reconstructed
    result masquerade as one produced by a normal execution/verification
    pass."""

    ORIGINAL = "ORIGINAL"
    RECONSTRUCTED = "RECONSTRUCTED"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PermissionLevel(str, enum.Enum):
    READ = "READ"
    WRITE = "WRITE"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
    FINANCIAL_ACTION = "FINANCIAL_ACTION"
    ADMIN = "ADMIN"


class EvidenceKind(str, enum.Enum):
    """What sort of source an EvidenceItem was retrieved from."""

    PRIMARY_SOURCE = "PRIMARY_SOURCE"
    NEWS = "NEWS"
    OFFICIAL_STATISTIC = "OFFICIAL_STATISTIC"
    ACADEMIC = "ACADEMIC"
    COMPANY_DISCLOSURE = "COMPANY_DISCLOSURE"
    BLOG_OR_OPINION = "BLOG_OR_OPINION"
    OTHER = "OTHER"


class EvidenceVerificationStatus(str, enum.Enum):
    """How much trust an EvidenceItem's retrieval carries.

    RETRIEVED: fetched from a live search/fetch provider, not independently
    cross-checked against a second source.
    VERIFIED: corroborated by more than one independent source.
    UNVERIFIED: provider returned it but retrieval itself could not be trusted
    (e.g. partial/failed fetch).
    MOCK: produced by MockResearchProvider — deterministic development data,
    never to be treated as real evidence.
    """

    RETRIEVED = "RETRIEVED"
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    MOCK = "MOCK"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="user")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    user: Mapped["User"] = relationship(back_populates="workspaces")
    projects: Mapped[list["Project"]] = relationship(back_populates="workspace")
    agents: Mapped[list["AgentRecord"]] = relationship(back_populates="workspace")
    memories: Mapped[list["Memory"]] = relationship(back_populates="workspace")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus), default=ProjectStatus.ACTIVE, nullable=False
    )
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class AgentRecord(Base):
    """A configured agent instance within a workspace (registry entry persisted to DB)."""

    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_agent_workspace_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AgentStatus] = mapped_column(
        Enum(AgentStatus), default=AgentStatus.ACTIVE, nullable=False
    )
    configuration: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="agents")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    parent_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True, index=True
    )
    assigned_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agents.id"), nullable=True, index=True
    )
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    priority: Mapped[TaskPriority] = mapped_column(
        Enum(TaskPriority), default=TaskPriority.NORMAL, nullable=False
    )
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="task")
    dependencies: Mapped[list["TaskDependency"]] = relationship(
        foreign_keys="TaskDependency.task_id", back_populates="task"
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    depends_on_task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id"), nullable=False, index=True
    )

    task: Mapped["Task"] = relationship(foreign_keys=[task_id], back_populates="dependencies")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"), nullable=True)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(Enum(AgentRunStatus), nullable=False)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship(back_populates="agent_runs")


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (Index("ix_memories_workspace_type", "workspace_id", "type"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    type: Mapped[MemoryType] = mapped_column(Enum(MemoryType), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="memories")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    requested_action: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PersistedActionPlanStatus(str, enum.Enum):
    """Persisted mirror of app.decision_intelligence.schemas.ActionPlanStatus
    (v0.1.3.1, v0.1.3.6 durability). Same separate-enum reasoning as
    PersistedActionStatus/ActionApprovalStatus above."""

    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    READY = "READY"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    EXECUTING = "EXECUTING"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ActionPlanRecord(Base):
    """Durable persistence for app.decision_intelligence.schemas.ActionPlan
    (v0.1.3.6). `plan_hash` covers orchestration/security-relevant
    structure only (plan id, failure_policy, every member Action's id +
    dependencies + action_hash) — deliberately NOT the same concept as an
    Action's approval hash or a sandbox side-effect fingerprint; see
    action_plan_persistence.py::compute_plan_hash's docstring.

    `orchestration_owner`/`orchestration_claimed_at`/
    `orchestration_lease_expires_at` are the plan-level execution lease
    (spec section 25) — a durable, conditional-UPDATE-based claim so two
    orchestrator processes can never both drive the same plan at once. An
    expired lease is never silently stolen — see
    action_plan_orchestrator.py.
    """

    __tablename__ = "action_plans"
    __table_args__ = (
        Index("ix_action_plans_decision_id", "decision_id"),
        Index("ix_action_plans_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(36), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_policy: Mapped[str] = mapped_column(String(50), default="STOP_ON_FAILURE", nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_model_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PersistedActionPlanStatus] = mapped_column(
        Enum(PersistedActionPlanStatus), default=PersistedActionPlanStatus.DRAFT, nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(320), default="system", nullable=False)
    plan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # v0.1.3.7: durable structural version — incremented by exactly one each
    # time an applied ReplanProposal rewrites this plan's Action membership/
    # dependency graph (spec sections 19/20). Distinct from `version`
    # (optimistic-concurrency row version, bumped by EVERY write).
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pause_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    orchestration_owner: Mapped[str | None] = mapped_column(String(200), nullable=True)
    orchestration_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    orchestration_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionApprovalRequest(Base):
    """Durable persistence for app.decision_intelligence.schemas.ApprovalRequest
    (v0.1.3.4). Deliberately a DISTINCT table/model from `Approval` above —
    see docs/decision_intelligence.md's v0.1.3.3 "Reconciliation" section for
    the full rationale (different purpose, ownership/layer, binding, and
    consumption semantics; merging them would be unsafe).

    `action_id` is NOT a ForeignKey: `Action`/`ActionPlan`/`Decision` remain
    plain Pydantic domain objects with no backing table (see
    docs/decision_intelligence.md's "Persistence" sections, v0.1.3.1-v0.1.3.3)
    — this row is keyed by the Action's UUID string only, not a database
    relationship. `proposed_inputs` is stored as a JSON string (Text), same
    convention as `Task.input_data`/`Task.output_data`.
    """

    __tablename__ = "action_approval_requests"
    __table_args__ = (Index("ix_action_approval_requests_action_id", "action_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[ActionApprovalStatus] = mapped_column(
        Enum(ActionApprovalStatus), default=ActionApprovalStatus.PENDING, nullable=False
    )
    requested_by: Mapped[str] = mapped_column(String(320), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    permission_level: Mapped[PermissionLevel] = mapped_column(Enum(PermissionLevel), nullable=False)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposed_inputs: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionRecord(Base):
    """Durable persistence for app.decision_intelligence.schemas.Action
    (v0.1.3.5). `action_hash` is the SAME canonical hash
    action_hash.py::compute_action_hash() already produces for
    ApprovalRequest.action_hash — deliberately reused rather than a second,
    competing hash algorithm (see docs/decision_intelligence.md's v0.1.3.5
    "Payload/hash integrity" section for the full rationale). `version` is
    the optimistic-concurrency column: every mutation goes through
    ActionRecordRepository.update_if_version_matches(), a conditional
    `UPDATE ... WHERE version = :expected` that increments it — a stale
    writer's update affects zero rows and must be treated as a failed
    write, not retried blindly.

    `approval_id` IS a real ForeignKey (unlike `action_id` on
    ActionApprovalRequest) — unlike `Action`/`ActionPlan`,
    `ActionApprovalRequest` already has a table, so this relationship can
    be enforced at the database level.
    """

    __tablename__ = "action_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    action_plan_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    inputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False)
    permission_level: Mapped[PermissionLevel] = mapped_column(Enum(PermissionLevel), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(
        ForeignKey("action_approval_requests.id"), nullable=True
    )
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    dependencies_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PersistedActionStatus] = mapped_column(
        Enum(PersistedActionStatus), default=PersistedActionStatus.PLANNED, nullable=False
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # v0.1.3.7: set when a ReplanProposal replaces this (terminally FAILED)
    # Action with a new one. NOT a ForeignKey — same non-FK convention as
    # ActionApprovalRequest.action_id — because the replacement row is
    # created as part of the same apply_replan() operation and back-filled
    # onto this row afterward; see replan.py. This Action's own row is
    # NEVER deleted or overwritten by a replan (spec section 21).
    superseded_by_action_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ExecutionAttemptRecord(Base):
    """Durable record of ONE try at running a tool adapter for an Action
    (v0.1.3.5). `idempotency_key` is deterministically derived from
    `(action_id, action_hash)` — never model-chosen — and is UNIQUE at the
    database level: this uniqueness constraint IS the atomic execution
    claim (spec section 24). A second concurrent claim attempt for the
    same key fails the INSERT with an IntegrityError, which
    ExecutionAttemptRepository.claim() catches and reports as "already
    claimed" rather than a crash.

    `lease_expires_at` is the minimal lease mechanism spec section 25
    asks for: set once an attempt moves to STARTED, used ONLY by
    discover_reconciliation_candidates() to flag a stale STARTED attempt
    for review. Nothing here ever automatically reclaims/reruns an expired
    lease — an expired lease means RECONCILIATION_REQUIRED, never "run
    again" (see reconciliation.py).
    """

    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_execution_attempts_idempotency_key"),
        Index("ix_execution_attempts_action_id", "action_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    action_id: Mapped[str] = mapped_column(ForeignKey("action_records.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(200), nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(200), nullable=False)
    adapter_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ExecutionAttemptStatus] = mapped_column(
        Enum(ExecutionAttemptStatus), default=ExecutionAttemptStatus.CREATED, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    side_effect_occurred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    side_effect_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery_state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class ExecutionResultRecord(Base):
    """Durable persistence for app.decision_intelligence.schemas.ExecutionResult
    (v0.1.3.5). One row per ExecutionAttempt — enforced by the UNIQUE
    constraint on attempt_id (spec section 30: "result -> attempt
    uniqueness")."""

    __tablename__ = "execution_results"
    __table_args__ = (UniqueConstraint("attempt_id", name="uq_execution_results_attempt_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("execution_attempts.id"), nullable=False)
    action_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provider_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    structured_output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    side_effect_occurred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    side_effects_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    adapter_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provenance: Mapped[ResultProvenance] = mapped_column(
        Enum(ResultProvenance), default=ResultProvenance.ORIGINAL, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class VerificationResultRecord(Base):
    """Durable persistence for app.decision_intelligence.schemas.VerificationResult
    (v0.1.3.5). One row per ExecutionAttempt — enforced by the UNIQUE
    constraint on attempt_id (spec section 30: "verification -> attempt
    uniqueness")."""

    __tablename__ = "verification_results"
    __table_args__ = (UniqueConstraint("attempt_id", name="uq_verification_results_attempt_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("execution_attempts.id"), nullable=False)
    action_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(100), nullable=False)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed: Mapped[str | None] = mapped_column(Text, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[ResultProvenance] = mapped_column(
        Enum(ResultProvenance), default=ResultProvenance.ORIGINAL, nullable=False
    )
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class FailureRecord(Base):
    """Durable failure history (v0.1.3.7, spec section 34) — persisted
    INDEPENDENTLY of `ActionRecord.last_error` (a single mutable field that
    only ever holds the MOST RECENT error). One row per observed failure,
    so a plan that retries three times keeps all three failures on record
    for future diagnostics, never just the last one. Deterministic
    classification only — see failure_intelligence.py; nothing here is
    ever written by an LLM."""

    __tablename__ = "failure_records"
    __table_args__ = (
        Index("ix_failure_records_action_id", "action_id"),
        Index("ix_failure_records_plan_id", "plan_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    execution_attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    side_effect_occurred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retry_safe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reconciliation_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retry_count_at_failure: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class RecoveryDecisionRecord(Base):
    """Durable record of what recovery_policy.py decided for one
    FailureRecord, and why (v0.1.3.7, spec section 35) — lets Jarvis answer
    "why did you retry/stop/replan this?" after the fact. `reason_codes` is
    a JSON list, same convention as PermissionDecision/ApprovalValidityResult's
    structured reason codes."""

    __tablename__ = "recovery_decisions"
    __table_args__ = (
        Index("ix_recovery_decisions_action_id", "action_id"),
        Index("ix_recovery_decisions_plan_id", "plan_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    failure_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_codes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    replan_proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class ReplanProposalStatus(str, enum.Enum):
    """v0.1.3.7 (spec section 15). Deliberately the SMALLEST contract that
    still supports the required idempotent/concurrent-apply/reject tests
    (spec section 15: "Use the smallest clean contract") — PROPOSED is the
    only non-terminal status; there is no separate VALIDATED/ACCEPTED
    durable checkpoint, since propose_replan()/apply_replan() validate
    synchronously and record the outcome directly as APPLIED or REJECTED."""

    PROPOSED = "PROPOSED"
    APPLIED = "APPLIED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ReplanProposalRecord(Base):
    """Durable persistence for a controlled, deterministic replan (v0.1.3.7,
    spec sections 14/15). `replacement_action_id` is generated ONCE when the
    proposal is first created and is the sole idempotency anchor for
    apply_replan() (spec section 52: applying the same accepted proposal
    twice must not create two replacement Actions) — `version` additionally
    guards against two concurrent callers both applying the same proposal
    (spec section 51)."""

    __tablename__ = "replan_proposals"
    __table_args__ = (
        Index("ix_replan_proposals_plan_id", "plan_id"),
        Index("ix_replan_proposals_failed_action_id", "failed_action_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    plan_id: Mapped[str] = mapped_column(String(36), nullable=False)
    failed_action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    replacement_action_id: Mapped[str] = mapped_column(String(36), nullable=False)
    replacement_action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    replacement_title: Mapped[str] = mapped_column(String(500), nullable=False)
    replacement_tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    replacement_inputs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_expected_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_verification_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_permission_level: Mapped[PermissionLevel] = mapped_column(Enum(PermissionLevel), nullable=False)
    replacement_risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel), nullable=False)
    replacement_dependencies_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ReplanProposalStatus] = mapped_column(
        Enum(ReplanProposalStatus), default=ReplanProposalStatus.PROPOSED, nullable=False
    )
    reason_codes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(320), default="system", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_plan_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BudgetScope(str, enum.Enum):
    ACTION = "ACTION"
    PLAN = "PLAN"


class BudgetType(str, enum.Enum):
    ACTION_ATTEMPTS = "ACTION_ATTEMPTS"
    RETRIES = "RETRIES"
    REPLANS = "REPLANS"
    MODEL_CALLS = "MODEL_CALLS"
    ESTIMATED_COST = "ESTIMATED_COST"


class BudgetAccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXHAUSTED = "EXHAUSTED"
    CANCELLED = "CANCELLED"


class BudgetAccountRecord(Base):
    """Durable budget enforcement (v0.1.3.7, spec sections 23-33). A
    cached, atomically-updated `consumed_value` PLUS an append-only
    `BudgetEventRecord` ledger (spec section 26) — the cache is what a hot
    conditional-UPDATE check reads; the ledger is what a human/audit trail
    reads. `limit_value` is set ONCE at creation (`ensure_account()` is a
    get-or-create that never changes an existing row's limit) — no Action
    or ReplanProposal has any path that raises it (spec section 30: "Jarvis
    cannot increase its own budget")."""

    __tablename__ = "budget_accounts"
    __table_args__ = (
        UniqueConstraint("scope_type", "scope_id", "budget_type", name="uq_budget_account_scope_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    scope_type: Mapped[BudgetScope] = mapped_column(Enum(BudgetScope), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(36), nullable=False)
    budget_type: Mapped[BudgetType] = mapped_column(Enum(BudgetType), nullable=False)
    limit_value: Mapped[float] = mapped_column(Float, nullable=False)
    consumed_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[BudgetAccountStatus] = mapped_column(
        Enum(BudgetAccountStatus), default=BudgetAccountStatus.ACTIVE, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class BudgetEventRecord(Base):
    """Append-only budget ledger (v0.1.3.7, spec section 26). One row per
    attempted consumption, `applied` distinguishing a granted consumption
    from one that was refused for exceeding the limit — both are recorded,
    so the ledger explains BUDGET_EXHAUSTED outcomes too, not just
    successful ones. `idempotency_key` is UNIQUE — the atomic,
    restart-safe replay anchor (spec sections 27/54): a caller retrying the
    exact same logical consumption (e.g. after a crash) after a crash gets
    back the ALREADY-RECORDED outcome rather than consuming twice."""

    __tablename__ = "budget_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_budget_events_idempotency_key"),
        Index("ix_budget_events_account_id", "budget_account_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    budget_account_id: Mapped[str] = mapped_column(ForeignKey("budget_accounts.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_workspace_created", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    event_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Evidence(Base):
    """A single retrieved, non-fabricated piece of external evidence.

    Always traceable to the mission (project) and task that produced it, and
    to the query that found it. Never written from model-invented data — see
    app/agents/research.py::ResearchAgent._gather_evidence, which builds these
    only from real ResearchProvider.search()/fetch() results.

    `id` is always set explicitly by EvidenceRepository.create() to the
    originating EvidenceItem.id (the pydantic schema's id) — never left to
    the `default=new_uuid` fallback below in the normal write path. That
    fallback exists only so the column has a sane value if a row is ever
    created without an explicit id; relying on it would silently disconnect
    this row's id from the id Strategy/QA and Task.output_data actually
    reference, which was a real bug (see docs/evidence.md).
    """

    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_project_task", "project_id", "task_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[EvidenceKind] = mapped_column(Enum(EvidenceKind), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    query_used: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[EvidenceVerificationStatus] = mapped_column(
        Enum(EvidenceVerificationStatus), nullable=False
    )
    source_quality: Mapped[str] = mapped_column(String(20), default="UNKNOWN", nullable=False)
    evidence_depth: Mapped[str] = mapped_column(String(20), default="SEARCH_SNIPPET", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class UsageRecord(Base):
    """One ModelProvider call's token/cost accounting.

    USAGE (input/output/total_tokens) is only ever what the provider actually
    reported — never guessed. estimated_cost_usd is populated separately, only
    when a pricing entry is configured for `model` (see app/config/pricing.py),
    and stays NULL otherwise so USAGE and ESTIMATED_COST are never conflated.
    """

    __tablename__ = "usage_records"
    __table_args__ = (Index("ix_usage_workspace_created", "workspace_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_calls: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retry_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    elapsed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
