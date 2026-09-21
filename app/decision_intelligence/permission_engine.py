"""Deterministic Permission Engine (v0.1.3.2, spec sections 5-13/17). Given
an Action and a ToolRegistry, produces an authoritative PermissionDecision.
NO REAL TOOL EXECUTION and NO APPROVAL GRANTING happen anywhere in this
module — see docs/decision_intelligence.md's v0.1.3.2 section for the full
NOT IMPLEMENTED list (Approval Engine, execution, verification execution).

Core security invariant: an Action's `permission_level`/`risk_level` are
PROPOSED metadata only (an LLM/agent may set them) — this module NEVER
trusts them as authoritative. The authoritative permission_level/risk_level
on the returned PermissionDecision are always derived from the resolved
ToolDefinition and the Action's action_type, taking the maximum (floor) of
the two; the agent-proposed values can only ever be escalated up to that
floor, never used to lower it. See evaluate_permission()'s docstring.

P-tier -> (PermissionLevel, outcome) mapping this checkpoint implements:

    P0  internal reasoning (no tool)         READ             -> ALLOW
    P1  read-only                            READ             -> ALLOW
    P2  internal/sandboxed creation          WRITE            -> ALLOW_WITH_AUDIT
    P3  reversible external change           EXTERNAL_ACTION  -> REQUIRE_APPROVAL  (*)
    P4  consequential external action        EXTERNAL_ACTION  -> REQUIRE_APPROVAL
    P5  financial                            FINANCIAL_ACTION -> REQUIRE_APPROVAL  (**)
    P5  privileged/security/system           ADMIN            -> BLOCK            (**)

(*)  P3 is explicitly policy-sensitive (spec section 6) and no rollback/
     reversal engine exists yet to make ALLOW_WITH_AUDIT safe for a genuine
     external mutation, even a reversible one. This checkpoint's conservative
     choice is REQUIRE_APPROVAL — operationally identical to P4 today, but
     carries its own risk tier (MEDIUM, not HIGH) and reason codes, so a
     future checkpoint can differentiate them without a schema change.
(**) Both are valid P5 readings of "REQUIRE_APPROVAL or BLOCK according to
     explicit policy" (spec section 6). This checkpoint splits P5 by
     PermissionLevel: FINANCIAL_ACTION (e.g. spend_money) is a bounded,
     well-understood human-approval workflow, so REQUIRE_APPROVAL is
     meaningful once an Approval Engine exists. ADMIN (install_software,
     privileged_shell, and anything else that would expand Jarvis's own
     capability surface) is BLOCKed unconditionally — matching spec section
     16's explicit "privileged_shell -> BLOCK by default" and the
     NON-NEGOTIABLE CONSTRAINTS list, which singles out installing software,
     arbitrary shell execution, and self-modification as categorically
     different from a single bounded purchase.

Action-type escalation floor (spec section 8). An action_type not listed
here is UNKNOWN and always BLOCKs (security test 14: unknown action
semantics never default to safe):

    read                                 -> P1  READ / LOW
    internal_create, sandbox_create      -> P2  WRITE / LOW
    external_modify                      -> P3  EXTERNAL_ACTION / MEDIUM
    send, publish, delete                -> P4  EXTERNAL_ACTION / HIGH
    financial                            -> P5  FINANCIAL_ACTION / CRITICAL
    install, privileged                  -> P5  ADMIN / CRITICAL

internal/no_op/manual/decision_only (plan_validation.py's
_NO_TOOL_ACTION_TYPES — reused here, not duplicated) are P0: they need no
tool at all and always ALLOW without a registry lookup.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.database.models import PermissionLevel, RiskLevel
from app.decision_intelligence.action_state_machine import assert_transition
from app.decision_intelligence.plan_validation import requires_tool
from app.decision_intelligence.schemas import Action, ActionStatus
from app.decision_intelligence.tool_registry import (
    DisabledToolError,
    ToolDefinition,
    ToolRegistry,
    UnknownToolError,
    UnsupportedActionTypeError,
)

POLICY_SOURCE = "app.decision_intelligence.permission_engine.evaluate_permission"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PermissionOutcome(str, enum.Enum):
    ALLOW = "ALLOW"
    ALLOW_WITH_AUDIT = "ALLOW_WITH_AUDIT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"


class PermissionDecision(BaseModel):
    """Authoritative result of evaluate_permission(). Never a bare bool
    (spec section 5) — always outcome + structured reason codes."""

    action_id: str
    outcome: PermissionOutcome
    permission_level: PermissionLevel
    risk_level: RiskLevel
    approval_required: bool
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str = ""
    policy_source: str = POLICY_SOURCE
    evaluated_at: datetime = Field(default_factory=_now)
    tool_name: str | None = None
    dry_run_recommended: bool = False


# --------------------------------------------------------------------------
# Ordering (for permission/risk floor comparisons)
# --------------------------------------------------------------------------

_PERMISSION_ORDER: list[PermissionLevel] = [
    PermissionLevel.READ,
    PermissionLevel.WRITE,
    PermissionLevel.EXTERNAL_ACTION,
    PermissionLevel.FINANCIAL_ACTION,
    PermissionLevel.ADMIN,
]
_RISK_ORDER: list[RiskLevel] = [
    RiskLevel.LOW,
    RiskLevel.MEDIUM,
    RiskLevel.HIGH,
    RiskLevel.CRITICAL,
]


def _permission_rank(level: PermissionLevel) -> int:
    return _PERMISSION_ORDER.index(level)


def _risk_rank(level: RiskLevel) -> int:
    return _RISK_ORDER.index(level)


def max_permission(a: PermissionLevel, b: PermissionLevel) -> PermissionLevel:
    return a if _permission_rank(a) >= _permission_rank(b) else b


def max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    return a if _risk_rank(a) >= _risk_rank(b) else b


# --------------------------------------------------------------------------
# Action-type escalation floor
# --------------------------------------------------------------------------

_ACTION_TYPE_FLOOR: dict[str, tuple[PermissionLevel, RiskLevel]] = {
    "read": (PermissionLevel.READ, RiskLevel.LOW),
    "internal_create": (PermissionLevel.WRITE, RiskLevel.LOW),
    "sandbox_create": (PermissionLevel.WRITE, RiskLevel.LOW),
    "external_modify": (PermissionLevel.EXTERNAL_ACTION, RiskLevel.MEDIUM),
    "send": (PermissionLevel.EXTERNAL_ACTION, RiskLevel.HIGH),
    "publish": (PermissionLevel.EXTERNAL_ACTION, RiskLevel.HIGH),
    "delete": (PermissionLevel.EXTERNAL_ACTION, RiskLevel.HIGH),
    "financial": (PermissionLevel.FINANCIAL_ACTION, RiskLevel.CRITICAL),
    "install": (PermissionLevel.ADMIN, RiskLevel.CRITICAL),
    "privileged": (PermissionLevel.ADMIN, RiskLevel.CRITICAL),
}

# Action types that need no tool at all (reused, not duplicated, from
# plan_validation.py's requires_tool()/_NO_TOOL_ACTION_TYPES) — P0.
_P0_PERMISSION = PermissionLevel.READ
_P0_RISK = RiskLevel.LOW

_OUTCOME_BY_PERMISSION: dict[PermissionLevel, PermissionOutcome] = {
    PermissionLevel.READ: PermissionOutcome.ALLOW,
    PermissionLevel.WRITE: PermissionOutcome.ALLOW_WITH_AUDIT,
    PermissionLevel.EXTERNAL_ACTION: PermissionOutcome.REQUIRE_APPROVAL,
    PermissionLevel.FINANCIAL_ACTION: PermissionOutcome.REQUIRE_APPROVAL,
    PermissionLevel.ADMIN: PermissionOutcome.BLOCK,
}


def _block(
    action: Action,
    *,
    permission_level: PermissionLevel,
    risk_level: RiskLevel,
    reason_codes: list[str],
    explanation: str,
    tool_name: str | None,
) -> PermissionDecision:
    return PermissionDecision(
        action_id=action.id,
        outcome=PermissionOutcome.BLOCK,
        permission_level=permission_level,
        risk_level=risk_level,
        approval_required=False,
        reason_codes=reason_codes,
        explanation=explanation,
        tool_name=tool_name,
    )


def evaluate_permission(action: Action, registry: ToolRegistry) -> PermissionDecision:
    """The deterministic Permission Engine entry point (spec sections 5-10).
    Never raises for a well-formed Action — every failure mode maps to a
    PermissionDecision with outcome=BLOCK instead, so a caller never needs a
    try/except around normal fail-closed behavior. Never consults an LLM.

    Authority model (spec section 12): `action.permission_level` and
    `action.risk_level` are PROPOSED and are read here ONLY to detect an
    attempted downgrade (-> PERMISSION_ESCALATED/RISK_ESCALATED reason
    codes on the returned decision); they never lower, and cannot bypass,
    the authoritative floor derived from the action_type + resolved
    ToolDefinition.
    """
    action_type = action.action_type

    # P0: action types that need no tool at all (spec section 4/8).
    if not requires_tool(action_type):
        authoritative_permission = _P0_PERMISSION
        authoritative_risk = _P0_RISK
        reason_codes = ["TOOL_ALLOWED"]
        escalated = _append_escalation_reasons(action, authoritative_permission, authoritative_risk, reason_codes)
        return PermissionDecision(
            action_id=action.id,
            outcome=PermissionOutcome.ALLOW,
            permission_level=authoritative_permission,
            risk_level=authoritative_risk,
            approval_required=False,
            reason_codes=reason_codes,
            explanation=(
                f"action_type '{action_type}' requires no tool (internal reasoning) -> ALLOW"
                + (" (proposed permission/risk was escalated to the floor)" if escalated else "")
            ),
            tool_name=None,
        )

    # Unknown action_type entirely (not in the escalation table and not a
    # no-tool type): fail closed, never default to a safe tier (security
    # test 14).
    if action_type not in _ACTION_TYPE_FLOOR:
        return _block(
            action,
            permission_level=PermissionLevel.ADMIN,
            risk_level=RiskLevel.CRITICAL,
            reason_codes=["UNSUPPORTED_ACTION_TYPE", "POLICY_BLOCK"],
            explanation=f"Unknown action_type '{action_type}' has no defined policy -> BLOCK",
            tool_name=action.tool_name,
        )

    action_type_permission, action_type_risk = _ACTION_TYPE_FLOOR[action_type]

    # Fail-closed rule (spec section 10): an action requiring execution but
    # having no declared tool must BLOCK, never silently proceed.
    if not action.tool_name:
        return _block(
            action,
            permission_level=action_type_permission,
            risk_level=action_type_risk,
            reason_codes=["MISSING_TOOL", "POLICY_BLOCK"],
            explanation=f"action_type '{action_type}' requires a tool but Action.tool_name is unset -> BLOCK",
            tool_name=None,
        )

    try:
        tool = registry.resolve(action.tool_name, action_type)
    except UnknownToolError:
        return _block(
            action,
            permission_level=action_type_permission,
            risk_level=action_type_risk,
            reason_codes=["UNKNOWN_TOOL", "POLICY_BLOCK"],
            explanation=f"tool_name '{action.tool_name}' is not registered -> BLOCK",
            tool_name=action.tool_name,
        )
    except DisabledToolError:
        return _block(
            action,
            permission_level=action_type_permission,
            risk_level=action_type_risk,
            reason_codes=["TOOL_DISABLED", "POLICY_BLOCK"],
            explanation=f"tool '{action.tool_name}' is registered but disabled -> BLOCK",
            tool_name=action.tool_name,
        )
    except UnsupportedActionTypeError:
        return _block(
            action,
            permission_level=action_type_permission,
            risk_level=action_type_risk,
            reason_codes=["UNSUPPORTED_ACTION_TYPE", "POLICY_BLOCK"],
            explanation=(
                f"tool '{action.tool_name}' does not support action_type '{action_type}' -> BLOCK"
            ),
            tool_name=action.tool_name,
        )

    return _evaluate_with_tool(action, tool)


def _evaluate_with_tool(action: Action, tool: ToolDefinition) -> PermissionDecision:
    action_type_permission, action_type_risk = _ACTION_TYPE_FLOOR[action.action_type]

    # The floor (spec section 7): the MAX of what the action's semantics
    # require and what the resolved tool declares as its own minimum.
    authoritative_permission = max_permission(action_type_permission, tool.default_permission_level)
    authoritative_risk = max_risk(action_type_risk, tool.default_risk_level)

    reason_codes: list[str] = []
    escalated = _append_escalation_reasons(action, authoritative_permission, authoritative_risk, reason_codes)

    outcome = _OUTCOME_BY_PERMISSION[authoritative_permission]

    if outcome == PermissionOutcome.ALLOW:
        reason_codes.insert(0, "TOOL_ALLOWED")
    elif outcome == PermissionOutcome.ALLOW_WITH_AUDIT:
        reason_codes.insert(0, "AUDIT_REQUIRED")
        reason_codes.insert(0, "TOOL_ALLOWED")
    elif outcome == PermissionOutcome.REQUIRE_APPROVAL:
        reason_codes.insert(0, "APPROVAL_REQUIRED")
    elif outcome == PermissionOutcome.BLOCK:
        reason_codes.insert(0, "POLICY_BLOCK")
        reason_codes.insert(0, "FORBIDDEN_CAPABILITY")

    if authoritative_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        reason_codes.append("HIGH_RISK")

    approval_required = outcome == PermissionOutcome.REQUIRE_APPROVAL

    explanation = (
        f"tool '{tool.name}' resolved for action_type '{action.action_type}' -> "
        f"permission={authoritative_permission.value}, risk={authoritative_risk.value} -> {outcome.value}"
    )
    if escalated:
        explanation += " (proposed permission/risk was below the tool/action floor and was overridden)"

    return PermissionDecision(
        action_id=action.id,
        outcome=outcome,
        permission_level=authoritative_permission,
        risk_level=authoritative_risk,
        approval_required=approval_required,
        reason_codes=reason_codes,
        explanation=explanation,
        tool_name=tool.name,
        dry_run_recommended=tool.supports_dry_run and outcome != PermissionOutcome.ALLOW,
    )


def _append_escalation_reasons(
    action: Action,
    authoritative_permission: PermissionLevel,
    authoritative_risk: RiskLevel,
    reason_codes: list[str],
) -> bool:
    """Appends PERMISSION_ESCALATED/RISK_ESCALATED when the agent-proposed
    Action.permission_level/risk_level sit BELOW the authoritative floor —
    i.e. an (accidental or malicious) downgrade attempt that this engine
    overrode rather than trusted. Returns whether anything was escalated.
    Never appends anything for a proposed value at or above the floor: that
    is not a downgrade, so it is not reported as one."""
    escalated = False
    if _permission_rank(action.permission_level) < _permission_rank(authoritative_permission):
        reason_codes.append("PERMISSION_ESCALATED")
        escalated = True
    if _risk_rank(action.risk_level) < _risk_rank(authoritative_risk):
        reason_codes.append("RISK_ESCALATED")
        escalated = True
    return escalated


# --------------------------------------------------------------------------
# Action-state integration (spec section 11)
# --------------------------------------------------------------------------


def apply_permission_decision(action: Action, decision: PermissionDecision) -> Action:
    """Returns a NEW Action (never mutates the input) with its
    permission_level/risk_level/approval_required overwritten by the
    authoritative `decision`, and its status transitioned via the existing
    action_state_machine: BLOCK -> ActionStatus.BLOCKED, everything else ->
    ActionStatus.PERMISSION_CHECKED. Raises ActionTransitionError (fail
    closed, reusing the existing typed error) if `action.status` is not a
    legal source state for that target — e.g. this is never called on an
    action that isn't VALIDATED. A BLOCKed action can never reach
    PERMISSION_CHECKED through this function, so it can never become
    eligible for execution in a later checkpoint.
    """
    target = (
        ActionStatus.BLOCKED
        if decision.outcome == PermissionOutcome.BLOCK
        else ActionStatus.PERMISSION_CHECKED
    )
    assert_transition(action.status, target)
    return action.model_copy(
        update={
            "status": target,
            "permission_level": decision.permission_level,
            "risk_level": decision.risk_level,
            "approval_required": decision.approval_required,
        }
    )
