"""Repository layer — the only place raw SQLAlchemy queries should live."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    ActionApprovalRequest,
    ActionApprovalStatus,
    ActionPlanRecord,
    ActionRecord,
    AgentRecord,
    AgentRun,
    Approval,
    AuditEvent,
    BudgetAccountRecord,
    BudgetAccountStatus,
    BudgetEventRecord,
    BudgetScope,
    BudgetType,
    Evidence,
    EvidenceKind,
    EvidenceVerificationStatus,
    ExecutionAttemptRecord,
    ExecutionAttemptStatus,
    ExecutionResultRecord,
    FailureRecord,
    Memory,
    MemoryType,
    PersistedActionPlanStatus,
    PersistedActionStatus,
    Project,
    RecoveryDecisionRecord,
    ReplanProposalRecord,
    ReplanProposalStatus,
    Task,
    TaskDependency,
    UsageRecord,
    User,
    VerificationResultRecord,
    Workspace,
)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_by_email(self, email: str) -> User:
        result = await self.session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(email=email)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)


class WorkspaceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: str, name: str, description: str | None = None) -> Workspace:
        ws = Workspace(user_id=user_id, name=name, description=description)
        self.session.add(ws)
        await self.session.flush()
        return ws

    async def get(self, workspace_id: str) -> Workspace | None:
        return await self.session.get(Workspace, workspace_id)

    async def list_for_user(self, user_id: str) -> list[Workspace]:
        result = await self.session.execute(select(Workspace).where(Workspace.user_id == user_id))
        return list(result.scalars().all())


class ProjectRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        workspace_id: str,
        name: str,
        description: str | None = None,
        objective: str | None = None,
    ) -> Project:
        project = Project(
            workspace_id=workspace_id, name=name, description=description, objective=objective
        )
        self.session.add(project)
        await self.session.flush()
        return project

    async def get(self, project_id: str) -> Project | None:
        return await self.session.get(Project, project_id)

    async def set_objective(self, project_id: str, objective: str) -> Project | None:
        project = await self.get(project_id)
        if project:
            project.objective = objective
        return project

    async def list_for_workspace(self, workspace_id: str) -> list[Project]:
        result = await self.session.execute(
            select(Project).where(Project.workspace_id == workspace_id)
        )
        return list(result.scalars().all())


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(
        self, workspace_id: str, name: str, role: str, description: str | None = None
    ) -> AgentRecord:
        result = await self.session.execute(
            select(AgentRecord).where(
                AgentRecord.workspace_id == workspace_id, AgentRecord.name == name
            )
        )
        agent = result.scalar_one_or_none()
        if agent:
            return agent
        agent = AgentRecord(workspace_id=workspace_id, name=name, role=role, description=description)
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def list_for_workspace(self, workspace_id: str) -> list[AgentRecord]:
        result = await self.session.execute(
            select(AgentRecord).where(AgentRecord.workspace_id == workspace_id)
        )
        return list(result.scalars().all())


class TaskRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        project_id: str,
        title: str,
        agent_type: str,
        description: str | None = None,
        priority=None,
        requires_approval: bool = False,
        parent_task_id: str | None = None,
        input_data: dict | None = None,
        success_criteria: str | None = None,
    ) -> Task:
        from app.database.models import TaskPriority

        task = Task(
            project_id=project_id,
            title=title,
            description=description,
            agent_type=agent_type,
            priority=priority or TaskPriority.NORMAL,
            requires_approval=requires_approval,
            parent_task_id=parent_task_id,
            input_data=json.dumps(input_data) if input_data is not None else None,
            success_criteria=success_criteria,
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def get(self, task_id: str) -> Task | None:
        return await self.session.get(Task, task_id)

    async def list_for_project(self, project_id: str) -> list[Task]:
        result = await self.session.execute(select(Task).where(Task.project_id == project_id))
        return list(result.scalars().all())

    async def add_dependency(self, task_id: str, depends_on_task_id: str) -> TaskDependency:
        dep = TaskDependency(task_id=task_id, depends_on_task_id=depends_on_task_id)
        self.session.add(dep)
        await self.session.flush()
        return dep

    async def get_dependencies(self, task_id: str) -> list[TaskDependency]:
        result = await self.session.execute(
            select(TaskDependency).where(TaskDependency.task_id == task_id)
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        task_id: str,
        status,
        output_data: dict | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> Task | None:
        task = await self.get(task_id)
        if not task:
            return None
        task.status = status
        if output_data is not None:
            task.output_data = json.dumps(output_data)
        if error is not None:
            task.error = error
        if started_at is not None:
            task.started_at = started_at
        if completed_at is not None:
            task.completed_at = completed_at
        await self.session.flush()
        return task


class AgentRunRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, task_id: str, agent_type: str, status, input_payload: dict, attempt: int = 1
    ) -> AgentRun:
        run = AgentRun(
            task_id=task_id,
            agent_type=agent_type,
            status=status,
            input=json.dumps(input_payload),
            attempt=attempt,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def complete(
        self, run_id: str, status, output: dict | None = None, error: str | None = None
    ) -> AgentRun | None:
        run = await self.session.get(AgentRun, run_id)
        if not run:
            return None
        run.status = status
        run.output = json.dumps(output) if output is not None else None
        run.error = error
        run.completed_at = datetime.now(run.started_at.tzinfo) if run.started_at else None
        await self.session.flush()
        return run

    async def list_for_task(self, task_id: str) -> list[AgentRun]:
        result = await self.session.execute(select(AgentRun).where(AgentRun.task_id == task_id))
        return list(result.scalars().all())


class MemoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        workspace_id: str,
        type: MemoryType,
        title: str,
        content: str,
        source: str | None = None,
        importance: int = 3,
    ) -> Memory:
        memory = Memory(
            workspace_id=workspace_id,
            type=type,
            title=title,
            content=content,
            source=source,
            importance=importance,
        )
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def search(
        self,
        workspace_id: str,
        type: MemoryType | None = None,
        keyword: str | None = None,
        min_importance: int | None = None,
    ) -> list[Memory]:
        query = select(Memory).where(Memory.workspace_id == workspace_id)
        if type is not None:
            query = query.where(Memory.type == type)
        if min_importance is not None:
            query = query.where(Memory.importance >= min_importance)
        result = await self.session.execute(query.order_by(Memory.importance.desc()))
        memories = list(result.scalars().all())
        if keyword:
            kw = keyword.lower()
            memories = [
                m for m in memories if kw in m.title.lower() or kw in m.content.lower()
            ]
        return memories


class ApprovalRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, workspace_id: str, task_id: str, requested_action: str, risk_level, reason: str | None = None
    ) -> Approval:
        approval = Approval(
            workspace_id=workspace_id,
            task_id=task_id,
            requested_action=requested_action,
            risk_level=risk_level,
            reason=reason,
        )
        self.session.add(approval)
        await self.session.flush()
        return approval

    async def get(self, approval_id: str) -> Approval | None:
        return await self.session.get(Approval, approval_id)

    async def get_for_task(self, task_id: str) -> Approval | None:
        result = await self.session.execute(
            select(Approval).where(Approval.task_id == task_id).order_by(Approval.requested_at.desc())
        )
        return result.scalars().first()

    async def resolve(
        self, approval_id: str, status, resolved_by: str, decision_reason: str | None = None
    ) -> Approval | None:
        approval = await self.get(approval_id)
        if not approval:
            return None
        approval.status = status
        approval.resolved_by = resolved_by
        approval.decision_reason = decision_reason
        approval.resolved_at = datetime.now(approval.requested_at.tzinfo)
        await self.session.flush()
        return approval

    async def list_for_workspace(self, workspace_id: str, status=None) -> list[Approval]:
        query = select(Approval).where(Approval.workspace_id == workspace_id)
        if status is not None:
            query = query.where(Approval.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class ActionApprovalRequestRepository:
    """Durable persistence for the v0.1.3.4 Action-scoped ApprovalRequest.
    Deliberately keyword-only/plain-dict-shaped (not coupled to
    app.decision_intelligence.schemas.ApprovalRequest) — the database layer
    does not import the domain layer; translation between the pydantic
    domain object and this repository happens in
    app/decision_intelligence/approval_persistence.py."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> ActionApprovalRequest:
        row = ActionApprovalRequest(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, request_id: str) -> ActionApprovalRequest | None:
        return await self.session.get(ActionApprovalRequest, request_id)

    async def update_status(
        self,
        request_id: str,
        *,
        status: ActionApprovalStatus,
        decided_at: datetime | None,
        decided_by: str | None,
    ) -> ActionApprovalRequest | None:
        row = await self.get(request_id)
        if row is None:
            return None
        row.status = status
        row.decided_at = decided_at
        row.decided_by = decided_by
        await self.session.flush()
        return row

    async def consume_if_valid(
        self, request_id: str, *, action_id: str, action_hash: str, now: datetime
    ) -> bool:
        """Atomic, single-consumer conditional UPDATE (spec sections 18/19).
        The WHERE clause re-checks status/consumed/action-ID/hash/expiry
        against the DURABLE row at the moment of the write — this row-level
        conditional UPDATE, not any value computed earlier, IS the
        atomicity boundary. Under two concurrent callers targeting the same
        row, the database guarantees at most one UPDATE ever matches (the
        other's WHERE clause no longer matches once the first commits), so
        exactly one caller observes `rowcount == 1`."""
        stmt = (
            sa_update(ActionApprovalRequest)
            .where(
                ActionApprovalRequest.id == request_id,
                ActionApprovalRequest.consumed.is_(False),
                ActionApprovalRequest.status == ActionApprovalStatus.APPROVED,
                ActionApprovalRequest.action_id == action_id,
                ActionApprovalRequest.action_hash == action_hash,
                or_(
                    ActionApprovalRequest.expires_at.is_(None),
                    ActionApprovalRequest.expires_at > now,
                ),
            )
            .values(consumed=True, consumed_at=now)
            # synchronize_session=False: this is a raw Core UPDATE we
            # always re-fetch after via .get() — SQLAlchemy's default
            # "evaluate" strategy would otherwise try to Python-evaluate
            # this WHERE clause (including the datetime comparison above)
            # against any already-loaded ActionApprovalRequest in this
            # session's identity map, which can hold a naive datetime
            # (SQLite does not preserve tzinfo) and raise
            # "can't compare offset-naive and offset-aware datetimes" even
            # though the actual SQL-level comparison is always correct.
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        # Deliberately COMMIT (not merely flush, unlike every other method in
        # this file): the entire purpose of this method is to be the durable
        # atomicity boundary a crash cannot unwind. Leaving it uncommitted
        # would let a subsequent crash silently undo a consumption that a
        # real side effect (e.g. a sandbox file write) may already have been
        # performed on the strength of — see action_executor.py's ordering
        # and docs/decision_intelligence.md's v0.1.3.4 crash-window section.
        await self.session.commit()
        return result.rowcount == 1


class ActionPlanRecordRepository:
    """Durable persistence for the v0.1.3.6 ActionPlanRecord, including the
    plan-level orchestration lease (spec sections 24/25)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> ActionPlanRecord:
        row = ActionPlanRecord(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, plan_id: str) -> ActionPlanRecord | None:
        # populate_existing=True — same reasoning as ActionRecordRepository.get():
        # update_if_version_matches()/claim_orchestration() write via raw
        # Core UPDATE, which does not refresh an already-identity-mapped
        # instance in this session.
        return await self.session.get(ActionPlanRecord, plan_id, populate_existing=True)

    async def update_if_version_matches(self, plan_id: str, *, expected_version: int, **fields) -> bool:
        """Atomic conditional UPDATE (spec section 41), identical pattern to
        ActionRecordRepository.update_if_version_matches()."""
        stmt = (
            sa_update(ActionPlanRecord)
            .where(ActionPlanRecord.id == plan_id, ActionPlanRecord.version == expected_version)
            .values(version=expected_version + 1, **fields)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount == 1

    async def claim_orchestration(
        self, plan_id: str, *, owner: str, now: datetime, lease_seconds: int, allow_stale_takeover: bool = False
    ) -> bool:
        """The atomic plan-level execution claim (spec section 24). By
        default only claims a genuinely UNCLAIMED plan
        (`orchestration_owner IS NULL`). `allow_stale_takeover=True` is the
        ONLY way to also match an expired-lease row — callers must pass it
        deliberately, and only after reconciling the plan first (spec
        section 25: "EXPIRED LEASE -> RECONCILIATION REQUIRED ... -> only
        then permit a new claim"); see action_plan_orchestrator.py for the
        enforced sequencing."""
        lease_expires = now + timedelta(seconds=lease_seconds)
        conditions = [ActionPlanRecord.id == plan_id]
        if allow_stale_takeover:
            conditions.append(
                or_(
                    ActionPlanRecord.orchestration_owner.is_(None),
                    ActionPlanRecord.orchestration_lease_expires_at < now,
                )
            )
        else:
            conditions.append(ActionPlanRecord.orchestration_owner.is_(None))

        stmt = (
            sa_update(ActionPlanRecord)
            .where(*conditions)
            .values(orchestration_owner=owner, orchestration_claimed_at=now, orchestration_lease_expires_at=lease_expires)
            # synchronize_session=False — see consume_if_valid()'s comment
            # above; this statement's `allow_stale_takeover` branch has the
            # exact same naive/aware datetime comparison shape.
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount == 1

    async def release_orchestration(self, plan_id: str, *, owner: str) -> bool:
        stmt = (
            sa_update(ActionPlanRecord)
            .where(ActionPlanRecord.id == plan_id, ActionPlanRecord.orchestration_owner == owner)
            .values(orchestration_owner=None, orchestration_claimed_at=None, orchestration_lease_expires_at=None)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount == 1

    async def list_by_status(self, statuses: list[PersistedActionPlanStatus]) -> list[ActionPlanRecord]:
        # populate_existing=True — same identity-map staleness reasoning as
        # get() above: a plain select() also returns an already-loaded
        # in-session instance unrefreshed, which can be stale after any
        # raw Core UPDATE elsewhere in this session (this is exactly how a
        # real bug — a silently-undetected plan mutation — surfaced during
        # this checkpoint's own testing; see docs/decision_intelligence.md).
        result = await self.session.execute(
            select(ActionPlanRecord).where(ActionPlanRecord.status.in_(statuses)).execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def list_stale_leases(self, *, before: datetime) -> list[ActionPlanRecord]:
        result = await self.session.execute(
            select(ActionPlanRecord)
            .where(
                ActionPlanRecord.orchestration_owner.is_not(None),
                ActionPlanRecord.orchestration_lease_expires_at < before,
            )
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())


class ActionRecordRepository:
    """Durable persistence for the v0.1.3.5 ActionRecord. Every mutation
    after the initial insert goes through update_if_version_matches() —
    the optimistic-concurrency conditional UPDATE (spec section 6)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> ActionRecord:
        row = ActionRecord(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, action_id: str) -> ActionRecord | None:
        # populate_existing=True: update_if_version_matches() below writes
        # via a raw Core UPDATE, which does NOT refresh any ActionRecord
        # instance the session's identity map already holds for this PK.
        # Without this, a caller that read this row earlier in the same
        # session (very much the normal case here — the durable executor
        # re-fetches after every version bump) would get back the STALE,
        # pre-update in-memory copy instead of the row's real current
        # state, silently reintroducing the exact staleness this
        # repository exists to prevent. Costs one extra round trip; worth
        # it for a correctness-critical optimistic-concurrency primitive.
        return await self.session.get(ActionRecord, action_id, populate_existing=True)

    async def update_if_version_matches(
        self, action_id: str, *, expected_version: int, **fields
    ) -> bool:
        """Atomic conditional UPDATE (spec section 6):
        `WHERE id=:id AND version=:expected_version`, incrementing
        `version` on success. A stale writer (wrong expected_version)
        matches zero rows and must treat that as a failed write — never
        retried automatically by this method."""
        stmt = (
            sa_update(ActionRecord)
            .where(ActionRecord.id == action_id, ActionRecord.version == expected_version)
            .values(version=expected_version + 1, **fields)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount == 1

    async def list_by_status(self, statuses: list[PersistedActionStatus]) -> list[ActionRecord]:
        result = await self.session.execute(
            select(ActionRecord).where(ActionRecord.status.in_(statuses)).execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def list_by_plan(self, action_plan_id: str) -> list[ActionRecord]:
        """Deterministic membership enumeration (spec section 7) — ordered
        by `sequence` then `id` as a stable tie-breaker, never database
        row-return order (spec section 49). populate_existing=True — see
        ActionPlanRecordRepository.list_by_status()'s comment: without it,
        a plain select() can silently return a stale, already-identity-
        mapped instance instead of reflecting a raw Core UPDATE made
        elsewhere in this same session (the real bug this checkpoint's own
        mutation-detection test caught)."""
        result = await self.session.execute(
            select(ActionRecord)
            .where(ActionRecord.action_plan_id == action_plan_id)
            .order_by(ActionRecord.sequence.asc(), ActionRecord.id.asc())
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())


class FailureRecordRepository:
    """Durable failure history (v0.1.3.7). Append-only from this
    repository's point of view — nothing here ever updates or deletes an
    existing row; every observed failure gets its own row."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> FailureRecord:
        row = FailureRecord(**fields)
        self.session.add(row)
        await self.session.commit()
        return row

    async def list_for_action(self, action_id: str) -> list[FailureRecord]:
        result = await self.session.execute(
            select(FailureRecord).where(FailureRecord.action_id == action_id).order_by(FailureRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_for_plan(self, plan_id: str) -> list[FailureRecord]:
        result = await self.session.execute(
            select(FailureRecord).where(FailureRecord.plan_id == plan_id).order_by(FailureRecord.created_at.asc())
        )
        return list(result.scalars().all())


class RecoveryDecisionRepository:
    """Durable recovery-decision history (v0.1.3.7) — the "why did you
    retry/stop/replan this?" audit trail, one row per evaluate_recovery()
    call whose outcome was acted on."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> RecoveryDecisionRecord:
        row = RecoveryDecisionRecord(**fields)
        self.session.add(row)
        await self.session.commit()
        return row

    async def list_for_action(self, action_id: str) -> list[RecoveryDecisionRecord]:
        result = await self.session.execute(
            select(RecoveryDecisionRecord)
            .where(RecoveryDecisionRecord.action_id == action_id)
            .order_by(RecoveryDecisionRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_for_plan(self, plan_id: str) -> list[RecoveryDecisionRecord]:
        result = await self.session.execute(
            select(RecoveryDecisionRecord)
            .where(RecoveryDecisionRecord.plan_id == plan_id)
            .order_by(RecoveryDecisionRecord.created_at.asc())
        )
        return list(result.scalars().all())


class ReplanProposalRepository:
    """Durable ReplanProposal persistence (v0.1.3.7, spec sections 15/51/52).
    `claim_for_apply()` is the atomic, version-guarded transition that
    ensures only ONE caller may ever move a given proposal out of PROPOSED —
    the same optimistic-concurrency shape as ActionPlanRecordRepository's
    orchestration lease, applied here to a single durable row instead of a
    lease/owner pair, since a proposal is applied at most once, never
    repeatedly re-claimed."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> ReplanProposalRecord:
        row = ReplanProposalRecord(**fields)
        self.session.add(row)
        await self.session.flush()
        return row

    async def get(self, proposal_id: str) -> ReplanProposalRecord | None:
        return await self.session.get(ReplanProposalRecord, proposal_id, populate_existing=True)

    async def get_by_replacement_action_id(self, replacement_action_id: str) -> ReplanProposalRecord | None:
        result = await self.session.execute(
            select(ReplanProposalRecord).where(ReplanProposalRecord.replacement_action_id == replacement_action_id)
        )
        return result.scalar_one_or_none()

    async def claim_for_apply(self, proposal_id: str, *, expected_version: int) -> bool:
        """Atomic PROPOSED -> APPLIED conditional UPDATE (spec sections 51/52):
        matches only a row still at `expected_version` AND still PROPOSED —
        a second concurrent caller (or a second call on an already-applied
        proposal) matches zero rows and must treat that as "someone else
        already applied this," never retry blindly."""
        stmt = (
            sa_update(ReplanProposalRecord)
            .where(
                ReplanProposalRecord.id == proposal_id,
                ReplanProposalRecord.version == expected_version,
                ReplanProposalRecord.status == ReplanProposalStatus.PROPOSED,
            )
            .values(version=expected_version + 1, status=ReplanProposalStatus.APPLIED)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount == 1

    async def update_fields(self, proposal_id: str, *, expected_version: int, **fields) -> bool:
        stmt = (
            sa_update(ReplanProposalRecord)
            .where(ReplanProposalRecord.id == proposal_id, ReplanProposalRecord.version == expected_version)
            .values(version=expected_version + 1, **fields)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount == 1


class BudgetAccountRepository:
    """Durable budget accounts (v0.1.3.7, spec sections 23-30). `ensure()`
    is a get-or-create that NEVER changes an existing row's `limit_value` —
    the only way this repository ever raises a limit is by creating a fresh
    account; nothing here can silently widen an already-established
    budget (spec section 30)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_scope(
        self, *, scope_type: BudgetScope, scope_id: str, budget_type: BudgetType
    ) -> BudgetAccountRecord | None:
        result = await self.session.execute(
            select(BudgetAccountRecord)
            .where(
                BudgetAccountRecord.scope_type == scope_type,
                BudgetAccountRecord.scope_id == scope_id,
                BudgetAccountRecord.budget_type == budget_type,
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get(self, account_id: str) -> BudgetAccountRecord | None:
        return await self.session.get(BudgetAccountRecord, account_id, populate_existing=True)

    async def ensure(
        self, *, scope_type: BudgetScope, scope_id: str, budget_type: BudgetType, limit_value: float
    ) -> BudgetAccountRecord:
        existing = await self.get_by_scope(scope_type=scope_type, scope_id=scope_id, budget_type=budget_type)
        if existing is not None:
            return existing
        row = BudgetAccountRecord(
            scope_type=scope_type, scope_id=scope_id, budget_type=budget_type, limit_value=limit_value
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError:
            # A concurrent caller created the same (scope_type, scope_id,
            # budget_type) account first (UNIQUE constraint) — not a
            # corruption, just lost a benign creation race.
            await self.session.rollback()
            existing = await self.get_by_scope(scope_type=scope_type, scope_id=scope_id, budget_type=budget_type)
            if existing is not None:
                return existing
            raise
        return row

    async def update_if_version_matches(self, account_id: str, *, expected_version: int, **fields) -> bool:
        stmt = (
            sa_update(BudgetAccountRecord)
            .where(BudgetAccountRecord.id == account_id, BudgetAccountRecord.version == expected_version)
            .values(version=expected_version + 1, **fields)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount == 1


class BudgetEventRepository:
    """Append-only budget ledger (v0.1.3.7, spec sections 26/27). The
    UNIQUE constraint on `idempotency_key` IS the atomic, restart-safe
    "did I already record this exact consumption attempt?" check — same
    claim-by-INSERT pattern as ExecutionAttemptRepository.claim()."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim(self, **fields) -> BudgetEventRecord | None:
        """Returns the newly created event row, or None if an event with
        this idempotency_key was already recorded by a prior call."""
        row = BudgetEventRecord(**fields)
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        return row

    async def get_by_idempotency_key(self, idempotency_key: str) -> BudgetEventRecord | None:
        result = await self.session.execute(
            select(BudgetEventRecord).where(BudgetEventRecord.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def list_for_account(self, account_id: str) -> list[BudgetEventRecord]:
        result = await self.session.execute(
            select(BudgetEventRecord)
            .where(BudgetEventRecord.budget_account_id == account_id)
            .order_by(BudgetEventRecord.created_at.asc())
        )
        return list(result.scalars().all())


class ExecutionAttemptRepository:
    """Durable ExecutionAttempt persistence, including the atomic execution
    claim (spec section 24) — implemented as a plain INSERT racing against
    the `idempotency_key` UNIQUE constraint, not a Python-level lock. Two
    concurrent claims for the same (action_id, action_hash) pair can both
    attempt the INSERT; the database guarantees only one succeeds."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim(
        self,
        *,
        action_id: str,
        idempotency_key: str,
        tool_name: str,
        adapter_name: str,
        adapter_version: str | None,
        claimed_by: str,
        now: datetime,
    ) -> ExecutionAttemptRecord | None:
        """Returns the newly created, claimed ExecutionAttemptRecord, or
        None if another caller already holds the claim for this
        idempotency_key (the INSERT's UNIQUE constraint was violated)."""
        row = ExecutionAttemptRecord(
            action_id=action_id,
            idempotency_key=idempotency_key,
            tool_name=tool_name,
            adapter_name=adapter_name,
            adapter_version=adapter_version,
            status=ExecutionAttemptStatus.CREATED,
            claimed_at=now,
            claimed_by=claimed_by,
        )
        self.session.add(row)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        return row

    async def get(self, attempt_id: str) -> ExecutionAttemptRecord | None:
        return await self.session.get(ExecutionAttemptRecord, attempt_id)

    async def get_by_idempotency_key(self, idempotency_key: str) -> ExecutionAttemptRecord | None:
        result = await self.session.execute(
            select(ExecutionAttemptRecord).where(ExecutionAttemptRecord.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def list_for_action(self, action_id: str) -> list[ExecutionAttemptRecord]:
        result = await self.session.execute(
            select(ExecutionAttemptRecord)
            .where(ExecutionAttemptRecord.action_id == action_id)
            .order_by(ExecutionAttemptRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def update_fields(self, attempt_id: str, **fields) -> ExecutionAttemptRecord | None:
        row = await self.get(attempt_id)
        if row is None:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        await self.session.commit()
        return row

    async def list_stale_started(self, *, before: datetime) -> list[ExecutionAttemptRecord]:
        """Attempts still STARTED whose lease has already expired — a
        candidate for reconciliation, never for automatic re-execution
        (spec section 25)."""
        result = await self.session.execute(
            select(ExecutionAttemptRecord).where(
                ExecutionAttemptRecord.status == ExecutionAttemptStatus.STARTED,
                ExecutionAttemptRecord.lease_expires_at.is_not(None),
                ExecutionAttemptRecord.lease_expires_at < before,
            )
        )
        return list(result.scalars().all())


class ExecutionResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> ExecutionResultRecord:
        row = ExecutionResultRecord(**fields)
        self.session.add(row)
        await self.session.commit()
        return row

    async def get_by_attempt(self, attempt_id: str) -> ExecutionResultRecord | None:
        result = await self.session.execute(
            select(ExecutionResultRecord).where(ExecutionResultRecord.attempt_id == attempt_id)
        )
        return result.scalar_one_or_none()


class VerificationResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **fields) -> VerificationResultRecord:
        row = VerificationResultRecord(**fields)
        self.session.add(row)
        await self.session.commit()
        return row

    async def get_by_attempt(self, attempt_id: str) -> VerificationResultRecord | None:
        result = await self.session.execute(
            select(VerificationResultRecord).where(VerificationResultRecord.attempt_id == attempt_id)
        )
        return result.scalar_one_or_none()


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record(
        self,
        workspace_id: str,
        actor_type: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            workspace_id=workspace_id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            event_metadata=json.dumps(metadata) if metadata is not None else None,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_for_workspace(self, workspace_id: str, limit: int = 200) -> list[AuditEvent]:
        result = await self.session.execute(
            select(AuditEvent)
            .where(AuditEvent.workspace_id == workspace_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_for_entities(
        self, entity_type_to_ids: dict[str, list[str]], limit: int = 200
    ) -> list[AuditEvent]:
        """Fetch events for a set of entities, e.g. {'project': [pid], 'task': [t1, t2]}."""
        from sqlalchemy import or_, and_

        if not entity_type_to_ids:
            return []
        conditions = [
            and_(AuditEvent.entity_type == etype, AuditEvent.entity_id.in_(eids))
            for etype, eids in entity_type_to_ids.items()
            if eids
        ]
        if not conditions:
            return []
        result = await self.session.execute(
            select(AuditEvent)
            .where(or_(*conditions))
            .order_by(AuditEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())


class EvidenceRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        evidence_id: str,
        workspace_id: str,
        project_id: str,
        task_id: str,
        claim: str,
        source_title: str | None,
        source_url: str | None,
        publisher: str | None,
        published_at: datetime | None,
        retrieved_at: datetime,
        excerpt: str | None,
        evidence_type: EvidenceKind,
        confidence: float,
        query_used: str | None,
        verification_status: EvidenceVerificationStatus,
        source_quality: str = "UNKNOWN",
        evidence_depth: str = "SEARCH_SNIPPET",
    ) -> Evidence:
        evidence = Evidence(
            id=evidence_id,
            workspace_id=workspace_id,
            project_id=project_id,
            task_id=task_id,
            claim=claim,
            source_title=source_title,
            source_url=source_url,
            publisher=publisher,
            published_at=published_at,
            retrieved_at=retrieved_at,
            excerpt=excerpt,
            evidence_type=evidence_type,
            confidence=confidence,
            query_used=query_used,
            verification_status=verification_status,
            source_quality=source_quality,
            evidence_depth=evidence_depth,
        )
        self.session.add(evidence)
        await self.session.flush()
        return evidence

    async def list_for_project(self, project_id: str) -> list[Evidence]:
        result = await self.session.execute(
            select(Evidence).where(Evidence.project_id == project_id)
        )
        return list(result.scalars().all())

    async def list_for_task(self, task_id: str) -> list[Evidence]:
        result = await self.session.execute(select(Evidence).where(Evidence.task_id == task_id))
        return list(result.scalars().all())


@dataclass
class UsageTotals:
    api_calls: int = 0
    initial_calls: int = 0
    retry_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None


class UsageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        workspace_id: str,
        project_id: str,
        task_id: str | None,
        agent_type: str,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None,
        api_calls: int = 1,
        retry_number: int = 0,
        elapsed_ms: float | None = None,
        estimated_cost_usd: float | None = None,
    ) -> UsageRecord:
        record = UsageRecord(
            workspace_id=workspace_id,
            project_id=project_id,
            task_id=task_id,
            agent_type=agent_type,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            api_calls=api_calls,
            retry_number=retry_number,
            elapsed_ms=elapsed_ms,
            estimated_cost_usd=estimated_cost_usd,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_for_project(self, project_id: str) -> list[UsageRecord]:
        result = await self.session.execute(
            select(UsageRecord).where(UsageRecord.project_id == project_id)
        )
        return list(result.scalars().all())

    async def totals_for_project(self, project_id: str) -> UsageTotals:
        result = await self.session.execute(
            select(
                func.coalesce(func.sum(UsageRecord.api_calls), 0),
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                func.sum(UsageRecord.estimated_cost_usd),
            ).where(UsageRecord.project_id == project_id)
        )
        api_calls, input_tokens, output_tokens, total_tokens, cost = result.one()
        return UsageTotals(
            api_calls=int(api_calls or 0),
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            total_tokens=int(total_tokens or 0),
            estimated_cost_usd=float(cost) if cost is not None else None,
        )

    async def total_cost_for_workspace_today(self, workspace_id: str) -> float | None:
        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self.session.execute(
            select(func.sum(UsageRecord.estimated_cost_usd)).where(
                UsageRecord.workspace_id == workspace_id,
                UsageRecord.created_at >= start_of_day,
            )
        )
        cost = result.scalar_one_or_none()
        return float(cost) if cost is not None else None
