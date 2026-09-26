# Jarvis OS v0.2.6 — HR11 Final Freeze Verification of Design Revision r9

```text
subject                        = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r9)
subject status on entry        = CORRECTED R9 — PENDING HR11 FINAL FREEZE VERIFICATION
controlling prior review       = HR10 (docs/V0_2_6_HR10_FINAL_FREEZE_VERIFICATION.md)
review type                    = independent technical freeze verification (read-only)
review date                    = 2026-09-26
design_modified                = false
hr2_to_hr10_modified           = false
code_tests_validators_modified = false
opendex_modified               = false
final_status                   = R9 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

Section numbers (§N) refer to the r9 design unless another document is
named. Line numbers refer to the r9 file as hashed in §2. Finding IDs
`HR11-NN` are new to this review.

---

## 1. Independence

This session authored **none** of:

- design revisions r1–r9;
- HR2, HR3, HR4, HR5, HR6, HR7, HR8, HR9 or HR10.

It started with no conversation history and worked only from repository
contents. The design's §0.10 authorship note requires that HR11 come from a
session that did not author r9. This session meets that condition.

The r9 correction record (§0.10), its "corrected" wording and the §44.5
sentence "No known freeze-blocking MEDIUM issues after r9" were **not**
treated as evidence. Conclusions come from the r9 normative text (§7.3,
§9.3, §9.7, §9.8, §9.11, §21.3, §21.5, §29.4, §32–§36, §38.2, §39.1, §40),
the frozen v0.2.5 text (§10, §11, the `revoke()` API row) and HR10.

**Limitation.** This review uses the same model family as HR2–HR10. It is
session-independent, not organizationally independent. The design's own
recommendation (§38.2, §44.5) of a human security review before freeze still
applies.

---

## 2. Repository

Inspected read-only before this file was written.

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `13796dcd61015098429f343e2fb982a9c75698bb` |
| `origin/master` | `13796dcd61015098429f343e2fb982a9c75698bb` (= HEAD) |
| Tag at HEAD | `v0.2.5.1` |
| Tracked changes (`git diff`, `git diff --cached`) | none |
| Untracked (`git status --short -uall`) | exactly ten v0.2.6 documents: the design and HR2–HR10 |

This matches the expected state.

**SHA-256 at start of review**

| File | Role | SHA-256 |
|---|---|---|
| `docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md` | r9 design (8009 lines) | `b8edcd6f545f6695cca4cf980e09fe4abfcf1ed75ca697f0079d3c207a2339b8` |
| `docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` | HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| `docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md` | HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| `docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |
| `docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` |
| `docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md` | HR6 | `42b170a580dba800fa310735c4ca0267083aa2beab0fb033fbebeeb289b4f07e` |
| `docs/V0_2_6_HR7_FINAL_FREEZE_VERIFICATION.md` | HR7 | `91e8d19eec8e98f38e7203b1f58d5181c2f25329c094de32fef53575fcecad64` |
| `docs/V0_2_6_HR8_FREEZE_VERIFICATION.md` | HR8 | `9848284e796f548b0012aa509de3b7a4cc3480f9fa5bad437020abf3d1b9aee7` |
| `docs/V0_2_6_HR9_FREEZE_VERIFICATION.md` | HR9 | `e8fcf9a2eb2598910b08c4cb64bc2c9d87c02ead5304743f6fb1c05f6ed73d15` |
| `docs/V0_2_6_HR10_FINAL_FREEZE_VERIFICATION.md` | HR10 | `a29b3e505313bab315c2f97ef780237cd401c5b844a1fc45848fad7f192c31a8` |

The HR2–HR9 hashes equal the values HR10 recorded, so those files have not
changed since HR10. The design hash differs from HR10's r8 hash
(`f8f01048…`), as expected for r9.

**OpenDex** (`C:\Users\Gyuro\opendex-reference`): HEAD
`3e898343d1127c8d5075b459acdd55da83b83f04`, the value in design §41.
`git status --short` is empty. No OpenDex file was opened or modified.

---

## 3. Materials

- **r9 design:** read directly, not through the terminal report of the r9
  pass. Read in full:
  - header, §0.9, §0.10, §5, §6 and §7;
  - §9.1–§9.11, all of it;
  - §14.5, §14.8, §21.3, §21.5, §21.6, §29.4, §30.1 and §32;
  - §33 rows 048, 090, 093 and 106 and the totals paragraph;
  - §34 `request_model_revocation`, `apply_due_model_revocations` and the
    explicit-behaviours table;
  - the §36 preamble, rows 048, 090, 093 and 106 and the closing cross-reference rows;
  - §37 items 49–55, §38.2 and the §39.1 revocation row;
  - §40.B, §40.E, the `valid(a, t)` block of §40.F, §43.1 and §44.5;
  - §44.12, §45 and the authorization block.

  A search for `r9` and `HR10` confirms that r9 touched no section outside
  these. The regression anchors (§17.9 normative rule, `deliver()` read-set
  DENY, §40.F "Not a conjunct", `L_net_max` / `reserved(esc)`,
  `RequiredActivationSet`) were re-read.
- **HR10:** read in full. HR9 and HR8 were not re-read. HR10 §4–§23 and
  design §0.9–§0.10 give sufficient traceability.
- **Frozen v0.2.5** (`docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md`):
  - §10, the store clock high-water mark;
  - §11, revocation: "immediate at commit; irreversible; idempotent (first
    record wins)", and "the delegate may renounce";
  - the `revoke(…, *, now)` API row.
- **Mechanical checks:** invariant and test accounting (§25 below).

---

## 4. HR10-01 — requester-local T-9 identity

**Construction (brief §5).**

- ESCs `A` and `B` are concurrently LIVE in one TaskControlRecord with
  account `Acct`.
- `A` submits T-9 with `request_ref = X`.
- Later, or concurrently, `B` submits T-9 with `request_ref = X`.

| Property | r9 text | Result |
|---|---|---|
| Idempotency key | `(requesting_esc_id, request_ref)` UNIQUE across `PendingModelRevocation` and `LocalRenunciationRecord` (§9.11, lines 2183–2185); r8's `(budget_account_id, request_ref)` withdrawn | ✓ |
| Lookup | `model_revocation_results.get(esc.esc_id, request_ref)`, and "the same request_ref of ANY other ESC is never found here" (§34) | ✓ |
| `B` receives `A`'s record / target / mode / timing / result identity | No: `B`'s lookup keys on `B.esc_id`; `A`'s row is unreachable; `B`'s request is evaluated only against `B`'s own lane and handles | ✓ |
| Accounting alias | `B`'s accepted act appends its own `TERMINATION_ACT` against `B`'s lane. `A`'s request is never dropped (§9.11 "Acceptance") | ✓ |
| Equivalent lane key | `(lane_id, request_ref)` is equivalent because lane ↔ holder ESC is 1:1, ever (§5, §9.11 `BudgetLane`) | ✓ |

**HR10-01: RESOLVED_IN_R9.** All three defects HR10 named are closed:

- the account-scoped key;
- the account-wide slot in the returned record;
- the family-wide target universe.

