# JARVIS OS — v0.1.3 FORMAL FREEZE MANIFEST

This document is the authoritative, human-readable freeze contract for
Jarvis OS v0.1.3. It describes the FROZEN BEHAVIORAL AND SECURITY BASELINE
of the release — not merely a development milestone summary. Every future
Jarvis version must be checked against this manifest before it can claim
compatibility with, or safe extension of, v0.1.3.

---

## 1. Release identity

| Field | Value |
|---|---|
| Product | Jarvis OS |
| Release | v0.1.3 |
| Subsystem | Decision & Action Intelligence |
| Status | **FROZEN** |
| Previous frozen subsystem | v0.1.2 — Research Intelligence |
| Freeze date | 2026-09-20 |
| Final verification baseline | 1431 passed, 0 failed |
| Alembic head | `7f2c9a1e4b6d` |
| Hostile benchmark | PASS |

This manifest exists so that any future Jarvis version can be mechanically
and manually checked for regression against a fixed, verified baseline —
not so that this milestone is merely remembered as "done."

---

## 2. Frozen version chain

All of the following are frozen as one coherent release:

- v0.1.2 — Research Intelligence
- v0.1.3.1 — Domain Contracts + State Machines
- v0.1.3.2 — Permission Engine + Tool Registry
- v0.1.3.3 — Approval Engine (+ v0.1.3.3.1 Approval Validity Hardening)
- v0.1.3.4 — Durable Authorization + Sandboxed Executor
- v0.1.3.5 — Durable Execution & Recovery
- v0.1.3.6 — Durable ActionPlan Orchestration
- v0.1.3.7 — Failure Intelligence + Bounded Retry + Controlled Replanning + Budget Enforcement
- v0.1.3.8 — Final Hostile End-to-End Benchmark

---

## 3. Architectural control pipeline (frozen)

```
OBJECTIVE
  -> RESEARCH
  -> EVIDENCE READINESS
  -> DECISION
  -> DECISION GATE
  -> ACTION PLAN
  -> PERMISSION EVALUATION
  -> APPROVAL GATE
  -> BUDGET GATE
  -> DURABLE EXECUTION
  -> VERIFICATION
  -> FAILURE INTELLIGENCE
  -> RETRY / REPLAN / RECONCILIATION
  -> CRASH / RESTART RECOVERY
  -> QA
  -> EXECUTIVE REPORT
```

**No future capability may bypass this control pipeline merely because the
capability itself is technically available.** A new ToolAdapter, a new
agent, or a new entry point does not get to skip Permission Evaluation,
Approval, Budget, Verification, or truthful Reporting just because it is
new — every real effect flows through this pipeline or it does not happen.

---

## 4. Core security invariants (frozen)

### Authority

- Agent request ≠ permission.
- Tool availability ≠ permission.
- User objective ≠ blanket permission.
- `ToolDefinition` ≠ executable capability.
- Approval ≠ creation of capability.
- External content is untrusted input.

### Decision safety

- A Decision that is not evidence-ready/comparison-ready cannot become
  actionable merely because an LLM recommends action.
- Decision readiness (`comparison_ready`) is mechanically enforced in
  `decision_rules.py::apply_decision_transition` — never derived from an
  LLM-set field.

### Action safety

- Every executable operation is represented by an `Action`.
- Actions pass deterministic validation and authority checks
  (`plan_validation.py`, `permission_engine.py`) before execution.

### Permission safety

Permission levels remain:

| Tier | Meaning |
|---|---|
| P0 | Internal reasoning/analysis |
| P1 | Read-only/search |
| P2 | Internal creation/local controlled artifact |
| P3 | Reversible external change |
| P4 | Consequential external action |
| P5 | Money/security/install/privileged operating-system action |

Future versions may refine these definitions but must not silently weaken
their security meaning.

### Approval safety

- P4/P5 actions never execute solely because an agent requested them.
- Approvals are action-specific.
- Approvals are bound to the canonical security-relevant Action payload via
  `action_hash.py::compute_action_hash` (`action_type`, `tool_name`,
  `inputs`, `expected_result`, `permission_level`, `risk_level`).
- A changed security-relevant Action payload invalidates prior
  authorization (hash mismatch -> `ApprovalHashMismatchError`).
