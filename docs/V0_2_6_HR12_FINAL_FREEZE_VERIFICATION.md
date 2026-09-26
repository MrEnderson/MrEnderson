# Jarvis OS v0.2.6 — HR12 Final Freeze Verification of Design Revision r10

```text
subject                        = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r10)
subject status on entry        = CORRECTED R10 — PENDING HR12 FINAL FREEZE VERIFICATION
controlling prior review       = HR11 (docs/V0_2_6_HR11_FINAL_FREEZE_VERIFICATION.md)
review type                    = independent technical freeze verification (read-only)
review date                    = 2026-09-26
design_modified                = false
hr2_to_hr11_modified           = false
code_tests_validators_modified = false
opendex_modified               = false
final_status                   = R10 DESIGN READY FOR OWNER FREEZE DECISION
```

Section numbers (§N) refer to the r10 design unless another document is
named. Line numbers refer to the r10 file as hashed in §2. Finding IDs
`HR12-NN` are new to this review.

---

## 1. Independence

This session authored **none** of:

- design revisions r1–r10;
- HR2, HR3, HR4, HR5, HR6, HR7, HR8, HR9, HR10 or HR11.

It started with no conversation history and worked only from repository
contents. The design's §0.11 authorship note requires that HR12 come from a
session that did not author r10. This session meets that condition.

The r10 correction record (§0.11), its "corrected" wording and the §44.5
sentence "No known freeze-blocking MEDIUM issues after r10" were **not**
treated as evidence. Conclusions come from the r10 normative text (§5, §7.3,
§9.3 step 12, §9.4, §9.8, §9.11, §14.4–§14.5, §21.3 rule 5, §32, §33, §34,
§35.2, §36, §37 item 56, §38.2, §39.1, §40.B, §40.E), the frozen v0.2.5 text
(§10, §11) and HR11.

**Limitation.** This review uses the same model family as HR2–HR11. It is
session-independent, not organizationally independent. The design's own
recommendation (§38.2, §44.5) of a human security review before freeze still
applies, and is listed as an owner decision in §25.

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
| Untracked (`git status --short -uall`) | exactly eleven v0.2.6 documents: the design and HR2–HR11 |

This matches the expected state.

**SHA-256 at start of review**