The r9 correction record also makes a sixth claim (§0.10 item 6): a
within-limit self-renunciation "is not exposed earlier through any record,
counter or ESC Issuer decision". That claim is contradicted by §9.3 step
12, in text r8 already contained and HR10 did not flag. It is recorded as
**HR11-01** (§29) and not folded into this verdict.

---

## 5. Same-requester replay

`A` repeats `X`:

- **Checked first.** The replay is checked before
  `re-run request_context`, before any lane read and before the CAS (§34
  comment "replay FIRST … before any allowance is consumed").
- **Stored result.** The replay returns the stored closed result
  (`ACCEPTED_PENDING` or `RENOUNCED_FOR_EXECUTION`).
- **Nothing new.** No second `TERMINATION_ACT`, no second record and no
  new `effective_at` exist.
- **Replay after `A` has ended.** The replay precedes the LIVE check, so it
  returns the stored result and does not open a new DENY path.

A *denied* request is not stored. Its replay is re-evaluated, but the
re-evaluation reads only `A`'s own state: LIVE, own lane, own handles and
the account horizon, which is fixed for all lanes. **✓**

## 6. RevocationTargetHandle

| Requirement (brief §9) | r9 (§9.7 step 5, §9.11 record, §21.6) | Result |
|---|---|---|
| Generated by trusted code | inserted by the T-7 transaction (CR-ESC-01) | ✓ |
| Non-ordinal, unpredictable | "fresh opaque value from a CSPRNG (≥ 128 bits; encodes no order, count, time or id)"; never reused | ✓ |
| Bound to one budget account | `budget_account_id` | ✓ |
| Bound to one owning lane | `owning_lane_id`, changed only by RETRY/CONTINUATION handover in the ESC transaction, append-only history | ✓ |
| Bound to one direct child pair | `child_pair_id` = the pair created by that T-7 | ✓ |
| Bound to allowed modes | `allowed_modes`; §34 checks `mode ∈ h.allowed_modes` | ✓ |
| Immutable | insert-once, except the append-only owner history | ✓ |
| Possession ≠ authority | "Possession of a handle value confers nothing … authority is the lane-ownership check"; §34 `h.owning_lane_id != lane.lane_id → DENIED(CB_MALFORMED_REQUEST)` | ✓ |

The only model-visible T-7 output is `ChildIssuanceResult = ISSUED(handle) |
DENIED(code)`. A T-7 replay returns the same handle, which the replaying
ESC's lane still owns, because a handle moves only after its holder ended.
**✓**

## 7. Lane T-9 isolation

### 7.1 Model-visible result (brief §7)

`RevocationRequestResult = ACCEPTED_PENDING | RENOUNCED_FOR_EXECUTION |
DENIED(code)`. Line 2205 lists what the result does **not** contain: "No
record, id, slot, index, counter, time, target-set size, order or requester
identity". No opaque request handle is issued.

- The account termination index, lane id, account id, pending id,
  `requested_at` and `effective_at` all stay TCB-internal (line 2193 and
  the §9.11 non-disclosure paragraph).
- Every item in the brief §7 list is absent. **✓**

### 7.2 Denial equivalence for requester `B` (brief §8)

| Input by `B` | Path (§34) | Output |
|---|---|---|
| 1. random unknown handle | `handles.get → None` | `DENIED(CB_MALFORMED_REQUEST)` |
| 2. `A`'s valid sibling-owned handle | `owning_lane_id ≠ B.lane` | same |
| 3. raw pair id | not handle syntax → `validate_exact`; or, if syntactically handle-shaped, `get → None` | same code |
| 4. malformed target | `validate_exact` | same code |
| 5. `A`'s handle whose pair was revoked externally | `owning_lane_id ≠ B.lane` | same (the effectiveness of the pair is never tested) |
| 6. `A`'s handle for a pair physically gone but logically known | handle rows are insert-once and never reused, so ownership check as in 2 | same |

- **Cases 2, 5 and 6.** These are the confidentiality-relevant ones. They
  follow the identical code path as case 1 (a store read of the handle, then
  one comparison), and none reads pair state.
- **Cases 3 and 4.** They may take a shorter path (a syntax reject), but
  that path does not depend on any sibling's state.

**No outcome lets `B` infer sibling or external state.** **✓**

### 7.3 Sibling target probe (brief §10)

`A` creates child `C`, and `B` probes it:

- **Raw pair ids** are never a valid target. `C`'s pair id is never
  model-visible.
- **Handles.** `A`'s handle is unguessable, and even when it leaks through
  a flow it is `DENIED`. Replays and malformed handles get the same answer.
- **Reason codes.** There is one code.
- **Timing.** The path is independent of whether `C` exists.
- **Allowance changes.** `B`'s lane changes only through `B`'s own acts,
  and denied T-9 requests consume nothing.