- An expired approval is invalid (`check_approval_validity`).
- A rejected approval cannot authorize execution.
- Approval cannot create a `ToolAdapter` or capability that does not
  exist — `ADAPTER_NOT_FOUND` fires regardless of approval status.

### Execution safety

Agents do not call real capabilities directly. The enforced boundary is:

```
Agent
  -> Action
  -> Permission Engine
  -> Approval/Budget Controls
  -> Durable Executor
  -> Tool Registry
  -> Tool Adapter
  -> Effect
  -> Verification
```

### Failure safety

- `UNKNOWN` failure never causes blind automatic retry (`retry_policy.py`
  fail-closed table).
- Verification failure does not automatically cause uncontrolled
  re-execution.
- Retries are bounded (`Action.retry_count`/`max_retries`).
- Replans create a changed authority context via a replacement Action
  rather than silently mutating the old approved Action.
- A changed P4/P5 Action requires fresh approval — the old Action's
  approval is never read, copied, or re-validated against a replacement.

### Recovery safety

- Crash recovery reconciles known durable state
  (`reconciliation.py::reconcile_action`) before deciding whether execution
  may occur again.
- Side-effect ambiguity fails safe (`SIDE_EFFECT_MISMATCH` ->
  `safe_to_retry=False`, `human_review_required=True`).
- No retry is ever justified merely because a process crashed.

### Budget safety

- Budget exhaustion fails closed.
- `ACTION_ATTEMPTS` and `ESTIMATED_COST` are enforced before the execution
  boundary when configured.
- `RETRIES` and `REPLANS` remain bounded.
- `MODEL_CALLS` is currently reservation/contract-only because no Action
  currently performs model calls. **This limitation must remain visible
  and must not be documented as having live Action-execution
  integration.**

### Reporting safety

Jarvis must not report bare `COMPLETED` when material work remains:

- waiting for approval;
- dependency blocked;
- failed;
- unresolved;
- requiring human review.

Truthful reporting (`plan_qa.py`/`executive_report.py`) is a
security/control property, not merely a UI preference.

---

## 5. Frozen permission model

Verified directly against `app/decision_intelligence/permission_engine.py`:

| Tier | PermissionLevel | Outcome |
|---|---|---|
| P0/P1 | `READ` | `ALLOW` |
| P2 | `WRITE` | `ALLOW_WITH_AUDIT` |
| P3 | `EXTERNAL_ACTION` | `REQUIRE_APPROVAL` (conservative — no rollback/reversal engine exists yet to make `ALLOW_WITH_AUDIT` safe for a real external mutation) |
| P4 | `EXTERNAL_ACTION` | `REQUIRE_APPROVAL` |
| P5 (financial) | `FINANCIAL_ACTION` | `REQUIRE_APPROVAL` |
| P5 (privileged/admin) | `ADMIN` | `BLOCK` unconditionally |

This is the actual source behavior (`_OUTCOME_BY_PERMISSION_LEVEL` /
`_ACTION_TYPE_FLOOR` in `permission_engine.py`) — no detail in this section
is an assumption. An unrecognized `action_type` always `BLOCK`s; it never
defaults to a safe tier.

---

## 6. Genuine ToolAdapter inventory

Verified directly against `app/decision_intelligence/tool_adapters.py::build_default_adapter_registry()`:

```python
registry.register(SandboxFileCreateAdapter.name, SandboxFileCreateAdapter())
```

Exactly one call, exactly one adapter registered.

**Genuine production ToolAdapter count: 1**

| Tool name | Real adapter? |
|---|---|
| `file.create_sandboxed` | **YES — the only one** |
| `research.read`, `plan.create`, `artifact.draft`, `mock.external_action`, `communication.send_email`, `content.publish`, `resource.delete_external`, `finance.spend_money`, `system.install_software`, `system.privileged_shell` | No — `ToolDefinition` metadata only |

A `ToolDefinition` without a registered `ToolAdapter` is a metadata/
capability *declaration* only — it describes what a tool would mean if it
existed, and cannot execute anything. Attempting to execute any
adapter-less tool fails closed with `ADAPTER_NOT_FOUND`
(`action_executor.py`/`durable_action_executor.py`). The presence of
definitions for email, publishing, finance, or privileged operations does
**not** mean Jarvis currently possesses those capabilities — it means the
permission/approval framework has already been designed to govern them
*if* a real adapter is ever added.