| File | Role | SHA-256 |
|---|---|---|
| `docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md` | r10 design (8397 lines) | `f934f3ec91365a63c6e27a9dcf1d17d08083866ff704bda3d9def0918d38e0b4` |
| `docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` | HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| `docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md` | HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| `docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |
| `docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` |
| `docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md` | HR6 | `42b170a580dba800fa310735c4ca0267083aa2beab0fb033fbebeeb289b4f07e` |
| `docs/V0_2_6_HR7_FINAL_FREEZE_VERIFICATION.md` | HR7 | `91e8d19eec8e98f38e7203b1f58d5181c2f25329c094de32fef53575fcecad64` |
| `docs/V0_2_6_HR8_FREEZE_VERIFICATION.md` | HR8 | `9848284e796f548b0012aa509de3b7a4cc3480f9fa5bad437020abf3d1b9aee7` |
| `docs/V0_2_6_HR9_FREEZE_VERIFICATION.md` | HR9 | `e8fcf9a2eb2598910b08c4cb64bc2c9d87c02ead5304743f6fb1c05f6ed73d15` |
| `docs/V0_2_6_HR10_FINAL_FREEZE_VERIFICATION.md` | HR10 | `a29b3e505313bab315c2f97ef780237cd401c5b844a1fc45848fad7f192c31a8` |
| `docs/V0_2_6_HR11_FINAL_FREEZE_VERIFICATION.md` | HR11 | `1ba2b13a59bad759de0de5029c9cd8fc800d957c3cc981f9538fd2757ee553eb` |

The HR2–HR10 hashes equal the values HR11 recorded, so those files have not
changed since HR11. The design hash differs from HR11's r9 hash
(`b8edcd6f…`), as expected for r10.

**OpenDex** (`C:\Users\Gyuro\opendex-reference`): HEAD
`3e898343d1127c8d5075b459acdd55da83b83f04`, the value in design §41.
`git status --short` is empty. No OpenDex file was opened or modified.

---

## 3. Materials

- **r10 design**, read directly (not through any terminal summary):
  - header, §0.9–§0.11 (all rows and the r10 supersession note, lines
    537–544), §5 terminology;
  - §7.3 T-7 to T-10 rows;
  - §9.2, §9.3 (all of `issue_esc`, lines 1246–1406), §9.4, §9.5, §9.6,
    §9.7 (all of `issue_child_delegation`), §9.8 (all), §9.11 (all, lines
    2036–2751);
  - §14.3–§14.8, §21.3 rule 5, §21.5 revoker table, §30.1 revocation / lane
    rows, §32, §33 (full table and totals), §34 `request_model_revocation`,
    `retire_lane`, `apply_due_model_revocations` and the explicit-behaviours
    table, §35.2, §36 (rows 048, 090, 106 in full and the closing
    cross-reference rows), §37 item 56, §38.2, §39.1 revocation row, §40.B
    (CR-POL-01, CR-LIN-01, CR-TASK-01, CR-ESC-01), §40.E (both graphs),
    §43.1 r10 row, §44.5, §44.13, §45 and the authorization block.
  - A line search for `r10` / `HR11` located every r10 edit (none in §16–§18,
    §40.F or the network-taint text).
- **HR11**, read in full. HR10 and HR9 were consulted through HR11 and
  design §0.9–§0.11; no regression question needed more.
- **Frozen v0.2.5** (`docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md`):
  §10 store high-water mark (line 671); §11 revoker set, "the delegate may
  renounce its own edge" (line 687) and "Effect: immediate at commit;
  irreversible; idempotent" (line 692).
- **Mechanical checks:** invariant/test accounting and build-graph tier
  ordering, by script over the r10 file (§22, §23).

---

## 4. HR11-01 — local renunciation scope (primary gate)

### 4.1 What the r10 text says

| Location | r10 normative text | Scope |
|---|---|---|
| §9.3 step 12, lines 1341–1359 | "the ESC Issuer NEVER asks 'does this task/account have a LocalRenunciationRecord?' … Only the new ESC's OWN trusted chain predecessors (RETRY/CONTINUATION) or its own source (FORK) are examined, by id"; lookup "by c's trusted id only"; "taint-only predecessors … renunciation records are NOT read"; "unrelated siblings' LocalRenunciationRecords and not-yet-effective PendingModelRevocations: ignored" | chain-local |
| §9.11 `LocalRenunciationRecord`, lines 2182–2194 | account / TCR / pair fields are "provenance only: never a lookup key for any decision about another ESC, and never read task-wide or account-wide"; "read ONLY (a) by the replay lookup of the same requester and (b) by the ESC Issuer for a successor whose own chain predecessor is renouncing_esc_id" | requester-local |
| §9.11 `RenouncedExecutionChain`, lines 2196–2200 | refused "iff the root is one of its chain_predecessor_esc_ids … An unrelated sibling branch is never affected" | chain-local |
| §9.11 item 8, lines 2309–2317 | never changes a LIVE sibling's execution, T-7, T-9, FORK, RETRY or CONTINUATION eligibility, lane allowance or handles | normative isolation claim |
| §9.11 out-of-limits bullet, lines 2605–2632 | r8/r9 task-wide rule "is withdrawn"; "not a pair, edge, delegation-store or task-wide revocation" | chain-local |
| §34 lines 6468–6478 | out-of-limits branch writes the record, ends the ESC, `retire_lane(lane)`; "no other ESC's state, eligibility or lane changes" | requester-local |
| §35.2, lines 6653–6658 | "another ESC's renunciation or pending record is never a reason for any code" | — |
| §37 item 56 | forbids task-wide / account-wide reading in any ESC Issuer, Scheduler, T-7, T-9 or FORK decision | — |

The record is **not** interpreted as a pair, edge, task-wide or account-wide
revocation anywhere in the current normative text (§11 below lists the
remaining historical phrasings, all marked superseded).

### 4.2 Verdict

**HR11-01: RESOLVED_IN_R10.** Both HR11 defects are removed, not merely
re-described: the account-wide `LocalRenunciationRecord` test and the
"(effective or not)" pending-record test are deleted from §9.3 step 12, and
the renouncer's own lane is now closed (HR11 §10.6 gap). The one residual
concern — multi-chain merges — is unreachable under the r10 schema and is
recorded as HR12-01 (LOW), §7.

---

## 5. Local renunciation: A/B attack (brief §6–§11)

Setup: task `T`, concurrently LIVE ESCs `A` and `B` with disjoint lanes.

### 5.1 Core A/B (brief §6)

`A` sends T-9 `(SELF, mode)` outside the limits (after `H`, or with lane
termination remainder 0 — e.g. any FORK lane when `R_max = 1`).

| Expected | r10 path | Result |
|---|---|---|
| `A` → `RENOUNCED_FOR_EXECUTION` | §34 `end(esc, RENOUNCED_FOR_EXECUTION)` in the same transaction as the record | ✓ |
| `A`'s lane CLOSED / retired | `retire_lane(lane)`: `LANE_CLOSE` ledger entry with `ref = RENOUNCED`, `CLOSED(close_reason = RENOUNCED)`, CAS on `account_revision` | ✓ |
| `A` cannot T-7 / T-9 / FORK | T-7 step 1 and T-9 `request_context` step 0 require LIVE; FORK requires a LIVE source (§9.3 step 12) | ✓ |
| `B` LIVE; lane, handles unchanged | `retire_lane` touches only `lane.lane_id` and handles `owned_by(lane.lane_id)`; no `LANE_HANDOVER` / `LANE_SPLIT` written | ✓ |
| `B`'s T-7 unchanged | T-7 step 0 reads only `B`'s lane; no step reads a renunciation record | ✓ |
| `B`'s T-9 unchanged | `request_model_revocation` reads only `B`'s lane, handles and own pair; replay key is `(B.esc_id, request_ref)` | ✓ |
| `B`'s FORK unchanged | FORK check reads only the source's state, trigger, lane; sibling records "never read" | ✓ |
| `B` ends; its RETRY / CONTINUATION allowed | Scheduler writes `chain_predecessor_esc_ids = {B}`; ESC Issuer looks up records only for `B` | ✓ |
| `A`'s record not consulted | read only for "a successor whose own chain predecessor is renouncing_esc_id" | ✓ |

The ESC Issuer's decision about `B`'s successor is a function of `B`'s own
end, `B`'s lane, the pair's effectiveness at `now`, trusted policy and class
A state. It is not a function of `A`'s record.

One precision point (HR12-04, INFO): if the Scheduler names `A` as a
*taint-only* predecessor of `B`'s successor (the §9.8 conservative
default), the successor must wait for `A` to have ended with a final
`H_exec` (§9.11 "Lanes", §14.4). The comparison "decided exactly as if the
renunciation had not happened" therefore holds against the counterfactual
in which `A` ends by other means at the same instant. `A`'s end time is
`A`'s own §14.8 status/timing residual, which §38.2 (b) already names. The
renunciation adds nothing to it.

### 5.2 Renouncer successor (brief §7)

| Attempt | Path | Result |
|---|---|---|
| RETRY with `A` as chain predecessor | §9.3 step 12: `LocalRenunciationRecord` with `renouncing_esc_id = A` → `DENY(ESC_LINEAGE_INVALID)`; also no OPEN chain lane (`A`'s lane CLOSED) | DENY ✓ |
| CONTINUATION with `A` as chain predecessor | same | DENY ✓ |
| Basis of denial | lookup "by c's trusted id only", for `c ∈ rel.chain_predecessor_esc_ids`; no task / account test exists | chain-derived ✓ |

The Scheduler also receives `own chain terminal = true` in
`ExecutionControlFacts(A)` and does not write the relation in normal
operation (§9.8, lines 1842–1844). The ESC Issuer check is the backstop.

### 5.3 Fork then renounce (brief §8)

`A` forks `B` (a valid `ForkAuthorization`); `B` gets `⌊r/2⌋` of each
remainder of `A`'s lane and no pre-existing handle. `A` then renounces out
of limits.

- `A` ends and `A`'s remaining `⌈r/2⌉` shares are retired, with no entry
  moving anything to `B` (`retire_lane`; §9.3 step 12 line 1390 "no lane
  ever receives any part of a retired (renounced) lane").
- `B`'s lane record is not touched: its numerical lane and its handles (only
  children `B` issued itself) do not change.
- `B`'s later RETRY / CONTINUATION has chain predecessor `B` only and is
  decided normally.
- TST-CB-090 case F and TST-CB-106 "No allowance redistribution" require
  this, compared across runs.

**✓**

### 5.4 Renounce then fork (brief §9)

- `A` renounces before any FORK commits. §9.3 step 12 FORK requires the
  source LIVE and its lane OPEN with fork remainder ≥ 1; both fail.
- A stale `ForkAuthorization` (SOURCE_ESC marker, checkpoint or owner event
  read before the renunciation) cannot help. The ESC transaction is a CAS
  on `account_revision`, the renunciation's `LANE_CLOSE` is an append to
  the same ledger, so the CAS fails, re-evaluation reads `A` ENDED and
  CLOSED, and the result is `ESC_RELATION_UNTRUSTED`.
- A deterministic checkpoint after the renunciation finds `A` not LIVE and
  writes nothing (§9.8 "Result").

No delayed scheduler event can create the fork. **✓** (TST-CB-090 case F,
second half.)

### 5.5 Local handle retirement (brief §10)

`A` owns handles `H1`, `H2` (children `C1`, `C2`) and renounces.

- `retire_lane` sets `retired_at` on every handle `owned_by(lane.lane_id)`
  in the same transaction (§34 lines 6490–6495; §9.11 lines 2178–2180).
- A retired handle is "never transferred, exposed or usable by any
  model-controlled execution".
- Transfer only happens in RETRY/CONTINUATION handover from an OPEN chain
  predecessor lane. `A`'s lane is CLOSED, and `A` can never be a valid
  chain predecessor. So there is no path to `B` or to an unrelated retry
  chain.
- `B` presenting `H1` gets `h.owning_lane_id ≠ B.lane` →
  `DENIED(CB_MALFORMED_REQUEST)`. This is byte-identical to before the
  retirement (it never owned `H1`), so `B` cannot observe that the handle
  capacity was retired.
- `C1` and `C2` stay effective until class A revocation, natural expiry or
  another independent frozen path (§9.11 lines 2260–2267).
  `C1`'s ESCs keep running: §9.3 step 6 CHILD requires the parent's *pair*
  to be effective, not the parent ESC to be LIVE. An out-of-limits
  renunciation revokes no pair.

**✓**

### 5.6 Unused allowance (brief §11)

`retire_lane` writes `LANE_CLOSE` with remainder 0 in `P_max`, `N_c`,
`R_max`, capacity and forks, and no handover or split entry.

| Property | Result |
|---|---|
| Redistributed / merged into a sibling | No |
| Exposed as account availability | No. Account totals are a never-binding backstop, and no ESC reads them |
| Later reclaimed | No. A CLOSED lane "can be spent, handed over or split by nobody" |

The availability loss is stated (§9.11 lines 2240–2245; §38.2 "availability
cost only"). A `B` T-7 that would need `A`'s retired capacity is DENY by
`B`'s own lane in both runs (TST-CB-106), so no channel arises. **✓**

---

## 6. Chain-predecessor model (brief §16–§18)

### 6.1 `chain_predecessor_esc_ids` (brief §16)

| Requirement | r10 text | Result |
|---|---|---|
| TCB-written | ExecutionRelation written only by ESC Issuer / Execution Scheduler; set "only by the Scheduler from trusted records" (§9.8) | ✓ |
| Never model-supplied | "never taken from model content, a Task row, a planner list or a sibling's output, and the model never proposes or enumerates predecessor ids" | ✓ |
| Non-empty for RETRY/CONTINUATION | §9.3 step 12, "non-empty … else DENY(ESC_RELATION_UNTRUSTED)" | ✓ |
| ⊆ `predecessor_esc_ids` | §9.3 step 12; §9.8 schema | ✓ |
| Derived only from continued execution(s) | "exactly the ended ESC(s) whose own trusted end event (closed status of THAT ESC) this relation continues"; "never adds … an ESC whose end the relation does not continue" | ✓ |

It is not an arbitrary selector. Its membership is fixed by which trusted
end event triggered the relation.

### 6.2 Taint vs chain separation (brief §17)

| Item | Taint-only predecessor | Chain predecessor |
|---|---|---|
| `H_exec` joined into genesis | yes (§9.3 step 12 "inherited = ⊔ predecessors' final H_exec"; §14.5 r10 row) | yes |
| Lane remainders | no ("lanes are never touched", line 1379) | yes (handover if OPEN) |
| Handles | no | yes (unless retired) |
| Renunciation / pending record read | no ("are NOT read", line 1356) | yes (terminal check) |
| Can terminate the successor | no | yes (class C) |

The separation is sound.

### 6.3 High-taint renounced taint predecessor (brief §18)

- `A` is high-taint and renounced locally. `B`'s successor names `A` as
  taint-only.
- The successor joins `H_A` into its genesis label (and may therefore fail
  `ESC_CEILING_UNSATISFIABLE`, exactly as it would had `A` ended normally
  with the same taint).
- It receives no lane, handle or terminal state from `A`.
- Confidentiality is enforced by taint, not by control suppression.
  TST-CB-106 "Taint-only predecessor" covers `A` ended normally, renounced,
  and ended by a within-limit SELF.

**✓**

---

## 7. Multi-predecessor continuation (brief §19–§21)

### 7.1 What r10 says

- §9.8, lines 1828–1830: "A merging continuation may name several, only
  where the profile's `retry_policy` defines that merge".
- §9.3 step 12, lines 1352–1354, and §9.8, lines 1841–1844: "A merge that
  includes such a chain is refused as a whole".
- TST-CB-090 case E: "A merging continuation whose chain set is `{A, B}` →
  DENY as a whole".

### 7.2 Is a merge definable?

**No.** The r10 `TaskProfile.retry_policy` (§9.4, lines 1431–1439) is
exactly:

- `max_retries`, `max_continuations`, `max_forks`;
- `allowed_relation_kinds`, `fork_triggers`;
- `fork_rule`.

It has no merge definition. §14.5 ("Retries, continuations, forks and
merges") defines only the child → parent result merge, which is a flow, not
a relation. A search for "merg" finds no other definition.

Under the r10 schema, therefore:

- the Scheduler can never legitimately write a relation with
  `|chain_predecessor_esc_ids| > 1`;
- TST-CB-090 case E is satisfiable only as a defensive ESC Issuer refusal
  of an injected relation.

### 7.3 Attack, if a merge were defined

`A` and `B` end. `A` renounced (out of limits, or within limits with
`effective_at` still in the future). A profile-defined merge `{A, B}` is
refused as a whole, so `B`'s chain is not continued by that relation.

| Question (brief §19) | Answer |
|---|---|
| Who requests / observes the merge? | The trusted Scheduler requests it. Its existence or absence is a §14.8 relation/status observable (orchestrator, API, other executions), and the merged successor's destinations see its emissions or their absence |
| Can a model choose the predecessor set? | No (§6.1). There is no probing: the model cannot ask "include A?" |
| Is membership predetermined? | It would be fixed by the profile rule and the trusted end events, independent of sibling model state (brief §20 ✓) |
| Does taint cover `A`'s influence? | For the merged successor and its emissions, yes: the successor's label ⊒ `H_A ⊔ H_B`, so everything it emits is already cleared for `A`'s data |
| Can a lower-taint observer learn hidden renunciation state from the absence? | **Out-of-limits:** the absence is a deterministic function of `A`'s own terminal status (`RENOUNCED_FOR_EXECUTION`), already a §14.8 observable, so nothing beyond the recorded residual. **Within limits, before `effective_at`:** `A`'s §14.8 status is "ENDED … exactly as when a parent simply finishes" (§9.11 lines 2595–2598), but the merge refusal distinguishes "renounced" from "finished" *before* `effective_at`. That is a ≤ 1-bit pre-effective disclosure to control-plane observers, and a change to `B`'s continuation eligibility contradicting §9.11 item 8 |

This merge-denial path is **bounded** (at most one event per renouncing ESC,
about one bit, of the order of the §14.8 retry residual) and **not
model-probeable**. It is not an unbounded channel. It exists only if a
merge is definable, and r10 defines none. It is recorded as **HR12-01
(LOW)** because the text contemplates a feature whose security effect it
does not account for. It also leaves unspecified what happens to the
non-renounced co-predecessor's OPEN lane after a refused merge.

### 7.4 Successor denial surface (brief §21)

- **Renouncer's own chain.** The only successor ever refused for a class C
  reason is one whose chain contains the renouncer. Its closed code
  `ESC_LINEAGE_INVALID` reveals nothing beyond `A`'s own status. The
  requester caused it.
- **Unrelated sibling chains.** They are never refused for this reason
  (§35.2: "another ESC's renunciation or pending record is never a reason
  for any code"). No distinguishable error reaches them.
- **Code reuse.** `ESC_LINEAGE_INVALID` is also the ordinary step-6
  pair-failure code, and it is used for the counted post-`effective_at`
  case.

**✓** (subject to HR12-01 for merges)

---

## 8. Pending within-limit SELF (brief §12–§15)

### 8.1 Before `effective_at` (brief §12)

`A` requests SELF within limits at `t` (bucket `k`).

- **One transaction.** It appends `TERMINATION_ACT` to `A`'s lane, inserts
  the `PendingModelRevocation`, runs `end(A)` and `retire_lane(A.lane)`
  (§34 lines 6480–6488).
- **The pair.** It stays effective: T-7 step 1 and §34 step 3 treat a
  pending record as effective only from `effective_at`.
- **`B`'s T-7, T-9 and FORK.** They are unchanged, because none of them
  reads the record.
- **`B`'s RETRY / CONTINUATION at `t′ ∈ (t, effective_at)`.** It is created
  with chain `{B}`. It binds the still-effective pair and stops at
  `effective_at`. The r9 "(effective or not)" test is withdrawn (§9.11 lines
  2562–2571), and TST-CB-090 case G asserts it.
- **`B`'s own T-9 SELF during the window.** It is accepted independently.
  At `effective_at` the second commit is an idempotent
  `DUPLICATE_REVOCATION`, and `B`'s result is `ACCEPTED_PENDING` in both
  runs.
- **Account totals.** The same CAS on `account_revision` serializes the
  write against every concurrent `B` ledger write. That affects latency
  only, which is inside the §38.2 timing residual.

There is no sibling pre-effective signal (merge corner excepted, HR12-01).
**✓**

### 8.2 At `effective_at` (brief §13)

| Expected | r10 text | Result |
|---|---|---|
| Pair ineffective | the pending record is treated as effective at every trusted time `≥ effective_at`, whether or not the scheduler ran (§9.11 "Effect for v0.2.6") | ✓ |
| `A` already stopped | yes, at acceptance | ✓ |
| `B` ineffective via ordinary pair rule | §9.5 rule 6; §9.3 step 6; §34 step 3; "no special task-wide pending-record test exists" | ✓ |
| Future successors fail normally | step 6 `ESC_LINEAGE_INVALID` | ✓ |
| Counted | one `R_max` slot, `(own pair, mode, bucket)` | ✓ |

### 8.3 Restart before `effective_at` (brief §14)

- The record survives restart (insert-once store).
- Recovery applies only records with `effective_at ≤ now`.
- Every LIVE ESC, `B` included, becomes TERMINATED on restart (§14.4).
  `B`'s CONTINUATION has chain `{B}` and is decided normally.
- "No startup or recovery rule exposes pending status early" (lines
  2576–2578).

**✓**

### 8.4 Restart after `effective_at`, rows not repaired (brief §15)

- Every v0.2.6 check at `≥ effective_at` treats the whole logical
  revocation as effective.
- `RevocationCommitBarrier` recovery runs before any touched store accepts
  another operation. It repairs idempotently with the same `effective_at`
  (`DUPLICATE_REVOCATION` for rows already present).
- The v0.2.6 gates are conjunctive with the v0.2.5 gate and read the logical
  record, so there is no authorization window.

**✓**

---

## 9. HR11-02 — `POLICY_DETERMINISTIC` fork checkpoints (brief §26–§30)

| Requirement | r10 text (§9.4 lines 1434–1439; §9.8 lines 1879–1908; §32; §9.3 step 12) | Result |
|---|---|---|
| Finite | "finite … tuple" | ✓ |
| Strictly ascending | "strictly ascending tuple of durations > 0" | ✓ |
| Bounded | §32 retry row "finite and bounded" | ✓ |
| In the exact sealed TaskProfile | part of `fork_rule` in the digest-bound TaskProfile version; CR-POL-01 r10 | ✓ |
| Fixed before source execution | "fixed in the approved TaskProfile version before any execution"; instants "fixed when `S` is created" | ✓ |
| Evaluated only at `created_at + offset_i` | "At each checkpoint instant, and only then … at most once" (UNIQUE `(source_esc_id, fork_rule ref, i)`) | ✓ |
| No sibling event creates / shifts / causes early evaluation | "No sibling, model, tool, QA or scheduler event can create, remove, shift or select a checkpoint" | ✓ |
| Missed → SKIPPED, never replayed | "recorded `SKIPPED` at recovery and is never evaluated later" | ✓ |
| Later checkpoints independent | each `i` has its own instant and UNIQUE key; a SKIPPED `i` does not affect `j > i` (implied, not stated; HR12-02) | ✓ (implicit) |
| Inputs source-local | `S`'s status and state, `S`'s lane state, TCR, exact policy binding, `(i, instant)`; "must not read any sibling's completion, output, QA result, tool result, pending revocation, local renunciation or lane state, or the order of any other scheduler event" | ✓ |
| Account counters changed by siblings | not an input; the `max_forks` task count is only a backstop | ✓ |
| ESC Issuer verification | "the trigger names a real checkpoint of `S`"; else `ESC_RELATION_UNTRUSTED` (TST-CB-106) | ✓ |
| SOURCE_ESC / OWNER unchanged | harness-recorded source request; OwnerChannel event; a sibling cannot write the source harness record | ✓ |

**Residual precision (HR12-02, LOW).** "Unavailable" is defined, but "late"
is not. No tolerance bounds:

- the lag between the checkpoint instant and the evaluation, or
  `ForkAuthorization.created_at`;
- the instant at which the predicate snapshots `S`'s state;
- the lag between the authorization and the FORK ESC transaction, where the
  split actually happens.

The ESC Issuer checks only that the trigger names a real checkpoint. A
Scheduler that is available but slowed (for example by load a sibling
generates) could therefore evaluate late, or create the FORK late, and the
result would be treated as timely. The lag is not selectable by a sibling
model, only loosely influenced through load, so it lies within the §38.2
CAS/latency timing residual. Brief §27 ("late evaluation treated as if
timely") is nonetheless not excluded by text.

**HR11-02: RESOLVED_IN_R10.** The instants are fixed and event-independent.
The lateness tolerance is carried as HR12-02 and is not freeze-blocking.

---

## 10. HR11-03 — `ExecutionControlFacts` (brief §31–§32)

Contents (§9.8, lines 1846–1864; §40.B CR-TASK-01):

- ESC id, state and closed terminal status;
- lane reference, lane state and a boolean "fork remainder ≥ 1";
- the `SOURCE_ESC` fork-request marker;
- a boolean "own chain terminal".

It is closed and content-free. It carries "no model content, no counter, no
sibling's state and no other ESC's facts", and it is read-only and per ESC.

- **Internal-only.** The lane reference is a lane id, which is "never
  model-visible" (§5 Budget lane; §9.11 `BudgetLane`). The consumer is the
  TCB Scheduler, and the §9.11 non-disclosure paragraph covers lane ids and
  records. The design does not say in one place that the record itself is
  TCB-internal and never rendered to a model, sibling, descendant or
  destination. This is implied, not stated (HR12-03, INFO).
- **Interface race (brief §32).** The Scheduler's facts may be stale. The
  ESC Issuer "re-validates both in the ESC transaction":
  - RETRY/CONTINUATION re-checks chain predecessor ended, the class C
    record lookup and OPEN lane under the CAS;
  - FORK re-checks source LIVE, lane OPEN with fork remainder ≥ 1, and the
    `ForkAuthorization` single use.

  A renunciation, fork or handover committed in between changes
  `account_revision`, so the CAS fails and the decision is re-evaluated on
  current state. **Stale facts cannot create a fork or retry. ✓**
- **Build graph.** There is no build edge (§23).

**HR11-03: RESOLVED_IN_R10.**

---

## 11. HR11-04 — terminology (brief §33)

A search for `effective or not`, `new ESCs of`, `of that task`, `of its
task`, `refuses every later`, `task-wide` and `account-wide`:

| Hit | Status |
|---|---|
| §0.9 rows HR9-02 / HR9-05, §0.10 rows HR10-01 (6) / HR10-02 | historical correction-record rows, explicitly superseded by the r10 note at lines 537–544 |
| §9.3 line 1342; §9.11 lines 2187, 2191, 2567, 2575, 2614–2615, 2625; §35.2 line 6653; §37 item 56; §38.2 lines 7086–7093; §45 | withdrawal or negation statements ("is withdrawn", "never read task-wide", "NOT a task-wide revocation") |
| §32 T7Policy row | "terminates **its own** execution chain (r10 … never other ESCs or chains of the task)" — corrected |
| §34 behaviour rows | corrected ("terminates only its own execution chain") |
| §40.B CR-LIN-01 / CR-ESC-01 | corrected ("never other chains of its task"; "the r8 'refusing new ESCs of its task' is withdrawn") |
| TST-CB-090 r8 clause | withdrawn in place and replaced by cases A–H |
| §36 cross-reference row line 6894 | qualified "(r10: of the renouncer's own chain only)" |

No current normative path implies:

- that a local renunciation is task-wide;
- that one record blocks all task successors;
- that a pending SELF affects siblings before `effective_at`.

The only surviving tension is the merge clause (HR12-01).

**HR11-04: RESOLVED_IN_R10.**

---

## 12. HR10 regressions (brief §34–§37)

| Item | r10 text | Result |
|---|---|---|
| T-9 replay key `(requesting_esc_id, request_ref)` | §9.11 lines 2184, 2440–2442; §34 `model_revocation_results.get(esc.esc_id, request_ref)` before any allowance; UNIQUE across both record kinds | ✓ no account aliasing |
| Handles lane-owned | `owning_lane_id` check; one closed invalid-target code; no effectiveness test | ✓ |
| Sibling probe resistance | unchanged §34 path; retirement does not change a sibling's view (§5.5) | ✓ |
| FORK receives no existing handle | §9.3 step 12 line 1387 | ✓ |
| Handover only along a valid non-renounced chain | chain predecessors only, OPEN lanes only; renounced lanes retired | ✓ |
| Local renunciation retires rather than redistributes handles | `retire_lane` | ✓ |
| FORK not triggerable by another ESC's output | trigger kinds unchanged; checkpoints make `POLICY_DETERMINISTIC` stricter | ✓ (HR10-02 closure intact) |
| Account: one per task, no fresh budget, `D` bound, lane conservation | unchanged; RETRY/CONTINUATION/FORK create no account or pair; `retire_lane` only decreases spendable totals, so Σ lanes ≤ account still holds and total allowance cannot increase | ✓ |

---

## 13. Channel bound (brief §38)

The formula is unchanged:

`C_T7(A) ≤ N_c·⌈log2(1+n_T·B)⌉ + R_max·⌈log2(1+3·(1+D_A)·B)⌉`, with
`B = ⌈H/g⌉ + 1`.

1. **Local out-of-limits renunciation.** Its only writes are:
   - `A`'s record;
   - `A`'s end event;
   - `A`'s `LANE_CLOSE`;
   - `retired_at` on `A`'s handles.

   No decision about any other ESC reads any of them (§4.1). `B`'s modeled
   observable state — status, T-7/T-9/FORK results, lane, handles and
   successor eligibility — is therefore invariant under the act. What
   remains is `A`'s own §14.8 status/timing and the absence of **`A`'s**
   successor, both named in §38.2 (b). The HR11 channel is **removed**, not
   ignored.
2. **Requester-local effect.** `A`'s chain suppression is observable only as
   `A`'s own outcome, inside the accepted residual.
3. **Within-limit SELF.** It remains a counted termination slot at
   `effective_at`, and is invisible before it (§8.1).
4. **Shared `max_retries` / `max_continuations`.** A renounced `A` consumes
   no retry count, which is identical to `A` finishing. §38.2 names these
   counts as the pre-existing §14.8 residual.

**The bound remains conservative.** The only qualification is HR12-01, and
it applies only if merges were definable.

---

## 14. INV-CB-048

INV-CB-048 (rev r8, unchanged in r10) states: "outside those limits … a
self-renunciation ends only the renouncing ESC (`RENOUNCED_FOR_EXECUTION`)
with no descendant-visible effect before natural expiry".

- Under r10 the act ends that ESC and suppresses only successors *of that
  ESC's own chain*, which are not other executions.
- No other ESC ends or changes. "Only the renouncing ESC" is therefore
  exact, as regards which executions are affected.
- The invariant does not mention chain suppression or lane retirement, but
  INV-CB-090 (iii) states both, and the two do not conflict.

**INV-CB-048: VALID.** (Editorial precision, HR12-04: it could say "ends
only the renouncing ESC and its own successor chain".)

**TST-CB-048 (r10)** runs adversarial decoders "over runs that vary only
whether, when and in which mode" `A` renounces out of limits. It observes
`B`, `B`'s RETRY/CONTINUATION/FORK chain, results, allowances, handles,
status, emissions, destinations and descendants, and requires "**no**
information about `A`'s act beyond `A`'s own coarse §14.8 status and
timing". It separately requires that a within-limit SELF be undetectable
before `effective_at`. This is the required comparison of no-renunciation
against local renunciation, with no additional sibling control symbol. **✓**

## 15. INV-CB-090

| Brief §22 case | INV-CB-090 rev r10 text | Result |
|---|---|---|
| Local out-of-limits SELF: requester chain only | (iii) "requester-local `LocalRenunciationRecord` … never interpreted as a pair, edge or task-wide revocation … affects only the renouncing ESC's execution-successor chain; unrelated live sibling lanes and their future successors are unaffected" | ✓ |
| Within-limit SELF: requester chain stops now, pair-wide at `effective_at` | (ii) "before `effective_at` it affects only the requester's own execution chain and has no sibling effect"; "commits a frozen pair / edge revocation at `effective_at`" | ✓ |
| Class A: immediate frozen revocation | (i) | ✓ |
| Lane retirement, handles retired | "its lane is CLOSED with every remainder retired … handles retired" | ✓ |
| Refusal basis | "refused only if one of its own trusted chain predecessors renounced; no decision about another ESC reads either record" | ✓ |
| Earlier clauses (requester-local key, closed result, barrier, no cancel) | retained | ✓ |

The clauses are mutually consistent and consistent with §9.3, §9.11 and
§34. HR12-01 concerns a §9.8 feature (merge) that the invariant does not
mention.

**INV-CB-090: VALID.**

**TST-CB-090 cases A–H** are all present, each "run twice — with and
without `A`'s act — and compared over `B`'s complete observable behaviour …
and the Scheduler's and ESC Issuer's decisions about `B`'s chain":

| Case | Brief §23 case | Genuine behavioural assertion |
|---|---|---|
| A | local `A` renunciation, `B` LIVE | ✓ lane CLOSED, handles retired, record fields, no `revoke()`/slot/epoch; `B`'s T-7/T-9/FORK, remainders and handles identical |
| B | `B` retry (also with `A` taint-only) | ✓ exactly `B`'s remainders/handles; identical across runs |
| C | `B` continuation | ✓ |
| D | `A` retry denied | ✓ `ESC_LINEAGE_INVALID`, no handover |
| E | `A` continuation denied | ✓ (plus the merge clause, HR12-01) |
| F | fork `B` then `A` renounces; renounce then fork | ✓ no transfer, `B` eligible; fork after renunciation `ESC_RELATION_UNTRUSTED` |
| G | pending SELF before `effective_at` | ✓ successor/fork of `B` created; restart unchanged |
| H | shared pair invalid at `effective_at` | ✓ ordinary step 6; instrumented "never queries … other than … own chain predecessors" |

## 16. INV-CB-106

- **r10 extension.** Successor isolation covers RETRY/CONTINUATION: lanes
  and handles come only from chain predecessors, and a successor is refused
  only for its own chain predecessors' class C acts.
- **Retired lanes.** Their remainder and handles are never redistributed or
  transferred.
- **Deterministic checkpoints.** The rule is evaluated at most once per
  checkpoint and a missed checkpoint is skipped.
- **Prior clauses.** They are retained.

All of this is consistent with §9.3, §9.8 and §9.11.

**INV-CB-106: VALID.** (Timing tolerance: HR12-02.)

**TST-CB-106 r10** covers:

- branch-local lane termination;
- no redistribution, compared across runs;
- no handle transfer, including class A revocation of `C1` still working;
- the taint-only predecessor in three variants;
- fork checkpoint timing with adversarial sibling events, SKIPPED on
  Scheduler down, and a non-checkpoint trigger →
  `ESC_RELATION_UNTRUSTED`.

**✓**

---

## 17. LineagePair regression

r10 touches the lineage only through:

- a §21.3 rule 5 parenthesis (an out-of-limits local renunciation "never
  makes this rule apply, because it revokes nothing");
- §9.3 step 12 relation checks, which add conjuncts only.

These are unchanged:

- no pair search;
- parent-bound pairs;
- the step 6 checks, including `pair.issuer_event == deb.issuance_event`
  and `deb.child_profile_ref == tcr.task_profile_ref`;
- leaf uniqueness;
- the approval digest;
- the ancestor walk;
- the rule 5 cascade;
- atomic co-issuance.

No r10 path binds, shops for, revives or re-parents a pair. A retired
handle removes model revocation capability; it adds none.

`LINEAGEPAIR R10 REGRESSION-FREE`

## 18. DelegationBudgetAccount regression

| Property | Result |
|---|---|
| One account per task (UNIQUE `task_control_record_id`; created only at T-8 / T-7) | ✓ unchanged |
| No fresh budget on RETRY / CONTINUATION / FORK | ✓ step 12 `ESC_RETRY_REBINDING`; lanes only hand over or split |
| `D` bound / capacity induction | ✓ unchanged; retirement creates no pair or account |
| Lane conservation | ✓ `LANE_CLOSE(RENOUNCED)` removes spendable allowance; nothing is added anywhere |
| Retirement cannot increase total allowance | ✓ |

**Regression-free.**

## 19. Read confinement

No r10 edit in §16–§18. The following are still present:

- §17.9 `unknown actual readable universe = DENY` (line 4210);
- `deliver()` `ars is None → DENY(CB_READ_SET_INCOMPLETE)` with "no
  owner-ceiling fallback" (lines 6295–6298);
- ConfinementRecord and GitReadClosure (§17.11);
- Level 2R (§6.5).

**Regression-free.**

## 20. Activation

No r10 edit in §40.F. `valid(a, t)` still has only the monotonic rollback
floor. The "Not a conjunct" paragraph keeps the global SecurityPolicyVersion
out of the predicate. ActivationPolicyBindings remain exact-dependency based,
and the §34 behaviour row "T-9 renunciation … **no** IntegrationActivation
changes state" is intact. There is no global revocation-epoch kill switch
and no SecurityPolicyVersion kill switch.

**Regression-free.**

## 21. Network taint

No r10 edit to §14.3, §17.6, `deliver()` or `complete_tool_invocation()`.
The following are intact:

- the persisted `L_net_max` and `reserved(esc)` in the delivery-commit
  ceiling check (lines 3244, 6262);
- the failed-tool taint append;
- the interleaving join;
- `RequiredActivationSet(op)`.

**Regression-free.**

---

## 22. Test and invariant accounting

Counted by script over the r10 file:

- **§33.** 106 `INV-CB-NNN` rows, IDs 001–106, no gaps, no duplicates.
- **Active.** 105; only INV-CB-030 is `**withdrawn**`.
- **New IDs.** None.
- **Rows marked "rev r10".** Exactly 090 and 106. INV-CB-048 keeps "rev r8"
  and INV-CB-093 keeps "rev r9". This matches §0.11 and the §33 totals
  paragraph (lines 6114–6118).
- **§36.** 105 `TST-CB-NNN` definition rows (lines 6712–6816), no
  duplicates, and none outside §36. The closing r8/r9/r10 rows are
  cross-references.
- **Mapping.** The active-invariant ID set equals the test ID set
  (symmetric difference ∅), so there is exactly one test per active
  invariant. TST-CB-023 carries 023(+030).
- **Semantics.** TST-CB-048, 090 and 106 match the final r10 semantics
  (§14–§16).

## 23. Dependency graphs

- **Build graph.** All edges were parsed from the §40.E tier listing and
  point to strictly lower tiers. Four parse artefacts were checked by hand:
  - `GATE-CONTAIN ← …, LOG-01`;
  - `CR-TAINT-01 ← ESC, EPOCH, POL`;
  - `CR-CB-05 ← CR-05, ESC`;
  - the descriptive v0.2.6.9 / pure-stage rows.

  r10 adds no edge. CR-TASK-01 (T5) depends on OBJ, POL, OWN, LIN and CR-04,
  not on ESC. The graph is **acyclic**.
- **Activation graph.** Unchanged; `act(CR-ESC-01)` and `act(CR-TASK-01)`
  share one line with no mutual prerequisite. **Acyclic.**
- **GATE-CONTAIN.** Unchanged; **cycle-free.**
- **`ExecutionControlFacts` injection.** The type lives in the pure v0.2.6.2
  contracts. The consumer is CR-TASK-01 and the provider CR-ESC-01, at
  runtime. There is no hidden inversion: without the injected provider the
  Scheduler has no facts and writes no relation, and the ESC Issuer
  revalidates anyway, so it fails closed. The design does not state that
  fail-closed default explicitly (HR12-03).

## 24. Frozen-contract compatibility

| Contract | r10 impact | Amendment? |
|---|---|---|
| v0.2 | strengthening only | No |
| v0.2.3 | none | No |
| v0.2.4 | identifiers unchanged | No |
| v0.2.5 | `revoke()` unchanged ("immediate at commit; irreversible; idempotent"). Class A is immediate. A local renunciation never calls `revoke()` and writes no `RevocationRecord`; v0.2.5's "the delegate may renounce" is a permission, not an obligation to forward. The execution-chain terminal state is an additive v0.2.6 execution-control rule and changes no frozen pair or edge revocation. Per-store marks are consistent with §10 | No |
| v0.2.5.1 | types unchanged | No |

**No amendment required.** AMD-025-01 remains uncreated.

## 25. Owner decisions (not decided here)

1. The `T7Policy` values (`N_c`, `P_max`, `n_T`, `g`, `H`, `R_max`,
   `D_max`), each `child_subtree_budget`, and acceptance of the stated
   per-task `C_T7` bound.
2. Template contents and choices per profile.
3. The fork policy per profile: `fork_triggers`, `fork_rule` predicate and
   `checkpoint_offsets` values.
4. The ApprovalRequirement vocabulary and each class's requirement set.
5. The policy supersession effects (`RETAIN_…` / `INVALIDATE_…`) and each
   ActivationManifest's `policy_dependencies`.
6. The CR classifications (§40.F), including CR-NET-01's
   `InternalEndpointPolicy` mode.
7. The earlier §44.5 dispositions (§0.2 / §0.4, the LineagePair
   realization, the §14.9 default labels, the environment-class vocabulary
   and the network-destination policy).
8. The recommended human security review before freeze, and the freeze
   decision itself.
9. Whether to fold the one-sentence HR12-01 clarification into the frozen
   text (recommended) or carry it as an implementation blocker.

There are no unresolved technical-architecture decisions. HR12-01 and
HR12-02 are precision items with stated corrections, not open design
choices.

---

## 26. New HR12 findings

### HR12-01 — Multi-chain merge continuation is contemplated but undefined, and its refusal rule is not isolation-accounted

- **Severity:** LOW
- **Category:** NEW (residual edge of the HR11-01 correction)
- **Section:**
  - §9.8, lines 1828–1830 and 1841–1844;
  - §9.3 step 12, lines 1352–1354;
  - §9.4 `retry_policy`, lines 1431–1439;
  - §14.5;
  - TST-CB-090 case E.
- **Invariant:** INV-CB-090 (ii)/(iii), INV-CB-106 (r10 clause); §9.11 item 8
- **Attack / contradiction:**
  - **The text.** §9.8 allows a continuation with several chain
    predecessors "where the profile's `retry_policy` defines that merge",
    and refuses such a merge "as a whole" if any chain predecessor ended by
    a class C act.
  - **The schema.** The r10 `retry_policy` has no merge definition, so no
    profile can define one.
  - **If one existed.** Let `A` renounce within limits at `t` and `B` end
    at `t′ < effective_at`. The merged successor `{A, B}` is refused before
    `effective_at`, whereas it would be created had `A` "simply finished".
    This changes `B`'s continuation eligibility and lane fate (`B`'s lane
    stays OPEN, orphaned), contradicting §9.11 item 8 ("never changes a
    concurrently LIVE sibling's … RETRY or CONTINUATION eligibility"). It
    also discloses about one bit pre-effective to §14.8 observers. In the
    out-of-limits case the refusal is a function of `A`'s own terminal
    status only, so it stays within the recorded residual.
- **Impact:**
  - **Under the r10 schema:** none; unreachable.
  - **If merges are later enabled without accounting:** a bounded,
    non-probeable, ≤ 1-bit-per-renouncing-ESC pre-effective signal and an
    unspecified orphan-lane state.
  - This is not an unbounded channel. The model cannot select the chain
    set.
- **Required correction:** one of:
  - **(a) Recommended.** State that in v0.2.6
    `|chain_predecessor_esc_ids| = 1` for every RETRY/CONTINUATION, because
    `retry_policy` defines no merge. Keep the ESC Issuer refusal of any
    relation with a larger chain set as a defensive check
    (`ESC_RELATION_UNTRUSTED`), and reword TST-CB-090 E accordingly.
  - **(b)** If merges are wanted:
    - define them in `retry_policy`;
    - specify that a class-C-terminated chain predecessor is demoted to
      taint-only, so the merge proceeds on the remaining chains, or that
      the refusal is deferred to `effective_at` and counted;
    - specify the co-predecessors' lane fate;
    - add the case to §9.11 item 8, the channel table and TST-CB-048.
- **Freeze blocker:** NO. Unreachable under the r10 sealed schema; a merge
  field would itself be a design change needing review. Folding (a) into
  the frozen text is recommended.
- **Implementation blocker:** YES (CR-TASK-01 Scheduler, CR-ESC-01 ESC
  Issuer must implement chain-set cardinality 1 unless (b) is designed and
  reviewed).
- **Deployment blocker:** NO

### HR12-02 — Fork checkpoint lateness tolerance undefined

- **Severity:** LOW
- **Category:** RESIDUAL-HR11 (HR11-02)
- **Section:** §9.8 "Deterministic fork checkpoints", lines 1879–1908;
  §9.3 step 12 FORK
- **Invariant:** INV-CB-106 (r10 checkpoint clause)
- **Attack / contradiction:** "Unavailable" is handled by SKIPPED, but
  nothing bounds:
  - the lag between the checkpoint instant and the evaluation or
    `ForkAuthorization.created_at`;
  - the time at which the predicate snapshots the source's state;
  - the lag before the FORK ESC transaction splits the lane.

  The ESC Issuer checks only that the trigger names a real checkpoint. A
  Scheduler slowed by load, which siblings can partly generate, can thus
  evaluate or fork late, and the result is treated as timely. The claim
  "the instant at which a deterministic fork splits `S`'s lane is a function
  of `S`'s own creation time" then holds only up to scheduling latency.
  Independence of a later checkpoint after a SKIPPED one is implied, not
  stated.
- **Impact:** At most `max_forks` split events per task, with timing jitter
  loosely correlated with aggregate load. The source observes it only
  through its own later lane-exhaustion outcomes. This is inside the §38.2
  timing residual. No sibling model can choose the instant.
- **Required correction:**
  - fix a TCB tolerance `δ`;
  - evaluate the predicate over the source's state as of the checkpoint
    instant;
  - require `ForkAuthorization.created_at ≤ instant + δ`, else record
    SKIPPED;
  - require the FORK ESC transaction within `δ′` of the authorization, else
    it expires unused;
  - have the ESC Issuer verify both;
  - state that each checkpoint is evaluated independently of earlier SKIPPED
    ones.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-TASK-01 Scheduler; CR-ESC-01 check)
- **Deployment blocker:** NO

### HR12-03 — `ExecutionControlFacts` visibility and fail-closed default not stated; minor audit gaps

- **Severity:** INFO
- **Category:** NEW (editorial)
- **Section:** §9.8 "Scheduler control interface"; §40.E r10 paragraph;
  §30.1
- **Invariant:** INV-CB-106
- **Attack / contradiction:**
  - The record is described as closed and content-free, but not explicitly
    as TCB-internal and never model- / sibling- / descendant- /
    destination-visible. This is implied by the lane-id non-visibility rule.
  - The Scheduler's behaviour when the injected provider is absent is not
    stated. It fails closed in effect, because of revalidation.
  - §30.1 lists no audit event for a checkpoint `SKIPPED` or a handle
    `retired_at`. The generic `LANE_CLOSED` covers the lane.
- **Impact:** none
- **Correction:** one sentence each in §9.8 / §40.E and two §30.1
  RESTRICTED/AUDIT event names.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR12-04 — Counterfactual and invariant wording precision

- **Severity:** INFO
- **Category:** NEW (editorial)
- **Section:** §9.11 lines 2617–2619 and 2568–2571; §34 behaviour row
  "ESC `A` renounces …"; INV-CB-048; TST-CB-090 r10 preamble
- **Invariant:** INV-CB-048, INV-CB-090
- **Attack / contradiction:**
  - "Decided exactly as if the renunciation had not happened" is exact only
    against the counterfactual in which `A` ended by other means at the same
    instant. Where `A` is a conservative taint-only predecessor, `B`'s
    successor must wait for `A`'s end (§14.4). `A`'s end time — `A`'s own
    §14.8 timing residual, already named in §38.2 (b) — thus affects the
    successor's timing, and the renunciation adds nothing to it.
  - INV-CB-048 "ends only the renouncing ESC" does not mention the
    renouncer's own chain.
- **Impact:** none; the channel claims are accurate.
- **Correction:**
  - define the TST-CB-090 / TST-CB-048 comparison baseline as "`A` ends
    normally at the same instant";
  - optionally append "and its own successor chain" to INV-CB-048 at the
    next revision.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 2 (HR12-01, HR12-02) ·
INFO 2 (HR12-03, HR12-04) · total 4.

---

## 27. Design freeze blockers

`NONE`

**Freeze-standard scorecard (brief §49)**

| Criterion | Status |
|---|---|
| 0 CRITICAL / 0 HIGH design blockers | ✓ |
| 0 freeze-blocking MEDIUM | ✓ |
| HR11-01 RESOLVED_IN_R10 | ✓ |
| HR11-02 RESOLVED_IN_R10 | ✓ (tolerance precision: HR12-02, LOW) |
| Local out-of-limits renunciation genuinely branch-local | ✓ |
| Unrelated sibling retry / continuation unaffected | ✓ |
| Pending SELF: no pre-effective sibling signal | ✓ (merge corner unreachable: HR12-01) |
| Chain-predecessor semantics create no new merge / probing channel | ✓ under the r10 schema; no probing possible; merge undefined (HR12-01) |
| Deterministic fork timing independent of sibling events | ✓ (latency residual: HR12-02) |
| INV-CB-090 sound | ✓ VALID |
| INV-CB-106 sound | ✓ VALID |
| Channel bound conservative | ✓ |
| HR10 closures intact | ✓ |
| LineagePair regression-free | ✓ |
| No frozen-contract amendment | ✓ |

## 28. Implementation blockers (separate from freeze)

Every §43.1 row remains, including the r8–r10 rows. None of the following
machinery exists:

- account store;
- lanes;
- handle store;
- pending store;
- barrier;
- `ForkAuthorization`;
- `LocalRenunciationRecord`;
- `retire_lane`;
- `chain_predecessor_esc_ids`;
- checkpoints;
- `ExecutionControlFacts`.

In addition:

- HR12-01 (CR-TASK-01, CR-ESC-01: chain-set cardinality);
- HR12-02 (CR-TASK-01, CR-ESC-01: checkpoint tolerance).

## 29. Deployment blockers (separate)

Every §43.2 row is unchanged. These live defects are not fixed by any design
revision:

- R-01..R-09, R-11 and R-13;
- R-22..R-26, R-29 and R-30.

No HR12 finding adds a deployment blocker.

## 30. Final status

r10 removes the HR11 channel at its source:

- **Record scope.** The ESC Issuer no longer reads any renunciation or
  pending record except for the new ESC's own chain predecessors, by id.
- **Lane closure.** The renouncer's lane closes with remainder and handles
  retired, never redistributed.
- **Chain control.** Execution-control inheritance is separated from taint
  inheritance.
- **Pending SELF.** It is invisible to siblings until `effective_at`, where
  the ordinary pair check applies.
- **Fork timing.** Deterministic fork evaluation is pinned to fixed
  source-relative checkpoints.

The attempt to falsify branch-locality, the pending-SELF window and the
chain-predecessor model found no reachable contradiction. The two LOW
findings concern:

- a merge feature the sealed schema cannot express (HR12-01);
- a lateness tolerance inside the accepted timing residual (HR12-02).

Neither blocks freeze.

These are regression-free:

- the HR10 closures;
- the account and capacity proof;
- the channel formula;
- the LineagePair;
- read confinement, activation and network taint.

No frozen contract needs amendment.

```text
R10 DESIGN READY FOR OWNER FREEZE DECISION
```

READY means only that the technical design review has passed and the owner
may now decide whether to freeze v0.2.6. It does **not** mean frozen,
implemented, implementation-authorized, deployed or production-secure. The
recommended human security review (§25 item 8) remains an owner decision.

> No v0.2.6 production implementation has been authorized or created.

---

## Appendix A — Read-only validation

Run from `C:\Users\Gyuro\jarvis-os` with `.venv/Scripts/python.exe`, before
this file was written (the untracked set was the eleven v0.2.6 documents).

| Command | Result |
|---|---|
| `python scripts/check_v013_freeze_baseline.py` | exit 0 (`v0.1.3 FREEZE BASELINE CHECK: OK`; Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `python scripts/check_v020_contract.py` | exit 0 |
| `python scripts/check_v023_router_contract.py` | exit 0 |
| `python scripts/check_v024_agent_contract.py` | exit 0 |
| `python scripts/check_v025_design_contract.py` | exit 1: `DISCREPANCY FOUND`, solely 11 × "file outside the v0.2.5.1 allowlist is new/modified" for the eleven untracked v0.2.6 documents (expected) |
| `python -m pytest -q -p no:cacheprovider` | **1 failed, 2234 passed, 1 warning** (371.4 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`: the same v0.2.5 allowlist discrepancy for the untracked v0.2.6 documents. Matches the HR7–HR11 baseline |

No validator, test or configuration was modified.

## Appendix B — Integrity

The design and HR2–HR11 were re-verified at the end of the review (see the
terminal report). They are unchanged from the §2 hashes, HEAD is unchanged,
there are no tracked changes, and the only new file is this HR12 document.
No commit, push or merge was made.
