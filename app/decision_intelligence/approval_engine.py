"""Deterministic Human Approval Engine (v0.1.3.3, spec sections 3-19).
AUTHORIZATION ONLY — nothing in this module executes an Action, invokes a
tool, or grants anything beyond flipping typed, fail-closed status fields.
See docs/decision_intelligence.md's v0.1.3.3 section for the full
IMPLEMENTED/NOT IMPLEMENTED split.

    PermissionDecision(REQUIRE_APPROVAL)
      -> create_approval_request()          ApprovalRequest(PENDING)
      -> advance_to_waiting_for_approval()   Action -> WAITING_FOR_APPROVAL
      -> decide_approval()                   ApprovalRequest -> APPROVED/REJECTED/CANCELLED
         (or expire_approval_request())      ApprovalRequest -> EXPIRED
      -> authorize_action()                  exact-hash check -> Action -> APPROVED
         (or finalize_action_from_approval_outcome())  Action -> REJECTED/CANCELLED
      -> consume_approval()                  ApprovalRequest.consumed = True
         (reserved for a future Action Executor; nothing here ever calls it)

v0.1.3.3.1 (security patch): `ApprovalRequest.status == APPROVED` is a
DECISION record, not a CURRENT AUTHORIZATION VALIDITY guarantee — an
APPROVED request can still be currently invalid (expired, already
consumed, or no longer hash-matching its Action) while `status` still
reads APPROVED, since EXPIRED remains reachable only from PENDING in the
existing state model (see expire_approval_request()). Both
`authorize_action()` and `consume_approval()` now route through ONE
authoritative gate, `assert_approval_valid()` (built on
`check_approval_validity()`/`validate_approval_for_action()`), which checks
status + action-ID binding + hash match + not-consumed + not-expired
together, so an APPROVED-but-expired-or-consumed request can no longer
authorize or be (re-)consumed. See "Authoritative approval validity" below
for the full design and the TOCTOU/atomicity caveat that persistence must
close in a future checkpoint.

Trust boundary (spec section 6/18): `decided_by` is a REQUIRED, explicit
caller-supplied identity. This module has no notion of "the current agent"
and never infers one — exactly like the existing task-scoped
`app.tools.approval_tools`, which documents "[r]esolving an approval is a
human action and is intentionally NOT exposed [to agent code] — it goes
through the service directly from the API/CLI/human layer, never from an
agent." The same rule applies here: `decide_approval()` must only ever be
called from that same trusted, non-agent layer, never from inside an
agent's own tool-calling loop. This module does not and cannot enforce
"who is allowed to call this function" (that is a caller-side/API-boundary
concern) — what it DOES enforce deterministically is that the caller
cannot approve a request it itself filed (`decided_by == requested_by` on
an APPROVE decision always fails closed; see SelfApprovalError).

Exact-action authorization (spec section 7/8): `authorize_action()` is the
ONLY path that may move an Action to `ActionStatus.APPROVED`, and it
requires BOTH `approval_request.action_id == action.id` (no cross-action
authorization, even on an accidental hash collision) AND
`compute_action_hash(action) == approval_request.action_hash` (the action's
security-relevant payload — action_type, tool_name, inputs,
expected_result, permission_level, risk_level, per action_hash.py — must be
byte-for-byte what was approved). A mismatch NEVER updates the old request
or silently re-approves; it raises `ApprovalHashMismatchError`, and the
only path forward is a brand new `ApprovalRequest` through
`create_approval_request()` again. Because `permission_level`/`risk_level`
are themselves hashed fields, a change to the authoritative permission
classification between approval-request-creation and authorization time is
already caught by this same hash check — no separate invariant is needed
for spec section 9's "if a security-relevant permission classification
changes" question; the answer this checkpoint chose is: the hash already
covers it, fail closed via ApprovalHashMismatchError.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.decision_intelligence.action_hash import compute_action_hash
from app.decision_intelligence.action_state_machine import assert_transition
from app.decision_intelligence.permission_engine import PermissionDecision, PermissionOutcome
from app.decision_intelligence.schemas import Action, ActionStatus, ApprovalRequest, ApprovalRequestStatus

# No blanket, unbounded approval is created through the normal factory path
# (spec section 11) — every ApprovalRequest built by create_approval_request()
# gets a bounded expiry unless the caller explicitly overrides it.
DEFAULT_APPROVAL_TTL = timedelta(hours=24)

ApprovalDecisionKind = Literal["APPROVE", "REJECT", "CANCEL"]

_DECISION_TARGET_STATUS: dict[str, ApprovalRequestStatus] = {
    "APPROVE": ApprovalRequestStatus.APPROVED,
    "REJECT": ApprovalRequestStatus.REJECTED,
    "CANCEL": ApprovalRequestStatus.CANCELLED,
}

# spec section 16: ActionStatus has no dedicated EXPIRED value. EXPIRED is
# mapped to CANCELLED — the closest existing terminal state semantically
# (an administrative lapse of the authorization window, not a human "no"
# (REJECTED) and not an execution failure (FAILED)). Both REJECTED and
# CANCELLED are already dead ends in action_state_machine.py (no outgoing
# transitions), matching decision_rules.py's equivalent choice for
# REJECTED/SUPERSEDED Decisions: reopening is explicitly not implemented
# yet, so a lapsed/rejected/cancelled Action requires a brand new Action
# (from a new ActionPlan revision) to try again, not a resurrection of this
# one.
_TERMINAL_ACTION_TARGET: dict[ApprovalRequestStatus, ActionStatus] = {
    ApprovalRequestStatus.REJECTED: ActionStatus.REJECTED,
    ApprovalRequestStatus.CANCELLED: ActionStatus.CANCELLED,
    ApprovalRequestStatus.EXPIRED: ActionStatus.CANCELLED,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Typed errors — every failure mode fails closed, nothing here falls back
# to a permissive default.
# --------------------------------------------------------------------------


class ApprovalEngineError(Exception):
    """Base class for all typed Approval Engine errors."""


class ActionApprovalMismatchError(ApprovalEngineError):
    def __init__(self, action_id: str, decision_action_id: str):
        super().__init__(
            f"PermissionDecision.action_id '{decision_action_id}' does not match Action.id '{action_id}'"
        )
        self.action_id = action_id
        self.decision_action_id = decision_action_id


class PermissionNotRequireApprovalError(ApprovalEngineError):
    def __init__(self, outcome: PermissionOutcome):
        super().__init__(
            f"PermissionDecision.outcome is {outcome.value}, not REQUIRE_APPROVAL — "
            "no ApprovalRequest may be created for it"
        )
        self.outcome = outcome


class InvalidActionStateForApprovalError(ApprovalEngineError):
    def __init__(self, current: ActionStatus, expected: ActionStatus):
        super().__init__(
            f"Action.status is {current.value}, but {expected.value} is required for this operation"
        )
        self.current = current
        self.expected = expected


class UnauthoritativeActionStateError(ApprovalEngineError):
    def __init__(self, action_id: str):
        super().__init__(
            f"Action '{action_id}' has not had apply_permission_decision() applied — its "
            "permission_level/risk_level are still proposed, not authoritative. Call "
            "app.decision_intelligence.permission_engine.apply_permission_decision() first."
        )
        self.action_id = action_id


class TrustedDecisionIdentityRequiredError(ApprovalEngineError):
    pass


class InvalidApprovalDecisionError(ApprovalEngineError):
    def __init__(self, decision: str):
        super().__init__(f"'{decision}' is not a supported approval decision (APPROVE/REJECT/CANCEL)")
        self.decision = decision


class ApprovalAlreadyDecidedError(ApprovalEngineError):
    def __init__(self, status: ApprovalRequestStatus):
        super().__init__(f"ApprovalRequest is already in terminal status {status.value}; it cannot be reopened")
        self.status = status


class SelfApprovalError(ApprovalEngineError):
    def __init__(self, approval_request_id: str, identity: str):
        super().__init__(
            f"'{identity}' cannot approve ApprovalRequest '{approval_request_id}' — it is also the requester"
        )
        self.approval_request_id = approval_request_id
        self.identity = identity


class ApprovalActionIdMismatchError(ApprovalEngineError):
    def __init__(self, approval_action_id: str, action_id: str):
        super().__init__(
            f"ApprovalRequest.action_id '{approval_action_id}' does not match Action.id '{action_id}' — "
            "an approval for one Action may never authorize another"
        )
        self.approval_action_id = approval_action_id
        self.action_id = action_id


class ApprovalHashMismatchError(ApprovalEngineError):
    def __init__(self, approved_hash: str, current_hash: str):
        super().__init__(
            f"Action payload no longer matches the approved hash ({approved_hash} != {current_hash}) — "
            "a new ApprovalRequest is required; the old one is not updated or reused"
        )
        self.approved_hash = approved_hash
        self.current_hash = current_hash


class ApprovalNotApprovedError(ApprovalEngineError):
    def __init__(self, status: ApprovalRequestStatus):
        super().__init__(f"ApprovalRequest.status is {status.value}, not APPROVED")
        self.status = status


class ApprovalOutcomeNotFinalError(ApprovalEngineError):
    def __init__(self, status: ApprovalRequestStatus):
        super().__init__(
            f"ApprovalRequest.status is {status.value}; expected REJECTED/CANCELLED/EXPIRED"
        )
        self.status = status


class ApprovalAlreadyConsumedError(ApprovalEngineError):
    def __init__(self, approval_request_id: str):
        super().__init__(f"ApprovalRequest '{approval_request_id}' was already consumed")
        self.approval_request_id = approval_request_id


class ApprovalNotExpirableError(ApprovalEngineError):
    def __init__(self, approval_request_id: str):
        super().__init__(f"ApprovalRequest '{approval_request_id}' has no expires_at set")
        self.approval_request_id = approval_request_id


class ApprovalNotYetExpiredError(ApprovalEngineError):
    def __init__(self, approval_request_id: str, expires_at: datetime, now: datetime):
        super().__init__(
            f"ApprovalRequest '{approval_request_id}' expires at {expires_at.isoformat()}, "
            f"which is after {now.isoformat()}"
        )
        self.approval_request_id = approval_request_id
        self.expires_at = expires_at
        self.now = now


class ApprovalExpiredError(ApprovalEngineError):
    """v0.1.3.3.1: raised when an APPROVED-but-expired request is used to
    authorize or consume — distinct from ApprovalNotYetExpiredError, which
    guards the PENDING -> EXPIRED status transition itself. This error
    guards CURRENT AUTHORIZATION VALIDITY, which is a separate concept from
    ApprovalRequest.status — see check_approval_validity()'s docstring."""

    def __init__(self, approval_request_id: str, expires_at: datetime | None, now: datetime):
        super().__init__(
            f"ApprovalRequest '{approval_request_id}' expired at "
            f"{expires_at.isoformat() if expires_at else '?'} (now={now.isoformat()}) "
            "and can no longer authorize or be consumed"
        )
        self.approval_request_id = approval_request_id
        self.expires_at = expires_at
        self.now = now


