"""Persistence bridge for durable ActionPlan orchestration (v0.1.3.6, spec
sections 6/7/33). Same pattern as approval_persistence.py/
execution_persistence.py: app.database.repositories stays domain-agnostic,
this module is the only place that knows about both the pure-domain
ActionPlan/Action objects and their durable rows.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.database.models import ActionPlanRecord, PersistedActionPlanStatus
from app.database.repositories import ActionPlanRecordRepository, ActionRecordRepository
from app.decision_intelligence.execution_persistence import action_to_record_fields, record_to_action
from app.decision_intelligence.schemas import Action, ActionPlan, ActionPlanStatus, ActionStatus

# spec sections 22/23: a minimal, explicit failure-policy contract. Anything
# unrecognized or blank defaults to the SAFER policy — never silently to
# the more permissive one.
VALID_FAILURE_POLICIES = ("STOP_ON_FAILURE", "CONTINUE_INDEPENDENT")
DEFAULT_FAILURE_POLICY = "STOP_ON_FAILURE"


def normalize_failure_policy(value: str | None) -> str:
    if value and value.strip().upper() in VALID_FAILURE_POLICIES:
        return value.strip().upper()
    return DEFAULT_FAILURE_POLICY


def compute_plan_hash(plan: ActionPlan) -> str:
    """Deterministic plan-integrity hash covering orchestration/security-
    relevant STRUCTURE only (spec section 33). Deliberately a THIRD,
    distinct concept from two other hashes already in this codebase:

    - `action_hash.py::compute_action_hash` — one Action's own
      authorization payload (what `ApprovalRequest.action_hash` binds to).
      Includes `permission_level`/`risk_level`, which the Permission
      Engine is EXPECTED to overwrite once, authoritatively, during
      normal orchestration (v0.1.3.2's `apply_permission_decision`) — so
      it is deliberately NOT reused verbatim here (see below).
    - `execution_persistence.py::compute_side_effect_fingerprint` — one
      adapter's actual on-disk effect, used only by reconciliation.

    `compute_plan_hash` selects a DELIBERATELY NARROWER field subset per
    Action than `compute_action_hash` — `action_type`/`tool_name`/
    `inputs`/`expected_result`/sorted `dependencies` — everything that
    must NEVER change once a plan is `READY`, while excluding
    `permission_level`/`risk_level`. Reusing the full `action_hash`
    verbatim would make this hash spuriously "change" the moment the
    Permission Engine legitimately overwrites an Action's proposed
    permission/risk with its authoritative values (the very first
    orchestration step for any Action) — that is expected, policy-driven
    correction, not evidence of mutation (spec section 34's concern).
    Also includes the plan id and normalized `failure_policy`.
    Deliberately excludes lifecycle-only fields (status, timestamps,
    estimated_cost, title/description) that naturally change during
    execution without changing what the plan structurally commits to.
    """
    canonical = {
        "plan_id": plan.id,
        "failure_policy": normalize_failure_policy(plan.failure_policy),
        "actions": sorted(
            (
                {
                    "id": action.id,
                    "action_type": action.action_type,
                    "tool_name": action.tool_name,
                    "inputs": action.inputs,
                    "expected_result": action.expected_result,
                    "dependencies": sorted(action.dependencies),
                }
                for action in plan.actions
            ),
            key=lambda entry: entry["id"],
        ),
    }
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def plan_structure_unchanged(plan_before: ActionPlan, plan_after: ActionPlan) -> bool:
    """Spec section 34: detects silent plan mutation after execution has
    begun (changed Action inputs/tool/dependencies/membership, or a
    changed `failure_policy`) — compares `compute_plan_hash()` before and
    after. Never confused with a legitimate authoritative permission/risk
    overwrite, which this hash deliberately excludes."""
    return compute_plan_hash(plan_before) == compute_plan_hash(plan_after)


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def plan_to_record_fields(plan: ActionPlan) -> dict:
    return dict(
        id=plan.id,
        decision_id=plan.decision_id,
        project_id=plan.project_id,
        title=plan.title,
        description=plan.description or None,
        failure_policy=normalize_failure_policy(plan.failure_policy),
        estimated_cost=plan.estimated_cost,
        estimated_model_calls=plan.estimated_model_calls,
        success_criteria=plan.success_criteria or None,
        status=PersistedActionPlanStatus(plan.status.value),
        created_by=plan.created_by,
        plan_hash=compute_plan_hash(plan),
        created_at=plan.created_at,
        revision=plan.revision,
    )


def record_to_plan(row: ActionPlanRecord, actions: list[Action]) -> ActionPlan:
    return ActionPlan(
        id=row.id,
        decision_id=row.decision_id,
        project_id=row.project_id,
        title=row.title,
        description=row.description or "",
        actions=actions,
        estimated_cost=row.estimated_cost,
        estimated_model_calls=row.estimated_model_calls,
        success_criteria=row.success_criteria or "",
        failure_policy=row.failure_policy,
        status=ActionPlanStatus(row.status.value),
        created_by=row.created_by,
        created_at=_ensure_utc(row.created_at),
        revision=row.revision,
    )


async def persist_new_plan(
    plan_repo: ActionPlanRecordRepository, action_repo: ActionRecordRepository, plan: ActionPlan
) -> ActionPlanRecord:
    """Persists the ActionPlanRecord AND one ActionRecord per member
    Action (spec section 7: durable plan<->Action membership must be
    unambiguous). Only ever called AFTER plan_validation.py's structural
    checks already passed — see action_plan_orchestrator.py::
    validate_and_persist_plan — so every member Action is persisted
    already at ActionStatus.VALIDATED, never PLANNED."""
    plan_row = await plan_repo.create(**plan_to_record_fields(plan))
    for action in plan.actions:
        validated_action = (
            action.model_copy(update={"status": ActionStatus.VALIDATED})
            if action.status == ActionStatus.PLANNED
            else action
        )
        await action_repo.create(**action_to_record_fields(validated_action))
    return plan_row


async def load_plan_actions(action_repo: ActionRecordRepository, action_plan_id: str) -> list[Action]:
    rows = await action_repo.list_by_plan(action_plan_id)
    return [record_to_action(row) for row in rows]


async def load_plan(
    plan_repo: ActionPlanRecordRepository, action_repo: ActionRecordRepository, plan_id: str
) -> tuple[ActionPlanRecord, ActionPlan] | None:
    """Returns (durable row, reconstructed domain object) or None. The row
    is returned separately because callers need `.version` for optimistic
    updates, which is not part of the pydantic domain object."""
    plan_row = await plan_repo.get(plan_id)
    if plan_row is None:
        return None
    actions = await load_plan_actions(action_repo, plan_id)
    return plan_row, record_to_plan(plan_row, actions)
