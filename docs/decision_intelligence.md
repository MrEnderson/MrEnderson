# Decision & Action Intelligence (v0.1.3.6)

v0.1.2's Research Intelligence pipeline answers "is the evidence good enough
to compare candidates?" v0.1.3 extends the same philosophy — never trust an
LLM's own claim, verify deterministically — one stage further down the
pipeline, toward eventually letting Jarvis actually *act* on a decision:

```
OBJECTIVE
  -> RESEARCH
  -> EVIDENCE READINESS        app/research_intelligence/gate.py (v0.1.2, unchanged)
  -> DECISION                  app/decision_intelligence/schemas.py::Decision
  -> DECISION GATE             app/decision_intelligence/decision_rules.py
  -> ACTION PLAN                app/decision_intelligence/schemas.py::ActionPlan
  -> TOOL REGISTRY              app/decision_intelligence/tool_registry.py (v0.1.3.2)
  -> PERMISSION EVALUATION     app/decision_intelligence/permission_engine.py (v0.1.3.2)
  -> APPROVAL REQUEST          app/decision_intelligence/approval_engine.py (v0.1.3.3, persisted v0.1.3.4)
  -> HUMAN APPROVAL ENGINE     app/decision_intelligence/approval_engine.py (v0.1.3.3)
  -> EXACT-ACTION AUTHORIZATION app/decision_intelligence/approval_engine.py::authorize_action (v0.1.3.3)
  -> DURABLE ATOMIC CONSUMPTION app/database/repositories.py::ActionApprovalRequestRepository.consume_if_valid (v0.1.3.4)
  -> ACTION EXECUTOR           app/decision_intelligence/action_executor.py (v0.1.3.4)
  -> TRUSTED TOOL ADAPTER      app/decision_intelligence/tool_adapters.py (v0.1.3.4 — ONE real adapter: file.create_sandboxed)
  -> EXECUTION RESULT          app/decision_intelligence/schemas.py::ExecutionResult (v0.1.3.4: real, for the sandbox adapter only)
  -> VERIFICATION              app/decision_intelligence/tool_adapters.py::SandboxFileCreateAdapter.verify (v0.1.3.4)
  -> ACTION COMPLETED          reached only via the unmodified v0.1.3.1 state machine
  -> AUDIT                     existing app/security/audit.py, now wired in for EXECUTION_*/VERIFICATION_*/APPROVAL_CONSUMED (v0.1.3.4, best-effort)
```

Everything above remains SANDBOXED: exactly one real, side-effecting
adapter exists (`file.create_sandboxed`, writing a UTF-8 text file
strictly inside an application-controlled sandbox root). No other tool
this codebase defines (v0.1.3.2's `send_email`/`publish`/`delete_external`/
`spend_money`/`install_software`/`privileged_shell`) has a registered
adapter — attempting to execute any of them fails closed with
`ADAPTER_NOT_FOUND`, by construction, not by policy that could later be
loosened accidentally.

## IMPLEMENTED IN v0.1.3.1

All of `app/decision_intelligence/` — domain contracts and deterministic
lifecycle rules only. Nothing in this package makes a live model call, a
live research-provider call, or executes anything.

| Module | Responsibility |
|---|---|
| `schemas.py` | Pydantic domain contracts: `Decision`, `ActionPlan`, `Action`, `ApprovalRequest`, `ExecutionResult`, `VerificationResult`, `PlanReadinessResult`, and their status enums |
| `decision_rules.py` | The Decision state machine, the `comparison_ready` readiness invariant, the `compute_actionable`/`enforce_actionable_flag` deterministic override of any LLM-set `actionable` flag, and the Decision -> ActionPlan boundary (`assert_can_produce_plan`) |
| `action_state_machine.py` | The Action lifecycle state machine — explicit transition table, no arbitrary jumps, same shape as `app/orchestration/state_machine.py` |
| `plan_validation.py` | Deterministic ActionPlan structural validation: duplicate/self/unknown/cyclic dependency detection (same DFS approach as `app/orchestration/planner.py::_assert_no_cycles`), forward-dependency-ordering checks, and `evaluate_plan_readiness` |
| `action_hash.py` | Canonical SHA-256 action fingerprint an `ApprovalRequest` binds to |
| `retry_policy.py` | Deterministic `FailureCategory` retryability/replannability classification — metadata only, no retry execution |

### Decision lifecycle

```
PROPOSED -> INSUFFICIENT_EVIDENCE -> PROPOSED
PROPOSED -> READY_FOR_ACTION            (blocked unless comparison_ready)
READY_FOR_ACTION -> APPROVAL_REQUIRED -> APPROVED
READY_FOR_ACTION -> APPROVED            (approval not always required)
{PROPOSED, INSUFFICIENT_EVIDENCE, READY_FOR_ACTION, APPROVAL_REQUIRED} -> REJECTED | SUPERSEDED
```

`READY_FOR_ACTION` can never be reached while `comparison_ready` is `False`
— enforced in `apply_decision_transition`, independent of whatever status
or `actionable` value an LLM-driven decision-writer agent (not built yet)
sets on the object. `compute_actionable()` is the only trusted source of
truth for actionability; it ignores `Decision.actionable` entirely.

### Action lifecycle

```
PLANNED -> VALIDATED -> PERMISSION_CHECKED
PERMISSION_CHECKED -> WAITING_FOR_APPROVAL -> APPROVED -> EXECUTING
PERMISSION_CHECKED -> EXECUTING                          (no approval needed)
EXECUTING -> EXECUTION_SUCCEEDED -> VERIFYING -> VERIFIED -> COMPLETED
VERIFYING -> VERIFICATION_FAILED -> FAILED | BLOCKED
```

`FAILED`/`REJECTED`/`CANCELLED`/`BLOCKED`(->`CANCELLED`) are reachable as
fail-closed escape hatches from most non-terminal states. No path skips
approval (`WAITING_FOR_APPROVAL -> EXECUTING` is not a legal transition) or
verification (`EXECUTION_SUCCEEDED -> COMPLETED` and
`VERIFICATION_FAILED -> COMPLETED` are both illegal).

### Action hash

`action_hash.py::compute_action_hash` hashes only the fields whose change
should invalidate a prior approval: `action_type`, `tool_name`, `inputs`,
`expected_result`, `permission_level`, `risk_level`. Volatile lifecycle
metadata (`status`, timestamps, `retry_count`, `result`, `error`, `id`,
`estimated_cost`, `title`/`description`, `dependencies`, ...) is
deliberately excluded so an approval survives cosmetic edits and progress
updates but is invalidated by anything that changes what the action
actually does. See the module docstring for the full rationale.

### Retry/failure taxonomy

| Category | Auto-retryable? | Replannable? |
|---|---|---|
| TRANSIENT | yes | no |
| TOOL | yes (bounded policy, not implemented yet) | no |
| VERIFICATION | yes | yes |
| VALIDATION | no | no |
| PERMISSION | no | no |
| APPROVAL | no | no |
| BUDGET | no | no |
| SECURITY | never | no |
| UNKNOWN | no (fail closed) | no |

## IMPLEMENTED IN v0.1.3.2

`app/decision_intelligence/tool_registry.py` and
`app/decision_intelligence/permission_engine.py` — deterministic tool
metadata/registry and permission classification only. NO REAL TOOL
EXECUTION and NO APPROVAL GRANTING happen anywhere in this checkpoint.

| Module | Responsibility |
|---|---|
| `tool_registry.py` | `ToolDefinition` (application-controlled, frozen/immutable tool metadata — never something model/agent output can register directly), `ToolRegistry` (register/unregister/get/contains/list/resolve, all fail-closed), `build_default_tool_registry()` — the safe, non-executing P1-P5 tool catalog |
| `permission_engine.py` | `PermissionOutcome` (`ALLOW`/`ALLOW_WITH_AUDIT`/`REQUIRE_APPROVAL`/`BLOCK`), `PermissionDecision` (structured outcome + reason codes, never a bare bool), `evaluate_permission()` (the deterministic policy), `apply_permission_decision()` (the `VALIDATED -> PERMISSION_CHECKED`/`BLOCKED` state-machine integration) |

### Authority model

`Action.permission_level`/`Action.risk_level` are **PROPOSED** metadata — an
LLM/agent-driven planner may set them, but `evaluate_permission()` never
reads them as authoritative. The **AUTHORITATIVE** `permission_level`/
`risk_level` on the returned `PermissionDecision` are always derived from
the action's `action_type` (an explicit escalation table) and the resolved
`ToolDefinition`'s own declared floor, taking the maximum of the two.
`ToolDefinition.default_permission_level`/`default_risk_level` are a floor:
an Action can never be authorized below what its tool requires, no matter
what the agent claims. A proposed value below that floor is corrected, not
trusted, and flagged with `PERMISSION_ESCALATED`/`RISK_ESCALATED` reason
codes — this is exactly how a malicious/incorrect agent setting
`permission_level=P0` (`READ`) on an action whose tool requires `P4`/`P5`
is prevented from bypassing policy (see `tests/test_permission_engine.py`'s
`test_security_*` tests).

### P-tier -> outcome mapping (documented, spec section 6)

| Tier | Meaning | PermissionLevel | Outcome |
|---|---|---|---|
| P0 | internal reasoning (no tool) | `READ` | `ALLOW` |
| P1 | read-only | `READ` | `ALLOW` |
| P2 | internal/sandboxed creation | `WRITE` | `ALLOW_WITH_AUDIT` |
| P3 | reversible external change | `EXTERNAL_ACTION` | `REQUIRE_APPROVAL` (conservative choice — see below) |
| P4 | consequential external action | `EXTERNAL_ACTION` | `REQUIRE_APPROVAL` |
| P5 | financial | `FINANCIAL_ACTION` | `REQUIRE_APPROVAL` |
| P5 | privileged/system (install, shell, self-modification-adjacent) | `ADMIN` | `BLOCK` |

**P3 policy chosen:** `REQUIRE_APPROVAL`. No rollback/reversal engine exists
yet to make `ALLOW_WITH_AUDIT` safe for a genuine external mutation, even a
reversible one, so this checkpoint is conservative — operationally
identical to P4 today, but distinguished by `RiskLevel.MEDIUM` (not `HIGH`)
and its own reason codes, so a future checkpoint can differentiate the two
behaviorally without a schema change.

**P5 policy chosen:** split by `PermissionLevel`. `FINANCIAL_ACTION`
(`finance.spend_money`) -> `REQUIRE_APPROVAL`, a bounded workflow a future
Approval Engine can meaningfully gate. `ADMIN`
(`system.install_software`, `system.privileged_shell`, and anything else
that would expand Jarvis's own capability surface) -> `BLOCK`
unconditionally, matching spec section 16's explicit
"`privileged_shell` -> BLOCK by default" and the checkpoint's
NON-NEGOTIABLE CONSTRAINTS, which single out installing software, arbitrary
shell execution, and self-modification as categorically different from a
single bounded purchase.

Action-type escalation floor (`permission_engine.py::_ACTION_TYPE_FLOOR`):
`read` -> P1; `internal_create`/`sandbox_create` -> P2; `external_modify`
-> P3; `send`/`publish`/`delete` -> P4; `financial` -> P5 (financial);
`install`/`privileged` -> P5 (admin). `internal`/`no_op`/`manual`/
`decision_only` (reused from `plan_validation.py`'s
`_NO_TOOL_ACTION_TYPES`) are P0 and need no tool. Any other `action_type`
is **unknown** and always `BLOCK`s — it never defaults to a safe tier.

### Fail-closed behavior

Every one of these BLOCKs, never falls back to a default tool/permission,
and never raises out of `evaluate_permission()` (every failure path is a
`PermissionDecision`, not an exception, so callers never need
exception-handling around normal fail-closed behavior):

- unknown tool (`UNKNOWN_TOOL`)
- disabled tool (`TOOL_DISABLED`)
- tool/action_type incompatible, or `action_type` entirely unrecognized
  (`UNSUPPORTED_ACTION_TYPE`)
- an action requiring a tool with no `tool_name` set (`MISSING_TOOL`)
- an `ADMIN`-floor tool/action (`FORBIDDEN_CAPABILITY` + `POLICY_BLOCK`)

Reason codes used: `TOOL_ALLOWED`, `AUDIT_REQUIRED`, `APPROVAL_REQUIRED`,
`UNKNOWN_TOOL`, `TOOL_DISABLED`, `UNSUPPORTED_ACTION_TYPE`,
`PERMISSION_ESCALATED`, `RISK_ESCALATED`, `HIGH_RISK`,
`FORBIDDEN_CAPABILITY`, `MISSING_TOOL`, `POLICY_BLOCK`.

### Action-state integration

`apply_permission_decision(action, decision)` reuses the existing
`action_state_machine.py` transition table (no new states, no new edges):
`outcome=BLOCK -> ActionStatus.BLOCKED`, everything else (`ALLOW`,
`ALLOW_WITH_AUDIT`, `REQUIRE_APPROVAL`) `-> ActionStatus.PERMISSION_CHECKED`,
with `assert_transition()` still enforcing that only a legal source state
(`VALIDATED`) can reach either — an illegal source state raises
`ActionTransitionError`, same as v0.1.3.1. Because `BLOCKED`'s only legal
next state is `CANCELLED` (unchanged from v0.1.3.1), a blocked Action can
never reach `EXECUTING` through this or any future path in the existing
state machine. `REQUIRE_APPROVAL` only sets `Action.approval_required =
True` on the resulting `PERMISSION_CHECKED` action here in the Permission
Engine — it does **not** itself create an `ApprovalRequest`, notify anyone,
or grant anything; that is the Approval Engine's job, implemented in
v0.1.3.3 (see that section below) as `approval_engine.py`.

### Trusted registration boundary

`ToolRegistry.register()` only accepts an already-constructed
`ToolDefinition` instance (`isinstance`-checked; a `dict`/duck-typed object
raises `TypeError`). `ToolDefinition` has no field capable of holding a
Python callable, shell command, URL-as-code, or import path, is `frozen`
(immutable after construction), and tool names are validated against a
strict lowercase-dotted pattern. There is no code path from "model/agent
output" to "registered executable capability" — tool definitions are
application-controlled configuration, the same trust tier as
`app/agents/registry.py`'s `AgentDescriptor` registrations.

### Reused vs. new abstractions (v0.1.3.2)

Reused, not duplicated:

- `app.database.models.PermissionLevel`/`RiskLevel` — same enums `Action`
  already used in v0.1.3.1; `ToolDefinition.default_permission_level`/
  `default_risk_level` reuse them too, rather than introducing a parallel
  `P0`-`P5` enum.
- `action_state_machine.py`'s `assert_transition`/`ActionTransitionError` —
  `apply_permission_decision()` calls straight into it rather than
  re-implementing transition checking.
- `plan_validation.py`'s `requires_tool()`/`_NO_TOOL_ACTION_TYPES` — reused
  as-is to identify P0 (no-tool) action types.
- The `ready`/structured-report shape convention from `PlanReadinessResult`
  is echoed by `PermissionDecision`'s `outcome` + `reason_codes` (never a
  bare bool).