`B` cannot learn whether `C` exists, was just issued, was previously issued,
was revoked or is effective, **through T-9**. **✓** (It can learn a
sibling's *counted* effect at `effective_at` / `e(t)`, which is intended.)

### 7.4 Direct child only (brief §11)

The targets are `SELF` and the direct child pairs whose handle the lane
owns.

- Deeper descendants are not enumerable. They are reached only by the
  frozen v0.2.5 cascade, "All descendants become NOT_EFFECTIVE
  (UPSTREAM_INEFFECTIVE)".
- This narrows which frozen revocations v0.2.6 invokes, of the same kind as
  HR5-11 (§21.5, §39.1). The frozen revoker set allows more, and v0.2.6
  uses less.
- It is compatible with the frozen authority semantics. **✓**

## 8. Retry / continuation ownership

### 8.1 Atomic transfer (brief §12)

§9.3 step 12 hands over, for each named predecessor whose lane is OPEN:

- `LANE_HANDOVER` of every remainder;
- every handle that lane owns;
- the lane's `OPEN → CLOSED` transition.

All three happen in the ESC transaction under CAS on `account_revision`.

After transfer:

- the predecessor lane is CLOSED, with spendable remainder 0 in every
  dimension (§9.11 `BudgetLane` comment);
- it owns no handle;
- the successor owns each transferred handle once;
- predecessors are ended before handover, so no two LIVE ESCs hold one
  handle.

**✓**

### 8.2 Double successor race (brief §13)

Two RETRY creations name the same ended predecessor:

- the handover and the CLOSE are one CAS, so exactly one succeeds;
- the other re-reads, finds the lane CLOSED, and, if it consumes no OPEN
  lane, is DENY (`ESC_RELATION_UNTRUSTED`), a closed code;
- the loser receives no allowance and no handle, and no lane is minted from
  historical values;
- both relations were written by the trusted Scheduler, so the denial is
  not a sibling-model observable.

**✓**

## 9. Fork ownership and trigger

### 9.1 Handle ownership (brief §14)

- "Every existing RevocationTargetHandle stays with the source lane; the
  fork lane owns none" (§9.3 step 12).
- Children the fork issues later are owned by the fork's lane, because the
  handle is inserted with `owning_lane_id = lane.lane_id` of the issuer.
- There is no duplicated handle authority.

**✓**

### 9.2 Trigger (brief §15–§17)

A FORK needs a `ForkAuthorization` naming exactly this relation and source,
whose `trigger_kind ∈ profile.retry_policy.fork_triggers` and whose trusted
event verifies (§9.3 step 12, §9.8).

| Attempted trigger | Result |
|---|---|
| Sibling QA verdict, sibling output, sibling model response, sibling tool result | Not a `SOURCE_ESC` event (it is recorded only by the source's own harness), not an owner event, and not a `POLICY_DETERMINISTIC` input (the rule reads "only the source's own closed status, the TCR and trusted time") → `ESC_RELATION_UNTRUSTED` |
| Sibling budget state or sibling T-9 state | Not an input to any kind; FORK "never refused because of a sibling's forks, pending records or local renunciation" (§9.3 step 12, §9.11 item 6) |
| `SOURCE_ESC` spoofed by another ESC | The trigger is "a fork-request event recorded by the source's own trusted harness from the source's own closed request"; harness binding is TCB (as for `esc_id`, §9.5 rule 2). Another ESC cannot write it. ✓ |
| `SOURCE_ESC` by `A` itself | `A` observes its own lane split; that is the consequence of its own act, not a cross-ESC signal. ✓ |

One residual imprecision: the `POLICY_DETERMINISTIC` `trigger_ref`
includes "the trusted scheduler event it fired on", and the design does
not say which scheduler events may cause an evaluation. See **HR11-02**
(LOW).

### 9.3 Fork allowance (brief §18)

The INITIAL/CHILD lane holds `max_forks`. A FORK:

- consumes one unit from the source;
- splits the rest `f − 1` by `⌊·/2⌋` to the fork and `⌈·/2⌉` to the source;
- is a CAS on the account.

| Property | Result |
|---|---|
| Total conserved | `1 + ⌊(f−1)/2⌋ + ⌈(f−1)/2⌉ = f` ✓ |
| Repeated splits cannot create allowance | induction on splits, as for the other dimensions (HR10 §6.4) ✓ |
| Odd rounding | exact ✓ |
| Fork races | CAS; the second re-reads the halved remainder ✓ |
| Sibling forks change another lane's fork outcome | no; the task-level `max_forks` count cannot bind, because the sum of consumed units ≤ the initial `max_forks` ✓ |

### 9.4 HR10-02 verdict

**HR10-02: RESOLVED_IN_R9.** The trigger sources are closed. The
evaluation-instant precision is carried as HR11-02 (LOW, not freeze
blocking).

---

## 10. LocalRenunciationRecord (primary falsification target)

### 10.1 Exact scope

The r9 text is unambiguous about scope:

- **§9.3 step 12, lines 1256–1257.** "RETRY/CONTINUATION: `acct` has no
  `LocalRenunciationRecord`, and no `PendingModelRevocation` of class C
  targeting the task's own pair (effective or not) else
  DENY(ESC_LINEAGE_INVALID)". `acct` is the task's single
  `DelegationBudgetAccount`.
- **§9.11, lines 2338–2340.** "the ESC Issuer refuses every later RETRY or
  CONTINUATION of that task".
- **INV-CB-090.** "prevents any new RETRY or CONTINUATION **of that task**
  from binding the renounced leaf".
- **§32, T7Policy row.** "blocks new ESCs of its task".

**The `LocalRenunciationRecord` is task-wide** (account-scoped). It is not
ESC-local and it is not lane-local. The FORK case alone was carved out in
r9.

### 10.2 Brief §20 questions

Setup: `A` and `B` are concurrently LIVE in task `T`. `A` makes an
out-of-limits `SELF` renunciation and ends locally. No frozen revocation
occurs.

| # | Question | Answer (r9 text) |
|---|---|---|
| 1 | Does `B` continue? | Yes ("Other already LIVE ESCs of the task are unaffected") |
| 2 | May `B` still T-7? | Yes. T-7 steps 0–5 read no `LocalRenunciationRecord` |
| 3 | May `B` still T-9? | Yes. `request_model_revocation` reads none |
| 4 | May `B` fork? | Yes, given a valid `ForkAuthorization` and own fork remainder (r9 carve-out) |
| 5 | After `B` ends, may `B` receive a RETRY or CONTINUATION? | **No.** Every RETRY/CONTINUATION of `T` is DENY (`ESC_LINEAGE_INVALID`), including one that names only `B` |
| 6 | Does `A`'s record alter `B`'s scheduler outcome? | **Yes** |
| 7 | Can `B`'s destination observe that future execution was suppressed? | **Yes.** `B`'s retry or continuation never emits. The relation denial with its closed reason code is a §14.8 control-plane observable to the orchestrator, other executions and the API |

### 10.3 Why this is an uncounted sibling / future-execution signal

1. **Model-controlled.** `A`'s model chooses to renounce, and when.
2. **Uncounted.** The out-of-limits path consumes no `R_max` slot and is
   not quantized. The §9.11 table row "Out-of-limits self-renunciation"
   records **0 additional**.
3. **Available whenever the counted channel is closed:**
   - after the horizon `H`;
   - and, inside the horizon, whenever the renouncer's lane has no
     termination remainder.

   The second case is common. With `R_max = 1`, every FORK lane receives
   `⌊1/2⌋ = 0`, so **every fork's `SELF` is always the out-of-limits
   path**.
4. **Effect.** It changes whether an unrelated sibling chain (`B`'s) is
   ever retried or continued. CONTINUATION follows crash, restart or
   timeout, which `B` may not control. So `A` decides whether `B`'s work
   survives.
5. **Inconsistent rationale.** The stated rationale, "no new successor
   execution binds the renounced leaf", does not fit the design's own
   semantics:
   - nothing is revoked, and `B` keeps binding the same pair while LIVE;
   - r9 itself lets a FORK bind it (§9.11 lines 2341–2345);
   - r9 exempts FORK because "that refusal would signal the renunciation to
     the source". The same refusal applied to `B`'s RETRY or CONTINUATION
     signals the renunciation to `B`'s successor chain and its observers,
     and the design gives no reason why that is acceptable.

### 10.4 Pending within-limit SELF: a pre-effective sibling signal (brief §25)

The same clause also refuses RETRY/CONTINUATION when a class C
`PendingModelRevocation` exists "(effective or not)".

- `A` makes a within-limit `SELF` renunciation at `t` in bucket `k`, so
  `effective_at = (k+1)·g`, and `A` ENDs at once.
- `B` ends, or crashes, at `t′ ∈ (t, effective_at)`.
- The Scheduler's CONTINUATION{B} is refused at `t′` with
  `ESC_LINEAGE_INVALID`.
- Without `A`'s act, the continuation would run normally. With the act
  handled like a FORK, it would run until `effective_at` and then be
  REVOKED with everyone else.

So, **before `effective_at`**, an ESC Issuer decision about `B`'s own lane
(its handover is refused, and the lane stays OPEN) and the resulting status
and emissions depend on `A`'s pending act.

This contradicts, in the normative text:

- **§9.11 lines 2318–2322:** "Before `effective_at` a sibling observes
  nothing of it: no pending record, counter, lane value, **ESC Issuer
  decision affecting its own lane**, T-7 or T-9 result or other metadata
  changes".
- **§0.10 item 6:** "not exposed earlier through any record, counter or ESC
  Issuer decision".

The observable is an early distinction between "`A` renounced its pair"
and "`A` simply finished". §9.11 itself says these look identical ("exactly
as when a parent simply finishes"). The distinction arrives before the
quantized effect.

After `effective_at` the clause is redundant, because §9.3 step 6 already
refuses every ESC that would bind the revoked pair. **The clause's only
effect is inside the window the pending mechanism exists to hide.**

### 10.5 Magnitude and precedent

The bandwidth is small:

- at most one such event per renouncing ESC;
- a few bits;
- comparable to the §14.8 "status and retry choices" residual. Shared
  task-level `max_retries` / `max_continuations` counts already let one
  chain exhaust another's retries, which is an accepted pre-r8 residual.

But the design does not make that argument. It states zero:

- the §9.11 table: "0 additional";
- the pre-effective statement (§10.4);
- §38.2, which enumerates what remains between LIVE ESCs and omits this.

The brief's freeze standard names both properties explicitly:

- "LocalRenunciationRecord creates no uncounted sibling/future-execution
  signal";
- "pending SELF revocation has no pre-effective sibling signal".

HR10 set the precedent that an explicit non-interference claim contradicted
by the normative procedure is a freeze-blocking MEDIUM (HR10-01).

The tests encode the defect rather than detect it:

- TST-CB-090 r8 requires "a later RETRY, CONTINUATION or FORK **of that
  task** → `ESC_LINEAGE_INVALID`";
- no test covers brief items 13–15 (§25).

→ **HR11-01 (MEDIUM, freeze blocker).**

### 10.6 Lineage identity (brief §23)

No frozen authority edge is changed by a local renunciation. §9.11 says
"not a delegation-store revocation", and no `revoke()` call is made. **✓**

The record does **not** block only the intended lineage branch: it blocks
every RETRY/CONTINUATION branch of the task. **✗** (HR11-01)

A related gap: the renouncer's own lane is never closed. In the
within-limit case `A` is ENDED with its lane OPEN and its handles attached.
Under a chain-local correction, a successor that conservatively names `A`
(§9.8 "name all prior ESCs") would inherit the renouncer's remainder and
handles. The correction must close the renouncer's lane (§29, HR11-01
correction).

---

## 11. Within-limit and pending SELF revocation

### 11.1 Within-limit SELF (brief §24)

| Property | r9 | Result |
|---|---|---|
| Frozen pair actually revoked at `effective_at` | `apply_due_model_revocations` → unchanged `revoke(…, now = effective_at)` | ✓ |
| Every ESC bound to the pair becomes ineffective; live siblings stop | §9.11 lines 2310–2315; §9.5 rule 6 | ✓ |
| Bucket-quantized | `effective_at = (⌊now/g⌋+1)·g` from the trusted clock | ✓ |
| One `R_max` act | one `TERMINATION_ACT` against the requester's lane | ✓ |
| Counted in `C_T7` | target = own pair ∈ `1 + D`, mode ∈ 3, bucket ∈ `B` | ✓ |

### 11.2 Pending SELF before `effective_at` (brief §25)

| Channel for sibling `B` | Result |
|---|---|
| FORK denial | none (r9 carve-out) ✓ |
| T-7 result | T-7 step 1 treats a pending record as effective only at `effective_at ≤ now` ✓ |
| T-9 result | `re-run request_context` reads pair effectiveness with the same rule; `B`'s own lane unaffected ✓ |
| Local counters / lane size | `A`'s `TERMINATION_ACT` is on `A`'s lane ✓ |
| Handle validity | handles never tested for pair state ✓ |
| **Scheduler behavior: RETRY / CONTINUATION of `B`'s chain** | **refused before `effective_at`** ✗ (HR11-01) |

---

## 12. Channel proof

### 12.1 Formula (brief §28)

`C_T7(A) ≤ N_c·⌈log2(1+n_T·B)⌉ + R_max·⌈log2(1+3·(1+D_A)·B)⌉`, where
`B = ⌈H/g⌉ + 1`, unchanged from r8.

r9 narrows valid targets from "any of `1 + D` pairs" to "`SELF` ∪ own
direct children". The per-lane target set at any instant is a subset of
the counted `3 · (1 + D_A)` alphabet, and the policy computation still uses
`D = D_max`.

| Candidate omitted symbol | Result |
|---|---|
| Owned handle whose pair is already revoked | accepted; a duplicate at commit; counted slot (overcount) |
| `SELF` by two different ESCs, different modes | two slots, both counted |
| Cascade to deeper descendants | effect of a counted direct-child act; the deeper pair is also in the alphabet (overcount) |
| Handle transfer to a successor | no descendant-visible effect |
| Fork allowance / FORK | no pair, no descendant effect |

**No undercount for the T-7/T-9 effects the formula governs.** The formula
remains a conservative upper bound.

It does **not** bound the out-of-limits renunciation's effect on sibling
chains, which is uncounted and claimed zero (HR11-01).

### 12.2 Internal metadata exclusion (brief §29)

| Surface | Replay collisions / counters / ledger / lane ownership / sibling target existence / internal order |
|---|---|
| T-7 / T-9 API response | closed results only ✓ |
| Tool result, task output | not written (TCB-internal) ✓ |
| Exception | `SecurityError(code, correlation_id)` (§18.3) ✓ |
| Audit projection | RESTRICTED / AUDIT only (§30.1 r9 rows, §30.4) ✓ |
| Log / telemetry | TCB-issued ids and counters in closed schemas (§18.3); not model-visible ✓ |
| QA feedback | an item labeled ⊒ `H_exec`; contains nothing TCB-internal ✓ |
| Retry status / error reason | **`ESC_LINEAGE_INVALID` on a sibling chain's RETRY/CONTINUATION reveals another ESC's pending class C record before `effective_at`, or its local renunciation** ✗ (HR11-01) |
| Timing | same path for invalid-target cases; CAS latency inside the §38.2 timing residual ✓ |

---

## 13. HR10-03 — closed lanes

- A CLOSED lane has "spendable_remainder = 0 in every dimension; owns no
  RevocationTargetHandle; can be spent, handed over or split by nobody".
  Its history is audit-only (§9.11 `BudgetLane`; §9.3 step 12 comment).
- There is a single-consumer rule, and a successor that consumes no OPEN
  lane is DENY.
- The §34 "last unit" row and the TST-CB-048 clause are reworded.

**HR10-03: RESOLVED_IN_R9.**

## 14. HR10-04 — historical template

Construction (brief §31):

1. **T is ACTIVE.** A T-7 step 3 checks it and step 5 re-reads it inside
   the transaction. The child is admitted, and the binding records
   `child_delegation_template_ref` as admission provenance.
2. **T is later REVOKED.**
   - The child's `issue_esc` step 4 checks `ExecutionPolicyBindings`
     without the template (lines 1186–1187).
   - The child's T-7 step 1 does not check its own creation template
     (lines 1542–1543).
   - So the child task, its ESCs (including RETRY, CONTINUATION and FORK)
     and its own T-7s continue.
3. **A new T-7 using T.** Step 3 requires ACTIVE, so it is DENY
   (`CB_POLICY_UNAPPROVED`). A revocation between step 3 and step 5 is
   caught by the re-read.

§29.4, §9.3, §9.7, §34 and INV-CB-093 say the same thing. TST-CB-093 r9
covers steps 1–4.

**HR10-04: RESOLVED_IN_R9.**

### 14.1 ExecutionPolicyBindings regression (brief §32)

The bindings still contain:

- the exact TaskProfile, with its sealed T7Policy;
- the ApprovalClass;
- the EnvironmentClass;
- each destination authorization.

These are checked at every decision, delivery, T-7 (steps 1, 3 and 5),
T-9 and new ESC. Only the historical template was removed. **No runtime
dependency was lost. ✓**

## 15. HR10-05 — RevocationCommitBarrier

| Store | Own mark | Barrier obligation |
|---|---|---|
| Authority / delegation (v0.2.5.2) | `hwm_auth` (v0.2.5 §10 "the store keeps a monotonic high-water mark") | no event `> p.effective_at` before `p` is committed, for every `p` with `auth ∈ stores(p)` |
| Clearance | `hwm_clr` | same, for `CLEARANCE_HALF` / `WHOLE_PAIR` |
| LineagePair | `hwm_pair` | same, for `WHOLE_PAIR` |

- **Entry points.** Every entry point of each store first applies the due
  `PENDING` records that touch it, as one coordinated commit across
  `stores(p)`.
- **Commit time.** `t = effective_at` iff `max(hwm_s) ≤ effective_at`, else
  actual (`late`).

**Partial physical commit (brief §34).** The authority write succeeds, then
a crash occurs before the clearance and pair writes (separated-store
deployment only; in the §21.3 single commit domain the commit is atomic).
Then:

- `p` stays `PENDING`;
- every v0.2.6 decision at `≥ effective_at` treats the **whole** logical
  revocation, all halves and the pair, as effective;
- the next entry point of any store in `stores(p)`, or recovery, repeats
  the block idempotently: the authority write becomes a
  `DUPLICATE_REVOCATION` under v0.2.5's "first record wins", and the rest
  is written with the same `effective_at`;
- no mixed state is ever authorization, because the v0.2.6 gates are
  conjunctive with the v0.2.5 gate and read the logical record.

TST-CB-090 r9 has the fixture.

**HR10-05: RESOLVED_IN_R9.**

**Frozen contract (brief §35).** The barrier is an additive v0.2.5.2
integration obligation (§21.3, §39.1). `revoke()` stays immediate,
irreversible and idempotent at its commit. `now = effective_at` is at or
above the store mark in the normal case, as v0.2.5 §10 requires, and
`late` uses actual time. **No amendment is required.**

## 16. HR10-06 — CR ownership

| Function | Owner (§40.B r9) | Result |
|---|---|---|
| Account persistence, ledger primitives, `ForkAuthorization` records | CR-TASK-01 (T5) | ✓ |
| Lane open / handover / split / close, handles, fork validation, T-7/T-9 lane accounting, `LocalRenunciationRecord` | CR-ESC-01 (T6) | ✓ |
| `PendingModelRevocation` store, scheduler, barrier; opaque ids, no cross-store constraint | CR-LIN-01 (T4) | ✓ |
| Policy lifecycle, including `fork_triggers` / `fork_rule` | CR-POL-01 (T1) | ✓ |

No edge changed. CR-ESC-01 (T6) depends on TASK (T5) and LIN (T4), and
TASK depends on LIN, so the graph is acyclic.

One runtime data interface is not stated. The Execution Scheduler
(CR-TASK-01) consumes the source harness's fork-request event and the
source's closed status, both produced under CR-ESC-01. This is the same
kind of item as HR10-06 and needs no edge: **HR11-03** (INFO).

**HR10-06: RESOLVED_IN_R9.**

---

## 17. INV-CB-090

| Required coverage (brief §37) | Present |
|---|---|
| Requester-local T-9 idempotency | ✓ `(requesting_esc_id, request_ref)` |
| No cancellation | ✓ |
| Effective-time semantics | ✓ `≥ effective_at`; barrier; late repair |
| Closed model-visible result | ✓ |
| Lane-owned targeting | ✓ `SELF` or owned handle; cascade |
| Immediate class A | ✓ |
| Local out-of-limits renunciation semantics | present, but mandates the **task-wide** block ("prevents any new RETRY or CONTINUATION **of that task**"), which is the HR11-01 channel; no pre-effective sibling non-disclosure clause |

**INV-CB-090: INCOMPLETE.** Every clause is sound except the renunciation
scope clause, which must become chain-local, or be stated and counted, per
HR11-01.

## 18. INV-CB-093

It is coherent. The template is an issuance capability, ACTIVE inside the
issuance transaction, and then immutable admission provenance. It is not
a binding, and its later lifecycle denies only new T-7s. The foundational
and capability split is unchanged.

**INV-CB-093: VALID.**

## 19. INV-CB-106

| Required coverage (brief §39) | Present |
|---|---|
| Requester-local replay (T-7 and T-9) | ✓ |
| Lane-owned handles | ✓ |
| No sibling target probe | ✓ |
| No shared-account counter observation | ✓ |
| Safe fork trigger | ✓ (precision: HR11-02) |
| Fork handle ownership | ✓ |
| Single-consumer handover | ✓ |
| Closed-lane semantics | ✓ |

**INV-CB-106: VALID** for the T-7/T-9/FORK scope it states. The isolation
it asserts is "another live lane's T-7 or T-9 decisions" plus FORK. It
does not cover RETRY/CONTINUATION creation for a sibling chain, which is
where HR11-01 lies. The HR11-01 correction should extend 106 or 090 to that
dimension.

---

## 20. LineagePair regression

r9 changes that touch the lineage:

- handle insertion in the T-7 transaction;
- lane-local target restriction (narrowing);
- template removed from `ExecutionPolicyBindings` (`issue_esc` step 4,
  T-7 step 1);
- `RevocationCommitBarrier`.

These are unchanged:

- no pair search;
- parent-bound pairs;
- the leaf-parent checks (§9.3 step 6);
- `pair.issuer_event == deb.issuance_event`;
- `deb.child_profile_ref == tcr.task_profile_ref`;
- leaf uniqueness;
- the approval digest;
- the ancestor walk;
- rule 5 cascade;
- atomic co-issuance in one commit domain, now also covering handles,
  lanes and `ForkAuthorization`.

No path binds, shops or revives a pair. Every r9 addition is a further
conjunct, a narrowing or a DENY.

`LINEAGEPAIR R9 REGRESSION-FREE`

## 21. DelegationBudgetAccount regression

| Property | Result |
|---|---|
| One account per task (UNIQUE `task_control_record_id`; created only at T-8 / T-7) | ✓ unchanged |
| `D` bound / capacity induction | ✓ unchanged; retries, continuations and forks create no pair or account |
| Channel accounting per account | ✓ unchanged formula |
| Lane conservation | ✓ one new dimension (forks), conserved |
| No fresh budget through retry or fork | ✓ step 12 `ESC_RETRY_REBINDING`; lanes only split or hand over |

**Regression-free.**

## 22. Read-confinement regression

r9 made no edit to §16–§18. The following still stand:

- the §17.9 rule `unknown actual readable universe = DENY` (line 3927);
- `deliver()` `ars is None → DENY(CB_READ_SET_INCOMPLETE)`, with "no
  owner-ceiling fallback" (lines 6003–6007);
- GitReadClosure (§17.11);
- Level 2R (§6.5);
- the ConfinementRecord checks.

**Regression-free.**

## 23. Activation regression

`valid(a, t)` (§40.F) still requires only `current_epoch ≥
monotonic_epoch_at_approval` as a rollback floor. The "Not a conjunct (r7)"
paragraph keeps the global SecurityPolicyVersion out of the predicate.
Exact ActivationPolicyBindings remain authoritative.

r9 lifecycle edits are ESC-scoped or template-scoped and do not touch
IntegrationActivation. There is no global epoch kill switch and no global
SecurityPolicyVersion kill switch.

**Regression-free.**

## 24. Network-taint regression

r9 made no edit to §14.3 or §17.6, or to `deliver()` /
`complete_tool_invocation()`. The following are intact:

- the persisted `L_net_max` and `reserved(esc)` in every ceiling check;
- the failed-tool taint append;
- the interleaved-delivery join against the latest `H_exec`;
- `RequiredActivationSet(op)`.

**Regression-free.**

---

## 25. Tests and invariant accounting

Counted mechanically from the r9 file:

- **§33:** 106 `INV-CB-NNN` rows, IDs 001–106, no gaps, no duplicates.
- **Active:** 105. Only INV-CB-030 has status `**withdrawn**`.
- **New IDs:** none.
- **"rev r9" rows:** exactly 090, 093 and 106. INV-CB-048 keeps "rev r8".
  This matches §0.10 and the §33 totals paragraph.
- **§36** (lines 6351–6589): 105 `TST-CB-NNN` definition rows, at lines
  6398–6502, all inside §36. There are no duplicates, and no definition row
  exists elsewhere. The closing r8/r9 "negative cases" rows are
  cross-references to test IDs, not definitions.
- **Mapping:** the active-invariant ID set equals the test ID set, so there
  is exactly one test per active invariant. TST-CB-023 carries `023(+030)`.

| Hostile test (brief §42) | Covered by | Status |
|---|---|---|
| 1 same `request_ref`, two concurrent siblings | TST-CB-090 r9 | ✓ |
| 2 requester-local replay | TST-CB-090 r9 | ✓ |
| 3 sibling handle probe | TST-CB-090 r9, TST-CB-106 r9 | ✓ |
| 4 raw pair-id probe | TST-CB-106 r9 "Sibling target probing"; TST-CB-048 r9 | ✓ |
| 5 no global slot or counter in the response | TST-CB-090 r9 | ✓ |
| 6 retry handle transfer | TST-CB-106 r9 | ✓ |
| 7 double successor race | TST-CB-106 r9 "retry double transfer" | ✓ |
| 8 fork receives no historical handles | TST-CB-106 r9 | ✓ |
| 9 fork trigger not from sibling output | TST-CB-106 r9 | ✓ |
| 10 closed lane zero remainder | TST-CB-106 r9 | ✓ |
| 11 historical template revoked after admission | TST-CB-093 r9 | ✓ |
| 12 partial-store revocation failure | TST-CB-090 r9 | ✓ |
| 13 pending SELF invisible to siblings before `effective_at` | FORK case only (TST-CB-106); no sibling RETRY/CONTINUATION, T-7 or T-9 case; descendants only in TST-CB-048 | **partial** |
| 14 out-of-limits local renunciation vs an already-LIVE sibling | FORK case only | **partial** |
| 15 later RETRY/CONTINUATION after another sibling's local renunciation | **absent**; TST-CB-090 r8 asserts the opposite (task-wide `ESC_LINEAGE_INVALID`) | **✗** |

Items 13–15 are part of HR11-01.

## 26. Dependency graphs

- **Build graph (§40.E).** r9 added no edge. Every edge still points to a
  strictly lower tier: POL T1, LIN T4, TASK T5, ESC T6. It is acyclic.
- **Activation graph.** Unchanged; acyclic.
- **GATE-CONTAIN.** Unchanged (EGR-01a, LEG-01a, IFR, LOG-01, and the
  CR-ISO-01 restriction-mode activation); cycle-free.
- **r9 CR ownership.** No hidden cycle. CR-LIN-01 stores foreign ids as
  opaque values, and the Scheduler/harness interface of HR11-03 is runtime
  data, not a build edge.

## 27. Frozen-contract compatibility

| Contract | r9 impact | Amendment needed? |
|---|---|---|
| v0.2 | strengthening only | No |
| v0.2.3 | router default never relied on | No |
| v0.2.4 | identifiers unchanged | No |
| v0.2.5 | `revoke()` unchanged; per-store marks consistent with §10 ("the store keeps a monotonic high-water mark"); duplicate = "first record wins"; lane-owned targets narrow the §11 revoker set as a usage restriction | No |
| v0.2.5.1 | types unchanged (`RevocationRecord`, `AuthorityScope`) | No |

**No amendment to any frozen v0.2.x contract is required.** AMD-025-01
remains uncreated and unnecessary. The HR11-01 correction is
v0.2.6-internal.

## 28. Owner decisions

These are genuine policy choices, left open. None is decided here.

1. The `T7Policy` values (`N_c`, `P_max`, `n_T`, `g`, `H`, `R_max`,
   `D_max`), template contents, each `child_subtree_budget`, and acceptance
   of the stated per-task `C_T7` bound.
2. Per-profile `retry_policy.fork_triggers` and `fork_rule` values, within
   the fixed technical rule.
3. The ApprovalRequirement vocabulary and each class's requirement set.
4. Each component's ActivationManifest `policy_dependencies`, and
   `RETAIN_…` / `INVALIDATE_…` for each successor version.
5. The CR classification from the §40.F procedure, with CR-NET-01's
   `InternalEndpointPolicy` recorded under a gated mode.
6. The earlier dispositions listed in §44.5: the §0.2 / §0.4 dispositions,
   the LineagePair realization, the §14.9 default labels, and the
   environment-class vocabulary and network-destination policy.
7. The recommended human security review before freeze.

**Not owner decisions** (technical rules still to be fixed):

- the scope of the local-renunciation / pending-class-C successor block
  (HR11-01);
- the `POLICY_DETERMINISTIC` evaluation instants (HR11-02).

If the author chooses HR11-01 option B, accepting the task-wide effect as a
stated residual, the owner would then have to accept that residual. That
acceptance is a policy decision, but the technical rule and its bound must
first be written.

---

## 29. New HR11 findings

### HR11-01 — The task-wide RETRY/CONTINUATION block lets one ESC's renunciation suppress, and signal through, a sibling's future execution

- **Severity:** MEDIUM
- **Category:** NEW. The r8 text was not flagged by HR10; r9's new explicit
  claims (§0.10 item 6, §9.11 lines 2318–2322) and its FORK-only carve-out
  now contradict it.
- **Section:**
  - §9.3 step 12, lines 1256–1257 and the FORK comment at 1265–1268;
  - §9.11, lines 2299–2350 (the within-limit and out-of-limits bullets),
    the channel table row "Out-of-limits self-renunciation", and item 6 of
    "Same-task state";
  - §0.10, HR10-01 item 6 and the HR10-02 row;
  - §32, T7Policy row ("blocks new ESCs of its task");
  - §34, explicit-behaviours row "Model-controlled T-9 act …";
  - §38.2, "T-7 shared quotas";
  - INV-CB-048 ("a self-renunciation ends only the renouncing ESC");
  - TST-CB-090 r8, "Out-of-limits renunciation".
- **Invariant:** INV-CB-090 (renunciation clause), INV-CB-106 (sibling
  isolation), INV-CB-048 (0-additional claim).
- **Attack / contradiction:** Task `T` has concurrently LIVE ESCs `A`
  (possibly high-taint after a post-fork read) and `B`.
  1. **Out-of-limits.** `A`'s model renounces `SELF` when its lane has no
     termination remainder (for example any FORK lane when `R_max = 1`) or
     after `H`. A task-wide `LocalRenunciationRecord` is written. When `B`
     later ends, or crashes, or times out, every RETRY/CONTINUATION of `T`
     is DENY (`ESC_LINEAGE_INVALID`), including one naming only `B`. The
     act is unquantized, consumes no `R_max`, and the design counts it as
     "0 additional".
  2. **Within-limit.** `A` renounces `SELF` inside the limits, so a
     `PendingModelRevocation` exists with `effective_at = e(t)`. `B` ends
     at `t′ < effective_at`, and `B`'s CONTINUATION is refused at `t′`
     because of the "(effective or not)" clause. Without the clause, the
     continuation would run until `effective_at`, exactly as a FORK now
     does. The refusal, with its closed reason code, is a §14.8 observable,
     and the continuation's absent emissions are destination-visible. Both
     occur before `effective_at`, which contradicts "Before `effective_at`
     a sibling observes nothing of it: no … ESC Issuer decision affecting
     its own lane". After `effective_at` the clause is redundant with §9.3
     step 6.
  3. **Rationale.** The stated rationale, "no successor binds the renounced
     leaf", is inconsistent. Nothing is revoked in case 1 (and nothing yet
     in case 2). LIVE `B` and new FORKs bind the same pair. r9 removed the
     FORK block precisely because such a refusal "would signal the
     renunciation", but kept it for RETRY/CONTINUATION of unrelated sibling
     chains.
- **Impact:**
  - **Out-of-limits case.** A model-controlled, uncounted,
    horizon-independent control effect of one ESC on another chain's
    survival, observable to the orchestrator, the API, other executions
    (for example a parent task reading child status) and the destinations
    of the suppressed successor.
  - **Within-limit case.** An early, pre-quantization disclosure of a
    counted act.
  - **Size.** Small: about one event per renouncing ESC, a few bits, of the
    order of the §14.8 retry residual. Shared `max_retries` /
    `max_continuations` counts already give a similar accepted coupling.
  - **Why it still matters.** The design's explicit claims (0 additional;
    no pre-effective ESC Issuer decision; FORK-only exposure) are false,
    §38.2 omits the effect, the tests assert the defect, and the brief's
    freeze standard names both properties.
- **Required correction** (narrow; the author chooses):
  - **Option A (recommended; chain-local).**
    1. At acceptance of any class C act, within limits or not, close the
       renouncer's lane (`OPEN → CLOSED`: spendable remainder 0, handles
       retired, and not transferable).
    2. Record the `LocalRenunciationRecord` against that ESC and lane, not
       the account.
    3. Delete the account-wide clause in §9.3 step 12. A RETRY/CONTINUATION
       that consumes no OPEN lane is already DENY
       (`ESC_RELATION_UNTRUSTED`), so a successor of the renouncer alone is
       refused, while a successor of `B` (even one that conservatively names
       `A` for taint) consumes only `B`'s lane and is created.
    4. Before `effective_at`, such a successor binds the still-effective
       pair and stops at `effective_at` with every other ESC, exactly like
       a FORK. After `effective_at`, step 6 refuses it.
    5. State that retired handles leave the affected child pairs revocable
       only by class A.
  - **Option B (keep task-wide).**
    1. Drop the "(effective or not)" pre-effective refusal, since step 6
       covers the post-effective case.
    2. For the out-of-limits record, declare the task-wide successor block
       an explicitly modeled task-family effect.
    3. Bound it, for example at most one event per ESC and at most `1 +
       max_forks + max_retries + max_continuations` per task, inside the
       §14.8 residual.
    4. List it in §38.2 and in the §9.11 table in place of "0 additional",
       and state why a sibling chain may be suppressed.
  - **Either option also requires:**
    - aligning the §32 T7Policy row, the §34 behaviour row, INV-CB-048,
      INV-CB-090 (renunciation scope; pre-effective non-disclosure for
      successor creation) and INV-CB-106 (extend isolation to sibling
      RETRY/CONTINUATION creation);
    - replacing the TST-CB-090 r8 "RETRY, CONTINUATION or FORK of that
      task" clause;
    - adding tests for brief §42 items 13–15: a sibling
      RETRY/CONTINUATION before `effective_at` of a pending class C act,
      and after an out-of-limits renunciation, compared across runs with
      and without `A`'s act.