# --------------------------------------------------------------------------
# ApprovalRequest creation (spec section 4)
# --------------------------------------------------------------------------


def create_approval_request(
    action: Action,
    decision: PermissionDecision,
    *,
    requested_by: str,
    reason: str = "",
    expires_at: datetime | None = None,
) -> ApprovalRequest:
    """Builds a PENDING ApprovalRequest bound to the EXACT current payload
    of `action`. Does not mutate or transition `action` — see
    advance_to_waiting_for_approval() for the companion state-machine step.
    Fails closed: every precondition below raises a typed error rather than
    silently substituting a default.
    """
    if decision.action_id != action.id:
        raise ActionApprovalMismatchError(action.id, decision.action_id)
    if decision.outcome != PermissionOutcome.REQUIRE_APPROVAL or not decision.approval_required:
        raise PermissionNotRequireApprovalError(decision.outcome)
    if action.status != ActionStatus.PERMISSION_CHECKED:
        raise InvalidActionStateForApprovalError(action.status, ActionStatus.PERMISSION_CHECKED)
    if action.permission_level != decision.permission_level or action.risk_level != decision.risk_level:
        # The action still carries proposed, not authoritative, values —
        # apply_permission_decision() was never applied. Refuse to bind an
        # ApprovalRequest (and its action_hash) to a payload that doesn't
        # reflect the real authoritative classification.
        raise UnauthoritativeActionStateError(action.id)
    if not requested_by:
        raise TrustedDecisionIdentityRequiredError("requested_by must be a non-empty identity")

    resolved_expires_at = expires_at if expires_at is not None else _now() + DEFAULT_APPROVAL_TTL

    return ApprovalRequest(
        action_id=action.id,
        requested_by=requested_by,
        reason=reason,
        action_summary=action.title or action.action_type,
        risk_summary=(
            f"risk_level={decision.risk_level.value}; outcome={decision.outcome.value}; "
            f"reasons={','.join(decision.reason_codes)}"
        ),
        permission_level=decision.permission_level,
        estimated_cost=action.estimated_cost,
        proposed_inputs=dict(action.inputs),
        expected_effect=action.expected_result,
        action_hash=compute_action_hash(action),
        expires_at=resolved_expires_at,
    )


