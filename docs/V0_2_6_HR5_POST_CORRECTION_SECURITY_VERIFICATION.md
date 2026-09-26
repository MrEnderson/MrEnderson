# Jarvis OS v0.2.6 — HR5 Focused Post-Correction Security Verification

```text
subject                       = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r3)
subject status on entry       = CORRECTED R3 — PENDING HR5 POST-CORRECTION VERIFICATION
prior reviews checked         = HR2 (docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md)
                                HR3 (docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md)
                                HR4 (docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md)
review type                   = security verification only
design_modified               = false
hr2_hr3_hr4_modified          = false
code_tests_validators_modified= false
opendex_opened_or_modified    = false
final_status                  = R3 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

---

## 1. Independence

- This verification was done in a **fresh session**. That session did not
  write the v0.2.6 design (r1, r2 or r3), HR2, HR3 or HR4. It had no access
  to the conversations that produced them. It saw only the repository.
- The r3 correction record (§0.4, §44.6) was treated as a **claim to test**,
  not as evidence. Every HR4 correction was checked against the r3 text,
  the frozen v0.2.5 design and the current code.
- **Limitation (HR5-16).** This reviewer is an AI model, very likely from the
  same model family as the authors of every earlier document. Session
  independence holds. Organizational and model-diversity independence do
  not. Shared blind spots are possible. The recommendation of HR3-16 and
  HR4-12 still stands: a human should review §6, §8, §9, §16.5, §17.6 and
  §21.3 before freeze.

## 2. Repository state

All checks were read-only.

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `13796dcd61015098429f343e2fb982a9c75698bb` |
| origin/master | `13796dcd61015098429f343e2fb982a9c75698bb` (= HEAD) |
| Tag at HEAD | `v0.2.5.1` |
| `git status --short -uall` at start | 4 untracked files: the design, HR2, HR3, HR4. No tracked change. |
| `git diff --stat HEAD` | empty (no tracked production change) |
| Alembic head | `7f2c9a1e4b6d` (from `check_v013_freeze_baseline.py`) |
| ToolAdapters | `['file.create_sandboxed']` |

**SHA-256 at start:**

| Document | SHA-256 |
|---|---|
| Design r3 | `ffa4cee724e9fe9b6b61f29bff052c624bcfb31ace85474d2de691fcd4df20c8` |
| HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |

The HR2 and HR3 hashes are identical to those that HR4 §39 recorded, so
neither was changed after HR4. The design hash differs from HR4's r2 hash
(`23a798d1…`), as expected for r3.

## 3. Materials reviewed

| Material | Extent |
|---|---|
| Design r3 (4,323 lines) | **In full**, §0–§45 |
| HR4 | §1–§3 and §28–§39 in full (findings, blockers, LineagePair recommendation, validation); the rest for context |
| HR2, HR3 | Headers and independence statements. HR2/HR3 residual claims were checked only through HR4's verified mapping and the r3 §44 tables. |
| v0.2.5 design | §3.1–§3.5 (authority model, check-not-clip), §4 (principals, roots, HR-06), §5 (contracts), §6 (issuance), §7 (lineage, CR-01 requester rules, parent pointers never searched), §9 (redelegation depth), §10 (time), §11 (revocation), §12 (lifecycle), CR-01 rows, T-05/T-13/T-44/T-46 |
| Code | `app/database/models.py` (every `String`/`Text`/`JSON` column), `app/api/routes.py` (all routes), `app/schemas/approvals.py`, `app/utils/logging.py`, every `logger.*` call in `app/`, `app/main.py` CLI output, `app/decision_intelligence/tool_adapters.py` and `sandbox_fs.py` (symlink handling), file/subprocess/cache usage across `app/` |

OpenDex was not opened.

---

## 4. HR4-01 verification — delegated child lineage

**r3 mechanism.** T-7 (§7.3, §9.7) issues one transaction containing:

- a child authority edge whose parent is the parent ESC's authority leaf;
- a child clearance edge whose parent is the parent ESC's clearance leaf;
- a `LineagePair` with `parent_pair_id = parent.lineage_pair_id`;
- the child `TaskControlRecord`;
- the `DelegatedExecutionBinding`.

The ESC Issuer (§9.3 step 6) reaches the pair **only by id** through the
binding. It then requires all of the following:

- `pair.parent_pair_id == parent.lineage_pair_id`;
- both edge parents equal the parent's leaves;
- `pair.issuer_event == deb.issuance_event`;
- `deb.task_id == tcr.task_id`;
- the parent is not REVOKED;
- every ancestor pair is effective (§21.3 rule 4, §34 step 3).

§21.3 rule 2 withdraws search. Rule 6 makes each edge belong to at most one
pair, ever.

| Attack | Path attempted | Result under r3 |
|---|---|---|
| **A. Root-pair substitution** | A child TCR naming the owner's root pair `R_fin` | Impossible to write: a CHILD TCR carries only `delegated_execution_binding_id`, and its pair comes from the binding. A root pair has `parent_pair_id = None ≠ parent.lineage_pair_id`, so the result is `ESC_LINEAGE_INVALID`. A ROOT TCR needs a T-8 owner act. **DENY.** |
| **B. Sibling substitution** | Child A's ESC tries to use Child B's pair | A's TCR names A's binding (both written in one T-7 transaction). B's pair has `issuer_event = B's issuance_event ≠ A's deb.issuance_event`. Leaf uniqueness stops B's edges being re-paired. **DENY.** |
| **C. Same agent/objective, broader pair** | Rely on a broader pair for the same (agent, objective, profile) | No component queries by that key (§21.3 rule 2; TST-CB-046 adds a static check). `ESC_LINEAGE_AMBIGUOUS` is withdrawn. **No fallback exists.** |
| **D. Parent replay** | A binding created under parent ESC P1, used after P1 ended or was superseded by continuation P2 | The binding names P1. P1 is ENDED or TERMINATED, not REVOKED, so issuance is allowed, but only with the pair P1 created. P2 carries the same pair, so no authority changes. If the parent pair was revoked, the result is DENY (ancestor check). **No widening.** |
| **E. Mixed pair** | Authority leaf from delegation X, clearance leaf from Y | The pair is store-built in one transaction. The ESC Issuer checks both edge parents against the one parent ESC. Leaf uniqueness covers revoked pairs. Mixing requires writing to the store directly (C-in/C-os, out of contract). **DENY.** |
| **F. Nested delegation** | Parent → Child → Grandchild; the grandchild tries the grandparent's pair or leaves | T-7 from the child ESC sets `parent_pair_id = child pair` and parents both edges on the child's leaves. The ESC Issuer checks against the **immediate** parent ESC, and the ancestor walk covers every generation. v0.2.5 continuity (`delegate(i) = delegator(i+1)`) and depth rules apply to the authority edge. **Each generation descends from the one before it.** |
| **G. Parent revocation race** | Parent pair revoked after the binding exists but before the child ESC is issued | Step 6 requires the parent not REVOKED and the pair effective. Rule 4 requires every ancestor pair to be effective. Rule 5 makes descendant pairs ineffective. **DENY.** After issuance, §34 step 3 revokes the child ESC at its next decision. |

Residuals found (none reopens HR4-01):

- the destination set and environment class are not attenuated along T-7
  (HR5-05);
- T-7 breadth and idempotency are unbounded (HR5-06);
- T-7 leaves the redelegation selectors unspecified (HR5-09).

**Verdict: HR4-01 — RESOLVED_IN_R3.**

## 5. HR4-02 verification — task-control trust

`TaskProposal ≠ TaskProfile ≠ TaskControlRecord ≠ Task row` is stated in
§9.6 and enforced by the ESC Issuer:

- step 1 accepts only a TCR written by `TASK_ADMISSION(T-8)` or
  `CHILD_ISSUANCE(T-7)`;
- objective, profile, origin, creating event and binding come only from
  the TCR;
- relations come only from `ExecutionRelation`s written by the Execution
  Scheduler (step 12).

| Planner-controlled field | Can it become a security input? |
|---|---|
| candidate agent | No. The agent is `profile.agent`. A disagreement gives `ESC_BINDING_CONTRADICTION` (DENY). |
| `requires_approval` / candidate approval | No. `approval_class` comes from the profile. A weaker proposal gives DENY; a stronger one is ignored (HR5-14). |
| objective ref | No. ROOT takes it from the owner act; CHILD takes it from the parent ESC. |
| `parent_task_id` | No. Parentage comes only from the binding. |
| `retry_count` | No. Retries come from Scheduler relations bounded by `retry_policy`. |
| dependencies | T-6 permits only an attempt at a flow. Hand-offs are item flows. |
| candidate profile | T-1 closed-vocabulary membership only (root: `allowed_task_profiles`; child: `allowed_child_profiles`). |
| predecessor list | No. Predecessors come from the relation; unknown means all prior ESCs of the task. |
| root/child status | No. `origin_kind` is written only by T-8 or T-7. |

**Contradiction handling.** Step 5 reads the untrusted Task row and
proposal only to **deny**. That is a DoS channel against the task whose
row is mutated: any writer of legacy Task rows can make an owner-admitted
root task unstartable. It never widens anything (HR5-14).

Residuals: the root pair is not bound to its task (HR5-08), and the text
has inconsistencies about who writes TCRs (HR5-14). Neither creates a
widening path (§13 of this review).

**Verdict: HR4-02 — RESOLVED_IN_R3.**

## 6. HR4-03 verification — artifact laundering by adapter effects

HR4-03 required five corrections:

1. join every read resource;
2. declared effect-side read sets, where an undeclared read means DENY;
3. commits and archives join their members;
4. a policy-defined Jarvis-controlled domain;
5. tests.

r3 §17.2 and §17.6–§17.8 apply 1, 3, 4 and 5. They apply 2 only as a
**declaration** requirement.

- An **undeclared read set** (no declaration) gives
  `CB_ARTIFACT_READ_UNDECLARED`.
- An **undeclared read** (the adapter reads more than it declared) is not
  detected. §17.6 rule 2 calls it "a reviewed adapter defect … out of
  contract at Level 1", and claims that "at ISO-TCB Level 2+ the sandbox
  exposes only the declared set".

The HR4 exploit (path-only copy of a bound file) is closed. The same class
of laundering remains reachable by a class-M attacker who controls
filesystem structure rather than arguments (§15 of this review):

- symlinks created by a checkout;
- archive member paths;
- repository config.

**Verdict: HR4-03 — PARTIALLY_RESOLVED** (residual HR5-01).

## 7. HR4-04 verification — content-store inventory

r3 adds R-22..R-28 and S-32..S-48, the three-class model and the CR-IFR-01
registry with a discovery-based validator. That fixes the specific HR4
omissions. The independent re-audit (§27 of this review), however,
finds content-bearing surfaces that are missing or misclassified.

The most important is **application logging**. S-14 marks it class **B
(content-free)** with no current-state marker, no R-fact and no CR. The
live code logs all of the following to stdout:

- full objective text (`app/agents/jarvis.py:65`);
- task titles (`app/agents/research.py:275`, `strategy.py:115`, `qa.py:56`,
  `execution.py:38`);
- objective-derived research queries (`app/agents/research.py:784`);
- QA issues and diagnostic summaries (`app/orchestration/evaluator.py:299`,
  `:392`);
- raw exception text (`app/orchestration/executor.py:274`).

The design's completeness claim ("every content-bearing table, column and
route") is therefore falsified again, and the registry's class-B
"content-free proof" for S-14 would be false.

**Verdict: HR4-04 — PARTIALLY_RESOLVED** (residual HR5-02; rule gap
HR5-03).

## 8. HR4-05 verification — taint ceiling and initial label

HR4-05 required four corrections:

1. per-dimension ceiling;
2. defined clamping;
3. an owner-bound objective content label;
4. a label for rendered control fields.

All four are in §14.7 and §14.9. The predicate and clamp were checked
dimension by dimension (§17 and §18 of this review) and are sound and
monotone in the safe direction. One new defect is in the genesis table:
`L_ctrl.expires_at = ObjectiveVersion expiry` and
`L_sys.expires_at = policy-version expiry` refer to fields that neither
record defines. That is LOW, not a widening (HR5-10).

**Verdict: HR4-05 — RESOLVED_IN_R3.**

## 9. HR4-06 verification — LineagePair issuance obligations

| HR4-06 item | r3 | Verified |
|---|---|---|
| 1. Leaf uniqueness | §21.3 rule 6 (a unique constraint per leaf column, including revoked pairs) | Yes |
| 2. Enclosing transaction | §21.3 rule 1 + "one atomic commit domain"; §40.A obligation (1) | Yes (see §11 of this review for the fallback protocol) |
| 3. Owner digest over both halves | §21.3 rule 7 `pair_approval_digest` containing `root_request_digest` | Yes. Compatible with v0.2.5 HR-06 (one event mints one root). |
| 4. Clearance revokers, no un-revoke | §21.5 | Yes, with an asymmetry versus the v0.2.5 path (HR5-11) |
| 5. Id non-reuse | §21.6, INV-CB-089 | Yes |

**Verdict: HR4-06 — RESOLVED_IN_R3.**

## 10. HR4-07 verification — connector resource identity and redirects

- `connector_claimed_resource` is separated from
  `canonical_resource_identity`.
- Untrusted connectors take their adapter-level ceiling. An undeclared
  ceiling means NO_FLOW.
- Trusted adapters report transport facts, including the final URL, the
  TLS identity and the resolved IP class.
- Redirect hops are each egress-authorized. Redirects to
  loopback/private/internal origins are denied. The label is the final
  origin ⊔ contributing hops ⊔ the initial URL when stricter. An unknown
  identity maps to `UNKNOWN_WEB`/NO_FLOW.

Both HR4 corrections (the lying connector and the redirect final origin)
are present and tested (TST-CB-062, -091, -092).

The broader identity boundary has a gap that HR4 did not raise. The
private-address rule covers **redirect hops only**. The initial hop, DNS
rebinding, connect-time versus resolve-time addresses, and URL
canonicalization are unspecified. This is filed as a new finding (HR5-04),
not as a failure of the HR4-07 corrections.

**Verdict: HR4-07 — RESOLVED_IN_R3** (new adjacent finding HR5-04).

---

## 11. LineagePair analysis

**Commit point.** In the primary model, all five inserts plus audit share
one database transaction (§21.3). There is exactly one durable commit, so
no partial state can exist.

| Failure injected | Outcome |
|---|---|
| Authority write succeeds, clearance fails | Transaction aborts; nothing exists |
| Clearance succeeds, pair fails | Aborts; nothing exists |
| Pair exists, binding missing (fallback protocol only) | The pair is unreachable: `ESC_DELEGATION_UNBOUND`. Its edges are "named by a pair", so the sweep does not revoke them, but nothing can bind them. Fail-closed. |
| Binding exists, TCR write fails (fallback only) | No TCR, so `ESC_TASK_UNCONTROLLED` |
| Crash before commit | Nothing exists |
| Retry after an uncertain commit | **Not specified.** A second T-7 creates a second child task, pair and edges with new ids. Each is ≤ parent, so there is no widening. It duplicates work and effects (HR5-06). |
| Duplicate request replay | Same as above. T-8 is protected by single-use owner events. T-7 has no idempotency key. |

**Fallback protocol and v0.2.5.** v0.2.5 `DelegationRecord` has "NO
status" (v0.2.5 §5). A `PENDING_PAIR` state must therefore live outside
the v0.2.5 record (for example in the pair store). Until the sweep runs,
an orphan authority edge is a fully effective v0.2.5 edge. It is
contained only because every Action must carry `leaf == esc.authority_leaf_id`
(§22 AuthorityGate). Recorded as INFO within HR5-08. It is not an
amendment.

**Revocation matrix.**

| Event | Effect |
|---|---|
| Authority leaf revoked only | Pair ineffective (rule 5); §34 step 3 → REVOKED |
| Clearance leaf revoked only | Pair ineffective; REVOKED |
| Parent revoked | Ancestor check fails for every descendant; v0.2.5 cascade (`UPSTREAM_INEFFECTIVE`) and clearance meet over the lineage both apply |
| Either half expires | The leaf is not effective, so the pair is not effective |
| Agent retired or disabled | DI-17: a lifecycle event since issuance makes the pair permanently ineffective; re-enabling restores nothing |
| Stores report different epochs | One anchored epoch (§31); regression or dependency failure means DENY everything (INV-CB-037/053) |

**LineagePair verdict:** the pair mechanism has no permission-shopping path
for authority or clearance. Its issuance, lookup and revocation are
coherent. The LOW items (HR5-08, HR5-11) are hardening. HR5-05 and HR5-06
concern T-7 inputs that lie outside the pair.

`LINEAGEPAIR R3 CONFIRMED`

AMD-025-01 is not needed. No frozen-contract contradiction was found
(§31 of this review).

## 12. Requesting-principal analysis (CR-01)

**Frozen v0.2.5 semantics** (§7, T-05, T-19, T-44, T-46, DI-16):

- the requesting principal is the principal that requests the **Action**;
- it is bound insert-once at Action creation, from the control-plane
  invocation context, never from content;
- "leaf delegate must equal the requesting principal";
- there is no default requester; `owner` and `"system"` hold no delegation.

Requester and delegate are therefore **identical by frozen rule**: the
agent asking for the Action is the agent whose leaf authorizes it.

**r3 semantics** (§9.2, §9.9, INV-CB-077):

- `requesting_principal = ESC.agent = delegate of both leaves`;
- every Action created in the ESC binds `requester = esc.agent` and
  `leaf = esc.authority_leaf_id`.

| Case | Actor asking for the Action | Principal authorized to perform it | Match with CR-01 |
|---|---|---|---|
| ROOT | The ESC agent (its model proposes; the harness asks) | Delegate of the root authority edge = the ESC agent | Yes. The owner is the *delegating* principal. v0.2.5 never lets the owner be an Action requester. |
| DELEGATED_CHILD | The child ESC agent | Delegate of the child edge = the child agent | Yes. Naming the parent as requester would give `DELEGATE_MISMATCH` in v0.2.5 and `CB_ACTION_BINDING_MISMATCH` in r3. |

r3 is also stricter than v0.2.5 in one respect: v0.2.5 lets the leaf id
come from content as a lookup key, while r3 fixes it to the ESC's leaf.
That is compatible, because it only narrows.

**Semantics conclusion:** there is no semantic mismatch for root or child
executions. The r2 overloaded `ESC.principal` is gone.

**Wording hazard (LOW, in HR5-14).** The §9.9 table row "Who requested the
work?" answers "the canonical owner" (ROOT) and "the parent execution"
(CHILD), while the next row defines `requesting_principal` as the agent.
The two uses of "request" differ. It should read "Who initiated the
work?" so that no implementer binds the owner or parent as a CR-01
requester.

## 13. TaskControl analysis

**Writers (exhaustive per §9.6):**

- Task Admission (T-8, ROOT, owner act only);
- child issuance (T-7, DELEGATED_CHILD, from a LIVE parent ESC only).

The Execution Scheduler writes ExecutionRelations, not TCRs.

**The laundering question:** can model proposal → Task Admission → trusted
TCR happen without an owner, policy or delegation decision?

- **As specified, no.**
  - ROOT requires an owner act. The ESC Issuer additionally requires a root
    pair whose `issuer_event == tcr.admission_owner_event_id`, and root
    pairs exist only from T-8.
  - CHILD requires a binding and pair created by T-7 in the same
    transaction.
- **Two text defects weaken the defence in depth (HR5-08, HR5-14):**
  1. The §9.6 "TaskProfile provenance" paragraph says Task Admission
     validates a proposal against the allowed workflow, including
     `allowed_dependency_profiles`, and the delegation state, and outputs "a
     TaskControlRecord naming an existing TaskProfile, or DENY". It does not
     say this happens only inside T-8 or T-7. An implementer could read it
     as a third, dependency-based admission route. §0.4 also lists "the
     Execution Scheduler for retries/continuations" as a TCR writer,
     contradicting §9.6 and §9.3 step 1.
  2. The ESC Issuer's ROOT path does not check that the root pair belongs to
     *this* task. The CHILD path checks `deb.task_id == tcr.task_id`, but
     ROOT pairs carry no `task_id`, and there is no uniqueness constraint on
     `TCR.root_lineage_pair_id` or `TCR.admission_owner_event_id`. The
     `pair_approval_digest` binds profile, objective and event, but not the
     admitted task or the proposal the owner reviewed.

  If defect 1 were implemented, a second ROOT TCR that reused an existing
  root pair and event would pass the ESC Issuer. The impact is bounded:
  the same agent, profile, objective and pair the owner approved, but for
  additional work the owner did not review. There is no widening of
  authority or clearance. Hence LOW, not HIGH.

## 14. Retry / continuation / fork analysis

| Relation | Written by | Inherits | Can differ | Verified |
|---|---|---|---|---|
| RETRY | Scheduler (T-10) from closed codes + `retry_policy` | Identical bindings; genesis ⊒ ⊔ predecessors' final H | Nothing security-relevant (`ESC_RETRY_REBINDING`) | Yes |
| CONTINUATION | Scheduler, after termination | Same as RETRY | Nothing | Yes. No fresh authority or clearance decision. |
| FORK | Scheduler, only if the profile allows FORK | Identical bindings; genesis ⊒ the forked-from H at the fork point | Only in-memory progress after the fork | Yes |
| CHILD | ESC Issuer in the ESC transaction, from a T-7 binding | Own genesis; content only by flows | Profile, pair and clearance (narrowed) | Yes. It never uses retry or fork semantics. |

**Conversion attempts:**

- RETRY → CHILD is impossible without a binding.
- CHILD → RETRY keeps the child's binding and ancestor checks.
- A retry that needs a changed binding is DENY, and new work needs a new
  T-8 or T-7.
- Re-spawning a sibling child instead of retrying drops predecessor taint
  inheritance. Every artifact and output of the failed child is still a
  labeled item or bound artifact, so nothing is laundered. This is the
  documented design.

**Gaps (hardening, HR5-08):**

- An ExecutionRelation is not stated to be single-use (one relation → one
  `new_esc_id`). A reused RETRY relation could exceed `max_retries`.
- `retry_policy` bounds retries, but no bound is stated for FORK or
  CONTINUATION counts.

## 15. Artifact derivation

**Operation walk-through** (§17.7 rules), with a CONFIDENTIAL source A and
declared reads:

| Chain | Result |
|---|---|
| A → copy → B | B ⊒ A ⊔ H (new id, provenance COPY) |
| A → rename → B | Same `ArtifactRef`, new `ArtifactLocation`, same label |
| A → ZIP → extract B | archive ⊒ ⊔ members; B ⊒ archive label (never a lower per-member digest match) |
| A → conversion → B | B ⊒ A ⊔ H |
| A → generated patch → apply → B | patch ⊒ both versions; B ⊒ target ⊔ patch ⊔ H |
| A → commit → checkout elsewhere → B | blob bound ⊒ A; checkout ⊒ ⊔ bindings for that blob digest ⊔ H |

**Restrictions cannot fall** for any effect whose actual reads equal its
declared, resolved read set. The re-ingestion digest join (§17.3) also
backstops byte-identical relocation by non-Jarvis processes.

**Undeclared tool reads (prompt §12).** §17.6 rule 2 relies on the
declaration. What enforces that reads stay within it?

| Adapter class | What actually confines reads under r3 | Assessment |
|---|---|---|
| Trusted adapter at Level 1 (ISO-AGENT) | Only reviewed code | Class M controls **filesystem structure**, not only arguments. Examples: a checkout creates a symlink blob (mode 120000); an archive carries `../` member names; a repository carries `.git/config` filters, hooks or `includeIf`; an attacker swaps a file between resolve and read (TOCTOU). A copy, zip or commit adapter with ordinary library defaults (for example `shutil.copy` follows symlinks) then reads a bound RESTRICTED artifact that is **not** in its declared set. The output is labeled from the declared set only. A later zip of that output has new bytes, so the digest join does not catch it. §38.2 files this under C-in ("reviewed-code defect"), but the attacker is class M driving an honest adapter: a confused deputy, which TC-03 claims to defend. The existing `file.create_sandboxed` adapter already refuses symlinks (`tool_adapters.py:160`, `sandbox_fs.py:23–28`), so the codebase treats this as a real hazard. The contract does not make it an obligation. |
| Untrusted connector (ISO-CONN) | Level 3 sandbox | §16.2 labels connector *results* by the adapter-level ceiling. §17.6 labels connector-produced *artifacts* by the declared read set, which is not tied to what the sandbox mounts. The ceiling rule should also apply to artifacts. |
| Isolated tool worker | CR-ISO-01 | §6.5 Level 2 is "separate worker process, no DB handle, no .env". It does not define per-invocation file views, and CR-ISO-01 (§40.B) does not include "expose only the declared read set". The Level-2 enforcement claimed by §17.6 rule 2 is therefore **not provided by any CR**. |

§17.2 item 4 ("for every read, the content digest of the bytes read equals
the binding's `content_digest`") would close symlink and TOCTOU attacks if
it applied to effect-side reads through an ArtifactRef-keyed reader. r3
does not say that it does. §17.2 item 5 routes "reads" through ingestion,
and effect-side reads are not ingestion. **Finding HR5-01.**

A secondary gap: the §17.6 output label uses `binding.label(r)` only. It
does not apply the digest join over `r`'s bytes, so an artifact that was
mislabeled once propagates its lower label through later derivations.

**Git taint (prompt §13).** `commit ⊒ ⊔ tree ⊔ parent commit ⊔ H`.

- Yes: once a CONFIDENTIAL blob enters the history, every descendant
  commit object on that line is ⊒ CONFIDENTIAL permanently, even after
  the file is deleted.
- **Confidentiality-safe:** push sends every missing reachable object, so
  blocking the push is correct.
- **Availability:** the commit label is used both for *reading commit
  objects* (log, message, metadata) and for push. The parent join is
  redundant for push, which r3 already defines as "⊔ over everything
  reachable that is sent". It is pathological for local reads.
- **Security-preserving alternative:** give the commit object its own
  content label (its tree's blobs ⊔ its message ⊔ H; the parent is named
  only by hash), and compute a separate reachability label for any
  transmission as the join over the objects actually sent. The same
  confidentiality holds with no permanent contamination of metadata reads.

HARDENING (HR5-13). Not a freeze blocker.

**Digest-based re-ingestion (prompt §14).**

| Case | Behaviour | Assessment |
|---|---|---|
| Same bytes from an independent public source | Joined with every registered label for that digest | Sound, since it never lowers a label. False positives, e.g. an MIT `LICENSE` committed in a CONFIDENTIAL repo taints every web copy with `REPOSITORY(r)`. |
| Same bytes under multiple labels | ⊔ of all | Sound |
| Huge registry | Requires a digest index over bindings and export records | Not specified (implementation) |
| Hash collision | SHA-256 | Acceptable |
| Transformed or equivalent content, partial excerpts | Not joined | Correctly stated as a residual for external transforms; covered by ArtifactDerivation for Jarvis transforms |
| **Membership oracle** | An ESC writes candidate bytes and re-ingests them. If they equal a registered CONFIDENTIAL artifact, the item becomes undeliverable, which leaks 1 bit per probe across compartments. | New residual, rate-bounded by §32 denial bounds; exact-bytes guesses only (HR5-12) |
| **Label poisoning** | A RESTRICTED-tainted ESC writes a popular public file; every later ingestion of those public bytes is RESTRICTED | Availability only (HR5-12) |

## 16. Information-flow registry (HR4-04 / CR-IFR-01)

**Discovery versus registration versus runtime mediation.**

| Surface kind | Discoverable by the §18.2 validator? | Runtime fail-closed under r3? |
|---|---|---|
| ORM columns, including JSON columns (new keys stay under the column's class) | Yes (SQLAlchemy metadata + Alembic) | Broker writes only through registered targets. Legacy code is covered by the Q class. |
| Dynamic model fields | Yes at startup, if the validator inspects live metadata. Not for models registered after startup. | Not specified |
| Route response models / new serializers | Yes (FastAPI router at startup). Not for routes added after startup. | Not specified |
| ToolRegistry adapters | Yes. `ToolRegistry.register` is callable at runtime (`tool_adapters.py:131`) | Not specified for post-startup registration |
| Log emitters | **Call sites can be listed. Payload content cannot be proven content-free** (structlog kwargs are untyped). No discovery method is defined. | No |
| Provider payloads, adapter arguments | By design they are flows through the assembler and TOOL_ARG gates | Yes, once integrated |
| Library/SDK caches and SDK debug logging, temp files, subprocess pipes, stdout/CLI output, generated reports outside managed stores | **No** discovery source is named | **No** mediation requirement |

The prompt's key invariant is: *"an unregistered content-bearing
source/store/sink cannot become reachable at runtime."* r3 guarantees it
only for **broker releases**, because the broker has no sink target for an
unregistered surface. Content that the broker has legitimately released
into `AGENT_WORKING_STATE`, `MODEL_LOCAL` or `TOOL_ARG_INTERNAL` is then
held by reviewed agent or adapter code. That code can write it to any
process-level sink. At ISO-AGENT (Level 1, permanent for ordinary agents,
§6.5) nothing contains that write except code review and a CI scan that
cannot see these sinks.

A missed CI discovery is therefore **not** safe by default, and the
contract does not say what makes it safe. The current code proves the
point: application logs carry content (§7 and §27 of this review), and the
design classifies them as B. **Finding HR5-03.**

## 17. Taint ceiling algebra

The check below is independent of the one in the design. For
`L1 ⊑ L2` (L2 more restrictive), each conjunct of
`within_taint_ceiling(L, C, now)` satisfied by L2 is satisfied by L1:

| Conjunct | Direction check |
|---|---|
| `L.level ≤ C.max_level` | L1.level ≤ L2.level ≤ max ✓ |
| `L.compartments ⊆ C.allowed` | L1 ⊆ L2 ⊆ allowed ✓ |
| `L.integrity ≥ C.min_integrity` | L1 ≥ L2 ≥ min ✓ |
| `C.required_sinks ⊆ L.sinks` | L1.sinks ⊇ L2.sinks ⊇ req ✓ |
| `required_purposes ⊆ L.purposes`, `required_nodes ⊆ L.nodes` | Same as sinks ✓ |
| `L.excluded ∩ must_not_exclude = ∅` | L1.excl ⊆ L2.excl ✓ |
| `L.persistence ≥ C.min_persistence` | L1 ≥ L2 ✓ |
| `export_required ⇒ L.export` | L2.export ⇒ L1.export ✓ |
| `L.expires_at > now + margin` | L1.exp ≥ L2.exp ✓ (the only time-dependent conjunct; it can only turn false) |
| `L ≠ NO_FLOW`, versions equal | NO_FLOW is top; `⊑` requires equal versions ✓ |

**Clamp:**

- `max_level` uses min; `allowed_compartments` uses ∩ K. These are upper
  bounds, narrowed ✓.
- `required_sinks`, purpose, `min_persistence`, `export_required` and the
  expiry margin are requirements. They are checked satisfiable against K,
  else `ESC_CEILING_UNSATISFIABLE`, never relaxed ✓.
- `min_integrity` is profile-only. Clearance has no integrity dimension ✓.

**Purpose of the ceiling.** It protects **availability and integrity**,
not confidentiality. It keeps an execution usable for its declared sinks,
purposes and persistence, and lets a profile refuse lower-integrity input.
Confidentiality is enforced by `flow()` and clearance. A more restrictive
joined label can only turn the predicate from true to false. A failed
predicate denies a delivery and never widens behaviour.

**No case was found** in which a more restrictive label passes where a less
restrictive one failed. The algebra is coherent.

## 18. Initial labels

`initial_label = L_sys ⊔ L_ctrl [⊔ L_obj] [⊔ L_inh]` (§14.9):

| Input | Label | Assessment |
|---|---|---|
| System policy | `SYSTEM_TEXT`: INTERNAL, TRUSTED_SYSTEM, all local sinks, all purposes, DURABLE_MEMORY, export false | Defined. `expires_at = policy-version expiry` refers to a field `SecurityPolicyVersion` does not have (§29.4) → HR5-10 |
| Rendered control fields | `CONTROL_RENDER`: INTERNAL, `{W,P}`, INTERNAL_RECORD, `{esc.purpose}` | Defined. `expires_at = ObjectiveVersion expiry`, but §10.1 has no expiry field → HR5-10 |
| Objective content | Owner-bound `content_label` in the T-2 act | Defined; default pre-filled, not RESTRICTED by default ✓ |
| Owner prose (T-8) | Label bound in the admission act; OWNER_ASSERTED | ✓ |
| Planner prose | UNTRUSTED item ⊒ proposer H, delivered after genesis | ✓ |
| Inherited retry content | ⊔ predecessors' final H | ✓ |

**Embedded untrusted text in control fields.** The rendered fields are:

- profile id and its reviewed template;
- purpose class;
- objective id and version;
- closed task type;
- canonical scope ids;
- output schema id.

Scope ids are server-generated UUIDs (`String(36), default=new_uuid`,
`models.py`). No name, title, description or objective text is rendered.
Placement never raises integrity (INV-CB-072). No upgrade path was found.
`objective_id` is chosen in an owner act; it should be restricted to the
v0.2.4 identifier character set so that it can never carry prose (noted in
HR5-10).

## 19. Revocation authority

| Revoker | Root authority | Child authority | Root clearance | Child clearance | Own subtree |
|---|---|---|---|---|---|
| Canonical owner | ✓ | ✓ | ✓ | ✓ | ✓ |
| Edge delegator / ancestor delegator | — (owner-delegated) | ✓ (v0.2.5 §11: any lineage where it is delegator) | — | ✓ **only via its own LIVE ESC, in that ESC's subtree** (T-9, §21.5) | ✓ |
| Delegate (renunciation) | ✓ own root edge (reduces only) | ✓ own edge | ✓ own | ✓ own | — |
| Unrelated agent | ✗ | ✗ | ✗ | ✗ | ✗ |

- Nobody can revoke an unrelated principal's authority or modify
  owner-rooted records. Renunciation only narrows. ✓
- **Asymmetry (HR5-11).** The authority half follows the v0.2.5 revoker set
  (any edge where the agent is delegator, in any lineage). The clearance
  half is ESC-scoped. §21.5 claims the two sets "mirror". Because revoking
  either half kills the pair, the *effective* revoker set is the v0.2.5
  one. An injected ESC of agent X in task T1 can therefore revoke X's own
  delegations in an unrelated task T2. That is narrowing only, so it
  cannot widen anything, but it is cross-task sabotage and contradicts the
  "mirrors" statement.

## 20. Resource identity and redirects

| Attack | r3 coverage | Gap |
|---|---|---|
| Redirect to another origin | Each hop egress-checked; label by the final origin | — |
| Redirect to loopback/private/link-local/internal | Denied (§16.5 rule 2) | — |
| **Initial URL whose host resolves to a private or loopback IP** | Not covered; rule 2 names redirects only | **Yes** |
| **DNS rebinding** (resolve public, connect private; or re-resolution between check and connect) | "resolved IP class" is a reported fact, but no rule says a non-public connected peer denies the fetch or changes identity, and no rule says the connected address (not a resolve-time address) is authoritative | **Yes** |
| IPv6 loopback/ULA/link-local, IPv4-mapped IPv6 (`::ffff:127.0.0.1`), `0.0.0.0` | Not enumerated | **Yes** |
| Alternate port | The port is part of the origin ✓. Whether a destination authorization binds a port is not stated. | Partial |
| Credentialed URL (`user:pass@host`) | Not addressed. Userinfo is both a parser-differential vector and a content channel inside the query. | **Yes** |
| URL parser ambiguity | The trusted transport reports the *connected* host, which mitigates this, but it is not required | Partial |
| Punycode/IDN | Canonical A-label form not required | **Yes** |
| Scheme change (https→http) | Scheme is part of the origin. A downgrade loses the TLS identity; "TLS identity mismatch" maps to unknown, but plain http has no TLS to mismatch. | Partial |
| Redirect to `file://` / local schemes | Not named; "origins" listed are network classes | **Yes** (a scheme allowlist is needed) |