- **Freeze blocker:** YES. The explicit non-interference and pre-effective
  claims on the primary r9 mechanism are contradicted by the normative
  procedure, and the brief's freeze criteria for `LocalRenunciationRecord`
  and pending SELF fail.
- **Implementation blocker:** YES (CR-ESC-01; CR-TASK-01 Scheduler
  behaviour)
- **Deployment blocker:** NO

### HR11-02 — `POLICY_DETERMINISTIC` fork evaluation instants are unconstrained

- **Severity:** LOW
- **Category:** RESIDUAL-HR10 (HR10-02)
- **Section:** §9.3 step 12 (POLICY_DETERMINISTIC); §9.4 `fork_rule`; §9.8
  `ForkAuthorization.trigger_ref` "(fork_rule ref, the trusted scheduler
  event it fired on)"
- **Invariant:** INV-CB-106
- **Attack / contradiction:** the rule's *inputs* are restricted to the
  source's own closed status, the TCR and trusted time, but the design does
  not say *when* the Scheduler evaluates it. Take a time-dependent rule
  ("fork when elapsed ≥ X") evaluated at arbitrary scheduler events. It
  fires at the first evaluation after X, and if that evaluation was caused
  by a sibling's end or failure event, the moment the source's lane halves
  is correlated with a sibling's act.