No discrepancy was found — the repository matches the expected baseline.

---

## 7. Sandbox security baseline

Verified against `app/decision_intelligence/sandbox_fs.py` and
`tests/test_sandbox_fs.py` (part of the 1431 passing tests):

- **Sandbox root confinement**: `resolve_sandbox_path()` resolves the
  joined path and checks `resolved_target.is_relative_to(resolved_sandbox_root)`
  — never a string-prefix check.
- **Traversal prevention**: absolute paths (POSIX, Windows, drive-relative,
  UNC), `..`/`.` traversal in `/` or `\` form, null bytes, and empty input
  are all rejected before any filesystem call.
- **Symlink defense**: an existing symlink is never followed, at the leaf
  or anywhere in the parent chain — `Path.resolve()` dereferences on-disk
  symlinks, so a symlink planted inside the sandbox pointing outside it is
  caught by the same containment check. (Windows junctions/reparse points
  are not exercised by a dedicated automated test — documented as a known
  gap, not claimed as verified.)
- **Overwrite protection**: no `overwrite=True` escape hatch exists;
  writing to an existing target fails.
- **Size limit**: content capped at 1 MiB (`sandbox_fs.MAX_CONTENT_BYTES`),
  checked before any write.
- **Extension allowlist**: `.txt/.md/.json/.csv/.log/.yaml/.yml` only; no
  extension at all is rejected too.
- **Deterministic verification**: `SandboxFileCreateAdapter.verify()`
  re-derives every claim from the actual filesystem (existence,
  containment, regular-file-ness, byte length, SHA-256 content hash, UTF-8
  round-trip) — it never trusts what `execute()` merely reported.
- **No arbitrary filesystem capability**: the adapter can only create a new
  UTF-8 text file strictly inside `Settings.sandbox_root`; it cannot read,
  modify, move, or delete anything, and cannot address any path outside
  the sandbox root.

---

## 8. Durability baseline

Durable record categories introduced through v0.1.3 (schema in
`app/database/models.py`):

| Record | Role |
|---|---|
| `ActionPlanRecord` | Durable mirror of an `ActionPlan` — its actions, dependency graph, hash, and revision counter. |
| `ActionRecord` | Durable mirror of an `Action` — status, optimistic-concurrency `version`, supersession pointer. |
| `ExecutionAttemptRecord` | One durable, uniquely-idempotency-keyed attempt to execute a specific Action payload. |
| `ExecutionResultRecord` | Durable record of what an adapter reported after executing. |
| `VerificationResultRecord` | Durable record of independently re-derived post-execution verification. |
| `ActionApprovalRequest` | Durable `ApprovalRequest` row, including atomic `consume_if_valid()`. |
| `FailureRecord` | Durable classification of why an Action failed. |
| `RecoveryDecisionRecord` | Durable record of what recovery action (retry/replan/block/human-review) was decided and why. |
| `ReplanProposalRecord` | Durable proposed replacement Action, its acceptance/rejection, and its eventual application. |
| `BudgetAccountRecord` | Durable ledger balance for one budget type/scope. |
| `BudgetEventRecord` | Durable, idempotency-keyed individual reserve/consume event against a budget account. |

No schema fields are invented in this manifest beyond what the above
models already define.

---

## 9. Retry / replan baseline

- **Retry** = same Action identity, same security payload, same effect
  intent — an attempt is repeated because a *transient* condition is
  believed to have changed, never because the plan of action changed.
- **Replan** = a changed approach represented through a **replacement**
  Action with its own identity, its own hash, and its own fresh authority
  evaluation.

Verified properties:

- Retry is bounded (`Action.retry_count` vs. `max_retries`).
- Retry count/history is durable (`ActionRecord`, `FailureRecord`,
  `RecoveryDecisionRecord`).
- `UNKNOWN` failures never trigger blind retry — fail-closed by
  `retry_policy.py`.
- Verification failures route through reconciliation, not automatic
  re-execution.
- A replacement Action receives fresh authority evaluation — the
  Permission Engine and Approval Engine both re-derive their
  classification from the replacement's own `action_type`/`tool_name`
  rather than inheriting the failed Action's classification.
- The old (failed) Action row is never deleted or overwritten — only
  `superseded_by_action_id` is set on it, preserving history.
- Plan `revision` increments on every applied replan
  (`compute_plan_hash`/`ActionPlanRecordRepository.update_if_version_matches`).
- Every dependent Action is rewired from the failed Action's ID to the
  replacement's ID through controlled replan logic
  (`apply_replan()`'s idempotent dependency-rewiring loop).
- Prior approval cannot authorize a changed replacement payload — the
  replacement is a new Action with a new hash; the old
  `ApprovalRequest`/hash binding does not apply to it.

---

## 10. Crash/recovery baseline

Jarvis v0.1.3 provides durable recovery and deterministic reconciliation
but does **not** claim mathematically guaranteed distributed exactly-once
execution:

> **Durable + idempotent + reconciled ≠ distributed exactly-once
> guarantee.**

Verified behavior:

- **Durable execution attempts**: every attempt to execute a specific
  Action payload is persisted as an `ExecutionAttemptRecord` before the
  adapter is invoked.
- **Idempotency keys**: `idempotency_key = sha256(f"{action_id}:{action_hash}")`,
  UNIQUE at the database level — the constraint itself is the atomic
  execution claim.
- **Effect inspection**: `SandboxFileCreateAdapter.inspect_effect()`
  performs a read-only inspection of the actual on-disk state during
  reconciliation — it never re-invokes `execute()`.
- **Reconstruction**: a proven-matching side effect with a missing durable
  result can be reconstructed and the Action advanced to `COMPLETED` in
  one reconciliation pass, because every step involved is independently
  safe/read-only/deterministic.
- **Reconciliation**: `reconcile_action()` classifies durable/actual-state
  mismatches into named categories (`CONSISTENT_COMPLETED`,
  `EXECUTION_INTERRUPTED`, `SIDE_EFFECT_MISMATCH`, `AMBIGUOUS_STATE`, etc.)
  and only recovers along paths that are independently safe.
- **Stale/interrupted execution handling**: an `ExecutionAttempt` whose
  lease has expired is flagged `RECONCILIATION_REQUIRED` — nothing
  automatically reclaims or reruns it.
- **Prevention of blind duplicate execution**: an already-`COMPLETED`
  Action is never re-executed, checked before any adapter is resolved; a
  mismatched/ambiguous side effect never triggers automatic retry.

---

## 11. Budget baseline

| Budget type | Enforcement |
|---|---|
| `ACTION_ATTEMPTS` | Enforced at the orchestrator's pre-execution boundary (`action_plan_orchestrator.py::_check_execution_budget()`) when configured — before `execute_action_durably()`/adapter invocation, and before approval consumption on the approval-gated path. |
| `ESTIMATED_COST` | Enforced at the same pre-execution boundary, same function, when configured and when the Action carries an `estimated_cost`. |
| `RETRIES` | Bounded/enforced through `Action.retry_count`/`max_retries` and the retry/recovery controllers. |
| `REPLANS` | Bounded/enforced through the plan-scoped `BudgetType.REPLANS` account inside `apply_replan()`. |
| `MODEL_CALLS` | **Reservation/control contract only** in v0.1.3 — no Action currently invokes a model, so there is no live per-Action enforcement path. This is a documented, deliberate scope limitation, not an oversight, and must not be described as having live execution integration. |

A denied `ACTION_ATTEMPTS`/`ESTIMATED_COST` check fails the Action durably
(`FAILED`, zero `ExecutionAttempt` ever created) and routes through the
same `_process_failure()` pipeline as any other failure — no second,
undocumented failure path exists.

---

## 12. Database migration baseline

| Field | Value |
|---|---|
| Alembic heads | 1 |
| Current head | `7f2c9a1e4b6d` |

Verified migration chain (`alembic history`):

```
2974c89766cf (initial schema)
  -> 352f47664add (evidence and usage records)
  -> f3097cded9d8 (evidence source_quality column)
  -> 88c5eab86b3b (evidence_depth column)
  -> b0a3e6d998fc (action approval requests, v0.1.3.4)
  -> 1a868c95f4ee (durable execution state, v0.1.3.5)
  -> 2b3daea54d5c (durable action plans, v0.1.3.6)
  -> 7f2c9a1e4b6d (failure intelligence, bounded retry, replan, budgets, v0.1.3.7)