New, deliberately not merged into an existing concept:

- `PermissionOutcome`/`PermissionDecision` — no prior equivalent existed;
  `app/security/approvals.py::classify_risk` is prose-keyword-based
  defense-in-depth over free text, not a structured, tool-aware decision.
- `ToolDefinition`/`ToolRegistry` — no prior tool abstraction existed
  (`app/tools/__init__.py` was empty; `app/tools/research_tools.py`'s
  `ResearchProvider` is a live-integration seam, not a permission-aware
  catalog).

## Persistence (v0.1.3.2)

`ToolDefinition` and `PermissionDecision` remain plain
Pydantic/application-configuration objects — **no new SQLAlchemy models or
Alembic migration were added.** The tool catalog is built in-process by
`build_default_tool_registry()`; nothing about it needs to be queried
across process boundaries yet. Persisting `PermissionDecision` history (for
audit) is deferred to whichever future checkpoint actually wires
`app/security/audit.py` into this pipeline — this checkpoint only ensures
`PermissionDecision` carries enough structured data (`action_id`,
`outcome`, `reason_codes`, `policy_source`, `evaluated_at`) for that
checkpoint to emit `PERMISSION_CLASSIFIED`/`PERMISSION_ESCALATED`/
`PERMISSION_BLOCKED` audit events without a schema change.

## API (v0.1.3.2)

None. No new routes were added — consistent with "No public
action-execution API" (spec section 20).

## IMPLEMENTED IN v0.1.3.3

`app/decision_intelligence/approval_engine.py` — the deterministic Human
Approval Engine. AUTHORIZATION ONLY: nothing in this module executes an
Action, invokes a tool, or performs a real side effect.

```
PermissionDecision(REQUIRE_APPROVAL)
  -> create_approval_request()          ApprovalRequest(PENDING)
  -> advance_to_waiting_for_approval()   Action -> WAITING_FOR_APPROVAL
  -> decide_approval()                   ApprovalRequest -> APPROVED/REJECTED/CANCELLED
     (or expire_approval_request())      ApprovalRequest -> EXPIRED
  -> authorize_action()                  exact-hash check -> Action -> APPROVED
     (or finalize_action_from_approval_outcome())  Action -> REJECTED/CANCELLED
  -> consume_approval()                  ApprovalRequest.consumed = True (reserved for
                                          a future Action Executor; never called here)
```

| Function | Responsibility |
|---|---|
| `create_approval_request()` | Builds a `PENDING` `ApprovalRequest` bound to the action's *authoritative* payload. Fails closed unless: the decision's `action_id` matches, `outcome == REQUIRE_APPROVAL` and `approval_required` is true, the action is `PERMISSION_CHECKED`, and the action's `permission_level`/`risk_level` already equal the decision's authoritative values (i.e. `apply_permission_decision()` was applied first — see `UnauthoritativeActionStateError`). Every request gets a bounded `expires_at` (`DEFAULT_APPROVAL_TTL` = 24h) unless the caller explicitly overrides it — no unbounded blanket approval is created through this path. |
| `advance_to_waiting_for_approval()` | `PERMISSION_CHECKED -> WAITING_FOR_APPROVAL`, via the unmodified v0.1.3.1 state machine. |
| `decide_approval()` | The only function that moves `PENDING -> APPROVED/REJECTED/CANCELLED`. Requires an explicit, non-empty `decided_by` trusted identity (see trust boundary below). Self-approval (`decided_by == requested_by`) fails closed **only on APPROVE** — a requester rejecting/cancelling its own request is not a security bypass. |
| `expire_approval_request()` / `is_expired()` | Deterministic, time-injectable (`now=...`) `PENDING -> EXPIRED`. No sleeps anywhere in the test suite. |
| `authorize_action()` | The **only** path to `ActionStatus.APPROVED`. Requires `approval_request.status == APPROVED`, exact `action_id` binding, and `compute_action_hash(action) == approval_request.action_hash`. Any mismatch raises `ApprovalHashMismatchError` — the old request is never mutated or silently reused; the only recovery is a brand new `ApprovalRequest`. |
| `finalize_action_from_approval_outcome()` | Companion for `REJECTED`/`CANCELLED`/`EXPIRED` outcomes -> `Action.status` `REJECTED`/`CANCELLED`/`CANCELLED` respectively (see below for why `EXPIRED` maps to `CANCELLED`). |
| `consume_approval()` | Marks an `APPROVED` request `consumed=True`. A second call raises `ApprovalAlreadyConsumedError` — double-use protection. Reserved for a future Action Executor; nothing in this checkpoint calls it. |

### Trust boundary (spec section 6/18)