- **Impact:** at most `max_forks` timing events per task, observable by the
  source only through its own later lane-exhaustion DENY. Bandwidth is very
  low, but the statement "a FORK outcome never depends on a sibling's …
  acts" is not guaranteed for timing.
- **Correction:** state that `POLICY_DETERMINISTIC` rules are evaluated only
  at the source's own status transitions or on a fixed trusted time grid
  (for example the `g` bucket boundaries), never on another ESC's event,
  and that the `trigger_ref` event is one of those.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-TASK-01 Scheduler)
- **Deployment blocker:** NO

### HR11-03 — Scheduler/harness data interface for fork triggers is unstated

- **Severity:** INFO
- **Category:** NEW (DAG hygiene, same kind as HR10-06)
- **Section:** §40.B CR-TASK-01 and CR-ESC-01; §9.8
- **Invariant:** —
- **Attack / contradiction:** CR-TASK-01 (T5) writes `ForkAuthorization`
  from a `SOURCE_ESC` fork-request event recorded by the source's trusted
  harness, and from the source's closed status. Both are produced under
  CR-ESC-01 (T6). The design does not say this is a runtime data interface
  (opaque event and status records) rather than a build dependency.
- **Impact:** none; no edge and no cycle.
- **Correction:** one sentence in §40.B / §40.E, as was done for the
  CR-LIN-01 opaque ids.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR11-04 — Residual wording of the renunciation scope