**Impact.** A class-M page or DNS zone can steer a first-party fetch to
`127.0.0.1:8000`. Today that is Jarvis's own unauthenticated API, which
returns task descriptions, outputs and errors (R-04). It could also reach
`169.254.169.254` (cloud metadata credentials) or any LAN service. The
bytes come back labeled by the public web policy, which is PUBLIC with
`export_allowed = true` (§15.5). That is a downgrade followed by an
exportable flow. No web-fetch adapter exists today (ToolAdapters =
`file.create_sandboxed`), so the exposure is design-level. **Finding
HR5-04.**

**Redirect labeling (prompt §22).** A redirect hop that contributes only
control flow does not join its policy. That is acceptable for
confidentiality, because the bytes come from the final origin and are
labeled by it. It is acceptable for integrity, because all external
content is ≤ UNTRUSTED (§16.2). The initial URL is joined when stricter.
An unknown identity gives `UNKNOWN_WEB`, NO_FLOW by default and never less
restrictive than any web policy. Conservative enough, once HR5-04 closes
the address-class gap.

## 21. Provider versus model destination

Attempt: authorized provider P / model A, and the router selects model B at
P. The checks are:

- §24.4: a provider allow-list never authorizes a model;
- §34 step 5: `dest.binds_model(target.provider_id, target.model_id)`,
  else `CB_EGRESS_NOT_AUTHORIZED`;