`decided_by` is a **required, explicit, caller-supplied identity** — this
module has no notion of "the current agent" and never infers one. This
mirrors the existing task-scoped rule in `app/tools/approval_tools.py`:
*"[r]esolving an approval is a human action and is intentionally NOT
exposed [to agent code] — it goes through the service directly from the
API/CLI layer, never from an agent."* The same applies here:
`decide_approval()` must only ever be called from that same trusted,
non-agent layer. This module cannot enforce *who* is allowed to call it
(that's a caller-side/API-boundary concern for a future checkpoint) — what
it DOES enforce deterministically is that the caller cannot approve a
request it itself filed.

### Exact-action authorization (spec sections 7/8/9)

`authorize_action()` requires **both** `approval_request.action_id ==
action.id` (no cross-action authorization, even if two different actions'
payloads happen to hash identically — see
`test_authorize_action_cannot_authorize_a_different_action_despite_matching_hash`)
**and** `compute_action_hash(action) == approval_request.action_hash`
(byte-for-byte the same security-relevant payload that was approved —
`action_type`, `tool_name`, `inputs`, `expected_result`,
`permission_level`, `risk_level`, per `action_hash.py`). Because
`permission_level`/`risk_level` are themselves hashed fields, **a change to
the authoritative permission classification between request-creation and
authorization time is already caught by this same hash check** — this is
the checkpoint's answer to spec section 9's "if a security-relevant
permission classification changes" question: no separate invariant was
needed, the hash already covers it, and it fails closed
(`ApprovalHashMismatchError`) rather than silently re-approving.
Lifecycle-only fields (`title`, `description`, `estimated_cost`,
`retry_count`, ...) are excluded from the hash (same allowlist as
v0.1.3.1) and do **not** invalidate an approval.

### Expiration design (spec sections 11/16)

Every `ApprovalRequest` built via `create_approval_request()` gets a
bounded `expires_at` (default 24h from creation) unless the caller
overrides it — arbitrary long-lived blanket approval is not possible
through the normal path. `expire_approval_request()` only transitions
`PENDING -> EXPIRED` (matching spec section 10's transition table
literally) and is deterministic/time-injectable rather than wall-clock or
sleep-based. `ActionStatus` has no dedicated `EXPIRED` value, so
`finalize_action_from_approval_outcome()` maps an `EXPIRED` request to
`ActionStatus.CANCELLED` — the closest existing terminal state
semantically (an administrative lapse of the authorization window, not a
human "no" (`REJECTED`) and not an execution failure (`FAILED`)). Both
`REJECTED` and `CANCELLED` are already dead ends in
`action_state_machine.py` (no outgoing transitions), matching
`decision_rules.py`'s equivalent choice for `REJECTED`/`SUPERSEDED`
Decisions — reopening a lapsed/rejected/cancelled Action is explicitly not
implemented; a new attempt requires a brand new `Action` from a new
`ActionPlan` revision.

### Consumption design (spec sections 12/13)

`consume_approval()` exists to let a **future** Action Executor mark an
`APPROVED` request as used exactly once, immediately at the point real
execution begins. Nothing in this checkpoint calls it — it is a contract
and a double-use guard (`ApprovalAlreadyConsumedError` on a second call),
not part of any execution path, since no execution path exists yet.
Deliberately not coupled to execution: implementing the guard now, ahead of
the Executor, means the Executor's only job later is "call
`consume_approval()` once, right before acting" rather than inventing its
own double-use bookkeeping.

### Reconciliation with the existing task-scoped Approval concept (spec section 20)

v0.1.3.1 already introduced `ApprovalRequestStatus`
(`PENDING/APPROVED/REJECTED/EXPIRED/CANCELLED`) as deliberately distinct
from the pre-existing `app.database.models.ApprovalStatus`
(`PENDING/APPROVED/REJECTED` only). This checkpoint keeps them **separate**
(option B) rather than merging:

| | `app.database.models.Approval`/`ApprovalStatus` | `ApprovalRequest`/`ApprovalRequestStatus` |
|---|---|---|
| **Purpose** | A coarse, human-readable go/no-go gate on a `Task` (`requested_action: str` free text) | Cryptographic, exact-payload authorization of one specific `Action` |
| **Ownership/layer** | `app.services.approval_service` / `app.tools.approval_tools`, SQLAlchemy-persisted, task-orchestration layer | `app.decision_intelligence`, pure domain object (no persistence yet), Decision/Action pipeline layer |
| **Binding** | None — approving it just flips the linked `Task` to `READY` | `action_hash` binds it to an exact `Action` payload; `action_id` binds it to an exact `Action` identity |
| **States needed** | 3 (`PENDING/APPROVED/REJECTED`) — a task either proceeds or fails | 5 — also needs `EXPIRED` (bounded authorization windows) and `CANCELLED` (an action superseded before a human ever decided) |
| **Consumption tracking** | None | `consumed`/`consumed_at` — one approval authorizes one execution attempt |

**Conversion boundary:** none exists yet. A future checkpoint might want a
`Task`'s aggregate approval state to reflect whether all of its `Action`s
are individually approved, but that mapping is out of scope here and not
attempted.

**Why merging would be unsafe:** forcing the coarse task-level `Approval`
to carry hash-binding/consumption/self-approval semantics it was never
designed for (and that its SQLAlchemy schema doesn't have columns for)
would either silently weaken those guarantees for real money/tooling
decisions, or force the new `ApprovalRequest` to drop `EXPIRED`/
`CANCELLED`/consumption tracking to fit the older 3-state enum — either
direction loses safety-relevant information. The two concepts answer
different questions ("should this task keep going?" vs. "is this exact
action payload authorized to run?") and are kept as two deliberately
separate abstractions.

### Documentation cleanup (spec section 2)

The v0.1.3.2 write-up of this document dropped a distinction it should
have kept: the deterministic Action/Tool **Permission Engine**
(`evaluate_permission()`, classification of what permission/risk tier an
Action+Tool pair requires) **is fully implemented** as of v0.1.3.2. What
remains **not** implemented is **runtime agent/workspace-specific grant
enforcement** — nothing today cross-checks an `Action`'s authoritative
`PermissionDecision` against the *proposing agent's* actual grants
(`app/security/permissions.py::check_permission`, which is keyed on
`agent_type` and is still unaware of `Action`/`PermissionDecision`
entirely), and there is no workspace-scoped grant concept at all (grants
are static/global per `AgentRegistry`). This is a distinct, still-open
integration gap, not a statement that permission classification itself is
unbuilt. See the corrected "NOT IMPLEMENTED YET" list below.

## IMPLEMENTED IN v0.1.3.3.1 — Approval Validity Hardening

Narrow security patch, closing a loophole found in review: v0.1.3.3's
`authorize_action()`/`consume_approval()` checked `ApprovalRequest.status
== APPROVED` but never checked `consumed` or `expires_at`, so an
**APPROVED, unconsumed request whose `expires_at` had already passed could
still authorize or be consumed.** `expires_at` only governed the
`PENDING -> EXPIRED` status transition — it did not constrain whether an
already-`APPROVED` request was still currently usable.

### Status vs. current authorization validity

These are two different questions, and this patch's central fix is
treating them as such:

- **`ApprovalRequest.status == APPROVED`** answers *"did a human approve
  the exact action?"* — a decision record, set once by `decide_approval()`
  and (deliberately) never mutated again by this module. `EXPIRED` remains
  reachable only from `PENDING` (unchanged from v0.1.3.3 — see
  `expire_approval_request()`), so an approved-then-lapsed request's
  `status` field still reads `APPROVED`.
- **"Is this approval currently valid?"** answers *"may this specific,
  unexpired, unconsumed, hash-matching approval authorize this Action
  right now?"* — computed fresh, every time, by
  `check_approval_validity()`/`validate_approval_for_action()`. An
  `APPROVED` request can be currently **invalid** (expired, already
  consumed, or no longer hash-matching) while its `status` still says
  `APPROVED`. Nothing that gates real authorization may treat `status`
  alone as sufficient.

### The single validity gate

`app/decision_intelligence/approval_engine.py` gained:

| Function | Shape | Purpose |
|---|---|---|
| `check_approval_validity(request, action, *, now=None)` | non-raising, structured (`ApprovalValidityResult`) | The one authoritative check. `action=None` supports `consume_approval()`'s self-contained (no-Action) check; every other caller supplies `action`. Accumulates *every* failing reason rather than stopping at the first. |
| `validate_approval_for_action(request, action, *, now=None)` | non-raising, `action` mandatory | The public gate a future Action Executor must call immediately before consuming/executing. Thin wrapper over `check_approval_validity()`. |
| `assert_approval_valid(request, action=None, *, now=None)` | raising | Internal, shared by `authorize_action()`/`consume_approval()` so both use exactly one implementation. Raises the highest-priority failing reason as its typed error (`NOT_APPROVED` > `ACTION_ID_MISMATCH` > `HASH_MISMATCH` > `ALREADY_CONSUMED` > `EXPIRED`) — the first three preserve `authorize_action()`'s exact pre-existing exception types/order from v0.1.3.3, so no v0.1.3.3 test needed to change. |

An approval is valid only if **all** hold: `status == APPROVED`; `action_id`
matches; `action_hash` matches the Action's current payload (this already
covers permission/risk binding — both are hashed fields, unchanged
invariant from v0.1.3.3); `consumed is False`; and `now < expires_at`
(exact equality, `now >= expires_at`, denies — tested explicitly).

### What changed in `authorize_action()` / `consume_approval()`

Both gained an optional keyword-only `now: datetime | None = None` for
deterministic time injection (default: real current time — fully backward
compatible, no existing call site needed to change) and now route through
`assert_approval_valid()` instead of hand-rolled partial checks.
`consume_approval()` additionally gained an optional `action: Action |
None = None` — when omitted (all existing v0.1.3.3 call sites), it gets
the status/consumed/expiry checks; when supplied, it additionally
re-verifies action-ID binding and the exact hash before consuming, which a
future Executor should always do.

### Time-of-check / future atomicity requirement (spec section 8)

`validate_approval_for_action()` returning `valid=True` is **not** by
itself a safety guarantee for later use — nothing in this patch is atomic,
and this patch does not claim to fully eliminate TOCTOU (time-of-check to
time-of-use) concerns. The intended boundary for the future Action
Executor is:

```
durable ApprovalRequest row -> validate -> consume atomically -> execute
```

Persistence and atomic consume-then-execute are explicitly **NOT**
implemented by this patch (no migration was added — see "Persistence"
below) — this is documented here as a hard requirement for whichever
checkpoint builds the Action Executor (v0.1.3.4), not solved now.

### Reused vs. new (v0.1.3.3.1)

Reused: `action_hash.compute_action_hash`, the `ApprovalEngineError` typed
family (four of its five original members are unchanged), the
`ApprovalValidityResult`/structured-report shape convention already used
by `PlanReadinessResult`/`PermissionDecision`.

New: `ApprovalValidityResult`, `check_approval_validity()`,
`validate_approval_for_action()`, `assert_approval_valid()`,
`ApprovalExpiredError` (distinct from the pre-existing
`ApprovalNotYetExpiredError`, which guards the `PENDING -> EXPIRED`
transition itself, not post-approval validity).

## IMPLEMENTED IN v0.1.3.4 — Durable Authorization + Sandboxed Action Executor

The FIRST REAL ACTION EXECUTION capability in this codebase. Strictly
sandboxed: exactly ONE adapter (`file.create_sandboxed`) ever performs a
real side effect, and that side effect is a single UTF-8 text file write
strictly inside an application-controlled directory.

| Module | Responsibility |
|---|---|
| `app/decision_intelligence/sandbox_fs.py` | Pure path-safety validation: rejects absolute/UNC/drive paths, `..`/`.` traversal, null bytes, empty input, symlinks (at the leaf or anywhere in the resolved chain), disallowed extensions, oversized content, and overwrite of an existing target — all via `Path.resolve()` + `is_relative_to()`, never a string-prefix check. |
| `app/decision_intelligence/tool_adapters.py` | `ToolAdapter` protocol, `ToolAdapterRegistry` (the trusted-capability counterpart to v0.1.3.2's metadata-only `ToolRegistry`), `ExecutionContext`, and `SandboxFileCreateAdapter` — the one real adapter. |
| `app/decision_intelligence/action_executor.py` | `execute_action()` — the single Executor entry point; owns every `ActionStatus` transition; never lets an adapter decide one. |
| `app/decision_intelligence/approval_persistence.py` | Translation layer between the pure-domain `ApprovalRequest` and its durable row — the only module that knows about both. |
| `app/database/models.py::ActionApprovalRequest` / `app/database/repositories.py::ActionApprovalRequestRepository` | Durable `ApprovalRequest` persistence, including the atomic, single-consumer `consume_if_valid()`. |

### Metadata vs. capability (spec sections 11/12)

`ToolDefinition` (v0.1.3.2) says what a tool is *allowed to represent*;
`ToolAdapter` (this checkpoint) says what *trusted code* actually performs
it. `build_default_tool_registry()` still defines all eleven tools from
v0.1.3.2 (P1 through P5); `build_default_adapter_registry()` registers
exactly one adapter (`file.create_sandboxed`). Every other tool — including
`mock.external_action`, `communication.send_email`, `finance.spend_money`,
`system.privileged_shell`, all of them — has a `ToolDefinition` but no
adapter, so attempting to execute any of them fails closed with
`ADAPTER_NOT_FOUND`. An `Action` can request routing by `tool_name`
STRING only; nothing in either registry ever accepts a callable, an import
path, a class name, a module path, or a shell/subprocess command as a
registration.

### Sandbox boundary (spec sections 4/6-10)

`sandbox_root` is trusted application configuration
(`Settings.sandbox_root`, default `runtime/sandbox`) — never chosen by an
Action/model input. `resolve_sandbox_path()` rejects, before any
filesystem call: absolute paths (POSIX, Windows, drive-relative, UNC),
`..`/`.` traversal (in `/` or `\` form), null bytes, empty input, and a
disallowed extension (conservative allowlist: `.txt/.md/.json/.csv/.log/
.yaml/.yml` — no extension at all is rejected too, deliberately stricter
than necessary and easy to loosen later). It then resolves the joined path
and checks `resolved_target.is_relative_to(resolved_sandbox_root)` —
never a string-prefix check, which a sibling directory like
`sandbox-evil/` would defeat. An existing symlink is never followed,
whether at the leaf or anywhere in the parent chain (`Path.resolve()`
dereferences on-disk symlinks, so a symlink planted inside the sandbox
pointing outside it is caught by the same containment check). Content size
is capped at 1 MiB (`sandbox_fs.MAX_CONTENT_BYTES`), checked before any
write. Overwrite is never allowed — no `overwrite=True` escape hatch
exists in this checkpoint.

**Known limitation:** Windows junctions/reparse points are not exercised
by an automated test — creating one requires either administrator
privileges or shell tooling (`mklink /J`), neither appropriate to invoke
from within this test suite. The `resolve()`-based containment check
should still catch a junction the same way it catches a symlink (both are
followed by `Path.resolve()` on Windows), but this is not verified by a
dedicated regression test in this checkpoint.

### Action Executor lifecycle (spec section 13)

`execute_action()` never raises for a legitimate "this Action cannot run"
outcome (unknown tool, no adapter, `BLOCK`ed permission, missing/invalid/
expired/consumed approval, already-`COMPLETED` Action) — those return a
structured `ExecutionOutcome` with a failed `ExecutionResult`, exactly like
`evaluate_permission()` never raising for a `BLOCK`. It raises a typed
`ActionExecutorError` only for genuine caller misuse (e.g.
`decision.action_id != action.id`). Every transition
(`PERMISSION_CHECKED`/`APPROVED -> EXECUTING -> EXECUTION_SUCCEEDED ->
VERIFYING -> VERIFIED -> COMPLETED`, or the various fail-closed exits) goes
through the unchanged v0.1.3.1 `action_state_machine.assert_transition()`
— the Executor owns every status change; no adapter ever sets one. A fail-
closed refusal from `APPROVED`/`WAITING_FOR_APPROVAL` maps to `CANCELLED`
rather than `FAILED` (illegal from those states in the existing state
machine — see `action_executor._FAIL_TARGET_BY_SOURCE`), matching the
precedent `approval_engine.py` already set for `EXPIRED -> CANCELLED`.

P2 (`ALLOW_WITH_AUDIT`, e.g. `file.create_sandboxed`) executes without any
`ApprovalRequest` — the Executor still requires the actual authoritative
`PermissionDecision`, it just never gates on approval for that outcome
(spec section 14). `REQUIRE_APPROVAL` actions require the Action to already
be `ActionStatus.APPROVED` (i.e. already passed `authorize_action()`) AND
an `ApprovalRequest` supplied; the Executor then **revalidates it fresh**
via `validate_approval_for_action()` — against the **durable row** when
`approval_repo` is given, never a cached/earlier result (spec section 19)
— before consuming it. No P3/P4/P5 real tool executes in this checkpoint
(none has an adapter); tests exercise the approval-gated path with an
in-memory fake adapter registered under `communication.send_email` in an
isolated `ToolAdapterRegistry`, never the shared one.

### Atomic approval consumption (spec sections 18/19/26/31)

`ActionApprovalRequestRepository.consume_if_valid()` is a single
conditional `UPDATE ... WHERE id=:id AND consumed=0 AND status='APPROVED'
AND action_id=:action_id AND action_hash=:hash AND (expires_at IS NULL OR
expires_at > :now)`, followed by an immediate `COMMIT` (the only method in
the repository layer that commits rather than flushes — deliberately, since
being the durable atomicity boundary is its entire purpose). Exactly one
caller can ever see `rowcount == 1` for the same row; every other
concurrent or subsequent caller sees `0` and is refused. Verified by both
a same-process sequential double-attempt test and a true
`asyncio.gather()` test using two independent `AsyncSession`s racing
against the same row.

### Failure classification (spec section 22)

A new `ExecutorFailureCode` enum (`VALIDATION_FAILURE`/
`PERMISSION_FAILURE`/`APPROVAL_FAILURE`/`ADAPTER_NOT_FOUND`/
`SANDBOX_VIOLATION`/`TOOL_EXECUTION_FAILURE`/`VERIFICATION_FAILURE`/
`INTERNAL_FAILURE`) is the fine-grained `ExecutionResult.error_code`;
`ExecutionResult.error_type` stays the reused, coarser `FailureCategory`
via the `EXECUTOR_FAILURE_CATEGORY` mapping (`SANDBOX_VIOLATION ->
SECURITY`, matching `retry_policy.py`'s existing "never auto-retryable"
treatment of security failures). No LLM ever classifies a failure — every
code is assigned by deterministic code in `action_executor.py`/
`tool_adapters.py` (verified by a structural test asserting neither module
mentions `anthropic`/`openai`/`httpx`/`requests.`).

### Deterministic verification (spec section 23)

`SandboxFileCreateAdapter.verify()` re-derives every claim from the actual
filesystem — existence, containment inside the sandbox root, regular-file-
ness (not a directory, not a symlink), byte length, SHA-256 content hash,
and UTF-8 round-trip — never trusting what `execute()` merely reported.
No LLM verifier exists or is planned for this adapter.

### Partial side-effect failure (spec section 25)

`ExecutionResult.side_effect_occurred` is set `True` truthfully whenever
the adapter actually wrote the file, independent of whether the overall
attempt is ultimately reported as failed (e.g. a buggy adapter that writes
correctly but reports a mismatched hash) — verified by a test using a
real file write with a deliberately corrupted report, asserting the file
genuinely exists on disk while the Action still ends at `FAILED`, never
`COMPLETED`. Verification failure never triggers an automatic retry or an
automatic deletion of the artifact — fail and report, as specified.

### Idempotency boundary (spec section 20) — HONEST, NOT "exactly once"

An already-`COMPLETED` `Action` is never re-executed — checked first, before
any adapter is even resolved. Beyond that, this checkpoint's guarantee is
narrower than exactly-once: no-overwrite is what actually stops a literal
retry of the identical write from duplicating it (an incidental, not
purpose-built, protection), and nothing here persists `Action`/
`ExecutionResult` durably, so a genuine crash mid-flight can leave the
system unable to tell *why* a file exists or *why* an approval was
consumed without one. See "Transaction / crash-window honesty" below —
this is a deliberate, documented limitation, not an oversight.

### Transaction / crash-window honesty (spec section 30)

Durable approval consumption (a SQL transaction, committed immediately)
and the sandbox filesystem write (not transactional; cannot be) are two
separate operations. Two real failure windows exist and are **not** solved
by this checkpoint:

1. **Approval consumed (committed) -> process crashes before the file
   write.** The approval is durably marked used; no file exists. No
   automatic recovery — a human or future reconciliation process must
   notice the `Action` never reached `COMPLETED`.
2. **File written -> process crashes before anything else is persisted.**
   Nothing here persists `Action`/`ExecutionResult`/`VerificationResult`,
   so the file's existence carries no durable record of why it exists. A
   later identical attempt is blocked by `SandboxTargetExistsError`
   (accidental protection, not a designed idempotency record).

v0.1.3.5 (not implemented — see "Recommendation" in the delivery report)
would need durable `Action`/`ExecutionResult` persistence plus an explicit
reconciliation pass to close these windows; this checkpoint does not
pretend to solve exactly-once distributed side effects.

## IMPLEMENTED IN v0.1.3.5 — Durable Execution State + Deterministic Reconciliation

Adds DURABILITY AND RECOVERY on top of the strictly-sandboxed v0.1.3.4
Action Executor. **No new real capability was added** — the only real
side-effecting adapter remains `file.create_sandboxed`; this checkpoint is
entirely about surviving a crash/restart/duplicate-request around it.

```
Durable Action -> Durable ExecutionAttempt -> Executor -> side effect
  -> Durable ExecutionResult -> Verification -> Durable VerificationResult
  -> Durable final Action state

  (after a restart)

Database -> Reconciliation Engine -> inspect durable state
  -> inspect actual side effect -> classify -> recover / verify / block /
     require human review
```

| Module | Responsibility |
|---|---|
| `app/database/models.py` | `ActionRecord`, `ExecutionAttemptRecord`, `ExecutionResultRecord`, `VerificationResultRecord` (+ `PersistedActionStatus`, `ExecutionAttemptStatus`, `ResultProvenance`) — durable mirrors of the pydantic domain objects. |
| `app/database/repositories.py` | `ActionRecordRepository` (optimistic concurrency), `ExecutionAttemptRepository` (atomic execution claim), `ExecutionResultRepository`, `VerificationResultRepository`. |
| `app/decision_intelligence/execution_persistence.py` | Bridge between pydantic domain objects and durable rows; idempotency-key and side-effect-fingerprint derivation; bounded serialization. |
| `app/decision_intelligence/durable_action_executor.py` | `execute_action_durably()` — the same lifecycle as v0.1.3.4's (FROZEN, untouched) `execute_action()`, reimplemented with a durable persistence checkpoint after every stage spec section 12 calls out. |
| `app/decision_intelligence/reconciliation.py` | `reconcile_action()`, `discover_reconciliation_candidates()` — the deterministic Reconciliation Engine. NO LLM. |
| `app/decision_intelligence/tool_adapters.py` | Additive: `EffectInspection`, `SandboxFileCreateAdapter.inspect_effect()` — read-only reconciliation inspection. `execute()`/`verify()` untouched. |

### Why a new module instead of extending the frozen Executor

v0.1.3.4's `execute_action()` is FROZEN this checkpoint (no reproducible
defect was found in it — see "Preflight" in the delivery report). Spec
section 12's durability ordering requires a persistence checkpoint
*between* steps that `execute_action()` currently performs as one
in-memory sequence with no pause points (e.g. "persist ExecutionResult"
must be independently observable from "run verification," which
`execute_action()` does back-to-back). Reimplementing the same lifecycle
in a new, additive module — reusing every lower-level primitive
(`tool_registry.resolve`, `approval_engine.validate_approval_for_action`/
`consume_approval`, `action_state_machine.assert_transition`) rather than
duplicating them — was judged the lower-risk path versus threading
optional persistence parameters through the frozen function.

### Payload/hash integrity (spec section 5)

`ActionRecord.action_hash` **reuses `action_hash.py::compute_action_hash()`
exactly** (option A from spec section 5) — no second, competing hash
algorithm was invented. This is the same canonical hash
`ApprovalRequest.action_hash` already used (v0.1.3.3), so an `ActionRecord`
and the `ActionApprovalRequest` that authorized it always agree on what
"the exact authorized payload" means. `execution_persistence.py`'s
`compute_side_effect_fingerprint()` is a **deliberately separate** concept
(spec section 11) — a reconciliation-only fingerprint of a specific
side effect (`sha256(tool_name + relative_path + content_hash +
expected_bytes)`), never confused with the authorization hash.

### Optimistic concurrency (spec section 6)

`ActionRecord.version` (integer, starts at 1) + `ActionRecordRepository.
update_if_version_matches()` — a conditional `UPDATE ... WHERE id=:id AND
version=:expected_version`, incrementing `version` on success. A stale
writer matches zero rows.

**Concurrency bugs found and fixed while stress-testing this checkpoint**
(all four were caught by the very tests spec section 38 asked for, not
found by inspection — direct evidence the concurrency tests earned their
place):

1. Two concurrent callers can both observe "no `ActionRecord` yet" before
   either commits — the loser's `INSERT` collides on the primary key.
   Fixed by catching `IntegrityError` and falling through to re-fetch +
   update.
2. A left-over `version` key from a failed create attempt leaked into the
   fallback update call, causing a duplicate-keyword `TypeError`.
3. **The most subtle one:** a losing caller (e.g. one that lost the
   execution claim, or was simply slower) could still write a stale,
   earlier-lifecycle status over a row the winner had already legitimately
   advanced past — not caught by the version check alone, since both
   callers could start from the *same* version before either commits.
   Fixed with a monotonic-progress guard (`_HAPPY_PATH_ORDER`): a
   non-terminal write that would regress an `ActionRecord` behind where it
   already is becomes a silent no-op instead of a corrupting write, and an
   already-terminal row is never written to again.
4. `ActionRecordRepository.get()` used `Session.get()`, which returns a
   session-cached (identity-mapped) object by default — after
   `update_if_version_matches()`'s raw Core `UPDATE` (which bypasses the
   ORM's normal object-refresh), a subsequent `get()` in the *same session*
   could return stale in-memory data even though the database row was
   correctly updated. Fixed with `populate_existing=True`.

`_upsert_action_record()` now retries internally (bounded, 5 attempts),
re-applying the monotonic-progress guard on every attempt, rather than
surfacing every transient conflict as an error — this resolved the
remaining flakiness a stress loop of 100+ concurrent trials caught after
each individual fix, without needing a bespoke fix for every possible
interleaving.

### Durable ExecutionAttempt / idempotency key / atomic claim (spec sections 7/8/23/24)

`idempotency_key = sha256(f"{action_id}:{action_hash}")` — deterministic,
never model-chosen. `execution_attempts.idempotency_key` is UNIQUE at the
database level; that constraint **is** the atomic execution claim
(`ExecutionAttemptRepository.claim()`): a losing concurrent `INSERT` fails
with `IntegrityError`, caught and reported as "already claimed," not a
crash. Verified with independent `AsyncSession`s racing via
`asyncio.gather()` — exactly one ever wins, and exactly one
`ExecutionAttemptRecord` row ever exists per `(action_id, action_hash)`.

### Execution lease (spec section 25)

Minimal, as recommended: `claimed_at`/`claimed_by`/`lease_expires_at`,
set once an attempt moves to `STARTED` (15-minute TTL — generous for a
single sandboxed file write). `discover_reconciliation_candidates()` flags
a `STARTED` attempt whose lease has expired as a candidate — **nothing
automatically reclaims or reruns it.** An expired lease always means
`RECONCILIATION_REQUIRED`, never "run again."

### Executor persistence ordering & crash windows (spec sections 12/13/30)

`execute_action_durably()` persists at every lettered checkpoint (A
through L) from spec section 12. All seven crash windows from spec section
13 have a deterministic reconciliation classification and recovery path
(or explicit non-recovery) — see the Reconciliation Engine section below
and `tests/test_reconciliation.py`'s eight `test_crash_*` tests, one per
spec section 37 point.

### Reconciliation Engine (spec sections 14-21/26-28)

`reconcile_action(action_id, ...)` is deterministic, **NO LLM**, and never
re-invokes `adapter.execute()`. It loads durable state (`ActionRecord`,
latest `ExecutionAttemptRecord`, its `ExecutionResultRecord`/
`VerificationResultRecord` if present), inspects the ACTUAL sandbox effect
via the adapter's read-only `inspect_effect()` when needed, classifies,
and — only for classifications where every remaining step is independently
safe, deterministic, and read-only-except-for-bookkeeping — recovers by
persisting the missing durable record(s) and advancing the `ActionRecord`
through the *existing, unmodified* v0.1.3.1 state machine. It never writes
a file, never overwrites, never deletes, never grants approval, and never
executes an unregistered/unknown adapter.

**Classifications implemented** (spec section 15): `CONSISTENT_COMPLETED`,
`CONSISTENT_FAILED`, `EXECUTION_NOT_STARTED`, `EXECUTION_INTERRUPTED`,
`SIDE_EFFECT_PRESENT_RESULT_MISSING`,
`EXECUTION_SUCCEEDED_VERIFICATION_MISSING`,
`VERIFICATION_PASSED_COMPLETION_MISSING`, `SIDE_EFFECT_MISMATCH`,
`APPROVAL_CONSUMED_EXECUTION_MISSING`, `AMBIGUOUS_STATE`,
`SECURITY_INCONSISTENCY`. (`DUPLICATE_REQUEST` is defined for completeness
but duplicate detection lives in `durable_action_executor.py`'s own
already-`COMPLETED` short-circuit, not in `reconcile_action()`, which is
only ever called for non-terminal Actions.)

**Recovery chains as far as is safely justified in one call** — e.g. a
proven-matching side effect (`SIDE_EFFECT_PRESENT_RESULT_MISSING`) is
reconstructed, verified, AND the Action advanced all the way to
`COMPLETED` in a single `reconcile_action()` call, because every one of
those steps is independently safe/read-only/deterministic. What is
**never** done automatically is re-invoking `adapter.execute()` to
reproduce a side effect whose presence/correctness inspection could not
establish (`SIDE_EFFECT_MISMATCH` → `safe_to_retry=False`,
`human_review_required=True`, the Action is never completed, and the
on-disk artifact is never touched).

### Provenance (spec sections 34/35)

`ResultProvenance.ORIGINAL` (set by `durable_action_executor.py`'s normal
run) vs. `ResultProvenance.RECONSTRUCTED` (set by anything
`reconciliation.py` persists) — visible on every `ExecutionResultRecord`/
`VerificationResultRecord` row. A recovered result is never indistinguishable
from one produced by a normal execution pass.

### Bounded serialization (spec section 32)

Non-security-relevant free text (`output`, `observed`, `issues`, error
messages) is safely truncated with a visible `...[truncated]` marker at
`MAX_TEXT_FIELD_CHARS` (4000). `Action.inputs` — security-relevant, part of
`action_hash` — is **never truncated**: `safe_inputs_json()` raises
`PayloadTooLargeForPersistenceError` and fails the persistence attempt
closed if it exceeds `MAX_INPUTS_JSON_CHARS` (200,000) rather than risk a
persisted row silently misrepresenting what was actually authorized.

### Database constraints (spec section 30)

`execution_attempts.idempotency_key` UNIQUE (the atomic claim primitive);
`execution_results.attempt_id` UNIQUE and `verification_results.attempt_id`
UNIQUE (at most one result/verification per attempt); `action_records.
approval_id` is a real `ForeignKey` into `action_approval_requests.id`
(both tables now exist, unlike `Action`↔`ApprovalRequest`); indexes on
every `action_id`/`action_plan_id` foreign-key-shaped column used for
lookups.

### Domain/persistence separation (spec section 31)

Preserved exactly as established in v0.1.3.4:
`app/database/repositories.py` stays domain-agnostic (plain ORM rows/
kwargs, no import of `app.decision_intelligence`); `execution_persistence.py`
is the only module that imports both sides and translates between them.

### Migration

`1a868c95f4ee` ("durable execution state"), chained directly after
v0.1.3.4's head `b0a3e6d998fc`. Validated: fresh database → head; the
existing `test_migrations.py`/`test_database_connection.py` suite (exactly-
one-head, fully-linked-chain, `init_db()` reconciliation) still passes
unmodified; a dedicated `test_migration_head_is_v0135_and_chained_from_v0134`
pins both revision IDs so a future stray branch is caught immediately.

## IMPLEMENTED IN v0.1.3.6 — Durable ActionPlan Orchestration + Dependency-Aware Execution + Pause/Resume

Makes an entire `ActionPlan` durable, dependency-aware, resumable, and
approval-aware — on top of, never bypassing, the frozen v0.1.3.1-v0.1.3.5
pipeline. **No new real capability was added** — `file.create_sandboxed`
remains the only genuine side-effecting adapter; this checkpoint is
entirely about coordinating multiple Actions safely over time.

```
OBJECTIVE -> DECISION -> ACTION PLAN -> DURABLE PLAN RECORD
  -> DEPENDENCY VALIDATION -> READY ACTION DISCOVERY
  -> PERMISSION / APPROVAL -> DURABLE ACTION EXECUTION -> VERIFICATION
  -> DEPENDENCY RELEASE -> NEXT READY ACTION -> PLAN COMPLETION

  (if interrupted)

RESTART -> LOAD DURABLE PLAN -> DISCOVER INCOMPLETE ACTIONS
  -> RECONCILE DURABLE ACTIONS -> REBUILD DEPENDENCY READINESS
  -> RESUME ONLY SAFE WORK -> CONTINUE PLAN
```

| Module | Responsibility |
|---|---|
| `app/database/models.py` | `ActionPlanRecord` (+ `PersistedActionPlanStatus`) — durable plan state, including the plan-level orchestration lease. |
| `app/database/repositories.py` | `ActionPlanRecordRepository` — optimistic concurrency + atomic lease claim/release. |
| `app/decision_intelligence/action_plan_persistence.py` | Bridge between the pydantic `ActionPlan`/`Action` objects and their durable rows; `compute_plan_hash()` (plan-integrity hash); failure-policy normalization. |
| `app/decision_intelligence/action_eligibility.py` | Pure, deterministic `evaluate_action_eligibility()` — no I/O, no LLM. |
| `app/decision_intelligence/action_plan_state_machine.py` | Explicit `ActionPlanStatus` transition table, same shape as `action_state_machine.py`. |
| `app/decision_intelligence/action_plan_orchestrator.py` | `validate_and_persist_plan()`, `run_plan_until_blocked()` — the coordinator. NEVER calls a `ToolAdapter` directly. |
| `app/decision_intelligence/plan_reconciliation.py` | `reconcile_plan()`, `discover_plan_reconciliation_candidates()` — delegates ALL Action-level recovery to v0.1.3.5's `reconcile_action()`. |

### Coordinator, not a superuser (spec section 58)

The orchestrator never gains authority an individual Action's own pipeline
didn't already grant:

```
ActionPlan Orchestrator -> eligible Action -> Permission Engine
  -> Approval Engine (if required) -> Durable Action Executor
  -> Trusted Tool Adapter -> ExecutionResult -> VerificationResult
  -> Action COMPLETED -> dependency released -> next eligible Action
```

There is no `Plan approved = all Actions approved` shortcut anywhere —
approval remains Action-specific, hash-bound, single-use, and is never
inherited by a dependent Action (spec section 60). `_advance_one_action()`
calls straight into the SAME v0.1.3.2-v0.1.3.5 functions
(`evaluate_permission`, `apply_permission_decision`, `create_approval_request`,
`authorize_action`, `execute_action_durably`, ...) the frozen single-Action
path already used — there is no parallel/competing implementation of
permission evaluation, approval handling, or Action-level reconciliation.

### Why a new module instead of extending frozen code

Same reasoning v0.1.3.5 used for `durable_action_executor.py`: rather than
touch `approval_engine.py`/`permission_engine.py`/`action_hash.py`/
`action_state_machine.py`/`tool_registry.py`/`sandbox_fs.py`/the sandbox
adapter/`durable_action_executor.py`/`reconciliation.py` (all frozen this
checkpoint, none had a reproducible defect — see "Bugs found" below, which
were all in v0.1.3.6's OWN new code, not the frozen layers), the
orchestrator is new, additive code built entirely on top of them.

### Dependency graph (spec sections 8/9/13)

Reuses `plan_validation.py::evaluate_plan_readiness()` VERBATIM for
`validate_and_persist_plan()` — no competing cycle-detection/graph-validation
logic was written. That function already rejects duplicate/self/unknown/
cyclic dependencies (via the same DFS `detect_dependency_cycle()` v0.1.3.1
built) and validates every Action's structural completeness before a plan
may become `READY`. A plan that fails validation is never persisted at
all — `PlanNotReadyError` carries the exact blockers.

### Dependency satisfaction rule (spec section 11)

A dependency is satisfied **only** when its prerequisite is durably
`COMPLETED` — not `EXECUTION_SUCCEEDED`, not `VERIFYING`, not even
`VERIFIED`. `action_eligibility.py::evaluate_action_eligibility()` is a
pure function (no I/O) returning one of 11 classifications: `READY`,
`ALREADY_COMPLETED`, `WAITING_FOR_DEPENDENCIES`, `WAITING_FOR_APPROVAL`,
`BLOCKED_BY_FAILED_DEPENDENCY`, `BLOCKED_BY_REJECTED_DEPENDENCY`,
`RECONCILIATION_REQUIRED`, `CURRENTLY_EXECUTING`, `TERMINAL_FAILED`,
`CANCELLED`, `SECURITY_BLOCKED`.

### Plan state machine (spec section 12)

`action_plan_state_machine.py` — explicit transition table, same shape as
`action_state_machine.py`. `run_plan_until_blocked()` always re-enters
through `EXECUTING` (including on resume from `WAITING_FOR_APPROVAL`/
`PARTIALLY_COMPLETED`) before recomputing the final status, so the final
recompute can legally reach any downstream terminal/pause state from one
consistent hub — see "Bugs found" below for the real bug this fixes.

### The orchestration algorithm (spec sections 14/15/49)

`run_plan_until_blocked(plan_id, ...)` — also serves as `resume_plan()`;
there is no separate resume function, because resuming IS simply calling
this again: every call re-derives everything from durable state. Per
call:

1. Load the durable plan + every durable Action (deterministic order:
   `sequence` then `id`, never database row-return order).
2. Acquire the plan-level orchestration lease (see below).
3. A one-time catch-up pass: check every currently `WAITING_FOR_APPROVAL`
   Action's approval status exactly once (a still-`PENDING` approval is
   left untouched, never re-polled in a loop).
4. Bounded loop (`max_orchestration_steps`, default 50): reconcile any
   in-progress Action first (delegating to v0.1.3.5's `reconcile_action()`),
   recompute eligibility, dispatch the single next `READY` Action (one
   meaningful step per iteration — VALIDATED->PERMISSION_CHECKED,
   PERMISSION_CHECKED->(approval request | durable execution),
   WAITING_FOR_APPROVAL->(authorize+execute | finalize)), stop when no
   `READY` work remains.
5. Recompute + persist the truthful final plan status; release the lease.

P0 "internal reasoning" Actions (no tool — spec section 4 of v0.1.3.2) have
nothing to execute or verify; `_complete_toolless_action()` walks the same
`EXECUTING -> ... -> COMPLETED` transitions the Executor would, but never
calls a `ToolAdapter` — there is nothing to call.

### Plan-level lease / atomic claim (spec sections 24/25/42)

`ActionPlanRecordRepository.claim_orchestration()` — a conditional `UPDATE`
matching only `orchestration_owner IS NULL` by default; `allow_stale_takeover=True`
is the ONLY way to also match an expired-lease row, and the orchestrator
only ever passes it immediately AFTER calling `reconcile_plan()` on that
same plan — an expired lease is **never** silently stolen (spec section
25's explicit requirement). Verified race-free with independent
`AsyncSession`s under `asyncio.gather()`. **SQLite concurrency honesty**
(spec section 42): these tests prove correctness against a single SQLite
file via real concurrent connections — they do not, and cannot, prove
production-grade distributed exactly-once orchestration across multiple
machines/a different database engine; a future PostgreSQL deployment
should receive its own dedicated concurrency testing.

### Plan reconciliation (spec sections 26-28)

`reconcile_plan()` delegates every in-progress Action to v0.1.3.5's
`reconcile_action()` UNCHANGED, then recomputes plan-level truth from the
(possibly just-recovered) Action states. Classifications: `CONSISTENT_READY`,
`CONSISTENT_EXECUTING`, `CONSISTENT_WAITING_FOR_APPROVAL`,
`CONSISTENT_PARTIAL`, `CONSISTENT_COMPLETED`, `CONSISTENT_FAILED`,
`ACTION_RECONCILIATION_REQUIRED`, `AMBIGUOUS_PLAN_STATE`. Never writes a
file, never grants approval, never re-invokes `adapter.execute()` — every
one of those guarantees is entirely inherited from `reconcile_action()`.

### Failure propagation / failure policies (spec sections 21-23)

`STOP_ON_FAILURE` (default) / `CONTINUE_INDEPENDENT` — a minimal, explicit
two-value contract (`action_plan_persistence.py::normalize_failure_policy()`);
anything blank/unrecognized defaults to the SAFER policy. A failed/rejected/
cancelled/blocked prerequisite is never treated as satisfied
(`BLOCKED_BY_FAILED_DEPENDENCY`/`BLOCKED_BY_REJECTED_DEPENDENCY`); a
dependent Action is never given a fabricated `ExecutionResult`. Under
`CONTINUE_INDEPENDENT`, an unrelated branch with no dependency on the
failed Action is still allowed to complete — verified by a dedicated fan-out
test with one failing branch and one succeeding, independent branch.

### Partial completion / no false completion (spec sections 20/30)

`PARTIALLY_COMPLETED` is truthfully distinct from `FAILED` (some real
progress exists) and from `COMPLETED` (not all required work is done).
`WAITING_FOR_APPROVAL` takes priority over `PARTIALLY_COMPLETED` whenever
nothing has actually failed — an approval-paused plan is fully resumable,
never degraded to looking like a failure. A plan is marked `COMPLETED`
**only** when every member Action is durably `COMPLETED` — no exceptions.

### Plan-integrity hash (spec section 33) — a deliberate divergence from `action_hash`

`compute_plan_hash()` selects a **narrower** field subset per Action than
`action_hash.py::compute_action_hash()` — `action_type`/`tool_name`/
`inputs`/`expected_result`/sorted `dependencies`, explicitly EXCLUDING
`permission_level`/`risk_level`. Reusing the full `action_hash` verbatim
would make the plan hash spuriously "change" the moment the Permission
Engine legitimately overwrites an Action's proposed permission/risk with
its authoritative values — the very first orchestration step for any
Action. Three distinct hash/fingerprint concepts now exist in this
codebase, each serving a different purpose, documented together to avoid
confusion: `action_hash.py::compute_action_hash` (one Action's
authorization payload), `execution_persistence.py::compute_side_effect_fingerprint`
(one adapter's actual on-disk effect, reconciliation-only), and
`action_plan_persistence.py::compute_plan_hash` (plan-level structural
mutation detection — spec section 34).

### Security invariants (spec sections 31/36/52)

`Plan permission <= individual Action permission` holds structurally: the
orchestrator never sets `permission_level`/`risk_level`/`approval_required`
itself — every Action still goes through the unmodified Permission Engine
and (when required) Approval Engine. Unknown tools, disabled tools,
missing adapters, and P5/`ADMIN` capabilities all fail closed exactly as
in v0.1.3.2/.4 — the orchestrator adds no new bypass path and cannot,
since it only ever calls `execute_action_durably()`/`reconcile_action()`,
never a `ToolAdapter` directly (verified structurally).

### Bugs found and fixed during this checkpoint's own testing

All in v0.1.3.6's NEW code — no reproducible defect was found in any
frozen v0.1.3.1-v0.1.3.5 module, so none was modified beyond what this
list describes:

1. **P0 "no tool" Actions crashed the durable Executor.** `_advance_one_action()`
   originally routed every non-`REQUIRE_APPROVAL` Action through
   `execute_action_durably()`, which assumes a resolvable `tool_name` —
   but P0 "internal reasoning" Actions legitimately have none. Fixed with
   `_complete_toolless_action()` (see above).
2. **`WAITING_FOR_APPROVAL` Actions were never re-checked.** The main loop
   only ever dispatched `READY` Actions; a pending approval becoming
   `APPROVED` was invisible to it. Fixed with the one-time catch-up pass
   (spec section 17's exact resume requirement).
3. **Resuming a paused plan could never reach `COMPLETED`.** `WAITING_FOR_APPROVAL
   -> COMPLETED` is not a legal direct transition (only `EXECUTING ->
   COMPLETED` is) — fixed by always re-entering through `EXECUTING` first
   on every call, including resumes.
4. **Naive/aware datetime comparisons** in the lease-expiry check
   (Python-side) and inside SQLAlchemy's default "evaluate" bulk-update
   synchronization strategy (which tries to Python-evaluate a bulk
   `UPDATE`'s `WHERE` clause against already-loaded, possibly
   SQLite-naive, in-session objects) — same root cause as v0.1.3.5's
   identical class of bug, now fixed with `.execution_options(synchronize_session=False)`
   on every bulk `UPDATE` in the repository layer.
5. **Stale `select()` reads.** `ActionRecordRepository.list_by_plan()`/
   `list_by_status()` and `ActionPlanRecordRepository.list_by_status()`/
   `list_stale_leases()` used plain `select()`, which (like `Session.get()`
   before it — see v0.1.3.5's identical fix) can return an already-
   identity-mapped, stale Python object instead of reflecting a raw Core
   `UPDATE` made elsewhere in the same session. This one actually caused a
   security-relevant test (the structural mutation guard) to silently
   pass a plan through with tampered Action inputs. Fixed with
   `.execution_options(populate_existing=True)` on all four.

### Known limitations

- Dispatch is strictly sequential — multiple `READY` Actions are correctly
  *identified*, but only one is dispatched per loop iteration (spec section
  50's explicit "do not add parallel execution yet").
- The plan-level lease is a cooperative mechanism, not a hard distributed
  lock — see "SQLite concurrency honesty" above.
- `discover_plan_reconciliation_candidates()` is not wired to any
  application startup hook, matching v0.1.3.5's identical choice.
- Replanning after an `ACTION_RECONCILIATION_REQUIRED`/`SECURITY_INCONSISTENCY`
  block is out of scope — a human must intervene; nothing here invents a
  new Action or approval.

## IMPLEMENTED IN v0.1.3.7 — Failure Intelligence + Bounded Retry + Controlled Replanning + Budget Enforcement

Teaches Jarvis what to do when an Action fails — on top of, never bypassing,
the frozen v0.1.3.1-v0.1.3.6 pipeline. **FAILURE DOES NOT IMPLY RETRY**
(spec section 4): every category defaults fail-closed; only a narrow,
side-effect-aware, bounded set of situations is ever automatically retried.
**No new real capability was added** — `file.create_sandboxed` remains the
only genuine side-effecting adapter.

```
ACTION FAILURE -> CLASSIFY (failure_intelligence.py, reused FailureCategory)
  -> persist FailureRecord -> EVALUATE RECOVERY (recovery_policy.py, pure)
  -> persist RecoveryDecision
  -> RETRY (retry_controller.py, durable, bounded)
   | REPLAN (replan.py, caller-supplied replacement, no LLM)
   | RECONCILE (v0.1.3.5's reconcile_action(), unchanged)
   | HUMAN_REVIEW / STOP / SECURITY_BLOCKED / BUDGET_EXHAUSTED
  -> re-evaluate permission (unmodified v0.1.3.2 Permission Engine)
  -> fresh approval if the (possibly-changed) Action requires it
  -> resume ActionPlan orchestration
```

| Module | Responsibility |
|---|---|
| `app/decision_intelligence/failure_intelligence.py` | Deterministic `classify_failure()` (reuses `EXECUTOR_FAILURE_CATEGORY`) + durable `FailureRecord` history — distinct from `ActionRecord.last_error` (a single mutable field). |
| `app/decision_intelligence/recovery_policy.py` | Pure `evaluate_recovery()` — the ONE place a `RecoveryDecision` is ever decided. No I/O, no LLM. |
| `app/decision_intelligence/retry_controller.py` | The single durable "authorize a bounded retry" write — resets a FAILED/crash-interrupted Action back to `VALIDATED` with `retry_count` bumped. |
| `app/decision_intelligence/replan.py` | `propose_replan()`/`apply_replan()` — controlled, deterministic, caller-supplied replacement Actions; dependency rewiring; plan revisions. |
| `app/decision_intelligence/budget.py` | `reserve_and_consume()` — atomic, restart-safe, ledgered budget enforcement (`ACTION_ATTEMPTS`/`RETRIES`/`REPLANS`/`MODEL_CALLS`/`ESTIMATED_COST`). |
| `app/decision_intelligence/action_plan_orchestrator.py` | Extended (not rewritten) with `_process_failure()` — the integration point, invoked at the two places a v0.1.3.6 `run_plan_until_blocked()` call can observe a failure. |

### Why five new modules instead of one giant one (spec section 57)

`app/decision_intelligence/action_plan_orchestrator.py` deliberately stays
a COORDINATOR: `_process_failure()` classifies, persists, and decides, but
every ACTUAL durable mutation (the retry reset, the replan application,
the budget ledger write) lives in its own dedicated module — the
orchestrator still never calls a `ToolAdapter` directly, and still never
duplicates permission/approval/reconciliation logic (all reused verbatim,
see below).

### Failure taxonomy — reused, not reinvented (spec section 5)

`FailureCategory` (TRANSIENT/VALIDATION/PERMISSION/APPROVAL/TOOL/
VERIFICATION/BUDGET/SECURITY/UNKNOWN) is the SAME v0.1.3.1 enum every
earlier checkpoint already used — no second, competing taxonomy.
`classify_failure()` maps a failed Action's `ExecutionResult.error_code`
through the SAME `EXECUTOR_FAILURE_CATEGORY` table `action_executor.py`/
`durable_action_executor.py` already populate; falls back to
`error_type`, then to `UNKNOWN` — never guesses, never pretends certainty.

### Recovery policy (spec sections 7/8/12)

`evaluate_recovery()` is a pure function; its full decision table:

| Category | Decision (default) |
|---|---|
| SECURITY | `SECURITY_BLOCKED` — never, under any budget, retried. |
| BUDGET | `BUDGET_EXHAUSTED` — stops; nothing here ever raises a budget automatically. |
| PERMISSION | `STOP` — a deliberate policy boundary, never retried/replanned around. |
| APPROVAL | `STOP` — recovery can never manufacture a fresh approval. |
| *(any, when `approval_required`)* | `HUMAN_REVIEW` — an approval-gated Action's ONE approval is already single-use/consumed; only a human can authorize another attempt. |
| TRANSIENT / TOOL, side effect absent, budget remaining | `RETRY` |
| TRANSIENT / TOOL, side effect MAY have occurred | `RECONCILE` — never a blind retry (spec section 8's non-negotiable rule). |
| TRANSIENT / TOOL, `retry_count >= max_retries` | `BUDGET_EXHAUSTED` |
| VALIDATION | `REPLAN` (candidate) if the plan's replan budget allows, else `STOP`. |
| VERIFICATION | `RECONCILE` — verification failing never implies "just execute again." |
| UNKNOWN | `RECONCILE` — `UNKNOWN -> RECONCILE`, **never** `UNKNOWN -> RETRY` (spec section 8's explicit example, preserved verbatim from v0.1.3.5). |

### Retry semantics (spec sections 10-13)

A retry is the SAME Action, SAME `action_hash`, SAME tool/inputs —
`retry_controller.py::authorize_retry()` never touches any
security-relevant field, only `status`/`retry_count`/`last_error`/
`started_at`/`completed_at`. Initial execution is attempt 1; `retry_count`
counts attempts AFTER that (spec section 33's exact example:
`max_retries=2` -> at most 3 total executions). Restart does not reset
`retry_count` — it is a durable `ActionRecord` column, read fresh on every
call. A durable retry-authorization write happens BEFORE the retry
executes (spec section 10) — `authorize_retry()` IS that write.

**Why this bypasses `action_state_machine.py` rather than extending it**
(a deliberate, documented divergence from the "reuse the existing
state machine" pattern every other module in this codebase follows): that
table is forward-only, with no notion of an authorized regression, and
`durable_action_executor.py::_upsert_action_record()`'s monotonic-progress
guard would silently DROP a `FAILED -> VALIDATED` (or `EXECUTING ->
VALIDATED`) write as "stale" if it were added as an ordinary edge —
retrying is a deliberate reset, not late/racing progress. `authorize_retry()`
instead validates against its own small, explicit
`_RETRY_REENTRY_SOURCES` allowlist (`FAILED`/`EXECUTING`/`APPROVED`) and
writes via a direct, version-guarded `update_if_version_matches()` call
that bypasses `_upsert_action_record()` entirely for this one operation.
`action_state_machine.py` itself is completely untouched by this
checkpoint.

**Idempotency-key threading** (spec section 23's "same idempotency key ->
duplicate" invariant, preserved): since a retry deliberately keeps the
SAME `action_hash`, `compute_idempotency_key()` gained an optional,
default-0, backward-compatible `attempt_number` parameter — `retry_number=0`
(every pre-v0.1.3.7 caller) reproduces the byte-identical digest it always
did; only `retry_controller`-authorized retries (via
`action_plan_orchestrator.py` passing `action.retry_count`) ever pass a
nonzero value, so a retry claims a NEW `ExecutionAttemptRecord` instead of
colliding with the failed attempt's own claim.

### Side-effect-aware retry / reconciliation-before-retry (spec sections 9/44/75)

A SYNCHRONOUS in-process failure (adapter's `execute()` returned within
the same call) always has a DEFINITE `side_effect_occurred` bool straight
from its `ExecutionResult` — no ambiguity to resolve. A CRASH-interrupted
Action is different: `run_plan_until_blocked()`'s existing "reconcile
in-progress Actions FIRST" pass (v0.1.3.5, unchanged) runs
`reconcile_action()` before anything else; when it returns
`safe_to_retry=True` with the side effect CONFIRMED ABSENT
(`EXECUTION_INTERRUPTED`), the SAME `_process_failure()` pipeline now
authorizes a retry from that confirmed-safe state — closing the exact gap
the v0.1.3.5 write-up flagged ("nothing yet acts on `safe_to_retry`"). A
side effect that MAY have occurred, or reconciliation returning
`human_review_required=True`, still NEVER authorizes a retry.

### Independent branches keep progressing (critical fix during this checkpoint's own testing)

An early implementation had `_process_failure()` immediately `break` the
bounded dispatch loop on any non-RETRY decision — this silently broke
`CONTINUE_INDEPENDENT` (an unrelated branch must keep making progress
after a sibling fails, spec section 22 of v0.1.3.6), caught by v0.1.3.6's
OWN pre-existing regression test
(`test_independent_branch_continues_when_unrelated_branch_fails`). Fixed
by never breaking the loop from inside `_process_failure()`'s caller —
a `pending_recovery_stop_reason` is recorded instead, and only OVERRIDES
the final `stop_reason` (computed exactly as v0.1.3.6 always did, via
`_determine_blocking_stop_reason()`/the natural "no more READY Actions"
condition) when that would otherwise be the generic `ACTION_FAILED`, with
recovery_policy.py's more specific/truthful reason
(`BUDGET_EXHAUSTED`/`REPLAN_REQUIRED`/`SECURITY_BLOCKED`/
`HUMAN_REVIEW_REQUIRED`).

### Controlled replanning (spec sections 14-22/45-52)

No LLM ever generates a replacement Action — `propose_replan()` always
takes a caller-supplied `Action` as-is (a deterministic test fixture, or a
future human-reviewed one). Cycle protection reuses
`plan_validation.py::detect_dependency_cycle()` verbatim against the
PROJECTED post-replan graph, before anything is persisted.

**No inherited authority** (spec sections 16/17/47/48), enforced entirely
by REUSE, not a new check: the replacement Action is persisted at
`ActionStatus.VALIDATED` — the same starting point every Action has always
had. It carries no `approval_id`, and its proposed `permission_level`/
`risk_level` are exactly as untrusted as any other Action's — the
unmodified Permission Engine recomputes its authoritative floor fresh the
next time it is advanced. A downgrade attempt cannot lower that floor; an
escalation is honored exactly as it would be for a brand-new Action.

**History preservation** (spec sections 18/21): the failed Action's row is
NEVER deleted or overwritten — a new, additive `superseded_by_action_id`
column (nullable, no FK, `action_records` table — a minimal, targeted
choice over adding a new `ActionStatus` enum member, which would have
required a full SQLite table rebuild to widen an existing `CHECK`
constraint for no functional benefit) marks it superseded. Every OTHER
Action that depended on it is rewired to depend on the replacement.

**Plan revision** (spec sections 19/20): `ActionPlanRecord.revision`
(new column, additive, default 1) increments by exactly one each time an
applied replan changes the plan's structural `plan_hash` — never
incremented by ordinary execution progress. A successfully applied
replan also REVIVES the plan's own status out of `FAILED` (which, like
`ActionStatus.FAILED`, has no legal outgoing transition in the normal
state machine) back to `EXECUTING` — the SAME "authorized deliberate
reset" reasoning `retry_controller.py` uses for a single Action, applied
here to the whole plan; `action_plan_state_machine.py` itself remains
untouched.

**A superseded Action is excluded from plan-completion accounting**
(bug found and fixed during this checkpoint's own testing): the historical
FAILED row would otherwise permanently block `_recompute_plan_status()`
from ever reaching `COMPLETED`, even after its replacement finished
successfully — `_recompute_plan_status()`/`_summarize()` now both filter
to `a.superseded_by is None` before counting.

**Idempotency and concurrency** (spec sections 50-52): every downstream
mutation (`apply_replan()`'s replacement-Action creation, supersede
marking, dependency rewiring, plan-hash/revision recompute) is
individually idempotent — existence-checked or `IntegrityError`-tolerant —
so the function is safe to call again after a crash, a duplicate caller,
or just to confirm an already-applied result. The actual `PROPOSED ->
APPLIED` status flip is the one EXCLUSIVE step, gated by
`ReplanProposalRecord.version` (`ReplanProposalRepository.claim_for_apply()`)
— the same optimistic-concurrency shape as the plan-level orchestration
lease, applied to a single row.

### Budget enforcement (spec sections 23-33)

Two budget types are wired into LIVE orchestration control flow:
**RETRIES** reuses the existing `Action.retry_count`/`max_retries` fields
directly (spec section 12's "reuse these where appropriate") — no new
durable account needed for the common per-Action case. **REPLANS** uses
the new `BudgetAccountRecord`/`BudgetEventRecord` machinery at PLAN scope.
`ACTION_ATTEMPTS`/`MODEL_CALLS`/`ESTIMATED_COST` accounts are fully
implemented and tested directly (`reserve_and_consume()`,
restart-persistence, concurrency) but NOT automatically enforced on every
Action dispatch in this checkpoint — see "Known limitations" below.

An **unconfigured budget behaves as unlimited** (no `BudgetAccountRecord`
row exists for that scope+type): `reserve_and_consume()` returns
`granted=True` without creating anything. This is a deliberate
backward-compatibility choice — every v0.1.3.6 orchestrator test
constructs plans with no budget configured at all, and this checkpoint
must not require one.

**Atomicity** (spec sections 27/53): `BudgetEventRecord.idempotency_key`
is UNIQUE — the same claim-by-INSERT pattern `ExecutionAttemptRecord`
already established — combined with a version-guarded conditional UPDATE
on `BudgetAccountRecord.consumed_value`. Two concurrent consumers of the
last unit: exactly one is granted, the other is durably recorded as
denied; `consumed_value` never goes negative or double-counts (stress-
tested via `asyncio.gather()`).

**Cannot self-increase** (spec section 30): `ensure_account()`/
`BudgetAccountRepository.ensure()` is a strict get-or-create — an existing
account's `limit_value` is NEVER changed by anything in this module,
`retry_controller.py`, or `replan.py`.

**Decimal vs. float** (spec section 25's suggestion, deliberately NOT
followed — documented, not silently ignored): every budget value here is
a plain `float`, matching `Action.estimated_cost`/`ActionPlan.estimated_cost`
(both `float` since v0.1.3.1, frozen contracts unchanged) and
`UsageRecord.estimated_cost_usd` elsewhere in this codebase. No real money
moves in this checkpoint (or any checkpoint so far); introducing `Decimal`
here in isolation would add a third numeric cost representation without
closing any real precision gap. A future real-payment integration is the
right point to migrate every cost-bearing field together.

### Durable failure/recovery history (spec sections 34/35)

`FailureRecord` (one row per observed failure — distinct from
`ActionRecord.last_error`, a single mutable field that only ever holds the
most recent error) and `RecoveryDecisionRecord` (one row per
`evaluate_recovery()` call whose outcome was acted on) together answer "why
did you retry/stop/replan this?" after the fact, durably, without needing
the original process still running.

### Known limitations

- Dispatch remains strictly sequential (unchanged from v0.1.3.6) — retry/
  replan add more WORK the loop can do, not parallelism.
- `ACTION_ATTEMPTS`/`MODEL_CALLS`/`ESTIMATED_COST` budgets are implemented
  and directly tested but not automatically enforced on every Action
  dispatch — wiring that in is deferred to avoid regression risk against
  every v0.1.3.6 test that constructs a plan with no budget configured.
- A TOOL-category failure whose retry budget is exhausted reports
  `BUDGET_EXHAUSTED` even when the underlying cause (e.g. a permanently
  missing adapter) would never have succeeded on retry regardless of
  budget — this checkpoint does not distinguish "permanently unretryable"
  from "retry budget exhausted" within the TOOL category.
- `RecoveryDecision.WAIT_FOR_APPROVAL`/`NO_ACTION` are part of the
  contract (spec section 7) but not reachable from any call site
  `evaluate_recovery()` actually has today — every APPROVAL-category
  failure resolves to `STOP` instead, since nothing in this checkpoint's
  scope leaves a "still waiting" path open after a failure.
- No generic rollback/compensation framework — unchanged from v0.1.3.4/.5/.6;
  a partially-succeeded Action's artifact is never automatically deleted.
- Replanning a Action that has ALREADY been superseded once is not
  specially handled — `superseded_by_action_id` is set-once (first writer
  wins); a second replan proposal against the same original failed Action
  still creates a valid new replacement, but the original's
  `superseded_by_action_id` continues pointing at the FIRST replacement,
  not the second. Not exercised by any real orchestration path (a caller
  would normally replan the newest failure, not the original), but noted
  honestly rather than silently glossed over.

## IMPLEMENTED IN v0.1.3.8 — Full Hostile End-to-End Benchmark + Control-Plane Validation

A VERIFICATION + INTEGRATION + HOSTILE-BENCHMARK + narrow-defect-fixing
checkpoint, not a new capability milestone — the explicit purpose was to
prove the composed v0.1.2/v0.1.3.1-.7 control plane works coherently
under deliberately adversarial conditions, not merely that each subsystem
passes its own tests in isolation.

```
OBJECTIVE -> RESEARCH -> EVIDENCE -> EVIDENCE READINESS -> DECISION
  -> DECISION GATE -> ACTION PLAN -> DURABLE PLAN
  -> DEPENDENCY ORCHESTRATION -> PERMISSION -> APPROVAL -> EXECUTION
  -> VERIFICATION -> FAILURE INTELLIGENCE -> RETRY / REPLAN / RECONCILIATION
  -> CRASH / RESTART -> DURABLE RECOVERY -> QA -> EXECUTIVE REPORT
```

### The hostile benchmark

`tests/test_v0138_hostile_benchmark.py::test_hostile_end_to_end_benchmark`
— one large, deterministic, offline integration test — plus
`scripts/benchmark_v0138.py`, a standalone harness sharing its scenario
logic with that test via `tests/_v0138_scenario.py` (so the two can never
drift apart). Both build a 7-Action, fan-out/fan-in plan
(`A1 -> A2 -> {A3, A4} -> A5 -> A6 -> A7`) driven through a genuinely
adversarial sequence: a real Candidate Completeness Gate negative-then-
positive result (never bypassed), a Decision-gate invariant violation, a
deterministic TRANSIENT failure + bounded retry (A4), a REAL
`VALIDATION_FAILURE` from malformed inputs (A5, not a manufactured one) +
a controlled replan to A5b, a P4 approval boundary (A6) that never
receives a real adapter, a P5 dependency that never becomes reachable
(A7), a full simulated process crash/restart (fresh engine, fresh
session, fresh orchestrator call — the durable file on disk is the only
thing carried across, per spec section 27), SHA-256/size/execution-attempt
proof that nothing was silently repeated, and finally a truthful QA +
executive report. Both harnesses print/assert the exact same top-level
outcome spec section 44 anticipated: `Overall: COMPLETED_WITH_REVIEW`,
never bare `COMPLETED` (spec section 45 — P4/P5 pending/blocked work can
never be reported as done).

### Budget integration defect found and fixed (spec sections 18-26)

The hostile benchmark's explicit purpose included proving v0.1.3.7's
budget claims were actually true at the real resource-consumption
boundary — and it found a genuine gap: **`ACTION_ATTEMPTS` and
`ESTIMATED_COST` were structurally implemented (`budget.py`) but never
actually consulted before an adapter call.** A plan with either budget
configured could silently exceed it, because nothing in
`action_plan_orchestrator.py` ever checked. Fixed with
`_check_execution_budget()` — called at BOTH points
`_advance_one_action()` is about to invoke `execute_action_durably()` (the
no-approval ALLOW path, and the post-approval path, in the latter case
positioned BEFORE `authorize_action()` ever consumes anything, per spec
section 28's exact ordering) — never inside the Durable Executor or an
adapter (spec section 56's "do not duplicate budget calculations
throughout adapters"). A denied budget fails the Action durably (FAILED,
zero `ExecutionAttempt` ever created — proving the refusal happens
strictly before adapter execution, spec section 21) and routes through
the SAME `_process_failure()` pipeline v0.1.3.7 already built, so the
durable `FailureRecord`/`RecoveryDecisionRecord` history stays complete
and truthful rather than gaining a second, undocumented failure path.
`RETRIES` and `REPLANS` needed no fix — v0.1.3.7 already wired them into
live control flow (retry via `Action.retry_count`/`max_retries`, replan
via the plan-scoped `BudgetType.REPLANS` account inside `apply_replan()`)
and both were re-verified still passing by this checkpoint's full-suite
run.

### Reproducible concurrency defect found and fixed in `replan.py` (frozen v0.1.3.7 component)

Repeated full-suite runs during this checkpoint's own hostile-benchmark
work surfaced an intermittent (~25% of runs) `sqlalchemy.exc.MissingGreenlet`
failure in `tests/test_replan.py::TestApplyReplan::test_concurrent_apply_creates_exactly_one_replacement`
— a REPRODUCIBLE defect in `apply_replan()` (`app/decision_intelligence/replan.py`),
confirmed with a standalone repeat-loop (2 failures in 8 isolated runs
before the fix, 0 in 15 after). **Root cause**: when two concurrent
callers race to create the same replacement Action, the loser's
`except IntegrityError: await action_repo.session.rollback()` expires
every ORM instance in that session's identity map — including the local
`row` (the loaded `ReplanProposalRecord`) the function goes on to read
via plain attribute access (`row.failed_action_id`, `row.plan_id`, ...)
several more times afterward. An attribute read on an expired instance
triggers an implicit lazy-refresh requiring SQLAlchemy's async greenlet
bridge, which is not guaranteed active at that point, intermittently
raising `MissingGreenlet`. **Fix**: every scalar field `apply_replan()`
needs from `row` is captured into plain Python locals (`proposal_pk`,
`plan_id`, `failed_action_id`, `replacement_action_id`, `initial_status`,
`initial_version`) immediately after the initial load, and the rest of
the function reads only those locals — never `row.<attr>` again. This is
not merely a workaround: `initial_status`/`initial_version` being fixed
at load time is also the semantically CORRECT behavior for an
optimistic-concurrency CAS (`claim_for_apply()` must use the version this
call originally observed, never a value re-read later in the same
function, which a stale-but-still-live `row` object could otherwise have
silently encouraged). **Frozen invariants preserved**: no change to
`apply_replan()`'s public signature, idempotency guarantees, exclusivity
mechanism (`claim_for_apply()`'s version guard, untouched), or any other
module — the fix is confined to how one already-loaded object's fields
are read inside one function. **Regression coverage**: the existing
`test_concurrent_apply_creates_exactly_one_replacement` test already
exercises this exact race (no new test needed — the fix makes an
existing test reliably pass instead of intermittently failing); a
20-repetition stress loop was additionally run standalone (15
consecutive passes shown above; combined with the pre-fix repro, the
defect is confirmed both reproducible and resolved). Full suite re-run
after this fix — see the delivery report for the final count.

### QA and Executive Report — new, not a re-invocation of the legacy QA loop

`app/decision_intelligence/plan_qa.py`/`executive_report.py` are NEW,
small, pure, code-only modules — deliberately NOT a re-invocation of the
pre-existing `app/orchestration/evaluator.py` QA-agent loop (Worker ->
Output -> QA verdict), which requires a live/mock model call per verdict
and belongs to the older Task-based mission architecture (v0.1.1/v0.1.2).
That loop answers "does this worker's output pass a model-judged
quality bar?"; `plan_qa.py` answers a structurally different question —
"what does this DURABLE ActionPlan's state truthfully say happened?" —
using v0.1.3.x's own contracts (`ActionEligibility`, `ActionStatus`,
`Action.superseded_by`, the authoritative `permission_level`) that the
older loop never had. `build_qa_report()` classifies every Action into
one of seven truthful buckets (COMPLETED/WAITING_FOR_APPROVAL/
BLOCKED_BY_DEPENDENCY/FAILED/SUPERSEDED/NOT_EXECUTED/HUMAN_REVIEW) and
excludes superseded Actions from the "fully completed" computation (the
same fix `_recompute_plan_status()` needed in v0.1.3.7 — see that
section above — applied consistently here). `build_executive_report()`
computes `overall_status` from `plan_qa.py`'s classification alone, so
"no false completion" (spec section 45) is enforced in exactly one place
rather than re-derived ad hoc by every caller.

### Crash/restart proof methodology (spec sections 27-29)

Every "restart" in the hostile benchmark genuinely discards Python-level
state: a fresh `AsyncSession`, a fresh `session_factory`, and — for the
main crash window — an explicit `db_connection.reset_engine()` (dropping
the connection pool/engine object entirely) before reconnecting to the
SAME durable SQLite file. `run_plan_until_blocked()` is never called on a
cached in-memory `ActionPlan` object; every phase reloads via
`load_plan()`. SHA-256, byte size, and `ExecutionAttemptRecord` counts
per Action are captured before and compared after — proving zero
re-execution, not merely "the file still exists."

### Attacks reused from existing regression coverage (not re-implemented)

Per spec section 49's "do not add hundreds of redundant unit tests":
duplicate-orchestrator claims, duplicate-execution-attempt claims,
unknown-tool/missing-adapter/sandbox-escape fail-closed behavior, and
the plan-structure mutation guard were already thoroughly covered by
v0.1.3.5/.6's own regression suites
(`test_action_plan_orchestrator.py`'s concurrency/security-invariant
tests, `test_execution_attempt.py`, `test_sandbox_fs.py`) — re-verified
as still passing by this checkpoint's full-suite run rather than
duplicated under a new name. New, genuinely novel hostile tests added
this checkpoint: `test_stale_worker_cannot_overwrite_current_plan_revision`
(plan-revision staleness didn't exist before v0.1.3.7's `revision`
column), `test_malicious_metadata_is_treated_as_inert_data`,
`test_approval_granted_but_no_adapter_still_never_executes`, and the
budget-integration class described above.

### Known limitations

- `MODEL_CALLS` remains tested only through its reservation/control
  interface (spec section 25's explicit instruction) — no automatic
  per-Action enforcement exists yet because no Action in this codebase
  makes a model call.
- The hostile benchmark's research phase uses two candidates (a
  comparison objective) to exercise the REAL Candidate Completeness Gate
  — that gate only applies at `MIN_CANDIDATES_FOR_GATE=2` (see
  `app/research_intelligence/gate.py`); a single-candidate objective
  would trivially return `ready=True` without ever exercising the gate,
  so this is a structural requirement, not an arbitrary choice.
- No new migration was needed or added this checkpoint (spec section 55
  explicitly preferred this) — every fix (`_check_execution_budget()`)
  reused v0.1.3.7's existing `BudgetAccountRecord`/`BudgetEventRecord`
  schema unchanged.

### FREEZE CANDIDATE

See `docs/v0.1.3_freeze_candidate.md` and this checkpoint's delivery
report for the full evidence trail and the explicit `YES`/`NO`
recommendation — not declared automatically merely because tests pass.

## NOT IMPLEMENTED YET

- v0.2 and any real-world capability phase — explicitly not started (spec
  section 75 of v0.1.3.8: "Do NOT begin v0.2... Do NOT design the next
  implementation phase beyond a brief recommendation").
- **Autonomous replanning driven by an LLM, sophisticated multi-strategy
  retry policies beyond the deterministic table above, a generic rollback/
  compensation framework, automatic enforcement of every budget type on
  every dispatch, parallel/distributed Action execution, real browser/
  email/desktop adapters, self-improvement, scheduling infrastructure** —
  none of these were implemented; v0.1.3.7 stops strictly at deterministic
  failure intelligence, bounded retry, controlled caller-supplied
  replanning, and budget enforcement on top of the existing pipeline.
- **Arbitrary filesystem tools** — only `file.create_sandboxed` (create,
  no overwrite, sandboxed, size-capped, extension-allowlisted) exists.
  No read/list/delete/move/rename tool, no path outside the sandbox root
  ever, no arbitrary binary writes (UTF-8 text only).
- **Delete/modify external files**, **shell execution** (PowerShell/cmd/
  bash/subprocess), **arbitrary Python code execution**, **browser
  control**, **desktop/keyboard/mouse control**, **email sending**,
  **Slack/Discord/Telegram/social-media/web publishing**, **purchases/
  financial transactions/money movement/cryptocurrency actions**,
  **software/package installation**, **OS configuration/registry/service
  control**, **process termination**, **SSH/remote-machine control**,
  **credential/secret access**, **self-modification/source-code
  modification**, **git commit/push**, **autonomous retries with side
  effects** — none of these has, or will ever silently gain, a registered
  `ToolAdapter` merely because a `ToolDefinition` exists for it (see
  "Metadata vs. capability" above).
- **Rollback engine** — a partially-succeeded (file written, verification
  failed) action's artifact is never automatically deleted; no rollback
  exists.
- **Retry/replan execution** — `retry_policy.py` only classifies; nothing
  re-runs a failed `Action` or reopens a `FAILED`/`REJECTED`/`CANCELLED`
  action back to `PLANNED`.
- **Runtime agent/workspace-specific grant enforcement** — see the
  "Documentation cleanup" note in the v0.1.3.3 section above; still an
  open integration gap.
- **Dry-run execution** — `ToolDefinition.supports_dry_run`/
  `PermissionDecision.dry_run_recommended` are metadata only; no dry-run
  engine exists yet, including for `file.create_sandboxed`.
- **Notification delivery** — no email/Slack/push notification is sent for
  any approval or execution event; only structured audit data exists.
- **External action-execution API endpoints** — no new API routes were
  added; `execute_action_durably()`/`reconcile_action()` are Python entry
  points only.
- **A second real `ToolAdapter`** — this checkpoint is entirely about
  durability/recovery around the existing one; no new capability.
- **P3/P4 real external execution** — no approval-gated tool has an
  adapter; the durable/approval-gated path is exercised only with
  in-memory fake adapters in tests (same as v0.1.3.4).
- **Automatic retries** — `EXECUTION_INTERRUPTED`'s `safe_to_retry=True`
  is a classification, not an action; nothing in this codebase
  automatically re-attempts a claim.
- **A rollback engine** — unchanged from v0.1.3.4; `SIDE_EFFECT_MISMATCH`
  blocks and requires human review rather than attempting to undo anything.
- **Autonomous startup recovery** — `discover_reconciliation_candidates()`
  is not wired into any application startup hook; nothing calls it or
  `reconcile_action()` automatically. A caller must invoke both explicitly.
- **Distributed multi-machine execution guarantees beyond the atomic
  claim** — the `idempotency_key` UNIQUE constraint correctly prevents two
  workers from both executing the same authorized Action, including across
  machines sharing the database, but this was only tested against a single
  SQLite file; a distributed database's exact isolation guarantees would
  need separate verification.
- **Mathematically guaranteed exactly-once external side effects** — see
  "Executor persistence ordering & crash windows" above. "Durable +
  idempotent + reconciled" is a strong, tested, real improvement over
  v0.1.3.4's crash-blind execution — it is NOT the same claim as
  distributed exactly-once delivery, which remains unsolved (nothing here
  spans a two-phase commit across the database and the filesystem, because
  no such thing exists for a plain filesystem write).
- v0.2 and any real-world capability phase.

## Audit preparation / integration (v0.1.3.3 contract, v0.1.3.4 wired)

v0.1.3.3 established the structured data (`id`, `action_id`, `status`,
`requested_by`, `decided_by`, `decided_at`, `action_hash`, `consumed`/
`consumed_at`) needed for these events without a schema change.
v0.1.3.4 wires `EXECUTION_STARTED`/`EXECUTION_SUCCEEDED`/`EXECUTION_FAILED`/
`VERIFICATION_STARTED`/`VERIFICATION_SUCCEEDED`/`VERIFICATION_FAILED`/
`APPROVAL_CONSUMED` into the existing `app/security/audit.py::record_event`
— **best-effort only**: `execute_action()` takes optional `workspace_id`/
`session` parameters; when either is omitted (the common case, since
`Action`/`ApprovalRequest` are workspace-agnostic domain objects with no
natural workspace to attribute to), audit recording is silently skipped
rather than forced with a fabricated `workspace_id`. This is a documented
limitation, not a silent bug — the same integration gap noted for runtime
grant enforcement above. `APPROVAL_REQUESTED`/`APPROVAL_GRANTED`/
`APPROVAL_REJECTED`/`APPROVAL_EXPIRED`/`APPROVAL_CANCELLED`/
`APPROVAL_INVALIDATED` (on an `ApprovalHashMismatchError`) remain
contract-only — nothing in `approval_engine.py` itself was touched to emit
them; only the Executor's own new events are wired.

## Persistence

**`ApprovalRequest` is durable as of v0.1.3.4** —
`app/database/models.py::ActionApprovalRequest` (table
`action_approval_requests`, migration `b0a3e6d998fc`), with
`app/decision_intelligence/approval_persistence.py` bridging it to the
pure-domain pydantic object. Deliberately a **separate table/model** from
the pre-existing task-scoped `Approval` — see the v0.1.3.3
"Reconciliation" section above for the full rationale (unchanged, still
applies). `action_id` is intentionally NOT a foreign key: `Action`/
`ActionPlan`/`Decision` still have no backing table (see below) — this row
is keyed by the Action's UUID string alone.

**`Action`, `ExecutionResult`, and `VerificationResult` are durable as of
v0.1.3.5** — `ActionRecord`/`ExecutionAttemptRecord`/`ExecutionResultRecord`/
`VerificationResultRecord` (migration `1a868c95f4ee`), bridged via
`app/decision_intelligence/execution_persistence.py`. This closes exactly
the gap the v0.1.3.4 write-up flagged: an in-memory-only execution result
cannot survive a process restart, and a 24/7 Jarvis process will restart.
Access patterns were no longer a guess by this point — `durable_action_executor.py`
and `reconciliation.py` are the real, now-built consumers that informed the
schema (see "Durable ExecutionAttempt" / "Reconciliation Engine" above).

**`ActionPlan` is durable as of v0.1.3.6** — `ActionPlanRecord` (table
`action_plans`, migration `2b3daea54d5c`, chained from v0.1.3.5's
`1a868c95f4ee`), bridged via
`app/decision_intelligence/action_plan_persistence.py`. This closes the gap
the v0.1.3.5 write-up left open just below: an `ActionPlan`'s aggregate
state (status, failure policy, the plan-level orchestration lease) now
survives a process restart, which a 24/7 Jarvis process resuming a
multi-Action plan requires. Member `Action`s were already durable — the new
row simply gives the *plan itself* (status, lease, structural-integrity
hash) a durable home, without touching the already-durable
`ActionRecord`/`ExecutionAttemptRecord`/`ExecutionResultRecord`/
`VerificationResultRecord` schema at all.

`Decision` remains a plain Pydantic domain object — **no migration was
added for it.** Nothing yet needs to query a past Decision's own state
across a process boundary the way an in-progress ActionPlan now does;
adding its persistence now would still be the same premature schema guess
v0.1.3.1 warned against (how a `Decision` relates to `Task`/`Project`
long-term). That remains deferred to whichever future checkpoint actually
needs it.

**Failure/recovery/replan/budget history is durable as of v0.1.3.7** —
five new tables (migration `7f2c9a1e4b6d`, chained from v0.1.3.6's
`2b3daea54d5c`): `failure_records`/`recovery_decisions` (bridged via
`app/decision_intelligence/failure_intelligence.py`/`recovery_policy.py`'s
own persistence helpers, following the same domain-object/repository split
every prior checkpoint used), `replan_proposals` (bridged via
`app/decision_intelligence/replan.py`), and `budget_accounts`/
`budget_events` (bridged via `app/decision_intelligence/budget.py`). Two
small, additive columns were also added to EXISTING tables:
`action_records.superseded_by_action_id` (nullable, no FK — deliberately
NOT a new `ActionStatus` enum member, which would have required a full
SQLite table rebuild to widen an existing `CHECK` constraint for no
functional benefit) and `action_plans.revision` (the structural version a
replan increments). Neither existing column's semantics changed.

## Reused vs. new abstractions

Reused, not duplicated:

- `app.database.models.PermissionLevel` — `Action.permission_level`.
- `app.database.models.RiskLevel` — `Action.risk_level`.
- The `_VALID_TRANSITIONS` dict + typed-error state-machine shape from
  `app/orchestration/state_machine.py`.
- The DFS cycle-detection approach from
  `app/orchestration/planner.py::_assert_no_cycles`.
- The `ready: bool` + structured-reasons result shape from
  `app/research_intelligence/schemas.py::ComparisonReadiness`
  (`PlanReadinessResult`).

New, deliberately not merged into an existing concept:

- `ApprovalRequestStatus` (`PENDING/APPROVED/REJECTED/EXPIRED/CANCELLED`) is
  a new enum, not a reuse of `app.database.models.ApprovalStatus`
  (`PENDING/APPROVED/REJECTED` only, Task-scoped, already persisted). An
  `ApprovalRequest` is Action-scoped and needs `EXPIRED`/`CANCELLED` states
  the existing Task-level approval concept never needed.
- `DecisionStatus`, `ActionPlanStatus`, `ActionStatus`, `FailureCategory`
  are all new — nothing pre-existing overlapped with them.

### Reused vs. new abstractions (v0.1.3.3)

Reused, not duplicated:

- `ApprovalRequestStatus` (`PENDING/APPROVED/REJECTED/EXPIRED/CANCELLED`,
  from v0.1.3.1) is used as-is — its five states already matched exactly
  what the Approval Engine needed; no schema change to the enum itself.
- `action_hash.py::compute_action_hash` — `authorize_action()`'s exact-hash
  check calls straight into the unmodified v0.1.3.1 hashing function.
- `action_state_machine.py::assert_transition` — every Action-state move in
  `approval_engine.py` (`advance_to_waiting_for_approval`,
  `authorize_action`, `finalize_action_from_approval_outcome`) goes through
  it; no new transition table, no bypass.
- `permission_engine.py::PermissionDecision`/`PermissionOutcome` — consumed
  directly as input to `create_approval_request()`, not re-derived.

New, deliberately not merged into an existing concept:

- `ApprovalRequest.expires_at`/`consumed`/`consumed_at` — additive fields
  (spec section 11/12 explicitly permitted schema evolution); existing
  v0.1.3.1 `ApprovalRequest` construction/serialization tests are
  unaffected since all three default appropriately.
- The `approval_engine.py` typed-error family
  (`ApprovalEngineError` and its subclasses) — no prior equivalent; the
  existing task-scoped flow (`app/services/approval_service.py`) raises
  bare `ValueError`, which this checkpoint deliberately does not imitate
  for a security-relevant contract.

### Reused vs. new abstractions (v0.1.3.4)

Reused, not duplicated:

- `action_state_machine.py::assert_transition`/`can_transition` — every
  transition the Executor drives (`EXECUTING`/`EXECUTION_SUCCEEDED`/
  `VERIFYING`/`VERIFIED`/`COMPLETED`, and every fail-closed exit) goes
  through the unmodified v0.1.3.1 table; no new states, no new edges.
  `_FAIL_TARGET_BY_SOURCE`'s `APPROVED -> CANCELLED` choice directly
  reuses the precedent `approval_engine.py` set for `EXPIRED -> CANCELLED`.
- `approval_engine.py::validate_approval_for_action`/`consume_approval` —
  the Executor's approval gate calls straight into the unmodified v0.1.3.3.1
  functions; no re-implementation of validity checking.
- `tool_registry.py::ToolRegistry.resolve` — the Executor's tool-resolution
  step is the same call v0.1.3.2's Permission Engine already used; the
  Executor does not re-derive tool compatibility.
- `FailureCategory` (v0.1.3.1) — `EXECUTOR_FAILURE_CATEGORY` maps every new
  `ExecutorFailureCode` onto it rather than introducing a second,
  competing coarse taxonomy.
- `app/agents/registry.py`'s duck-typed `AgentProtocol` convention — the
  new `ToolAdapter` Protocol follows the same "no forced base class" shape.
- `ExecutionResult`/`VerificationResult` (v0.1.3.1 contracts) — extended
  with additive optional fields (`execution_attempt_id`, `error_code`,
  `side_effect_occurred`, `adapter_version`), not replaced or duplicated.

New, deliberately not merged into an existing concept:

- `ToolAdapter`/`ToolAdapterRegistry` — a distinct trust boundary from
  `ToolDefinition`/`ToolRegistry` (metadata vs. executable capability;
  spec section 12 explicitly required keeping these separate).
- `sandbox_fs.py`'s path-safety primitives — no prior filesystem-writing
  code existed in this codebase to reuse (`app/tools/url_safety.py` is the
  closest analog in spirit — deterministic, fail-closed input validation
  before a real operation — but validates URLs, not filesystem paths).
- `ExecutorFailureCode`/`EXECUTOR_FAILURE_CATEGORY` — a finer-grained
  taxonomy than `FailureCategory` alone provides, explicitly requested by
  spec section 22 rather than overloading the existing enum with new,
  execution-specific members.
- `ActionApprovalRequest`/`ActionApprovalRequestRepository` — see
  "Persistence" above; deliberately not merged with `Approval`/
  `ApprovalRepository`.

### Reused vs. new abstractions (v0.1.3.5)

Reused, not duplicated:

- `action_hash.py::compute_action_hash` — `ActionRecord.action_hash`
  reuses it exactly (see "Payload/hash integrity" above); no second
  hashing algorithm.
- `action_state_machine.py::assert_transition`/`can_transition` — every
  transition both `durable_action_executor.py` and `reconciliation.py`
  drive goes through the unmodified v0.1.3.1 table.
- `tool_registry.py::ToolRegistry.resolve`,
  `approval_engine.py::validate_approval_for_action`/`consume_approval`,
  `tool_adapters.py::ToolAdapterRegistry`/`ExecutionContext` — the durable
  Executor calls straight into the same v0.1.3.2-v0.1.3.4 primitives the
  frozen `execute_action()` uses; no parallel implementation of tool
  resolution, approval validation, or adapter execution.
- The `_FAIL_TARGET_BY_SOURCE`/`ExecutionOutcome` shapes from
  `action_executor.py` — imported directly, not recreated.
- `sandbox_fs.py`'s path-safety primitives (via
  `SandboxFileCreateAdapter.inspect_effect()`, which calls
  `resolve_sandbox_path()` exactly as `execute()` does) — the same
  traversal/symlink/containment guarantees apply to read-only inspection
  as to a real write.

New, deliberately not merged into an existing concept:

- `ActionRecord`/`ExecutionAttemptRecord`/`ExecutionResultRecord`/
  `VerificationResultRecord` and their repositories — no prior durable
  equivalent existed for any of them.
- `durable_action_executor.py` — a new module rather than an extension of
  the frozen `action_executor.py`; see "Why a new module instead of
  extending the frozen Executor" above.
- `reconciliation.py`'s `ReconciliationClassification`/`ReconciliationResult`
  — no prior equivalent; distinct from, and not merged with,
  `PermissionOutcome`/`PermissionDecision` or `ApprovalValidityResult`,
  since a reconciliation classification answers a different question
  ("what actually happened, durably and on disk?") than either of those.
- `ResultProvenance` — no prior concept of "was this result original or
  reconstructed" existed anywhere in this codebase.

### Reused vs. new abstractions (v0.1.3.6)

Reused, not duplicated:

- `plan_validation.py::evaluate_plan_readiness` (and its DFS
  `detect_dependency_cycle`) — `validate_and_persist_plan()` calls it
  verbatim; no second dependency-graph-validation or cycle-detection
  algorithm was written for this checkpoint.
- `action_state_machine.py`, `permission_engine.py::evaluate_permission`/
  `apply_permission_decision`, `approval_engine.py::create_approval_request`/
  `authorize_action`/`finalize_action_from_approval_outcome`,
  `durable_action_executor.py::execute_action_durably`/`_upsert_action_record`,
  `reconciliation.py::reconcile_action` — every one of these v0.1.3.1-v0.1.3.5
  functions is called directly by `_advance_one_action()`/`reconcile_plan()`;
  none was re-implemented, forked, or bypassed.
- The `_VALID_TRANSITIONS` + typed-error state-machine shape from
  `action_state_machine.py` — `action_plan_state_machine.py` mirrors it
  exactly for `ActionPlanStatus`, rather than inventing a differently-shaped
  contract for plan-level transitions.
- The `INSPECT -> RECONCILE -> VERIFY -> DECIDE` reconciliation philosophy
  from v0.1.3.5's `reconciliation.py` — `plan_reconciliation.py` applies the
  same philosophy one level up (plan truth is recomputed FROM reconciled
  Action truth), rather than inventing a separate recovery strategy.
- The optimistic-concurrency (`version` column + conditional `UPDATE`) and
  atomic-claim (`WHERE owner IS NULL OR ...`) patterns from
  `ActionRecordRepository`/`ExecutionAttemptRecord`'s idempotency-key
  constraint (v0.1.3.4/.5) — `ActionPlanRecordRepository` applies the same
  two patterns at the plan level instead of inventing new locking
  primitives.

New, deliberately not merged into an existing concept:

- `ActionPlanRecord`/`ActionPlanRecordRepository` — no prior durable
  equivalent existed for plan-level state or the plan-level orchestration
  lease.
- `action_eligibility.py::ActionEligibility` — a distinct concept from
  `ActionStatus` (a durable fact) and from `PermissionOutcome`/
  `ApprovalValidityResult` (single-Action authorization facts); eligibility
  answers "is this specific Action workable right now given the whole
  plan's dependency graph," which none of those existing types answer.
- `action_plan_orchestrator.py`'s `StopReason`/`OrchestrationResult` — no
  prior "why did a multi-step process pause" contract existed; not merged
  with `ReconciliationResult` (a different question: "what happened to one
  Action," not "why did the whole plan stop").
- `compute_plan_hash()` — deliberately a narrower field-selection than
  `action_hash.py::compute_action_hash()`, not a reuse of it; see
  "Plan-integrity hash" above for the exact rationale.
- `PlanReconciliationClassification` — a coarser, plan-level sibling to
  v0.1.3.5's `ReconciliationClassification`, not a replacement for it; the
  two answer different questions at different levels and are used together,
  never interchangeably.

### Reused vs. new abstractions (v0.1.3.7)

Reused, not duplicated:

- `FailureCategory` (v0.1.3.1) and `EXECUTOR_FAILURE_CATEGORY` (v0.1.3.4)
  — `failure_intelligence.py::classify_failure()` maps through the SAME
  table `action_executor.py`/`durable_action_executor.py` already
  populate; no second, competing failure taxonomy.
- `reconciliation.py::reconcile_action()` (v0.1.3.5, unmodified) — every
  crash-interrupted "is a retry safe?" question is answered by calling
  straight into it; `_process_failure()` only acts on its
  `safe_to_retry`/`human_review_required` result, never re-derives it.
- `plan_validation.py::detect_dependency_cycle()` (v0.1.3.1) —
  `replan.py`'s cycle protection calls it against the projected
  post-replan graph; no second cycle-detection algorithm.
- `permission_engine.py::evaluate_permission()`/`approval_engine.py`
  (v0.1.3.2/.3, unmodified) — a replacement Action's authority is
  established ENTIRELY by being persisted at `ActionStatus.VALIDATED` and
  then advancing through the SAME unmodified pipeline every Action always
  has; no new permission/approval logic of any kind exists in `replan.py`.
- `ExecutionAttemptRecord`'s claim-by-UNIQUE-INSERT pattern (v0.1.3.5) —
  `BudgetEventRecord.idempotency_key`'s atomicity/restart-safety uses the
  identical mechanism, and `ActionPlanRecordRepository`'s
  version-guarded-conditional-UPDATE lease pattern (v0.1.3.6) is reused
  again for `ReplanProposalRepository.claim_for_apply()`.
- `action_to_record_fields()`/`compute_action_hash()`/
  `evaluate_plan_readiness()`'s "persist a brand-new Action" path
  (v0.1.3.1/.5/.6) — `apply_replan()` persists a replacement Action through
  the EXACT same `action_to_record_fields()` helper every other Action
  creation path uses; no parallel Action-construction code exists.

New, deliberately not merged into an existing concept:

- `RecoveryDecision`/`RecoveryEvaluation` — a distinct question from
  `PermissionOutcome` (may this Action execute at all?) and
  `ReconciliationClassification` (what actually happened, durably?):
  "given that this Action failed, what should happen next?" No prior type
  answered that question.
- `FailureRecord`/`RecoveryDecisionRecord` — durable, append-only history,
  deliberately NOT merged into `ActionRecord.last_error` (a single mutable
  field that only ever holds the most recent error); see "Durable
  failure/recovery history" above for the full rationale.
- `retry_controller.py`'s bypass of `action_state_machine.py` via its own
  `_RETRY_REENTRY_SOURCES` allowlist — a new, narrow, explicitly-scoped
  mechanism rather than adding a general-purpose "authorized regression"
  concept to the shared state machine, which every other caller would then
  have to reason about.
- `ReplanProposal`/`ReplanProposalRecord` — no prior "a structured,
  durable proposal to change a plan's own structure" concept existed;
  `ActionPlan.revision` is new for the same reason `ActionRecord.version`
  (optimistic concurrency) and `ActionPlanRecord.revision` (structural
  version) are kept as two DIFFERENT counters, not one — they answer
  different questions ("was this row written concurrently?" vs. "how many
  times has this plan's structure been deliberately revised?").
- `app.decision_intelligence.budget` (`BudgetScope`/`BudgetType`/
  `BudgetAccountRecord`/`BudgetEventRecord`/`reserve_and_consume()`) — a
  new module and schema, deliberately NOT merged with the pre-existing
  `app.orchestration.budget`/`UsageRecord` (the mission-level API-call/
  token/cost budget from v0.1.1/v0.1.2): that budget tracks LLM usage
  against a whole mission; this one tracks recovery-specific resources
  (retries, replans, model calls, estimated cost) at Action/Plan scope,
  answers a structurally different question, and is enforced through a
  different mechanism (durable ledger + atomic reservation vs. a
  post-hoc `UsageRecord` sum check). The two remain intentionally
  independent — see `tests/test_budget.py` (the pre-existing mission
  budget) vs. `tests/test_recovery_budget.py` (this one) for the
  corresponding test-level separation.
