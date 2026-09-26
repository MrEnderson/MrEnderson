# Jarvis OS v0.2.6 — HR10 Final Freeze Verification of Design Revision r8

```text
subject                        = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r8)
subject status on entry        = CORRECTED R8 — PENDING HR10 FINAL FREEZE VERIFICATION
controlling prior review       = HR9 (docs/V0_2_6_HR9_FREEZE_VERIFICATION.md)
review type                    = independent technical freeze verification (read-only)
review date                    = 2026-09-25
design_modified                = false
hr2_to_hr9_modified            = false
code_tests_validators_modified = false
opendex_modified               = false
final_status                   = R8 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

Section numbers (§N) refer to the r8 design unless another document is
named. Finding IDs `HR10-NN` are new to this review.

---

## 1. Independence

This session authored **none** of:

- design revisions r1–r8;
- HR2, HR3, HR4, HR5, HR6, HR7, HR8 or HR9.

It started with no conversation history and worked only from repository
contents. The design's §0.9 authorship note says r8 was written by a session
that did not author HR9 and that HR10 must come from a session that did not
author r8. This session meets that condition.

The r8 correction record (§0.9), its "corrected" wording and the §44.5
sentence "No known freeze-blocking MEDIUM issues after r8" were **not**
treated as evidence. Conclusions come from the r8 normative text (§5, §7.3,
§9, §14, §21, §29.4, §31–§36, §39, §40), the frozen v0.2.5 text, and HR9.

**Limitation.** This review uses the same model family as HR2–HR9. It is
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
| Untracked (`git status --short -uall`) | exactly nine v0.2.6 documents: the design and HR2–HR9 |

This matches the expected state.

**SHA-256 at start of review**

| File | Role | SHA-256 |
|---|---|---|
| `docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md` | r8 design | `f8f0104849e190880862a6ba24a64abe0636a03db5e063a30af5aa7fd88dfae7` |
| `docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` | HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| `docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md` | HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| `docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |
| `docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` |
| `docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md` | HR6 | `42b170a580dba800fa310735c4ca0267083aa2beab0fb033fbebeeb289b4f07e` |
| `docs/V0_2_6_HR7_FINAL_FREEZE_VERIFICATION.md` | HR7 | `91e8d19eec8e98f38e7203b1f58d5181c2f25329c094de32fef53575fcecad64` |
| `docs/V0_2_6_HR8_FREEZE_VERIFICATION.md` | HR8 | `9848284e796f548b0012aa509de3b7a4cc3480f9fa5bad437020abf3d1b9aee7` |
| `docs/V0_2_6_HR9_FREEZE_VERIFICATION.md` | HR9 | `e8fcf9a2eb2598910b08c4cb64bc2c9d87c02ead5304743f6fb1c05f6ed73d15` |

The HR2–HR8 hashes equal the values HR9 recorded, so those files have not
changed since HR9. The design hash differs from HR9's r7 hash
(`7e8ff401…`), as expected for r8.

**OpenDex** (`C:\Users\Gyuro\opendex-reference`): HEAD
`3e898343d1127c8d5075b459acdd55da83b83f04`, the value in design §41.
`git status --short` is empty. No OpenDex file was opened or modified.

---

## 3. Materials

- **r8 design** (7520 lines): read directly, not through the terminal
  report of the r8 pass. Read in full: §0.8–§0.9, §5, §7, §9 (all of
  §9.1–§9.11), §14, §21, §22, §29.4, §30–§35, the four r8-revised §33 rows
  and §36 rows, §37 items 49–54, §38.2 (T-7 rows), §39, §40.B r8 scopes,
  §40.E, §44.5, §44.11, §45 and the authorization block. The unchanged
  regression anchors (§17.6 rule 2a, §17.9, §17.11, §40.F `valid(a, t)`)
  were re-read. A search for `r8`, `HR9` and `HR10` confirms that r8
  touched no other section except the §11 threat row TC-71 and the §43.1
  blocker row (both read).
- **HR9:** read in full.
- **HR8 / HR7:** not re-read; HR9 §4–§23 and design §0.8–§0.9 give
  sufficient traceability.
- **Frozen v0.2.5:** §10 (trusted time, clock high-water mark), §11
  (revocation), §22 R-01..R-10, the `revoke(…, *, now)` API row and the
  `RevocationRecord` type, in
  `docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md`.
- **Mechanical checks:** invariant and test accounting (§22 below).

---

## 4. HR9-01 — DelegationBudgetAccount identity

| Requirement | r8 text | Result |
|---|---|---|
| Exactly one durable account per TCR | `DelegationBudgetAccount.task_control_record_id` UNIQUE, "exactly one account per TaskControlRecord, ever" (§9.11); `TCR.delegation_budget_account_id` UNIQUE (§9.6) | ✓ |
| ROOT account created only at T-8 | §9.6 writers; §7.3 T-8 result row; §9.11 "Creation" | ✓ |
| CHILD account created only atomically at T-7 | §9.7 step 5 `child_acct = budget_accounts.insert(…)` inside the one transaction; "any failure → … no child account" | ✓ |
| Account ID stored in the TCR | §9.6 `delegation_budget_account_id`; §9.7 step 5 TCR insert names `child_acct.id` | ✓ |
| Every ESC gets the id only from the TCR | §9.2 field row; §9.3 step 1 `budget_accounts.get(tcr.delegation_budget_account_id)`, "by id, never searched"; step 12 successor must equal predecessor (`ESC_RETRY_REBINDING`) | ✓ |
| ESC Issuer cannot create an account | §9.3 step 1 "The ESC Issuer never creates an account; a task without its account is uncontrolled" | ✓ |
| T-10 cannot create an account | §7.3 T-10; §9.11 "No ESC, ExecutionRelation, replay, restart or recovery creates an account"; CR-TASK-01 "never creates an account" | ✓ |
| Replay cannot create an account | §9.7 step 0 "a replay returns before the counter step … creates no account"; INV-CB-106 | ✓ |
| Account binds exact policy | `t7_policy_ref = (task_profile_id, profile_version, t7_policy_digest)`; §9.3 step 1 checks it names the TCR's profile | ✓ |

The two defects HR9-01 named are corrected:

- **(a) budget reset** — the budget is per task, not per ESC (§9.11);
- **(b) whole-pair targets** — `WHOLE_PAIR` is a third mode, and the target
  term is `3 · (1 + D)` (§9.11).

**HR9-01: RESOLVED_IN_R8** for the defects it named.

The lane mechanism that r8 introduced to keep HR8-05's non-interference
property contains a new, r8-introduced defect in the T-9 path. It is
recorded separately as **HR10-01** (§25) and not folded into this verdict.

---

## 5. DelegationBudgetAccount

### 5.1 One task with INITIAL, RETRY, CONTINUATION and several FORKs

Construction: root task `T`, account `A` with allowances `(N_c, P_max,
R_max)` and capacity `D`.

- `I` (INITIAL);
- `F1 = FORK(I)`, `F2 = FORK(I)`, `F3 = FORK(F1)`;
- after `I` ends: `R = RETRY{I}`;
- after `R` crashes: `C = CONTINUATION{R}`.