- §24.3: the grant binds the exact model; the dispatcher verifies that the
  dispatched target equals the bound one; any fallback needs a new grant
  after a full decision;
- a model class counts only when its members are enumerated with terms.

Result: DENY unless B is explicitly authorized or an enumerated member.
Fallback re-authorizes. **HR4-13 correction verified** (TST-CB-095, -065).

## 22. Owner bootstrap (§8.4)

| Attack | Result | Guarantee or assumption? |
|---|---|---|
| Second enrollment | Record is `ENROLLED` → `OWNER_ACT_REJECTED` | Guarantee (within store integrity) |
| Restore of a pre-enrollment snapshot | The anchor records ENROLLED → epoch regression → DENY everything | Guarantee **only if the anchor survives**. Whole-machine rollback including the anchor is stated as out of contract (§31.6). ✓ honest |
| Lost owner credential | New owner act from an enrolled credential, or reinstall with a new installation identity | Stated. The fate of the old stores under the new identity is unspecified (hardening). |
| Local malware under the same OS account **before** enrollment | Becomes the owner | **Explicit trust assumption** (§8.4 row 2; §6.3). Correctly not claimed as protected. ✓ |
| HTTP triggering bootstrap | "No HTTP route … can reach it" | Requirement ✓ |
| Agent triggering bootstrap | "No … agent, tool … can reach it" | **Weak.** An "OS-authenticated local IPC endpoint" authenticates the OS *account*, and at Level 1 the Jarvis process (agents included) runs as that account. An OS-keystore key can be generated without user presence. Nothing requires human presence or requires the agent runtime to be stopped during enrollment (HR5-15). |