- **Severity:** INFO
- **Category:** NEW (editorial)
- **Section:**
  - §32 T7Policy row, "blocks new ESCs of its task";
  - §34 behaviour row, "blocks new ESCs of the task";
  - INV-CB-048, "ends only the renouncing ESC";
  - TST-CB-090 r8, "RETRY, CONTINUATION or FORK", reinterpreted by an r9
    parenthesis;
  - §9.11, which does not state what happens to the renouncer's lane and
    handles.
- **Invariant:** INV-CB-048, INV-CB-090
- **Attack / contradiction:** four texts describe the renunciation's reach
  differently, and one test clause is corrected only by a parenthesis. The
  renouncer's lane state is unspecified.
- **Impact:** none beyond HR11-01. The HR11-01 correction resolves it.
- **Correction:** part of HR11-01.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 1 (HR11-01) · LOW 1 (HR11-02) ·
INFO 2 (HR11-03, HR11-04) · total 4.

---

## 30. Freeze blockers

| ID | Why it blocks freeze |
|---|---|
| **HR11-01** | The task-wide RETRY/CONTINUATION refusal on a `LocalRenunciationRecord` or on a not-yet-effective class C record lets one ESC's model-controlled act suppress, and signal through, a concurrent sibling chain's future execution. The act is uncounted in the out-of-limits case and precedes `effective_at` in the within-limit case. This contradicts the design's explicit claims (§9.11, §0.10 item 6, "0 additional") and fails two named criteria of the freeze standard |