def advance_to_waiting_for_approval(action: Action) -> Action:
    """PERMISSION_CHECKED -> WAITING_FOR_APPROVAL via the existing, unmodified
    action_state_machine transition table. Raises ActionTransitionError
    (fail closed) from any other source state."""
    assert_transition(action.status, ActionStatus.WAITING_FOR_APPROVAL)
    return action.model_copy(update={"status": ActionStatus.WAITING_FOR_APPROVAL})


# --------------------------------------------------------------------------
# Approval decision (spec sections 6/10/18)
# --------------------------------------------------------------------------


def decide_approval(
    approval_request: ApprovalRequest,
    decision: ApprovalDecisionKind,
    *,
    decided_by: str,
) -> ApprovalRequest:
    """The only function that moves a PENDING ApprovalRequest to APPROVED/
    REJECTED/CANCELLED. EXPIRED is handled separately by
    expire_approval_request() (spec section 6). Returns a NEW
    ApprovalRequest; never mutates the input.

    Self-approval defense (spec section 18) applies ONLY to APPROVE: a
    requester cancelling or rejecting its own pending request is not a
    security bypass (neither path can ever lead to execution), so only
    `decided_by == requested_by` on an APPROVE decision fails closed.
    """
    if decision not in _DECISION_TARGET_STATUS:
        raise InvalidApprovalDecisionError(decision)
    if not decided_by:
        raise TrustedDecisionIdentityRequiredError("decided_by must be a non-empty, explicit trusted identity")
    if approval_request.status != ApprovalRequestStatus.PENDING:
        raise ApprovalAlreadyDecidedError(approval_request.status)
    if decision == "APPROVE" and decided_by == approval_request.requested_by:
        raise SelfApprovalError(approval_request.id, decided_by)

    target = _DECISION_TARGET_STATUS[decision]
    return approval_request.model_copy(
        update={"status": target, "decided_at": _now(), "decided_by": decided_by}
    )