A second issue is **atomicity with the external anchor**. The enrollment
writes the DB and the external anchor "at the same time", which is two
commit points.

- If the anchor write fails after the DB commit, a later restore of a
  pre-enrollment DB is not detected.
- If the DB commit fails after the anchor write, the installation is
  permanently in regression.

The ordering and recovery rule is unspecified (HR5-15, LOW).

The design correctly distinguishes its guarantee from its bootstrap trust
assumption and does not claim protection against the root.

## 23. Invariant review

### 23.1 New r3 invariants (076–096)

| ID | Class | Note |
|---|---|---|
| 076 | VALID | Parent-bound child pair; verified against attacks A–G |
| 077 | VALID | Matches v0.2.5 CR-01 (§12 of this review) |
| 078 | VALID | Task row never authoritative; see HR5-14 on the step-5 contradiction read |
| 079 | VALID | |
| 080 | VALID | Relation single-use and fork/continuation bounds are hardening (HR5-08) |
| 081 | **INCOMPLETE** | "An undeclared … read makes the operation DENY" is enforceable only for undeclared read *sets*. Actual over-reads are unobserved; the claimed Level-2 enforcement exists in no CR; untrusted-connector artifacts are not ceiling-labeled (HR5-01) |
| 082 | VALID | Recommend also applying the digest join to derivation read sets (HR5-01) |
| 083 | VALID | |
| 084 | VALID | |
| 085 | **INCOMPLETE** | Discovery-only. Non-ORM and dynamic sinks are not discoverable and no runtime containment is required (HR5-03) |
| 086 | VALID | |
| 087 | **AMBIGUOUS** | Genesis `expires_at` sources reference undefined fields (HR5-10) |
| 088 | VALID | Idempotency of T-7 is hardening (HR5-06) |
| 089 | VALID | |
| 090 | **AMBIGUOUS** | "Mirrors v0.2.5" is not accurate: T-9 is ESC-scoped for clearance, v0.2.5 is not (HR5-11) |
| 091 | VALID | |
| 092 | **INCOMPLETE** | Private-address denial is for redirects only; the initial hop, connected-address authority and URL canonicalization are missing (HR5-04) |
| 093 | VALID | |
| 094 | VALID | Membership grants nothing; oversight still needs clearance, purpose and ceiling ✓ |
| 095 | VALID | |
| 096 | VALID | Enrollment presence and anchor ordering are hardening (HR5-15) |