**Freeze-standard scorecard (brief §51)**

| Criterion | Status |
|---|---|
| No CRITICAL / HIGH design blocker | ✓ |
| No freeze-blocking MEDIUM | ✗ (HR11-01) |
| HR10-01 RESOLVED_IN_R9 | ✓ |
| Requester-local T-9 replay sound | ✓ |
| Sibling target probing impossible | ✓ |
| Lane handle transfer / fork ownership sound | ✓ |
| Fork triggering creates no sibling channel | ✓ for trigger sources (HR11-02 LOW timing precision) |
| LocalRenunciationRecord creates no uncounted sibling / future-execution signal | ✗ (HR11-01) |
| Pending SELF has no pre-effective sibling signal | ✗ (HR11-01: sibling RETRY/CONTINUATION) |
| Template lifecycle coherent | ✓ |
| Per-store revocation barrier coherent | ✓ |
| INV-CB-090 / 093 / 106 acceptable | ✗ 090 INCOMPLETE; 093 VALID; 106 VALID |
| LineagePair regression-free | ✓ |
| Account / capacity proof sound | ✓ |
| Read / activation / network blockers remain closed | ✓ |
| No frozen-contract amendment necessary | ✓ |

## 31. Implementation blockers (separate from freeze)

Every §43.1 row remains, including the r8 and r9 rows. There is no account
store, no lanes, no handle store, no pending store, no barrier and no
`ForkAuthorization`. None of that machinery exists.