```

v0.1.3.8 introduced **no migration** — both of its fixes (budget-boundary
gating, `replan.py` concurrency fix) reused the existing schema unchanged.

---

## 13. Test baseline

| Field | Value |
|---|---|
| Full suite | 1431 passed, 0 failed |
| Warning | One unrelated, pre-existing `DeprecationWarning` (Starlette `TestClient`/AnyIO `BlockingPortal` alias) — not connected to any v0.1.3.x code |
| New v0.1.3.8 test delta | 23 (1431 − 1408 v0.1.3.7 baseline) |
| Replan concurrency stress | 20/20 isolated runs passed |
| Standalone hostile benchmark | PASS |

Key verified benchmark outcomes (from the final independent verification
pass):

- Evidence readiness: negative (`ready=False`) → positive (`ready=True`).
- Decision gate: blocked an unready Decision (`comparison_ready=False,
  blocked=True`), then allowed a ready one.
- Seven-Action dependency graph (`A1 -> A2 -> {A3, A4} -> A5 -> A6 -> A7`)
  built and orchestrated.
- Safe sandboxed execution: five actions completed via
  `file.create_sandboxed` only.
- Transient failure: A4 hit one transient failure.
- Exactly one bounded retry for the benchmark's retry case
  (`a4_execute_calls=2`).
- Real validation failure: A5 failed with a genuine `VALIDATION_FAILURE`
  from malformed inputs, not a manufactured one.
- Controlled replacement Action: A5 replanned to A5b.
- Plan revision incremented (`new_revision=2`).
- Historical superseded Action retained (old A5 marked `SUPERSEDED`, never
  deleted).
- Crash/restart reconciliation: `hashes_match=True`,
  `attempts_unchanged=True`.
- Budget attack tests: all 4 `TestBudgetIntegrationAttacks` tests passed.
- P4 stopped at approval: `Prepare publish action` ended
  `WAITING_FOR_APPROVAL`.
- P5 remained non-executed: `Prepare paid-advertising action` ended
  `BLOCKED_BY_DEPENDENCY`/`WAITING_FOR_DEPENDENCIES`, never reachable.
- Truthful QA: all 8 action rows correctly classified.
- Overall status: `COMPLETED_WITH_REVIEW` (never bare `COMPLETED`).
- Zero unauthorized external side effects; zero real P3/P4/P5 side
  effects.

---

## 14. Hostile benchmark baseline

Final benchmark plan concept:

```
A1 -> A2 -> {A3, A4} -> A5 -> A6 -> A7
```

| Action | Behavior |
|---|---|
| A4 | Transient failure -> bounded retry -> success. |
| A5 | Real validation failure -> controlled replan -> replacement A5b. |
| A6 | P4 publishing boundary -> `WAITING_FOR_APPROVAL`. No real publishing adapter exists — this only proves the approval gate holds. |
| A7 | P5 financial/paid-advertising boundary -> not executed, `BLOCKED_BY_DEPENDENCY`. No real financial adapter exists. |

**No real publishing or financial adapter exists in this codebase.** A6
and A7 demonstrate that the permission/approval/dependency machinery
correctly halts consequential and financial work at the appropriate gate
— not that Jarvis can publish content or spend money.

---

## 15. Known limitations

These are **scope boundaries of the frozen release**, not defects, unless
existing project documentation (`docs/decision_intelligence.md`,
`docs/v0.1.3_freeze_candidate.md`) describes them as such:

1. Action dispatch is sequential.
2. No parallel Action execution.
3. No distributed worker pool.
4. PostgreSQL distributed/concurrent behavior has not yet been proven.
5. SQLite concurrency testing does not prove distributed concurrency.
6. No mathematical distributed exactly-once guarantee.
7. `MODEL_CALLS` is contract/reservation-only.
8. No generic rollback/compensation framework.
9. No real browser capability.
10. No real email capability.
11. No real publishing capability.
12. No real financial capability.
13. No unrestricted shell capability.
14. No privileged operating-system capability.
15. No autonomous software installation.
16. No self-modification capability.
17. No autonomous Git/code-deployment capability.
18. No multi-machine worker architecture yet.

---

## 16. Prohibited capability assumptions

v0.1.3 does **NOT** imply Jarvis can currently:

- send emails;
- publish content;
- spend money;
- purchase products/services;
- run unrestricted shell commands;
- install software;
- administer Windows/Linux;
- control arbitrary browser sessions;
- control arbitrary desktop applications;
- modify its own source code autonomously;
- deploy its own code;
- alter permission policy autonomously;
- approve its own consequential actions;
- bypass budget controls;
- bypass approval controls;
- bypass verification;
- access arbitrary files outside its sandbox.

Future versions must add such capabilities deliberately, through governed
`ToolAdapter`s subject to the full control pipeline (§3), rather than
assuming them from agent intelligence or from the mere existence of a
`ToolDefinition`.

---

## 17. Rules for modifying frozen components

### New features

New features **MUST NOT** be added directly to v0.1.3 frozen scope. They
belong to a later version.

### Bug fixes

A frozen component may be modified only for a reproducible defect,
security vulnerability, compatibility requirement, or data-integrity
problem. Any such change requires:

1. Documented reproduction.
2. Root-cause analysis.
3. Smallest reasonable fix.
4. A regression test.
5. Affected targeted tests re-run.
6. Complete test-suite re-run.
7. Hostile/security benchmark re-run when the change touches security,
   permissions, approvals, budgets, execution, retry, replan, recovery, or
   reporting.
8. An updated freeze/change record.

### Security weakening

No later version may silently weaken a frozen invariant. If a future
architecture intentionally changes an invariant:

- the change must be explicit;
- rationale documented;
- threat model reconsidered;
- tests updated deliberately;
- migration/compatibility impact documented;
- user approval obtained before implementation when it materially expands
  Jarvis's authority.

### Refactoring

Refactoring frozen security-critical modules must not be performed merely
for style or convenience. A refactor requires a concrete engineering
reason and proof that frozen behavior remains intact.

---

## 18. Compatibility Contract for v0.2+

Every future Jarvis release must be checked against this v0.1.3 freeze
manifest. Future versions may add capabilities, but must demonstrate that:

- new ToolAdapters remain governed by the full control pipeline (§3);
- permission ceilings still apply (§5);
- approval requirements remain authoritative and hash-bound (§4 Approval
  safety);
- budget gates cannot be bypassed (§11);
- changed Actions invalidate stale approval;
- crash recovery remains safe (§10);
- retries remain bounded (§9);
- replanning does not inherit invalid authority (§9);
- verification remains separate from execution;
- reporting remains truthful (§4 Reporting safety);
- new capabilities cannot create hidden side channels around the Action
  pipeline.

---

## 19. Freeze checklist

For use on future releases and maintenance changes:

```
[ ] Full regression suite passes
[ ] Alembic has exactly one expected head
[ ] Frozen security invariants preserved
[ ] ToolAdapter inventory reviewed
[ ] No unexpected capability added
[ ] Approval binding preserved
[ ] Permission behavior preserved
[ ] Budget enforcement preserved
[ ] Retry/replan controls preserved
[ ] Recovery/reconciliation preserved
[ ] Sandbox controls preserved
[ ] QA/reporting truthfulness preserved
[ ] Known limitations reviewed
[ ] Hostile benchmark passes when required
```

---

## 20. Provenance of this manifest

This manifest was compiled from an independent verification pass against
the live repository at `C:\Users\Gyuro\jarvis-os` (full pytest suite,
isolated replan-concurrency stress run, and a fresh standalone hostile
benchmark run), cross-checked against `docs/decision_intelligence.md` and
`docs/v0.1.3_freeze_candidate.md`, and against direct reads of
`permission_engine.py`, `tool_adapters.py`, `sandbox_fs.py`,
`replan.py`, and `action_plan_orchestrator.py`. No unsupported capability
claim in this document goes beyond what those sources demonstrate.

Freeze status recorded here (`FROZEN`) reflects the verification evidence
gathered; the final freeze decision authority remains with Peter/Sol per
`docs/v0.1.3_freeze_candidate.md`.