def expire_approval_request(
    approval_request: ApprovalRequest, *, now: datetime | None = None
) -> ApprovalRequest:
    """PENDING -> EXPIRED, deterministic and time-injectable (no sleeps
    required in tests). Fails closed if the request has no `expires_at`
    (ApprovalNotExpirableError) or hasn't reached it yet
    (ApprovalNotYetExpiredError) — expiration is never assumed early."""
    if approval_request.status != ApprovalRequestStatus.PENDING:
        raise ApprovalAlreadyDecidedError(approval_request.status)
    if approval_request.expires_at is None:
        raise ApprovalNotExpirableError(approval_request.id)

    effective_now = now if now is not None else _now()
    if effective_now < approval_request.expires_at:
        raise ApprovalNotYetExpiredError(approval_request.id, approval_request.expires_at, effective_now)

    return approval_request.model_copy(
        update={
            "status": ApprovalRequestStatus.EXPIRED,
            "decided_at": effective_now,
            "decided_by": "system:expiration_policy",
        }
    )


def is_expired(approval_request: ApprovalRequest, *, now: datetime | None = None) -> bool:
    """Non-raising predicate: whether `approval_request` has passed its
    expiry, independent of whether expire_approval_request() has actually
    been called on it yet."""
    if approval_request.expires_at is None:
        return False
    effective_now = now if now is not None else _now()
    return effective_now >= approval_request.expires_at


# --------------------------------------------------------------------------
# Authoritative approval validity (v0.1.3.3.1, the single security gate)
# --------------------------------------------------------------------------
#
# CORE DISTINCTION (spec section 9/16 of the v0.1.3.3.1 patch):
# `ApprovalRequest.status` is a DECISION record — "a human approved the
# exact action" — and, once APPROVED, is deliberately never mutated again
# by this module (EXPIRED remains reachable only from PENDING, matching the
# existing state model; see expire_approval_request()). It is NOT the same
# thing as CURRENT AUTHORIZATION VALIDITY — whether that approval may still
# be used RIGHT NOW. An APPROVED request can be currently INVALID (expired,
# already consumed, or bound to an action payload that has since changed)
# while its `status` field still reads APPROVED. Anything that gates real
# authorization must therefore check validity, not just status, which is
# exactly what check_approval_validity()/validate_approval_for_action()
# exist to do, and what authorize_action()/consume_approval() now both
# route through rather than re-implementing their own partial checks.