In addition:

- HR11-01 (CR-ESC-01, CR-TASK-01);
- HR11-02 (CR-TASK-01).

## 32. Deployment blockers (separate)

Every §43.2 row, unchanged. The live defects are not fixed by any design
revision:

- R-01..R-09, R-11 and R-13;
- R-22..R-26, R-29 and R-30.

No HR11 finding adds a deployment blocker.

## 33. Final status

r9 correctly closes everything HR10 required:

- **T-9 identity.** It is requester-local.
- **Results.** The model-visible T-7 and T-9 results are closed.
- **Targets.** Revocation targets are lane-owned opaque handles. Sibling
  target probing is impossible.
- **Handles and lanes.** Handles transfer atomically to one successor, and
  forks receive none. CLOSED lanes are spendable by nobody.
- **Forks.** Fork triggers cannot come from another ESC's output.
- **Policy.** The template lifecycle is coherent.
- **Barrier.** The barrier is per store and repairs partial writes
  idempotently.

The account, capacity proof, channel formula, LineagePair, read
confinement, activation and network taint are regression-free, and no
frozen contract needs amendment.

One MEDIUM defect prevents READY. The r9 FORK carve-out shows the author
recognised that refusing a sibling's new execution because of another ESC's
renunciation is a signal. The same refusal remains, task-wide, for every
RETRY and CONTINUATION, both for an out-of-limits (uncounted) renunciation
and for a within-limit renunciation before `effective_at`. The correction
is narrow: close the renouncer's own lane and drop the account-wide clause
(option A), or state and bound the effect (option B). A focused
verification of that delta should suffice.

```text
R9 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

READY would have meant only that the technical review passed. It would not
have meant frozen, implementation-authorized, deployed or production-secure.

> No v0.2.6 production implementation has been authorized or created.

---

## Appendix A — Read-only validation

Run from `C:\Users\Gyuro\jarvis-os` with `.venv/Scripts/python.exe`, before
this file was written (the untracked set was the ten v0.2.6 documents).

| Command | Result |
|---|---|
| `python scripts/check_v013_freeze_baseline.py` | exit 0 (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `python scripts/check_v020_contract.py` | exit 0 |
| `python scripts/check_v023_router_contract.py` | exit 0 |
| `python scripts/check_v024_agent_contract.py` | exit 0 |
| `python scripts/check_v025_design_contract.py` | exit 1: `DISCREPANCY FOUND`, solely 10 × "file outside the v0.2.5.1 allowlist is new/modified" for the ten untracked v0.2.6 documents (expected) |
| `python -m pytest -q -p no:cacheprovider` | **1 failed, 2234 passed, 1 warning** (390.3 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`: the same v0.2.5 allowlist discrepancy for the untracked v0.2.6 documents. Matches the HR7–HR10 baseline |

No validator, test or configuration was modified.

## Appendix B — Integrity

The design and HR2–HR10 were re-verified at the end of the review (see the
terminal report). They are unchanged from the §2 hashes, HEAD is unchanged,
there are no tracked changes, and the only new file is this HR11 document.
No commit, push or merge was made.