| ESC | `delegation_budget_account_id` | Source |
|---|---|---|
| I | A | TCR (§9.3 step 1) |
| F1, F2, F3 | A | step 12 "every security field … must equal the predecessor's (r8: including `delegation_budget_account_id`)" |
| R, C | A | same rule |

**No fresh values.** No ESC receives a fresh `N_c`, `P_max`, `R_max`, `D`,
`horizon_start` or channel budget:

- the allowances and capacity are copied once into `A` (§9.11, "never
  re-read");
- `horizon_start` is set only in the INITIAL/CHILD transaction (§9.3 step
  14);
- lanes only "split or hand over what the account already holds" (step 12).

Only a lane of `A` is created per ESC. **✓**

### 5.2 Horizon

`horizon_start` is written "set once; never reset by any later ESC" (§9.3
step 14), only when `relation_id is None` (INITIAL/CHILD, "only once per
task").

- **Late retry.** `I` ends at `t0 + 10 min`. `R` starts at `t0 + 3 h` with
  `H = 1 h`. T-7 step 0 reads `now < acct.horizon_start + H`, which is
  false, so DENY. `request_model_revocation` reads the same condition, so a
  class B act is DENY and a class C act takes the out-of-limits path.
- **Continuation, fork, crash recovery, process restart.** None of these
  creates an INITIAL/CHILD relation, so none writes `horizon_start`.
- **Test coverage.** TST-CB-048 r8 covers "a RETRY after the horizon of the
  first ESC → T-7 and class B T-9 DENY".

**✓**

### 5.3 Policy identity

- **Copied values.** The account copies `(N_c, P_max, R_max)` and the
  capacity. It binds the exact TaskProfile version, and that version seals
  its `T7Policy` (§9.4 "sealed inside this TaskProfile version").
- **Values read from the policy.** `n_T`, `g` and `H` are read from the
  parent's exact profile version. That version is an insert-once ESC field
  and equals `acct.t7_policy_ref` (§9.3 step 1).
- **Later versions.** A later TaskProfile or `T7Policy` version is never
  read in its place (§29.4 "never re-reads an id under a newer definition";
  §37 item 54).

So none of `N_c`, `P_max`, `R_max`, `D`, `H` or `g` can be silently enlarged.
The task can only be:

- kept on its exact version, while that version is `ACTIVE` or
  `SUPERSEDED_BUT_STILL_VALID_FOR_EXISTING_BINDINGS`; or
- terminated, when that version becomes `REVOKED` or `EXPIRED`.

**✓**

*Note (not a finding).* The per-lane "per-window" issuance bound refers to
"the policy's window bound" without saying which version. It does not enter
`C_T7`, because `N_c` caps total issuances. The owner should still pin it to
the bound version when the policy store is built.

---

## 6. Lane algebra

### 6.1 Rules (§9.3 step 12, §9.11 "Lanes", §9.8)

| Event | Lane effect |
|---|---|
| INITIAL / CHILD | one lane holding the whole allowance and capacity; only once per task |
| RETRY / CONTINUATION | the remainders of the named predecessors' lanes are handed over (`LANE_HANDOVER`); each predecessor must be ENDED/TERMINATED/REVOKED with final `H_exec` accounted; the predecessor lanes close in the ESC transaction |
| FORK | new lane = `⌊r/2⌋` of each remainder `r` of the forked-from lane; the forked-from keeps `⌈r/2⌉` (`LANE_SPLIT`) |
| Every append | compare-and-swap on `account_revision` |

### 6.2 Global capacity

**Global capacity holds independently of the lane arithmetic.** T-7 step 0
checks the account totals as well as the lane: "Σ lanes ≤ acct P_max",
"Σ over lanes of reserved = acct.reserved_descendant_count ≤
acct.descendant_capacity". Step 5 then "re-check[s] every step-0 lane and
account limit against the ledger as of this revision" under CAS.

Even a lane-arithmetic error could not over-commit `N_c`, `P_max` or the
descendant capacity. It could only make the account-level check bind, which
would be a non-interference defect, not a capacity defect.

### 6.3 Dimensions

The split and handover apply to each remainder. That means:

- the proposal allowance;
- the issuance allowance;
- the termination allowance;
- the capacity remainder (`capacity − reserved`).

`⌊r/2⌋ + ⌈r/2⌉ = r` for every non-negative integer, so each split is exact.

### 6.4 Repeated forks (brief §17)

| Step | Lanes, `r` per dimension | Σ |
|---|---|---|
| S holds 5 | S=5 | 5 |
| FORK(S) → A | S=3, A=2 | 5 |
| FORK(A) → A′ | S=3, A=1, A′=1 | 5 |
| FORK(S) → B | S=2, A=1, A′=1, B=1 | 5 |
| FORK(B) → B′ | S=2, A=1, A′=1, B=1, B′=0 | 5 |
| `r = 1`: FORK(A) → A″ | A=1, A″=0 | only one branch holds the unit ✓ |

By induction on the number of splits, the sum of all lanes equals the
original `r` in every dimension, minus what was spent. **✓**

### 6.5 Fork race (brief §18)

Two FORK relations of the same source are two ESC transactions. Each appends
`LANE_SPLIT` entries by CAS on `account_revision`, and each reads the
source's remainder at that revision. The second transaction's CAS fails, so
it re-reads the already halved remainder and halves that. No duplicated
halves. **✓**

### 6.6 Double handover (brief §15)

Two RETRY relations name the same ended predecessor `P`:

- the first ESC transaction hands over `P`'s remainder and closes `P`'s
  lane;
- the second transaction serializes behind the first (CAS), and `P`'s lane
  is then closed with remainder 0.

The text supports "closed lane contributes 0" through three rules:

- derived counters are sums of ledger entries (§9.11);
- predecessor lanes "close in this transaction" (step 12);
- "a lane whose holder ended is otherwise never reused" (§9.11).

**Transferred once. ✓** Precision note: HR10-03.

### 6.7 Multi-predecessor continuation (brief §16)

§9.8 requires the Scheduler, when unsure, to "name all prior ESCs of the
task". So a CONTINUATION can name, for example, `{I, R, F1, F3}`, where
`I`'s lane was already handed to `R`.

- `I` contributes 0, because its lane is closed.
- `R`, `F1` and `F3` hold disjoint parts, from the handover and the splits.
- A predecessor that is still LIVE (for example `F2`) makes the relation
  wait, because every named predecessor must be ended.

The merged total is at most the original allowance, and overlapping lanes
are never summed twice. **✓** (Same precision note, HR10-03.)

### 6.8 Concurrent last unit (brief §11)

With disjoint lanes, the last capacity unit belongs to exactly one lane.
Take two LIVE ESCs `X` (lane remainder 1) and `Y` (lane remainder 0):

- `Y` is DENY by its own lane whatever `X` does;
- two concurrent requests **of `X`** compete under CAS, so exactly one
  commits and the other re-evaluates and is DENY;
- a failed transaction creates no pair, binding, TCR, account, reservation
  or issuance entry (§9.7 step 5).

No temporary over-commit and no orphan: the pair is the commit point and
every store is in one commit domain (§21.3). **✓**

(§34 row "Two ESCs of the same task compete for the last unit" and the
matching TST-CB-048 clause describe this loosely; HR10-03.)

### 6.9 Replay (brief §12)

T-7 step 0 checks `(parent_esc_id, proposal_ref)` first. It returns the
existing binding "before the counter step", so a replay creates no
proposal, issuance or reservation entry, no child account and no pair. A
replay under another parent ESC is DENY, because `proposal_ref` is unique
across all bindings.

**✓ for T-7.** The T-9 replay path is **not** ESC-scoped; see HR10-01.

---

## 7. Lane side-channel analysis (primary new falsification target)

### 7.1 T-7

Every T-7 limit reads only the caller's lane:

- `lane.p_max`;
- `lane.n_c`;
- `lane.capacity`;
- the per-lane window.

With correct lanes, the account-level backstop never binds. The proposal
counter is lane-private. So no T-7 outcome of `A` depends on a concurrently
LIVE `B`. The remaining effect of CAS contention is latency, which is inside
the accepted timing residual (§38.2). **✓**

### 7.2 T-9 — falsified

§9.11 ("Same-task state is not an inter-boundary channel") claims: "no T-7
or T-9 outcome of one depends on the other's acts". §38.2 claims: "no
channel between concurrently LIVE ESCs remains". The normative T-9 procedure
(§34 `request_model_revocation`) contradicts both claims in three places.

1. **Account-scoped replay key.** The procedure reads
   `if pending = pending_revocations.get(acct.id, request_ref): return pending`,
   and §9.11 says "(budget_account_id, request_ref) UNIQUE".

   The key is per account, not per requesting ESC. The design says only
   that `request_ref` is "harness-set". Take a natural harness that numbers
   requests per ESC, as T-7's own key `(parent_esc_id, proposal_ref)` is per
   ESC. Then fork `A`'s first T-9 collides with fork `B`'s first T-9, and:

   - `A` receives `B`'s record: `B`'s target, mode, exact `requested_at`
     (finer than a bucket), `requesting_esc_id` and slot;
   - `A`'s own request is silently not recorded.

2. **Account-wide values in the returned record.** `return p` hands the
   requester the record, including `termination_slot`, "the R_max slot
   (1..R_max) it consumed". That is an account-wide ordinal. With it, `A`
   learns how many termination acts other lanes have made. Store-generated
   `pending_revocation_id`s have the same problem if they are ordinal.
   §21.6 requires uniqueness only, and "Store-generated ids of revocations
   are assigned in the canonical application order".

3. **Family-wide target universe.** A class B target is valid if it "is a
   pair beneath acct.lineage_pair_id", and the target set is "the same for
   every ESC of `A`" (§9.11, §21.5). A pair that `B` creates by T-7 at time
   `t` is a valid target for `A` at once. It becomes descendant-visible
   only at `e(t)`. So for `A`:

   - a probe naming that pair is accepted after `t` and `CB_MALFORMED_REQUEST`
     before;
   - denied probes consume nothing (limited only by the §32 denied-request
     rate).

   §21.1 states that ids "are references, never credentials", so the design
   does not, and cannot, rely on pair ids being unguessable. If ids are
   ordinal, or leak through a §14.8 "opaque id" observable, `A` learns that
   and when `B` issued, at sub-bucket resolution and before any descendant
   can.

**Why this matters under different taints (brief §20).** A fork's genesis
is `⊒` the forked-from ESC's `H_exec` at the fork point. After that point
the two taints diverge. A high-taint `B` can therefore pass information to a
low-taint `A`, and `A` can emit it through ordinary low-taint outputs.

The `C_T7` table rows "Which ESC of the family acted — 0 additional" and
"Number of observers … another ESC of the same family — same `(target,
mode, bucket)` value" assume the sibling sees only the bucketed,
descendant-visible value. Items 1–3 give it more than that:

- exact times;
- values before `effective_at` or `e(t)`;
- account-wide counts.

These are outside the counted alphabet.

**Classification:** an unaccounted intra-family channel, introduced by the
r8 family model (a shared target universe and an account-scoped T-9 key).
It contradicts the design's explicit non-interference claims and the brief's
freeze criterion "lane system does not introduce an unaccounted information
channel". See **HR10-01**.

### 7.3 Lane allocation by taint (brief §20)

Allocation itself does not leak from high taint to low taint:

- a FORK's lane is a function of the forked-from's remainder, which the fork
  may know because it inherits that taint;
- the forked-from ESC's new remainder `⌈r/2⌉` is a function of its own
  state;
- a RETRY/CONTINUATION inherits its predecessors' remainders together with
  their final taint.

One gap remains. The text does not say what may **trigger** a FORK of a
LIVE ESC. T-10 inputs include "QA verdict as a closed enum", which is the
output of another execution's model. If a FORK of `A` can be triggered by
another execution, `A` sees its own lane halve at a time chosen elsewhere.
Before r8, a fork never changed the forked-from ESC's own budget. The signal
is bounded by `max_forks` and falls within the §14.8 "status and retry
choices" residual. It should still be stated. See **HR10-02** (LOW).

### 7.4 Task security identity (brief §21)

Treating all ESCs of one TCR as one delegation-control family is sound:

- they share the pair, profile, objective, account and delegator principal;
- the account holds only trusted control metadata: counts, amounts, ids and
  trusted times;
- "no model value is written to one" (§9.11).

What must not be shared is per-ESC **observation**. HR10-01 concerns
observation, not the shared accounting. **✓** for accounting.

---

## 8. Capacity proof

Claim: `created_descendant_pairs(A) ≤ descendant_capacity(A)` (§9.11).

1. **Structure.** Every pair beneath `A`'s lineage node comes from a T-7 by
   an ESC whose account is `A`, or by an ESC of a descendant task. T-8 only
   creates root pairs. Each T-7 creates exactly one pair and one account
   `C` with `parent_budget_account_id = A`. Two TCRs never share a pair:
   ROOT `root_lineage_pair_id` is UNIQUE, and each CHILD pair is new. So
   `created(A) = Σ_C (1 + created(C))`.
2. **Reservation.** The same transaction reserves `1 +
   template.child_subtree_budget` from `A`. That is at least `1 +
   capacity(C)`, because `capacity(C) = min(child_subtree_budget, child D_max,
   0 if no T7Policy)`. CAS gives `Σ_C reservation(C) ≤ capacity(A)`.
3. **Induction** on creation order (or on depth):
   `created(A) ≤ Σ (1 + capacity(C)) ≤ Σ reservation(C) ≤ capacity(A)`.
4. **Successors.** RETRY, CONTINUATION, FORK, crash, restart and replay
   create no pair and no account.

| Case | Result |
|---|---|
| Direct child | counted by its reservation |
| Grandchild, deeper | reserved from the child's account, whose capacity ≤ its reservation in the parent |
| Sibling children | reservations summed under CAS |
| Nested capacities | `min(budget, D_max)` never exceeds the reservation |

**The proof is valid.**

### 8.1 D_max example (brief §10)

Root `D_max = 4`; the task allows INITIAL, RETRY, CONTINUATION and FORK.

| Attempt | Outcome |
|---|---|
| `I` issues child `C1` (budget 3), reserving 4 | `I` capacity 0; F, R, C inherit 0 |
| Instead: FORK first (`I`: 2, `F`: 2); `I` issues a budget-1 child, `F` issues a budget-1 child | 2 children + ≤ 1 grandchild each = 4 |
| `C1`'s own retries and forks | share `C1`'s account (≤ 3) |
| Replay of any committed T-7 | returns binding, reserves 0 |

A fifth descendant pair is impossible. **✓** TST-CB-048 r8 has this fixture.

---

## 9. Channel proof

### 9.1 Formula (brief §25)

`C_T7(A) ≤ N_c·⌈log2(1+n_T·B)⌉ + R_max·⌈log2(1+3·(1+D_A)·B)⌉`, where
`B = ⌈H/g⌉+1`. HR9's proof of `B` is unchanged and still holds.

| Observable (descendant or destination) | Counted by |
|---|---|
| Issue / don't issue, template, bucket, count, order | issuance slots (`1 + n_T·B`), ordered |
| Interleaving of issuances from different lanes | the family's merged ordered sequence |
| Termination: target pair (own + ≤ `D_A`), mode (3), bucket | termination slots, ordered |
| Several acts on one target (e.g. AUTHORITY_HALF, then CLEARANCE_HALF, then WHOLE_PAIR) | each consumes a slot; all legal sequences included; redundant ones overcounted |
| Issuance vs termination order | not observable (boundary semantics; §9.11 row) |
| Child account allowances, reservation, child `horizon_start` | fixed by template/profile; scheduler-chosen start |
| Out-of-limits renunciation | no descendant-visible effect; ESC status is the §14.8 residual |
| Class A | outside the channel |

The ordered slot sequences give an injective map from descendant-visible
outcomes to slot vectors, and `log2 ∏ ≤ Σ ⌈log2⌉`. **The formula is a
conservative upper bound on descendant- and destination-visible outcomes
of the family.** Overcounting (for example cancelling a never-issued child)
is harmless.

It is **not** a bound on what a concurrently LIVE sibling of the same
family learns through the T-9 interface; see §7.2 and HR10-01.

### 9.2 Target alphabet (brief §23–§24)

- **Request fields.** `validate_exact` accepts exactly `(esc_id,
  request_ref, target_pair_id, mode)`. `esc_id` and `request_ref` are
  harness-set; model content never supplies them (§9.5 rule 2).
- **TCB-set fields.** The reason code, revoker role, times and effective
  time are all TCB-set (§9.11). Any extra field is `CB_MALFORMED_REQUEST`.
- **No selection syntax.** There is no descendant-selection syntax: one
  target pair per request.
- **Target count.** Targets are the own pair plus at most `D_A` descendants,
  so at most `3 · (1 + D_A)` values.
- **WHOLE_PAIR is one value.** It is one transaction revoking both edges
  and the pair, with a deterministic set of records and epoch increments.
  Its visible variants depend only on earlier class A acts or earlier
  counted acts, not on a model choice.

**✓**

### 9.3 Target-set evolution (brief §26)

The design uses `D_A`, and the policy store shows the value with `D_A =
D_max` for every termination slot (§9.11 "The policy store shows the value
with `D_A = D_max`"). Growth of the target universe over time is therefore
overcounted, not undercounted. **✓**

### 9.4 Actor non-disclosure (brief §28)

| Leak path | r8 |
|---|---|
| Audit | RESTRICTED/AUDIT only (§30.4); an auditor reading it is tainted accordingly |
| `parent_esc_id`, lane ids, `requesting_esc_id`, `request_ref`, pending ids, request order | declared TCB-internal (§9.11) |
| `TASK_INSTRUCTION` rendering | profile id, template, purpose, objective, type, scope, schema only (§14.9) |
| Revocation `revoked_at` | `= effective_at` (boundary-aligned) except the defect-only `late` path |
| Delegator / `revoked_by` | the family agent, identical for every ESC |
| Scheduler identity, network output | the scheduler emits nothing descendant-visible |
| Exact `issued_at` of the binding, pair and v0.2.5 edge | not rendered; §14.8 permits only coarse timestamps. Not listed in the §9.11 non-disclosure paragraph (see the HR10-01 correction) |

**Toward descendants: ✓.** Toward siblings of the family: ✗ (HR10-01).

### 9.5 Within-bucket order (brief §29)

Revocations are applied in `(effective_at, target_pair_id, mode)` order
(§34). `target_pair_id` is a store-generated id, not a model-chosen key, so
the order is a function of the set of acts. Issuance order within a bucket
is model-controlled, but the ordered issuance sequence already counts it.
**✓**

---

## 10. Pending T-9 (HR9-02)

### 10.1 The PendingModelRevocation object

| Property (brief §30) | r8 | Status |
|---|---|---|
| TCB-written | §9.11 | ✓ |
| Insert-once, append-only chain | "The record and each state entry are insert-once … hash-linked" | ✓ |
| Idempotent replay | `(budget_account_id, request_ref)` | ✓ for the same ESC; ✗ scope (HR10-01) |
| Immutable target, mode, `requested_at`, `effective_at`, T7Policy, account | record fields, insert-once | ✓ |
| Immutable slot | `termination_slot` field | ✓ (its account-wide ordinal: HR10-01) |
| States | `PENDING → COMMITTED_EFFECTIVE`; "`CANCELLED` does not exist"; class A overlap makes the later commit an idempotent duplicate, with no supersession state | ✓ |

### 10.2 Behaviour

- **Cannot cancel (brief §31).** No cancel, rewrite, delete or backward
  transition exists "for the model, the agent, the harness or any other
  caller". The record commits at `effective_at` even if a class A act
  intervened. **✓**
- **Replay (brief §32).** The same ESC replaying the same `request_ref`
  gets the same record: no second slot and no second timing event.
  Replay is checked before the CAS. **✓** (cross-ESC scope: HR10-01)
- **`effective_at` (brief §33).** `effective_at = (⌊now/g⌋ + 1)·g`.
  `now` is the trusted clock and `g` comes from the account's exact
  `T7Policy`. The model has no input to it. **✓**

### 10.3 Frozen `revoke()` (brief §34)

- `apply_due_model_revocations` calls the unchanged `revoke(…, now = t)`,
  with `t = effective_at` unless the high-water mark is already above it.
- `revoked_at = effective_at`.
- The epoch increments at that commit (§31 item 3).
- Cascade stays evaluation-time (v0.2.5 §11).
- No v0.2.5 / v0.2.5.1 type or rule is changed.

**✓**

### 10.4 Apply-before-advance barrier (brief §35)

v0.2.5 §10 defines the high-water mark as "the latest trusted time it has
recorded from **issuance, revocation or evaluation** events". The r8
barrier covers "every operation on the delegation, clearance or pair store
at trusted `now` (issuance, revocation or evaluation, including the v0.2.5
authority gate)". That is exactly the set of HWM-advancing events, so no
store path advances the mark past `effective_at` without first applying the
due records.

| Path | Covered |
|---|---|
| Owner T-8 root issuance, T-7 issuance | issuance ✓ |
| Class A revoke, orphan sweep | revocation ✓ |
| v0.2.5 authority gate, §34 step 3, ESC Issuer step 6, ancestor walk | evaluation ✓ |
| Several boundaries due at once (idle store) | applied in ascending `effective_at` (§34 ordering) ✓ |
| Restart | "Recovery … runs the same application before the stores accept any other operation" ✓ |

Residual precision: the pseudocode compares one
`store.clock_high_water_mark`, but three stores are written (HR10-05,
INFO). **The barrier is complete as specified.**

### 10.5 Crash at the bucket boundary (brief §36)

- Every v0.2.6 check at `≥ effective_at` treats `PENDING` as effective,
  whatever the scheduler state.
- Every store operation first applies due records.
- Recovery applies before any other store operation.
- The v0.2.6 gate is conjunctive with the v0.2.5 gate (§22).

No authorization window opens. **✓**

---

## 11. Self-renunciation outside limits

| Requirement (brief §37) | r8 (§9.11, §34) | Status |
|---|---|---|
| Distinct from lineage revocation | "not a delegation-store revocation"; no pending record, no slot, no epoch change | ✓ |
| Current ESC ends immediately | `end(esc, RENOUNCED_FOR_EXECUTION)` in one transaction | ✓ |
| No frozen `revoke()` | explicit | ✓ |
| No descendant pair state change | "Existing descendant LineagePairs are unchanged until their natural expiry" | ✓ |
| `LocalRenunciationRecord` blocks new ESCs | §9.3 step 12, "every later RETRY, CONTINUATION or FORK of that task (`ESC_LINEAGE_INVALID`)" | ✓ |

### 11.1 Already-LIVE siblings (brief §38)

The design is explicit: "Other already LIVE ESCs of the task are
unaffected."

- **Does sibling `B` continue?** Yes.
- **Can `B` issue T-7 or T-9?** Yes, from its own lane. The pair stays
  effective, so this is consistent.
- **Is `A`'s act observable to `B`?** Only through `A`'s ESC status
  (`RENOUNCED_FOR_EXECUTION`, coarse time), a §14.8 observable of the same
  class as finishing. The retry block is observable only as fewer later
  issuances, which the issuance slots already count.
- **Is an uncounted task-family control signal created?** No. The signal
  lies within the pre-existing §14.8 status residual.

No finding.

### 11.2 LocalRenunciationRecord (brief §39)

- The record is TCB-written and insert-once. No update or delete path
  exists, and model output never reaches it.
- **Scope:** the task's account, covering every new ESC of that task. It
  covers neither descendants nor LIVE siblings. **✓**

---

## 12. Frozen compatibility (HR9-03)

The new §39.1 row states every required point:

- the frozen `revoke()` stays immediate at commit, irreversible and
  idempotent;
- v0.2.6 changes only **when** it invokes the primitive for class B/C, or
  does not invoke it at all outside the limits;
- class A revocations invoke it immediately;
- the revoker set is not widened;
- the barrier is an additive v0.2.5.2 obligation (also §21.3);
- "**no contract amendment**".

Against v0.2.5 §10 the backdated `now = effective_at` is consistent. The
barrier guarantees that no store event is recorded between `effective_at`
and the application, so the mark is at most `effective_at`. The value is a
TCB-computed trusted time, never request-supplied. The `late` fallback
records actual time.

**HR9-03: RESOLVED_IN_R8.** No amendment needed.

---

## 13. HR9-04 policy lifecycle

| Requirement | r8 | Status |
|---|---|---|
| Exact refs (no mutable-id binding) | `ExecutionPolicyBindings` = exact `(kind, id, version, digest)` from insert-once ESC fields (§29.4) | ✓ |
| New TCR requires ACTIVE | §29.4 table; §9.7 step 3 "NEW task binding … must be ACTIVE" | ✓ |
| Existing task may use SUPERSEDED_BUT_STILL_VALID… | §9.3 step 4; §9.4 note; §29.4 | ✓ |
| REVOKED / EXPIRED fail closed | §29.4; §34 step 2 terminates on a foundational ref; `ESC_POLICY_OBJECT_INVALID` for new ESCs | ✓ |
| Foundational (TaskProfile/T7Policy, ApprovalClass, EnvironmentClass) → ESC TERMINATED at next decision | §29.4, §34 step 2 | ✓ |
| Capability (destination authorization, template) → capability removed | §29.4; §34 step 5 egress; T-7 step 3 | ✓ |
| T-7 re-read inside the commit transaction | §9.7 step 5 first clause | ✓ |

- **Brief §44 attack.** A template is valid at step 3, and the owner revokes
  it before step 5. The step-5 re-read sees `REVOKED`, so the transaction
  aborts and nothing exists.
- **If the policy store is outside the §21.3 commit domain.** A revocation
  committed after the re-read but before commit can still yield a child
  task. The child's `issue_esc` step 4 then refuses every ESC, because the
  template is a binding ref. So the outcome is still fail-closed.
- **Foundational vs capability.** The split is safe. A foundational object
  defines every decision, so terminating is the only coherent result. A
  capability object gates one sink or template, so removing that capability
  is sufficient and fail-closed.
- **Editorial inconsistency** for a child's own template (§29.4 "everything
  else continues" vs §9.7 step 1): HR10-04 (INFO, fail-closed direction).

**HR9-04: RESOLVED_IN_R8.**

---

## 14. INV-CB-048

It covers the whole T7ControlFamily bound:

- no fresh budgets for successors;
- every issuance and T-9 signal (target, three modes, bucket);
- actor non-disclosure **toward descendants**;
- template-fixed selectors;
- the capacity invariant;
- quantization and horizon;
- class A immediate;
- the formula with `D = D_max`, not multiplied per ESC.

It is complete for the descendant- and destination-visible channel it
governs. Intra-family (sibling) non-interference is INV-CB-106's property,
not this one.

**INV-CB-048: VALID.**

## 15. INV-CB-090

It covers:

- the insert-once `PendingModelRevocation`;
- the append-only chain with no cancel;
- replay;
- one slot per act;
- effective at `≥ effective_at`;
- `revoked_at = effective_at` with the barrier;
- late repair;
- the epoch at commit;
- class A immediate;
- the out-of-limits `RENOUNCED_FOR_EXECUTION` with the retry block.

Restart is covered through the barrier and "late application is repaired at
once" (TST-CB-090 has the restart case). The phrase "idempotent on its
request ref" inherits the account-scoped key that HR10-01 corrects.

**INV-CB-090: VALID** (wording depends on the HR10-01 correction).

## 16. INV-CB-093

It covers exact-version evaluation at every decision, delivery, T-7, T-9
and new ESC; ACTIVE for new bindings; SUPERSEDED… for existing ones; the
foundational/capability effects; and T-7 revalidation in the commit.

**INV-CB-093: VALID.**

## 17. INV-CB-106

| Required coverage (brief §48) | Present |
|---|---|
| Proposal identity / replay | ✓ |
| Shared budget account | ✓ one per TCR |
| T-10 account inheritance | ✓ |
| No fresh budget | ✓ |
| Account / lane isolation | **T-7 only.** "no T-7 outcome of an ESC depends on … a concurrently LIVE ESC's issuances or denials". The T-9 half of lane isolation, which §9.11 and §38.2 claim, is neither stated here nor true of §34 (HR10-01) |
| Atomic accounting | ✓ CAS; no over-commit |

**INV-CB-106: INCOMPLETE** (HR10-01).

---

## 18. LineagePair regression

The r8 changes that touch the lineage:

- account fields in the TCR and binding;
- the child-account insert in T-7 step 5;
- lifecycle checks in `issue_esc` step 4 and T-7 steps 1, 3 and 5;
- the class C pending check in `issue_esc` step 12;
- `WHOLE_PAIR` through `lineage_pairs.revoke`;
- `revoked_at = effective_at`.

Unchanged:

- no pair search;
- parent-bound pairs;
- the leaf-parent checks;
- `pair.issuer_event == deb.issuance_event`;
- leaf uniqueness;
- the approval digest;
- the ancestor walk;
- rule 5.

T-9 class B targets (pairs beneath the account) are within the v0.2.5
"delegator or ancestor delegator" set, because the family's agent is the
delegator of every pair its ESCs issued. No path binds, shops or revives a
pair. Every r8 addition is a further conjunct or a further DENY.

`LINEAGEPAIR R8 REGRESSION-FREE`

---

## 19. Read-confinement regression

r8 made no edit to §16–§18 (search above). The following still stand:

- the §17.9 normative rule `unknown actual readable universe = DENY`;
- `deliver()` `if ars is None → DENY(CB_READ_SET_INCOMPLETE)`;
- no owner-ceiling fallback (§34 comment, TST-CB-097);
- the GitReadClosure (§17.11);
- Level 2R (§6.5);
- the ConfinementRecord checks in `complete_tool_invocation()` and
  `ingest_tool_result()`.

**Regression-free.**

## 20. Activation regression

`valid(a, t)` (§40.F) still requires only `current_epoch ≥
monotonic_epoch_at_approval` (a rollback floor). The "Not a conjunct (r7)"
paragraph keeps the global SecurityPolicyVersion out of the predicate.

r8's policy-lifecycle checks are ESC-scoped (§29.4) and never touch an
IntegrationActivation. The r8 epoch increment for class B/C happens at
`effective_at` and still "revokes nothing by itself" (§31 item 3). Exact
ActivationPolicyBindings remain the rule.

**Regression-free.**

## 21. Network-taint regression

The HR8-03 corrections are intact in `deliver()` and
`complete_tool_invocation()`:

- persisted `L_net_max`;
- `reserved(esc)` in every ceiling check;
- the TNL records written before any byte;
- accounting-first transaction 1 for every outcome;
- the `L_net_max` fallback;
- the join against the latest `H_exec`.

HR9-06 is recorded in §38.2 without change.

**Regression-free.**

---

## 22. Invariant / test accounting

Counted mechanically from §33 and §36:

- **§33:** 106 `INV-CB-NNN` rows, IDs 001–106, no gaps, no duplicates.
- **Active:** 105. Only INV-CB-030 is `**withdrawn**`.
- **New IDs:** none.
- **"rev r8" rows:** exactly 048, 090, 093, 106. This matches §0.9 and the
  §33 totals paragraph.
- **§36:** 105 `TST-CB-NNN` definition rows, lines 5985–6089, all inside
  §36. The file contains no other definition row and no duplicates.
- **Mapping:** the set difference between active invariant IDs and test IDs
  is empty, so there is exactly one test per active invariant. TST-CB-023
  carries `023(+030)`.

| Test | Reflects final r8 semantics | Gap |
|---|---|---|
| TST-CB-048 | ✓ D_max = 4 retry/fork/continuation attack, horizon not reset, three modes, `3·(1+D_max)`, actor non-disclosure to descendants | "Concurrent last unit" wording (HR10-03) |
| TST-CB-090 | ✓ pending record, no cancel, replay, frozen commit timing, barrier, late, class A overlap, out-of-limits then retry | no cross-ESC `request_ref` case (HR10-01) |
| TST-CB-093 | ✓ foundational / capability, commit-time revalidation, RETAIN, no newer-id read | — |
| TST-CB-106 | ✓ account inheritance, replay, cross-task use, sibling T-7 probe | sibling probe is T-7 only; no fork-vs-forked-from **T-9** probe (target existence, replay key, returned slot) (HR10-01) |

---

## 23. Dependency graphs

- **Build graph (§40.E).** r8 added no edge. Every edge still points to a
  strictly lower tier:
  - CR-TASK-01 (T5) ← CR-LIN-01 (T4);
  - CR-ESC-01 (T6) ← CR-TASK-01, CR-LIN-01.
- **Activation graph.** Unchanged; acyclic.
- **GATE-CONTAIN.** Unchanged; cycle-free.
- **HR9-05.** CR-LIN-01 is now "only this store and applier". Stopping the
  renouncer and blocking the task are CR-ESC-01's. **RESOLVED_IN_R8.**
- **Hidden-dependency hygiene (INFO, HR10-06), no cycle:**
  - CR-TASK-01's scope names "T-10 lane handover / fork split", but lanes
    are keyed by ESC ids and written in the ESC transaction (CR-ESC-01, T6);
  - the CR-LIN-01 `PendingModelRevocation` record references account and
    lane ids owned by CR-TASK-01 (T5).

**Both graphs acyclic.**

---

## 24. Owner decisions

These remain genuine policy choices once HR10-01 and HR10-02 are corrected.
None is decided here.

1. `T7Policy` values (`N_c`, `P_max`, `n_T`, `g`, `H`, `R_max`, `D_max`),
   template contents, each template's `child_subtree_budget`, and
   acceptance of the stated per-task bound.
2. The ApprovalRequirement vocabulary and each class's requirement set.
3. Each component's `policy_dependencies`, and `RETAIN_…` vs `INVALIDATE_…`
   for each successor version.
4. The CR classification from the §40.F procedure, with CR-NET-01's
   `InternalEndpointPolicy` recorded under a gated mode.
5. The earlier dispositions listed in §44.5.

**Not owner decisions** (technical rules still undefined, see §25):

- the scope of the T-9 idempotency key and of the requester-visible T-9
  response;
- the T-9 target-validity rule for pairs created by a concurrently LIVE
  lane;
- what may trigger a FORK of a LIVE ESC.

---

## 25. New HR10 findings

### HR10-01 — The T-9 path is account-scoped where lane non-interference requires ESC scope

- **Severity:** MEDIUM
- **Category:** NEW (r8 text; family model)
- **Section:** §34 `request_model_revocation`; §9.11 `PendingModelRevocation`
  (`request_ref`, `termination_slot`), "T-9 target vocabulary" ("the same
  for every ESC of `A`"), "Same-task state is not an inter-boundary
  channel", non-disclosure paragraph; §21.5 timing row; §21.6; §38.2
  "T-7 shared quotas"; §9.11 channel table rows "Which ESC … acted" and
  "Number of observers"
- **Invariant:** INV-CB-106 (lane isolation), INV-CB-090 ("idempotent on its
  request ref"), INV-CB-048 (non-disclosure)
- **Attack / contradiction:** Setup: fork `B` (high taint after a
  post-fork read) and its forked-from `A` (low taint) are concurrently LIVE
  in account `Acct`.
  1. `B` issues T-9 with harness `request_ref = r`. `A` later issues T-9
     with the same `r`. Nothing in the design prevents this; a per-ESC
     request counter is enough. `pending_revocations.get(Acct, r)` returns
     `B`'s record to `A`. `A` learns `B`'s target, mode, exact
     `requested_at` and slot, and `A`'s own request is dropped.
  2. Every accepted `A` request returns `p` with the account-wide
     `termination_slot` (and possibly ordinal pending ids). This discloses
     how many termination acts `B`'s lane has made.
  3. `B` issues a child at `t`. Before `e(t)`, `A` probes T-9 on candidate
     pair ids. A target is valid iff it "is a pair beneath
     `acct.lineage_pair_id`", so the answer flips from
     `CB_MALFORMED_REQUEST` to accepted exactly when `B` issued. Denied
     probes consume nothing. The design disclaims id secrecy (§21.1,
     "never credentials") and requires only uniqueness (§21.6), so it cannot
     rely on unguessable ids.

  §9.11 claims "no T-7 or T-9 outcome of one depends on the other's acts".
  §38.2 claims "no channel between concurrently LIVE ESCs remains". The
  normative procedure contradicts both.
- **Impact:** an intra-family channel from a high-taint ESC to a
  concurrently LIVE low-taint ESC. It carries exact times, values before the
  effect, and account-wide counts, none of which is inside the counted
  `(target, mode, bucket)` alphabet. The low-taint ESC can then emit this
  information through ordinary low-taint outputs.

  The size is bounded, of the order of the §38.2 timing residual. The
  accepted statement shown to the owner is nevertheless false, and item 1
  also silently drops a voluntary reduction. This is the property HR9 §11
  warned a shared ledger must not reopen, and it fails the brief's freeze
  criterion "lane system does not introduce an unaccounted information
  channel".
- **Correction** (options for the design author; narrow text change):
  1. Key T-9 idempotency on `(requesting_esc_id, request_ref)`, as T-7 does
     with `(parent_esc_id, proposal_ref)`. A `request_ref` that matches
     another ESC's record is a fresh request, never a replay.
  2. Make the requester-visible T-9 result a closed acknowledgement that
     depends only on the requester's lane and inputs: a lane-relative slot
     (or none), and no other ESC's ids or times. Require every id that is
     rendered to a model or descendant to be opaque and non-ordinal (§14.8
     "opaque ids"; §21.6).
  3. Define class B target validity so it does not depend on
     not-yet-visible acts of another LIVE lane. For example, a valid target
     is a pair already descendant-visible (`now ≥ e(issued_at)`) or issued
     by the requester's own holder chain. Any other id gets the same
     `CB_MALFORMED_REQUEST` whether it exists or not.
  4. Add exact `issued_at` / `requested_at` / `committed_at` values to the
     §9.11 non-disclosure list (they are already excluded by §14.8's
     "coarse timestamps"; state it).
  5. Extend INV-CB-106 to T-9 lane isolation, align INV-CB-090's replay
     wording, and correct §38.2.
  6. Add to TST-CB-106 / TST-CB-090 a fork-vs-forked-from T-9 probe that
     varies the other lane's T-7 and T-9 acts, colliding `request_ref`s and
     pair-id probing. The expected result is identical outcomes.
- **Freeze blocker:** YES. The design's explicit non-interference claims are
  contradicted by its normative procedure on the primary new r8 mechanism.
- **Implementation blocker:** YES (CR-ESC-01, CR-LIN-01, CR-TASK-01)
- **Deployment blocker:** NO

### HR10-02 — The FORK trigger for a LIVE ESC is unspecified, so another execution can move its lane

- **Severity:** LOW
- **Category:** NEW (r8 lane split interacting with pre-existing T-10 inputs)
- **Section:** §7.3 T-10 ("QA verdict as a closed enum"); §9.8 FORK row;
  §9.3 step 12; §9.11 "Lanes"
- **Invariant:** INV-CB-106, INV-CB-048
- **Attack / contradiction:** r8 halves the **forked-from** ESC's LIVE lane
  at every FORK. Before r8, a fork never changed the forked-from ESC's own
  budget. The design does not say what may trigger a FORK of a LIVE ESC. If
  another execution's model output (for example a QA verdict) can cause
  one, the forked-from ESC observes its own lane halve, through a T-7 or
  T-9 DENY, at a time chosen elsewhere.
- **Impact:** at most `max_forks` events of bounded information, within the
  §14.8 "status and retry choices" residual. The design's claim "a local
  lane changes only through its own acts and trusted control flow" is
  unstated for this trigger.
- **Correction:** state that a FORK of a LIVE ESC is triggered only by that
  ESC's own closed outcome or by trusted non-model scheduler policy. Or fix
  each ESC's fork allotment when its lane opens, so later forks do not
  change the forked-from ESC's spendable lane. Or record the signal as part
  of the §14.8 residual.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-TASK-01, CR-ESC-01)
- **Deployment blocker:** NO

### HR10-03 — Lane handover and "last unit" wording

- **Severity:** INFO
- **Category:** EDITORIAL
- **Section:** §9.3 step 12; §9.11 "Lanes"; §34 row "Two ESCs of the same
  task compete for the last unit"; TST-CB-048 "Concurrent last unit"
- **Invariant:** INV-CB-106
- **Attack / contradiction:** the text implies, but never states, that a
  closed or handed-over lane has remainder 0 and that a later handover from
  it transfers nothing. This matters because §9.8 requires naming all prior
  ESCs when the Scheduler is unsure. The "compete for the last unit" row
  reads as though two lanes could contend for one unit. Under disjoint lanes
  only one lane holds it, and the other ESC is DENY by its own lane.
- **Impact:** none if implemented as a ledger. Without the explicit rule, an
  implementation could double-hand-over a lane. The account-level check
  still prevents over-commit, but the double handover would make the
  account-level check bind, and that is an inter-ESC dependence.
- **Correction:** state "a closed lane's remainder is 0; a LANE_HANDOVER
  from a closed lane transfers nothing; the account-level checks are a
  backstop that never binds while lanes are correct". Reword the §34 row
  and the TST-CB-048 clause.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR10-04 — A child's own revoked template: §29.4 vs §9.7 step 1

- **Severity:** INFO
- **Category:** EDITORIAL (fail-closed direction)
- **Section:** §29.4 capability bullet; §9.7 step 1
- **Invariant:** INV-CB-093
- **Attack / contradiction:** §29.4 says revoking "the template the ESC's
  own child binding came from" removes only that capability and "everything
  else continues". §9.7 step 1 requires every ref in
  `ExecutionPolicyBindings(parent)`, including "its own template if it is a
  child", to be valid for **any** T-7. So such a child can issue no child
  at all.
- **Impact:** none for security; the stricter rule wins.
- **Correction:** align the two texts.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR10-05 — The late-application test names one high-water mark for three stores

- **Severity:** INFO
- **Category:** PRECISION
- **Section:** §34 `apply_due_model_revocations`
- **Invariant:** INV-CB-090
- **Attack / contradiction:** `t = p.effective_at if
  store.clock_high_water_mark ≤ p.effective_at else now` writes the
  delegation, clearance and pair stores with a single `t`.
- **Impact:** none while the barrier covers all three stores. It is
  ambiguous if their marks differ.
- **Correction:** use the maximum of the three stores' marks, or state that
  they share one mark in the common commit domain.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR10-06 — Lane operations are attributed to CR-TASK-01

- **Severity:** INFO
- **Category:** EDITORIAL (DAG hygiene)
- **Section:** §40.B CR-TASK-01, CR-LIN-01, CR-ESC-01; §40.E
- **Invariant:** —
- **Attack / contradiction:**
  - CR-TASK-01 (T5) lists "T-10 lane handover / fork split". These run in
    the ESC transaction and need ESC state (CR-ESC-01, T6).
  - The CR-LIN-01 (T4) pending record references account and lane ids from
    CR-TASK-01.
- **Impact:** none; no edge and no cycle. It is the same kind of item as
  HR9-05.
- **Correction:** state that CR-TASK-01 provides the account store and
  ledger primitives, and that CR-ESC-01 performs lane opening, handover and
  split. State that the pending store holds opaque ids without a
  cross-store constraint.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 1 (HR10-01) · LOW 1 (HR10-02) ·
INFO 4 (HR10-03..06) · total 6.

---

## 26. Freeze blockers

| ID | Why it blocks freeze |
|---|---|
| **HR10-01** | r8's lane model is claimed to make concurrently LIVE ESCs of a task non-interfering for T-7 **and T-9** (§9.11, §38.2). The normative T-9 procedure is account-scoped in its replay key, its returned record and its target-validity rule. That creates an unaccounted intra-family channel, and INV-CB-106 is INCOMPLETE |

**Freeze-standard scorecard (brief §58)**

| Criterion | Status |
|---|---|
| No CRITICAL blocker | ✓ |
| No HIGH blocker | ✓ |
| No freeze-blocking MEDIUM | ✗ (HR10-01) |
| HR9-01 RESOLVED_IN_R8 | ✓ |
| D bound holds across all executions | ✓ |
| Lane system cannot duplicate budget | ✓ (account backstop; exact splits; single handover) |
| Lane system introduces no unaccounted information channel | ✗ (HR10-01; HR10-02 LOW) |
| Whole-pair target counted | ✓ |
| Channel formula a true upper bound | ✓ for descendant/destination observers |
| Pending T-9 semantics deterministic | ✓ except the replay-key scope (HR10-01) |
| Delayed commit frozen-compatible | ✓ |
| Policy lifecycle coherent | ✓ |
| LineagePair regression-free | ✓ |
| Read confinement regression-free | ✓ |
| Activation regression-free | ✓ |
| No frozen-contract amendment | ✓ |

## 27. Implementation blockers (separate from freeze)

Every §43.1 row remains, including the r8 row: no account store, lanes, CAS
ledger, pending store or barrier. None of that machinery exists.

In addition:

- HR10-01 (CR-ESC-01, CR-LIN-01, CR-TASK-01);
- HR10-02 (CR-TASK-01, CR-ESC-01).

## 28. Deployment blockers (separate)

Every §43.2 row, unchanged. The live defects (R-01..R-09, R-11, R-13,
R-22..R-26, R-29, R-30) are not fixed by any design revision. No HR10
finding adds a deployment blocker.

## 29. Frozen-contract compatibility

| Contract | r8 impact | Amendment needed? |
|---|---|---|
| v0.2 | strengthening only | No |
| v0.2.3 | router default never relied on | No |
| v0.2.4 | identifiers unchanged | No |
| v0.2.5 | `revoke()` unchanged; the invocation timing for class B/C is a usage restriction (§39.1 row); the barrier is an additive v0.2.5.2 obligation consistent with §10's high-water mark | No |
| v0.2.5.1 | types unchanged | No |

**No amendment to any frozen v0.2.x contract is required.** AMD-025-01
remains uncreated and unnecessary. HR10-01's correction is v0.2.6-internal.

## 30. Final status

r8 fixes what HR9 required:

- **One account per task.** There is exactly one `DelegationBudgetAccount`
  per task, created only by T-8 or T-7 and inherited exactly by every ESC.
- **Capacity bound.** The descendant-pair bound holds across retries,
  continuations, forks, crashes and replays, by a valid induction.
- **Target modes.** `WHOLE_PAIR` is counted.
- **Channel formula.** It is a true per-family upper bound for descendant
  and destination observers.
- **Pending revocations.** Their lifecycle is append-only and
  non-cancellable, with frozen-compatible commit timing and a complete
  barrier.
- **Out-of-limits renunciation.** It is local and fully specified,
  including for LIVE siblings.
- **Policy lifecycle.** It is exact and fails closed.
- **Frozen compatibility.** It is documented in §39.1.
- **Regressions.** LineagePair, read confinement, activation and network
  taint show none.

One MEDIUM defect prevents READY. The lanes make T-7 non-interfering, but
the r8 T-9 path is account-scoped in three places:

- its idempotency key;
- the record it returns;
- its family-wide target-validity check.

A LIVE sibling can therefore observe another LIVE ESC's revocation or
issuance acts outside the counted alphabet, contrary to the design's own
§9.11 and §38.2 claims. The correction is a narrow text change. A focused
verification of that delta, together with HR10-02, should suffice.

```text
R8 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

READY would have meant only that the technical review passed. It would not
have meant frozen, implementation-authorized, deployed or production-secure.

> No v0.2.6 production implementation has been authorized or created.

---

## Appendix A — Read-only validation

Run from `C:\Users\Gyuro\jarvis-os` with `.venv/Scripts/python.exe`, before
this file was written.

| Command | Result |
|---|---|
| `python scripts/check_v013_freeze_baseline.py` | exit 0 — `v0.1.3 FREEZE BASELINE CHECK: OK` (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `python scripts/check_v020_contract.py` | exit 0 — `v0.2.0 CONTRACT CHECK: OK` |
| `python scripts/check_v023_router_contract.py` | exit 0 — `v0.2.3 ROUTER CONTRACT CHECK: OK` |
| `python scripts/check_v024_agent_contract.py` | exit 0 — `v0.2.4 AGENT CONTRACT CHECK: OK` |
| `python scripts/check_v025_design_contract.py` | exit 1 — `DISCREPANCY FOUND`, solely 9 × "file outside the v0.2.5.1 allowlist is new/modified" for the nine untracked v0.2.6 documents (expected) |
| `python -m pytest -q -p no:cacheprovider` | **1 failed, 2234 passed, 1 warning** (426.8 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`: the same v0.2.5 allowlist discrepancy for the nine untracked v0.2.6 documents. Matches the HR7–HR9 baseline |

No validator, test or configuration was modified.

## Appendix B — Integrity

Re-verified at the end of the review (see the terminal report): the design
and HR2–HR9 are unchanged from the §2 hashes; HEAD is unchanged; there are
no tracked changes; the only new file is this HR10 document. No commit, push
or merge was made.