_VALIDITY_REASON_PRIORITY: tuple[str, ...] = (
    "NOT_APPROVED",
    "ACTION_ID_MISMATCH",
    "HASH_MISMATCH",
    "ALREADY_CONSUMED",
    "EXPIRED",
)


class ApprovalValidityResult(BaseModel):
    """Structured, non-raising result of check_approval_validity(). Never a
    bare bool — mirrors PlanReadinessResult/PermissionDecision's
    ready/outcome + structured-reasons shape. `reason_codes` accumulates
    EVERY failing check (e.g. a request can be both HASH_MISMATCH and
    EXPIRED at once) rather than stopping at the first."""

    valid: bool
    reason_codes: list[str] = Field(default_factory=list)
    explanation: str = ""
    checked_at: datetime = Field(default_factory=_now)


def check_approval_validity(
    approval_request: ApprovalRequest,
    action: Action | None,
    *,
    now: datetime | None = None,
) -> ApprovalValidityResult:
    """The single authoritative validity check (spec section 2). Never
    raises. An approval is valid only if ALL of the following hold:

      1. status == APPROVED
      2. action_id matches (only checked when `action` is given)
      3. action_hash matches the action's CURRENT payload (only checked
         when `action` is given — this already covers permission/risk
         binding, since permission_level/risk_level are hashed fields;
         see action_hash.py and the v0.1.3.3 doc section on this)
      4. consumed is False
      5. current time has not reached expires_at (`now >= expires_at` is
         EXPIRED, not `now > expires_at` — exact equality denies)

    `action=None` is used only by consume_approval()'s self-contained check
    (status/consumed/expiry — the request alone, with no Action to hash
    against); every other caller, and validate_approval_for_action() in
    particular, always supplies `action`.
    """
    effective_now = now if now is not None else _now()
    reasons: list[str] = []

    if approval_request.status != ApprovalRequestStatus.APPROVED:
        reasons.append("NOT_APPROVED")
    if action is not None and approval_request.action_id != action.id:
        reasons.append("ACTION_ID_MISMATCH")
    if action is not None and compute_action_hash(action) != approval_request.action_hash:
        reasons.append("HASH_MISMATCH")
    if approval_request.consumed:
        reasons.append("ALREADY_CONSUMED")
    if approval_request.expires_at is not None and effective_now >= approval_request.expires_at:
        reasons.append("EXPIRED")

    return ApprovalValidityResult(
        valid=not reasons,
        reason_codes=reasons,
        explanation="valid" if not reasons else f"invalid: {', '.join(reasons)}",
        checked_at=effective_now,
    )


def validate_approval_for_action(
    approval_request: ApprovalRequest, action: Action, *, now: datetime | None = None
) -> ApprovalValidityResult:
    """The public, non-raising security gate a future Action Executor must
    call immediately before consume_approval()/execution (spec section 2/8
    of the v0.1.3.3.1 patch). Thin wrapper over check_approval_validity()
    with `action` mandatory, since an Executor always has one.

    TIME-OF-CHECK CAVEAT: calling this and getting `valid=True` does not by
    itself make later use of the same approval safe — nothing here is
    atomic. A future Executor must re-validate immediately before
    consuming/executing (ideally via the same durable row, consumed in one
    atomic operation), not cache this result. See the module docstring and
    docs/decision_intelligence.md's v0.1.3.3.1 section for the full
    TOCTOU/atomicity discussion; persistence/atomicity are explicitly NOT
    implemented by this patch.
    """
    return check_approval_validity(approval_request, action, now=now)


def _raise_for_validity_reason(reason: str, approval_request: ApprovalRequest, action: Action | None, now: datetime) -> None:
    if reason == "NOT_APPROVED":
        raise ApprovalNotApprovedError(approval_request.status)
    if reason == "ACTION_ID_MISMATCH":
        raise ApprovalActionIdMismatchError(approval_request.action_id, action.id)  # type: ignore[union-attr]
    if reason == "HASH_MISMATCH":
        raise ApprovalHashMismatchError(approval_request.action_hash, compute_action_hash(action))  # type: ignore[arg-type]
    if reason == "ALREADY_CONSUMED":
        raise ApprovalAlreadyConsumedError(approval_request.id)
    if reason == "EXPIRED":
        raise ApprovalExpiredError(approval_request.id, approval_request.expires_at, now)
    raise ApprovalEngineError(f"ApprovalRequest is invalid for an unrecognized reason: {reason}")