**Counts (21 new):** VALID 16 · AMBIGUOUS 2 (087, 090) · INCOMPLETE 3
(081, 085, 092) · UNSOUND 0 · REDUNDANT 0.

### 23.2 r3-revised invariants

| ID | Class | Note |
|---|---|---|
| 005 | VALID | One lineage per execution; the child descends from the parent's |
| 015 | VALID | Empty-set wording fixed |
| 035 | VALID | Release events exactly once; denials best-effort |
| 046 | VALID | Lookup by id only |
| 049 | VALID | |
| 050 | VALID | The property is correctly stated; its enforcement depends on 081 |
| 061 | VALID | |
| 062 | VALID | Connector claim and redirect covered; the address-class gap sits in 092 |
| 066 | VALID | Every ancestor pair checked |
| 069 | VALID | |
| 071 | VALID | T-7 and T-8 added. The §9.6 paragraph ambiguity is HR5-14. |
| 073 | VALID | The invariant is right; the catalogue that realizes it misclassifies S-14 (HR5-02) |
| 074 | VALID | |
| 075 | VALID | |

**Counts (14 revised):** VALID 14.

**Total reviewed: 35** — VALID 30 · AMBIGUOUS 2 · INCOMPLETE 3 · UNSOUND 0 ·
REDUNDANT 0.