def assert_approval_valid(
    approval_request: ApprovalRequest, action: Action | None = None, *, now: datetime | None = None
) -> ApprovalValidityResult:
    """Raising variant of check_approval_validity(), used internally by
    authorize_action() and consume_approval() so both share exactly one
    validity implementation rather than two drifting, inconsistent checks.
    Raises the highest-priority failing reason (see
    _VALIDITY_REASON_PRIORITY) as its corresponding pre-existing typed
    error, so authorize_action()'s exception types/order for its original
    three checks (NOT_APPROVED/ACTION_ID_MISMATCH/HASH_MISMATCH) are
    unchanged from v0.1.3.3 — this patch only ADDS the ALREADY_CONSUMED and
    EXPIRED checks, both previously missing from authorize_action()
    entirely (the root cause this patch closes)."""
    effective_now = now if now is not None else _now()
    result = check_approval_validity(approval_request, action, now=effective_now)
    if result.valid:
        return result
    for reason in _VALIDITY_REASON_PRIORITY:
        if reason in result.reason_codes:
            _raise_for_validity_reason(reason, approval_request, action, effective_now)
    raise ApprovalEngineError("ApprovalRequest is invalid but no reason was recorded")  # unreachable


# --------------------------------------------------------------------------
# Exact-action authorization (spec sections 7/8) and finalization
# --------------------------------------------------------------------------


def authorize_action(action: Action, approval_request: ApprovalRequest, *, now: datetime | None = None) -> Action:
    """The ONLY path that may move an Action to ActionStatus.APPROVED.
    Delegates every precondition to assert_approval_valid() (status,
    action-ID binding, exact action_hash match, not-consumed, not-expired)
    — any failure fails closed with a typed error and never updates the
    old request or silently authorizes a changed/expired/consumed
    approval; the only way forward for a changed action is a new
    ApprovalRequest via create_approval_request()."""
    assert_approval_valid(approval_request, action, now=now)
    assert_transition(action.status, ActionStatus.APPROVED)
    return action.model_copy(update={"status": ActionStatus.APPROVED})


def finalize_action_from_approval_outcome(action: Action, approval_request: ApprovalRequest) -> Action:
    """Companion to authorize_action() for the non-approved terminal
    outcomes (REJECTED/CANCELLED/EXPIRED — spec sections 14/15/16). Always
    enforces action-ID binding. No hash check is performed: none of these
    outcomes can ever lead to execution, so a payload change is irrelevant
    to them."""
    if approval_request.status not in _TERMINAL_ACTION_TARGET:
        raise ApprovalOutcomeNotFinalError(approval_request.status)
    if approval_request.action_id != action.id:
        raise ApprovalActionIdMismatchError(approval_request.action_id, action.id)

    target = _TERMINAL_ACTION_TARGET[approval_request.status]
    assert_transition(action.status, target)
    return action.model_copy(update={"status": target})


# --------------------------------------------------------------------------
# Consumption / double-use protection (spec sections 12/13)
# --------------------------------------------------------------------------


def consume_approval(
    approval_request: ApprovalRequest, *, action: Action | None = None, now: datetime | None = None
) -> ApprovalRequest:
    """Marks an APPROVED, currently-valid ApprovalRequest as consumed.
    Reserved for a future Action Executor to call EXACTLY ONCE, immediately
    at the point real execution begins — nothing in this checkpoint ever
    calls it, and this module contains no execution logic whatsoever.
    Enforces "one approval authorizes one execution attempt of one exact
    action": a second call, or a call on an expired request, fails closed
    (ApprovalAlreadyConsumedError / ApprovalExpiredError) rather than
    silently re-authorizing.

    Routes through the same assert_approval_valid() gate authorize_action()
    uses (spec section 7: "make consumption require the same authoritative
    validity helper"). `action` is optional here — unlike
    validate_approval_for_action(), which always requires one — so existing
    callers that only have the ApprovalRequest in hand still get the
    status/consumed/expiry checks; passing `action` additionally re-checks
    action-ID binding and the exact action_hash before consuming, which a
    future Executor should always do (see the module docstring's TOCTOU
    note: validate immediately before consuming, on the same object).
    """
    effective_now = now if now is not None else _now()
    assert_approval_valid(approval_request, action, now=effective_now)
    return approval_request.model_copy(update={"consumed": True, "consumed_at": effective_now})