**Unrevised invariant affected:** INV-CB-048 ("closed, reviewed,
low-bandwidth" observables) does not hold once T-7 is unbounded (HR5-06).

## 24. Test-quality review

| Hostile sequence | Test(s) | Would it catch the exact sequence? |
|---|---|---|
| Unrelated child pair (root-pair substitution) | TST-CB-076, -005 | **Yes** |
| Sibling substitution | — | **No explicit case.** Add: child A's TCR, binding or pair ids swapped with child B's → DENY. |
| Nested (grandchild uses the grandparent's pair or leaves) | TST-CB-076 (single level) | **Partial.** Add a three-generation case. |
| Parent revocation race | TST-CB-076 ("revoking the parent's pair makes descendants REVOKED") | **Partial.** Add revocation between T-7 commit and `issue_esc`. |
| Mixed pair | TST-CB-088 (re-pairing rejected) | Yes for the store constraint |
| Partial pair issuance | TST-CB-088 (real-store) | **Partial.** Covers edge-then-failure. Missing: pair without binding or TCR (fallback protocol); retry after an uncertain commit and duplicate T-7 replay. |
| Task-row forgery | TST-CB-078 | **Yes** (byte-identical ESC or DENY) |
| Undeclared adapter read | TST-CB-081 ("undeclared read set") | **No.** It tests a missing declaration, not over-reading. Add: a symlink in a managed store (from checkout) → copy/zip; a zip-slip member path; file swap between resolve and read; git config filter or hook; an untrusted-connector artifact labeled below its ceiling. |
| Copy/archive/Git laundering | TST-CB-081, -050, -082 | **Yes** for declared reads; add "derivation over a previously mislabeled artifact" |
| Dynamic unregistered sink | TST-CB-085 (fixture branch column/route/adapter) | **Partial.** Static only. Add: post-startup `ToolRegistry.register` and route or logging-handler addition; a content-bearing kwarg in a log call; a temp-file write from agent code; SDK debug logging enabled. |
| Taint-ceiling subset direction | TST-CB-075 (antitone property), -086 (per-dimension table) | **Yes** |
| Redirect / DNS identity | TST-CB-092 | **Redirect only.** Add: an initial host resolving to 127.0.0.1/::1/169.254.x/10.x; DNS rebinding between check and connect; IPv4-mapped IPv6; userinfo URL; IDN; https→http; redirect to `file://`. |
| Provider/model fallback | TST-CB-095, -065 | **Yes** |
| TST-CB-005, -035, -046, -049, -050, -061, -062, -068, -069, -073 | — | Strengthened as HR4 asked; adequate for their invariants. TST-CB-073 must also reject class B for any log emitter whose payload keys are not proven closed (HR5-02). |

**Conclusion.** The future tests cover the LineagePair, task-control,
ceiling and provider properties well. They **do not** cover the three
residual surfaces:

- over-reads beyond the declared set;
- dynamic or non-ORM sinks;
- initial-hop network identity.

## 25. Dependency DAG

The 12-tier graph (§40.E) was reconstructed independently. Every edge
points to a strictly lower tier. **It is acyclic.**

| Required order | Holds? |
|---|---|
| Policy store before consumers | Yes (POL tier 1 < OWN, OBJ, LIN, TASK, ESC, TAINT, ING, ART, EGR) |
| Isolation before OwnerChannel | Yes (ISO tier 0 < OWN tier 2) |
| TaskControl before ESC issuance | Yes (TASK 5 < ESC 6) |
| LineagePair store before ESC issuance | Yes (LIN 4 < ESC 6) |
| IFR before live stores are mediated | Yes (IFR tier 0 < ING, ART, LEG, SINK) |
| Egress containment before cloud-capable integration | **Not enforced.** CR-EGR-01a has no dependents; CR-EGR-01 (tier 8) has no edge to CR-CB-04 or CR-CB-02 (also tier 8) |
| Legacy quarantine before broker retrieval | Safe by construction: legacy rows are never items. **But** CR-LEG-01 (tier 9) depends on CR-CB-04 (tier 8), so agent-input plumbing via grants necessarily lands **before** agent outputs stop flowing into unlabeled legacy columns that the unauthenticated API serves (R-04). |

**Staged-implementation gap (HR5-07).** CR-CB-02 (memory reads and writes
through the broker) and CR-CB-04 (agent input via grants and the
assembler) change the live runtime. They are listed as *prerequisites* of
v0.2.6.9. Nothing requires them to land disabled. If they are enabled
before CR-EGR-01 and CR-LEG-01:

- broker-delivered labeled content enters live agents whose provider path
  is still the unconditional cloud (R-08, R-09);
- their outputs go to `tasks.output_data` and `agent_runs`, served
  unauthenticated.

The graph is acyclic but **not safely ordered** for live integration.

## 26. New HR5 findings

### HR5-01: Effect-side reads are declared, never observed — class-M over-reads launder artifact labels

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR4 (HR4-03)
- **Affected section:** §17.2 items 4–5; §17.6 rule 2 and output formula;
  §6.5 (Level 2 definition); §38.2 (residual attributed to C-in); §40.B
  CR-ISO-01, CR-ART-01; §16.2 (connector ceiling not applied to artifacts)
- **Affected invariant:** INV-CB-081, INV-CB-050, INV-CB-082
- **Attack:**
  1. An INTERNAL-taint ESC checks out a class-M-controlled repository
     into a managed store. The repository contains a symlink blob
     `notes.txt → ../finance-store/q3.csv` (RESTRICTED FINANCIAL, bound).
  2. The ESC calls `zip([notes.txt], out.zip)`. The declared read set
     `{notes.txt}` resolves to the symlink's own binding (the checkout
     label).
  3. The adapter follows the link (library default) and reads `q3.csv`.
  4. `out.zip` is bound at the checkout label ⊔ INTERNAL. Its bytes are
     new, so the §17.3 digest join never matches.
  5. Variants: zip-slip member paths on extraction; a file swap between
     resolve and read; git filters, hooks or `includeIf`.
- **Impact:** a persistent-label downgrade of RESTRICTED data by class M
  through an honest reviewed adapter. The design files this as C-in
  (out of contract) and claims Level-2 enforcement that no CR provides.
- **Required correction:**
  1. Normatively require every effect-side read to go through the managed
     store's **ArtifactRef-keyed reader**. It verifies the digest of the
     bytes actually read against the resolved binding (extend §17.2
     item 4 explicitly to effect-side reads). It refuses symlinks,
     hardlinks, device files and path traversal. It resolves identity from
     the opened handle.
  2. Require outputs (including archive members) to be enumerated and
     containment-checked **before** the effect.
  3. Require git adapters to run with repository-local config, hooks,
     filters and submodules disabled.
  4. Apply the digest join to derivation read sets.
  5. Label untrusted-connector artifacts at least at the adapter-level
     ceiling.
  6. Either add per-invocation read-set confinement to CR-ISO-01 or delete
     the Level-2 claim.
  7. Reclassify the §38.2 residual from C-in to "M against a non-conforming
     adapter".
  8. Add the TST-CB-081 cases from §24 of this review.
- **Design freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO (no write-capable adapter other than
  `file.create_sandboxed`, which already refuses symlinks; blocks enabling
  any new write-capable adapter)

### HR5-02: Re-audit still misses or misclassifies live content-bearing sinks — application logs are content, not class B

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR4 (HR4-04)
- **Affected section:** §4.3 (no R-fact); §18.1 S-14 (class B), S-19/S-23
  (CLI); §17.5; §40 (no CR covers log content); §43.2
- **Affected invariant:** INV-CB-073, INV-CB-084, INV-CB-035 (by analogy
  to R-07)
- **Attack or contradiction:** S-14 asserts "B — closed event names, ids,
  codes … no content". The live code writes content to stdout JSON logs:
  - objective text (`app/agents/jarvis.py:65`, `:77`);
  - task titles (`research.py:275/340/482`, `strategy.py:115`, `qa.py:56`,
    `execution.py:38`, `evaluator.py:299`);
  - objective-derived research queries (`research.py:784`);
  - QA issues (`evaluator.py:299`);
  - diagnostic summaries (`evaluator.py:392`);
  - raw `str(exc)` (`executor.py:274`).

  The dev CLI prints task titles and the full report (`app/main.py:93–136`).

  ORM surfaces that the catalogue does not list:
  - `users.email` (`models.py:205`, the `users` table appears nowhere in
    §18);
  - `approvals.resolved_by` (caller-supplied free text, `models.py:392`,
    returned in `ApprovalOut`);
  - `action_approval_requests.requested_by/decided_by`;
  - `action_plans.created_by/orchestration_owner`;
  - `replan_proposals.created_by`;
  - `execution_attempts.claimed_by`;
  - `agents.name/role`.

  The ORM omissions would be caught by the §18.2 discovery rule. The
  log-payload misclassification would **not**, because S-14 is registered
  wholesale as B.
- **Impact:** a false content-free proof in the authoritative registry. A
  live, unrecorded sink of objective and query text, which is exactly what
  R-07 records for audit. No CR removes it.
- **Required correction:**
  1. Add R-29 (application logs and CLI output carry content).
  2. Reclassify S-14 as **Q → B** with a CR (extend CR-CB-03/CR-CB-06, or
     add CR-LOG-01) that restricts log kwargs to a closed allowlist of
     typed keys.
  3. Add the CLI as a USER_DISPLAY/EXPORT surface.
  4. Add rows for the listed columns (free-text `*_by` fields are
     content-capable until restricted to `PrincipalRef` or closed codes).
  5. Add R-29 to §43.2 as a live deployment blocker.
- **Design freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** YES (live)

### HR5-03: CR-IFR-01 is discovery-only; no runtime fail-closed rule for non-discoverable or dynamic sinks

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected section:** §18 (preamble "at runtime the broker has no sink
  for it"), §18.2 completeness rule, §40.B CR-IFR-01, §6.5 ISO-AGENT
- **Affected invariant:** INV-CB-085, INV-CB-073
- **Attack or contradiction:** discovery sources are ORM, migrations,
  router, ToolRegistry and "log emitters". None covers:
  - temp files;
  - library or SDK caches and SDK debug logging of request bodies;
  - subprocess pipes;
  - stdout/CLI;
  - routes, models, adapters or log handlers registered after startup
    (`ToolRegistry.register` is a runtime API).

  Broker-released content held by Level-1 agent or adapter code can reach
  any of them. The contract enforces "unregistered ⇒ unreachable" only for
  broker releases.
- **Impact:** the completeness guarantee holds for what CI can see, not
  for what runs. HR5-02 shows a live instance.
- **Required correction:** restate INV-CB-085 as a runtime property, and
  require all of the following:
  1. a discovery method per surface kind, including log payload keys;
  2. closed-by-construction controls in the agent and adapter runtime:
     - a logging configuration allowlist verified at startup;
     - SDK debug logging off and verified;
     - temp directories only inside managed stores;
     - no subprocess or file API outside registered adapters;
  3. registry re-validation, or refusal, for any post-startup registration
     of routes, models, adapters or handlers;
  4. an explicit statement that an undiscovered sink is **not** considered
     safe;
  5. TST-CB-085 extended as in §24 of this review.
- **Design freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO (covered by CR-SINK-01 before integration)

### HR5-04: Network resource identity — initial hop, DNS rebinding and URL canonicalization unspecified

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected section:** §16.2 (trusted adapter row), §16.5 rules 1–5,
  §24.2 `ToolDestination`
- **Affected invariant:** INV-CB-092, INV-CB-091, INV-CB-062, INV-CB-063
- **Attack:** a class-M page makes the model fetch `http://r.attacker.example:8000/tasks/<id>`.
  1. DNS answers a public IP at check time and `127.0.0.1` at connect time
     (or always `127.0.0.1`).
  2. The bytes are Jarvis's own unauthenticated task output (R-04), or
     `169.254.169.254` metadata.
  3. Rule 2 denies private targets for **redirects** only. The initial hop
     is "authorized" by hostname.
  4. The label comes from the public web policy: PUBLIC, `export_allowed
     = true`.
- **Impact:** downgrade of local, internal or legacy content to PUBLIC,
  followed by an exportable flow (SSRF and exfiltration). Design-level
  only; no fetch adapter exists.
- **Required correction:**
  1. The canonical identity of a network resource includes the **actually
     connected peer address**, used for both labeling and authorization.
     There is no re-resolution after the check; the address is pinned.
  2. Any hop, **initial or redirect**, whose connected peer is loopback,
     private, link-local, ULA, IPv4-mapped-private, unspecified, multicast
     or a Jarvis-internal endpoint is DENY unless an owner-approved source
     policy names that exact internal endpoint.
  3. Scheme allowlist `{https, http}`. No redirect to any other scheme. No
     https→http downgrade unless the destination authorization allows it.
  4. URLs with userinfo are rejected.
  5. IDN → A-label; default ports normalized; destination authorizations
     bind scheme, host and port.
  6. The canonical identity is computed from the transport's own parsed
     request, not from a separate parse.
  7. Extend TST-CB-092.
- **Design freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO (blocks enabling any web-fetch adapter)

### HR5-05: T-7 does not attenuate the destination set or the environment class

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected section:** §9.2 `destination_policy_ref`, §9.3 steps 10–11,
  §9.7 step 4, §21.3 rule 11, §24.2 "effective destination permission"
- **Affected invariant:** INV-CB-076, INV-CB-063; v0.2 §8 ("delegation
  never increases authority in any dimension, including context scope"),
  v0.2 §10
- **Attack:** parent profile `P_ORCH` has `destination_ids = ∅`. Its
  clearance includes the `MODEL_CLOUD` sink, which the owner granted so
  that children may use it. Allowed child `P_RES` has `destination_ids =
  {D2}`.
  1. An injected orchestrator issues T-7 for `P_RES` and delivers to the
     child items that carry `MODEL_CLOUD` in their sinks.
  2. The child sends them to D2.
  3. The parent could not have sent them to D2 itself.

  Destinations come from `child_profile.destination_ids ∩ effective(now)`
  and are never intersected with the parent ESC's. The environment class
  is likewise taken from the child profile. A `DEV_SANDBOX` parent can
  spawn a `LOCAL_RUNTIME` child.
- **Impact:** a non-monotone egress dimension across delegation ("A asks
  B, which has broader capability"). It is bounded by attenuated clearance
  sinks, `export_allowed`, label sinks and owner-approved destination
  terms. No egress outside owner-approved destinations is possible.
- **Required correction:** either
  - (a) set `child.destination_policy_ref ⊆ parent.destination_policy_ref`
    (check-not-clip in T-7 step 4), and require the child environment to
    be at least as restrictive as the parent's; or
  - (b) state explicitly that destinations and environment are per-profile
    owner policy outside the delegation algebra, record that the
    `allowed_child_profiles` relation is the owner's consent to this
    widening, and add a residual and a test.

  Either way, INV-CB-076 must name the dimension. This is an owner
  decision.
- **Design freeze blocker:** YES (decision + text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR5-06: T-7 breadth is unbounded — an unbounded control-plane channel, and no idempotency

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected section:** §9.7 procedure, §14.8, §32 (no T-7 dimension),
  §23.2 (profile id and task type rendered into the child's
  `TASK_INSTRUCTION`), TC-50
- **Affected invariant:** INV-CB-048, INV-CB-056, INV-CB-088
- **Attack:** a RESTRICTED-tainted parent (local only) encodes data in the
  sequence and number of T-7 issuances. Each issuance carries
  `log2(|allowed_child_profiles|)` bits, plus bits in its selectors and
  timing. The child's genesis excludes parent taint, yet its
  `TASK_INSTRUCTION` renders the parent-chosen profile id and task type.
  A cloud-enabled child therefore transmits them in its prompt. No bound
  limits the number of children, so the "few bits per execution" of §14.8
  does not hold. Separately, a harness retry after an uncertain T-7 commit
  creates duplicate children, and therefore duplicate effects.
- **Impact:** a covert channel of unbounded total bandwidth from a tainted
  parent to a less-cleared child (the accepted residual class, without its
  bound), plus duplicated work.
- **Required correction:**
  1. Add §32 bounds: T-7 issuances per ESC and per root lineage, and a
     rate.
  2. Include T-7 decisions in the §14.8 observable accounting and state
     the resulting bandwidth.
  3. Optionally, give the child genesis ⊒ the confidentiality projection
     of the parent's H at T-7 when policy requires strict implicit-flow
     control (the standard "spawn inherits the pc label" rule).
  4. Make `(parent_esc_id, proposal_ref)` a unique idempotency key for T-7,
     so a replay returns the existing binding.
- **Design freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR5-07: Staged-integration ordering lets live-touching CRs precede egress and legacy containment

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected section:** §40.D, §40.E (tiers 8–9), §24.5
- **Affected invariant:** INV-CB-063, INV-CB-073
- **Attack or contradiction:** see §25 of this review.
  - CR-CB-02 and CR-CB-04 modify live code and have no edge to CR-EGR-01
    or CR-EGR-01a.
  - CR-LEG-01 depends on CR-CB-04, so it necessarily lands after it.
  - An owner-authorized, individually reviewed CR-CB-04 deployment could
    therefore feed broker-labeled content into agents whose provider path
    is unconditional cloud, and whose outputs are persisted unlabeled and
    served unauthenticated.
- **Impact:** v0.2.6 guarantees are void during that window (§24.5 already
  concedes this for the live path). The DAG does not prevent the window.
- **Required correction:** either
  - require every CR that alters the live runtime (CB-02, CB-04, CB-05,
    LEG-01) to land **disabled** behind one broker-enforcement switch that
    only v0.2.6.9 turns on, after SINK-01 and EGR-01; or
  - add the edges CB-02/CB-04 ← EGR-01a and CB-04 → enforcement ← LEG-01.
- **Design freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR5-08: Root admission binds the pair to an event, not to the admitted task; relations are not single-use

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §9.3 step 6 (ROOT), §9.6, §21.3 rules 2 and 7,
  §9.8, §21.3 transaction semantics
- **Affected invariant:** INV-CB-046, INV-CB-078, INV-CB-080
- **Attack or contradiction:**
  - The ROOT path does not verify pair ↔ task. There is no `task_id` in
    ROOT pairs and no uniqueness on `TCR.root_lineage_pair_id` or
    `admission_owner_event_id`. The `pair_approval_digest` omits the task
    and the proposal digest the owner reviewed.
  - An ExecutionRelation can in principle be reused for a second ESC.
  - FORK and CONTINUATION counts are unbounded.
  - An orphan authority edge in the fallback protocol is fully effective
    under v0.2.5 until swept (INFO).
- **Impact:** defence in depth only. Combined with the HR5-14 wording, it
  could let additional unreviewed root tasks run under an owner-approved
  pair. There is no widening.
- **Required correction:**
  1. Add `task_id` and the proposal digest to ROOT pairs and to the
     approval digest.
  2. Add unique constraints on the TCR's root pair and admission event.
  3. The ESC Issuer checks `pair.task_id == tcr.task_id` for ROOT.
  4. A relation binds exactly one `new_esc_id`.
  5. Bound FORK and CONTINUATION in `retry_policy`.
  6. State that orphan edges are unusable outside ESC binding.
- **Design freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR5-09: T-7 selector semantics incomplete

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §9.7 steps 3–5
- **Affected invariant:** INV-CB-076, INV-CB-079
- **Attack or contradiction:**
  - The child edges' `redelegation` (authority `RedelegationPolicy` and
    clearance `redelegation`) is neither a selector nor defined. An
    implementer may default it to "maximal allowed". It stays bounded by
    v0.2.5 and §21.2, but it is an upward default.
  - `TaskProfile.objective_types` is never checked (ROOT or CHILD).
  - v0.2.5 rejects a child agent equal to the parent or to any ancestor
    (principal repetition, `delegate ≠ delegator`). T-7 then DENYs, which
    is unstated.
- **Required correction:**
  1. An omitted redelegation selector means `None`.
  2. Check `objective_types` in T-1 and T-7.
  3. State the principal-repetition consequence for `allowed_child_profiles`.
- **Design freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR5-10: Genesis expiry sources reference undefined fields

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §14.9 (`L_sys`, `L_ctrl` rows), §10.1, §29.4
- **Affected invariant:** INV-CB-087
- **Attack or contradiction:** `expires_at = policy-version expiry` and
  `= ObjectiveVersion expiry`, but neither record has an expiry field.
  Labels require `expires_at` with no default, so the genesis is not
  reproducible as specified. There is no widening, because expiry is
  min-combined.
- **Required correction:**
  1. Add `expires_at` to `ObjectiveVersion` and `SecurityPolicyVersion`,
     or define the genesis expiry as a policy value.
  2. Restrict `objective_id` to identifier characters (§18 of this review).
- **Design freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR5-11: Revoker-set asymmetry between the authority and clearance halves

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §21.5, §7.3 T-9
- **Affected invariant:** INV-CB-090
- **Attack or contradiction:** clearance revocation by an agent is
  ESC-scoped (T-9), while the v0.2.5 authority revocation path is not.
  Revoking either half kills the pair. The "mirrors v0.2.5 §11" claim is
  therefore inaccurate, and an injected ESC can revoke the same agent's
  delegations in unrelated tasks. That is narrowing and DoS only.
- **Required correction:** state that authority revocation invoked from
  an ESC is also limited to that ESC's subtree, or correct the "mirrors"
  statement and record the residual.
- **Design freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR5-12: Digest join — membership oracle and label poisoning; index unspecified

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §17.3, §17.4, §34 `ingest_tool_result`
- **Affected invariant:** INV-CB-082, INV-CB-045
- **Attack or contradiction:**
  - **Membership oracle.** Write guessed exact bytes, re-ingest them, and
    observe whether delivery is denied. This leaks 1 bit per probe across
    compartments.
  - **Label poisoning.** A tainted ESC registers popular public bytes at a
    high label, so every later ingestion of those public bytes is raised.
  - The digest index over bindings and export records is not required.
- **Required correction:**
  1. State the oracle and poisoning residuals with their rate bound (§32).
  2. Consider applying the join only for digests registered from
     restricted artifacts above a size floor.
  3. Require an indexed digest lookup.
- **Design freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR5-13: Git commit label joins the parent — permanent taint of commit metadata

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §17.7 (Git commit, Git push)
- **Affected invariant:** INV-CB-081
- **Attack or contradiction:** every descendant commit object stays ⊒ any
  historical blob label. This is confidentiality-safe but degrades
  availability for local history reads. It is redundant for push, which
  is already "⊔ over everything sent".
- **Required correction:** separate the commit content label (tree ⊔
  message ⊔ H; parent by hash) from the transmission label (⊔ over the
  objects sent) (§15 of this review).
- **Design freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO (HARDENING)

### HR5-14: Task-control wording inconsistencies

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §0.4 HR4-02 row; §9.6 "TaskProfile provenance"
  paragraph; §9.3 step 1 vs step 5; §9.9 "Who requested the work?"
- **Affected invariant:** INV-CB-071, INV-CB-078, INV-CB-077
- **Attack or contradiction:**
  1. §0.4 names the Execution Scheduler as a TCR writer, contrary to the
     exhaustive list in §9.6 and to step 1.
  2. The §9.6 provenance paragraph reads as a dependency-based TCR route
     outside T-7 and T-8 (§13 of this review).
  3. Step 1 says the Task row is not read, but step 5 reads it for
     contradictions. That is a DoS channel against root tasks through any
     Task-row writer. There is no widening.
  4. A stronger planner approval requirement is silently dropped.
  5. "Requested the work" versus `requesting_principal` (§12 of this
     review).
- **Required correction:**
  1. Align §0.4.
  2. Scope the §9.6 paragraph to T-8 and T-7.
  3. Document the contradiction DoS as a residual, or compare only against
     the proposal recorded in the TCR.
  4. State whether stronger planner approval requests are honoured.
  5. Rename the §9.9 row.
- **Design freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR5-15: Bootstrap enrollment hardening

- **Severity:** LOW
- **Category:** NEW
- **Affected section:** §8.4
- **Affected invariant:** INV-CB-096
- **Attack or contradiction:**
  - OS-account-authenticated IPC does not separate agents running as the
    same account at Level 1.
  - An OS-keystore key can be registered without user presence.
  - The DB and the external anchor are two commit points with no defined
    order.
  - The fate of old stores after "reinstall with a new identity" is
    unspecified.
- **Required correction:**
  1. Require a user-presence or verification ceremony.
  2. Enroll only while the agent runtime is stopped.
  3. Define the anchor-first-or-last ordering and its recovery rule.
  4. State that old stores are not trusted under a new installation
     identity.
- **Design freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR5-16: Review independence limitation

- **Severity:** INFO
- **Category:** RESIDUAL-HR4 (HR4-12)
- **Affected section:** §38.2, §44.5
- **Affected invariant:** —
- **Attack or contradiction:** same-model-family blind spots.
- **Required correction:** human review of §6, §8, §9, §16.5, §17.6 and
  §21.3 before freeze.
- **Design freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 7 (HR5-01…07) · LOW 8 (HR5-08…15)
· INFO 1 (HR5-16) — 16 findings.

## 27. Design freeze blockers

| Source | IDs |
|---|---|
| HR5 | **HR5-01, HR5-02, HR5-03, HR5-04, HR5-05** (all MEDIUM, text-level) |
| HR4 not fully resolved | HR4-03 (→ HR5-01), HR4-04 (→ HR5-02) |

**Freeze-criteria check (prompt §34):**

| Criterion | Met? |
|---|---|
| No CRITICAL design blocker | Yes |
| No HIGH design blocker | Yes |
| HR4-01..07 all RESOLVED_IN_R3 | **No** (HR4-03, HR4-04 PARTIALLY_RESOLVED) |
| LineagePair has no permission-shopping path | Yes for authority and clearance. Destinations sit outside the pair (HR5-05). |
| TaskControl has a trusted creation path | Yes (LOW text defects HR5-08, HR5-14) |
| Artifact derivation cannot launder labels | **No** (HR5-01) |
| Registry rules fail closed for unregistered content paths | **No** (HR5-02, HR5-03) |
| Taint ceiling algebra coherent | Yes |
| LineagePair issuance/revocation coherent | Yes (LOW HR5-08, HR5-11) |
| Resource identity trusted | **No** (HR5-04) |
| Dependency DAG safe | Acyclic yes; staged ordering **no** (HR5-07, not a freeze blocker) |
| Frozen-contract compatibility | Yes. No amendment required. |

## 28. Implementation blockers

- Every CR in r3 §43.1 (unchanged): CR-POL-01, CR-LIN-01, CR-TASK-01,
  CR-ESC-01, CR-TAINT-01, CR-IFR-01, CR-ING-01, CR-ART-01, CR-EGR-01,
  CR-OWN-01, CR-PRN-01, CR-OBJ-01, CR-EPOCH-01, CR-API-01, CR-LEG-01,
  CR-SINK-01, CR-ISO-01, v0.2.5.2/.3 and v0.2.5 CR-01..CR-05, CR-CB-01..08.
  Numeric bounds are also still needed.
- HR5-01, HR5-02, HR5-03, HR5-04, HR5-05, HR5-06, HR5-07, HR5-08, HR5-09,
  HR5-10, HR5-14, HR5-15.

## 29. Deployment blockers

- All live rows of r3 §43.2, re-confirmed where inspected:
  - unauthenticated API (R-01);
  - caller-asserted `resolved_by` (R-02; `schemas/approvals.py:19`);
  - `/chat` confused deputy (R-03);
  - unauthenticated content disclosure (R-04, R-23, R-25; `ApprovalOut`
    returns `requested_action`, `reason`, `decision_reason`);
  - unlabeled action-pipeline content;
  - planner-written Task rows (R-05);
  - arbitrary `User` creation (R-13);
  - unconditional cloud egress (R-08, R-09);
  - audit content (R-07);
  - raw secrets and no isolation (R-11);
  - no rollback anchor;
  - no at-rest encryption;
  - any second node.
- **HR5-02:** application logs and CLI output carry objective text, task
  titles, research queries and exception text (live, newly recorded).
- **HR5-07:** no live-touching CR may be enabled before egress and legacy
  containment.

## 30. Final status

Revision r3 correctly closes the core of the HR4 HIGH findings:

- delegated-child lineage is parent-bound, looked up by id, never
  searched;
- Task rows are data plane, and TaskControlRecords have only trusted
  writers;
- artifact effects join their declared reads;
- the LineagePair is atomic and revocation-coherent.

The taint-ceiling algebra is sound. CR-01 semantics match v0.2.5. Model
authorization is enforced after selection. No HIGH or CRITICAL design flaw
was found, and no frozen-contract amendment is required.

The design is still not freeze-ready. Five MEDIUM text-level gaps remain
in exactly the areas the freeze criteria name:

- over-reads beyond the declared artifact read set (HR5-01);
- a live content sink misclassified as content-free (HR5-02);
- registry completeness enforced only by static discovery (HR5-03);
- network identity for the initial hop and DNS rebinding (HR5-04);
- non-attenuated destinations under delegation (HR5-05).

HR4-03 and HR4-04 are therefore only partially resolved. Each item can be
corrected in contract text, and none requires redesign.

**R3 DESIGN NOT READY — FURTHER CORRECTION REQUIRED**

---

## Appendix A — Read-only validation

Run with `.venv/Scripts/python.exe` while the HR5 document was being
written:

| Command | Result |
|---|---|
| `scripts/check_v013_freeze_baseline.py` | exit 0: OK (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `scripts/check_v020_contract.py` | exit 0: OK |
| `scripts/check_v023_router_contract.py` | exit 0: OK |
| `scripts/check_v024_agent_contract.py` | exit 0: OK |
| `scripts/check_v025_design_contract.py` | exit 1: DISCREPANCY FOUND. The four untracked v0.2.6 documents are outside the v0.2.5.1 allowlist (expected). |
| `python -m pytest -q -p no:cacheprovider` | exit 1: **1 failed, 2234 passed, 1 warning** (368.86 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`, for the same allowlist reason. This matches HR4 §38. |

No validator or test was modified.

## Appendix B — Integrity

SHA-256 was recomputed before finishing:

| File | Start | End | Changed? |
|---|---|---|---|
| Design r3 | `ffa4cee7…df20c8` | `ffa4cee724e9fe9b6b61f29bff052c624bcfb31ace85474d2de691fcd4df20c8` | no |
| HR2 | `ec7d9f31…b9b2e` | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` | no |
| HR3 | `081c8993…ee58` | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` | no |
| HR4 | `d6a76101…379c` | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` | no |

`git status --short -uall` at the end shows the four pre-existing
untracked documents plus this one. `git diff --stat HEAD` is empty, and
HEAD is still `13796dc`. The only file created by this review is
`docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md`. There was no
commit, no push and no merge. OpenDex was not opened.

No v0.2.6 production implementation has been authorized or created.
