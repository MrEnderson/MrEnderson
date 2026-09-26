# Jarvis OS v0.2.6 — HR9 Final Freeze Verification of Design Revision r7

```text
subject                        = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r7)
subject status on entry        = CORRECTED R7 — PENDING HR9 FREEZE VERIFICATION
controlling prior review       = HR8 (docs/V0_2_6_HR8_FREEZE_VERIFICATION.md)
review type                    = independent technical freeze verification (read-only)
review date                    = 2026-09-25
design_modified                = false
hr2_to_hr8_modified            = false
code_tests_validators_modified = false
opendex_modified               = false
final_status                   = R7 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

Section numbers (§N) refer to the r7 design unless another document is
named. Finding IDs `HR9-NN` are new to this review.

---

## 1. Independence

This session authored **none** of the following:

- design revisions r1, r2, r3, r4, r5, r6 or r7;
- HR2, HR3, HR4, HR5, HR6, HR7 or HR8.

It started with no conversation history and worked only from repository
contents. The design's correction record (§0.8) says r7 was written by a
session that did not author HR8, and that HR9 must come from a session that
did not author r7. This session meets that condition.

The r7 correction record, its "corrected" wording and the §44.5 sentence
"No known freeze-blocking MEDIUM issues after r7" were **not** treated as
evidence. Every conclusion below comes from the r7 normative text, the
frozen v0.2.5 / v0.2.5.1 documents, and HR8.

**Limitation.** This review uses the same model family as HR2–HR8. It is
session-independent but not organizationally independent. The design's
recommendation (§38.2, §44.5) for a human security review before freeze
still applies.

---

## 2. Repository state

Inspected read-only before this file was written.

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `13796dcd61015098429f343e2fb982a9c75698bb` |
| `origin/master` | `13796dcd61015098429f343e2fb982a9c75698bb` (= HEAD) |
| Tag at HEAD | `v0.2.5.1` |
| Tracked changes (`git diff`, `git diff --cached`) | none |
| Untracked (`git status --short -uall`) | exactly eight v0.2.6 documents: the design and HR2–HR8 |

This matches the expected state.

**SHA-256 at start of review**

| File | Role | SHA-256 |
|---|---|---|
| `docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md` | r7 design | `7e8ff40138c188aa825ec4def9cbb80dca3fb1166fb5704918f211a1f7d098d3` |
| `docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` | HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| `docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md` | HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| `docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |
| `docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` |
| `docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md` | HR6 | `42b170a580dba800fa310735c4ca0267083aa2beab0fb033fbebeeb289b4f07e` |
| `docs/V0_2_6_HR7_FINAL_FREEZE_VERIFICATION.md` | HR7 | `91e8d19eec8e98f38e7203b1f58d5181c2f25329c094de32fef53575fcecad64` |
| `docs/V0_2_6_HR8_FREEZE_VERIFICATION.md` | HR8 | `9848284e796f548b0012aa509de3b7a4cc3480f9fa5bad437020abf3d1b9aee7` |

The HR2–HR7 hashes equal the values HR8 recorded, so those files have not
changed since HR8. The design hash differs from HR8's r6 hash
(`1397db59…`), as expected for r7.

**OpenDex** (`C:\Users\Gyuro\opendex-reference`): HEAD
`3e898343d1127c8d5075b459acdd55da83b83f04`, the value in design §41.
`git status --short` is empty. No OpenDex file was opened or modified.

---

## 3. Materials reviewed

- **r7 design:** read in full (lines 1–6957): every correction record,
  every normative section, the §33 invariant table, the §34 procedure, the
  §36 test table, §37–§45 and the authorization block.
- **HR8:** read in full.
- **HR7/HR6:** not re-read. HR8 §4–§23 and design §0.6–§0.8 give enough
  history for traceability.
- **Frozen v0.2.5 / v0.2.5.1 revocation and delegation semantics:** checked
  in `docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md`:
  - §10 (lifecycle, trusted time, clock high-water mark);
  - §11 (revocation);
  - §12 (disabled identities);
  - §17 (atomicity);
  - the `revoke()` API row;
  - R-01..R-10;
  - Q10;
  - DA-05.

  Also checked: `docs/v0.2.5_delegation_authority_design.json`
  (`revocation` block) and the v0.2 contract (no revocation-timing clause).
- **Mechanical checks** (grep and diff over §33 and §36): see §21.

---

## 4. HR8-01 — activation policy bindings

### 4.1 One model

r7 has exactly one activation-policy model:

- `IntegrationActivation.policy_bindings: ActivationPolicyBindings`
  = `frozenset[PolicyObjectRef]`, with `PolicyObjectRef = (policy_object_kind,
  policy_object_id, object_version, object_digest)` (§40.F);
- exactly one ref per `(kind, id)` declared in the ActivationManifest
  `policy_dependencies`. Omissions and extra refs are rejected at approval,
  and every ref must name an ACTIVE version at approval;
- `valid(a, t)` resolves each ref by exact `(id, version)`, recomputes its
  digest, and requires lifecycle `ACTIVE` or
  `SUPERSEDED_BUT_STILL_VALID_FOR_EXISTING_BINDINGS`;
- `security_policy_version_at_approval` is "AUDIT AND REPRODUCIBILITY ONLY;
  never compared". The "Not a conjunct (r7)" paragraph withdraws the r6
  "active policy still contains a" conjunct.

### 4.2 Removed equality rules

Every location HR8-01 named is corrected:

| HR8-01 location | r7 text |
|---|---|
| TST-CB-105 Case E | "(The r6 clause 'or a different policy version' is withdrawn …)" |
| §35.2 `CB_ACTIVATION_NOT_CONTAINED` | lists exact-binding causes; "A later or different global SecurityPolicyVersion is never a cause" |
| §40.F startup step 4 | "the r6 comparison 'and the current SecurityPolicyVersion' is withdrawn" |
| §30.1 `INTEGRATION_ACTIVATED` | "(audit and reproducibility only; never compared with the current version)" |

A repository-wide search for residual equality phrasing ("still contain",
"different policy version", "current SecurityPolicyVersion", "latest
policy", "activation epoch") finds only historical correction-record rows
and prohibitions (§37 item 51). No normative rule compares the global
version.

**HR8-01: RESOLVED_IN_R7.**

---

## 5. ActivationPolicyBindings — attack cases

### 5.1 Unrelated policy evolution (brief §6)

Activation A binds `IsolationPolicy I@4` and `LoggingPolicy L@7`. The owner
approves an unrelated `TaskProfile P@12`, and the global
SecurityPolicyVersion advances.

Evaluating `valid(A, t)`:

- lifecycle: no entry was appended to A's chain ("Approving an unrelated
  object version, or a new snapshot, changes the lifecycle state of **no**
  existing object version");
- digests: unchanged;
- I@4 and L@7: still resolvable, digests match, still ACTIVE;
- owner approval event: not revoked;
- prerequisites, isolation, containment: unchanged;
- epoch: at least as high as before, so no rollback.

**A remains ACTIVE.**

I searched the whole design for any rule that invalidates A **solely**
because the global snapshot changed:

- `§34` step 0 `policy_approved_and_at_hwm()` concerns the broker's own
  policy load, not A;
- step 2 `esc.security_policy_version revoked` concerns an ESC, not an
  activation;
- `§29.4` bullets say "Approving a new snapshot … changes no existing
  binding".

I found none. The r7 §40.F example (I@4, L@7, P@12) is exactly this case.

### 5.2 Exact dependency revocation (brief §7)

An owner act revokes L@7. `PolicyObjectLifecycleRecord` appends `REVOKED`
and increments the epoch (§40.F table, §31 item 3). Then `valid(A)` fails on
`lifecycle_state(L@7) ∈ {ACTIVE, SUPERSEDED…}`. A's gated paths deactivate
and in-flight ESCs are TERMINATED (§40.F "Runtime invalidation", TST-CB-105
E2). The cause is L@7's lifecycle. The epoch increment is not it: with
`current_epoch ≥ monotonic_epoch_at_approval`, the epoch conjunct still
holds. An activation not bound to L@7 stays ACTIVE (E2, E5). **✓**

### 5.3 Superseded versions (brief §8)

| Requirement | r7 | Status |
|---|---|---|
| New activations cannot bind obsolete versions | "every ref names an ACTIVE version at approval"; the lifecycle table: `SUPERSEDED…` → "New bindings may use it: No" | ✓ Stricter than "unless explicitly permitted": no exception exists |
| Existing bindings continue only if the owner retained them | `SUPERSEDED…` is entered only by a successor approval stating `RETAIN_EXISTING_BINDINGS` | ✓ |
| No ambiguous default | "A successor approval **must** state a supersession effect for every predecessor … There is no default. A T-5 act that omits it is rejected." TST-CB-105 E4 | ✓ |
| REVOKED / EXPIRED unusable | Lifecycle table: existing bindings valid "No"; `valid()` admits only ACTIVE or SUPERSEDED… | ✓ |

### 5.4 Security-tightening successors (brief §9)

A predecessor stays usable for existing bindings **only** when the
successor's T-5 act explicitly says `RETAIN_EXISTING_BINDINGS`. A new
version does not grandfather anything by itself existing. For emergency
invalidation, three routes exist:

- `INVALIDATE_EXISTING_BINDINGS` on the successor;
- an explicit owner act revoking the predecessor version;
- later, `SUPERSEDED… → REVOKED` ("may later move to REVOKED or EXPIRED").

**✓**

One consequence is worth a note (not a finding). Revoking a whole snapshot
approval revokes every object version that approval introduced (§29.4).
An owner who revokes a snapshot to withdraw one object therefore also
invalidates every activation bound to any other object introduced in that
same act. This is explicit and audited (`POLICY_OBJECT_LIFECYCLE_CHANGED`
names the activations), so it is an owner choice, not accidental
invalidation. The OwnerChannel should show the affected activations before
confirmation.

### 5.5 Related gap outside activations (HR9-04)

The per-object `REVOKED` / `EXPIRED` states are defined as inputs to
activation validity. The design does not say they are inputs to the
effectiveness of an ESC or a T-7 issuance that recorded that object version
(for example a TaskProfile, template or EnvironmentClass version). See
HR9-04. It is not an activation defect.

---

## 6. HR8-02 — T-7 channel model

### 6.1 Coverage of signals

| Signal (brief §12) | r7 | Counted |
|---|---|---|
| Issue / don't issue | issuance slot `1 + …` | ✓ |
| Template choice | `n_T` | ✓ |
| Issuance bucket | `B` | ✓ |
| Issuance count / order | ordered slot vector, including within-bucket order by store ids | ✓ |
| Direct-child cancellation | class B, termination slot | ✓ |
| Deeper descendant-edge revocation | class B ("any deeper descendant edge"), termination slot | ✓ in kind; **alphabet undercounted** (HR9-01) |
| Self-renunciation with descendant-visible effect | class C, termination slot (own leaf, either half) | ✓ |
| Target selection | `2 · (1 + D_max)` targets | ✓ in kind; **alphabet undercounted** (HR9-01) |
| Termination bucket | `B` | ✓ |

Quantization now covers every class B/C act, not only direct children. The
horizon `H` and `R_max` apply to all of them. Owner, system and security
revocations are class A and immediate (§9.11, §7.3 T-9, §21.3 rule 5,
§21.5 "Timing", §32, §37 item 52).

### 6.2 Where the model is still not a true upper bound

The target alphabet `2 · (1 + D_max)` rests on the claim "at most `D_max`
descendant pairs in its subtree" (§9.11, §21.5, INV-CB-048). That claim
fails in two ways:

- the subtree budget is reserved and enforced **per ESC**, while the
  descendant pairs P can revoke are counted **per lineage**;
- T-9 may also target pair objects, which the alphabet does not count.

See HR9-01 and §7.3.

**HR8-02: PARTIALLY_RESOLVED** (residual HR9-01). The HR8-02 items
themselves are fixed:

- (a) self-renunciation is quantized;
- (b) descendant-edge revocation is quantized and counted in kind;
- (c) `B` is corrected.

The new target term that r7 introduced to count (b) is not a sound upper
bound.

---

## 7. T-7 channel proof

### 7.1 Bucket count `B = ⌈H/g⌉ + 1` (brief §13)

Definitions (§9.11):

- `k(t) = ⌊t/g⌋`;
- an act at `t` takes effect at `e(t) = (k(t)+1)·g`;
- admissible acts: `t ∈ [t0, t0+H)`;
- `k_first = k(t0) + 1`;
- `k_last = k(t0 + H − ε) + 1`, where `ε` is the trusted-clock resolution;
- the window is inclusive: `B_actual = k_last − k_first + 1`.

**Proof.** Let `d = k(t0+H−ε) − k(t0)`. Then:

- `k(t0+H−ε) ≤ (t0+H−ε)/g < (t0+H)/g`;
- `k(t0) > t0/g − 1`.

So `d < H/g + 1`. For any real `x`, an integer `d < x + 1` satisfies
`d ≤ ⌈x⌉`:

- if `x` is an integer, `d ≤ x`;
- otherwise `d ≤ ⌊x⌋ + 1 = ⌈x⌉`.

Hence `B_actual = d + 1 ≤ ⌈H/g⌉ + 1 = B` for every `t0`.

| Case | Example | `B_actual` | `B` | OK |
|---|---|---|---|---|
| Start exactly on a boundary, `H` a multiple of `g` | `g=5, H=10, t0=0` | buckets 1..2 → 2 | 3 | ✓ (overcounts) |
| Start just after a boundary, `H` a multiple | `g=5, H=10, t0=0.001` (ε ≪) | 1..3 → 3 | 3 | ✓ (tight) |
| Start just before a boundary | `g=5, H=10, t0=4.999` | 1..3 → 3 | 3 | ✓ |
| `H` not a multiple of `g` | `g=5, H=7, t0=4` | `k(10.999)=2` → 1..3 → 3 | `⌈1.4⌉+1 = 3` | ✓ |
| Minimum `H/g` (`H < g`) | `g=5, H=1, t0=4.5` | `k(5.499)=1` → 1..2 → 2 | 2 | ✓ |
| `H < g`, start on boundary | `g=5, H=1, t0=5` | `k(5.999)=1` → 2..2 → 1 | 2 | ✓ |
| Design fixture | `g=5, H=10, t0=2` | 1..3 → 3 | 3 | ✓ |

The bound may overcount and never undercounts. Two related values carry no
extra information:

- the child ESC creation time, which is never before `e(t)`; a later start
  is chosen by the scheduler, not the parent;
- the derived expiry, which uses the index `k(t)`.

**`B` is valid.**

### 7.2 Formula structure (brief §14)

`C_T7 ≤ N_c·⌈log2(1+n_T·B)⌉ + R_max·⌈log2(1+2·(1+D_max)·B)⌉`

| Aspect | Assessment |
|---|---|
| Two ordered slot sequences, `log2 ∏ ≤ Σ ⌈log2⌉` | Sound, given injectivity from outcomes to slot vectors |
| Count / order | Covered by ordered slots |
| Multiple acts on the same target | Each uses a slot; later ones overcount; harmless |
| Acts impossible after an earlier revocation (e.g. anything after self-renunciation ends the ESC) | Overcount; harmless |
| Number of observers of one act | Same value; 0 extra; correct |
| Cross-sequence interleaving (issuance vs termination order inside one bucket) | Not enumerated. Sound only if the relative order of a T-7 commit and a pending T-9 record is not exposed to descendants. Store revocations are written at `e(t)` by the scheduler, and pending-record ids are not described as descendant-visible, so this appears to hold. It is not stated (see HR9-02) |
| Retries / continuations / forks | Slots: "per task … multiplied by the number of ESCs the task may have" ✓. **Target alphabet: not covered** (HR9-01) |
| Authority vs clearance halves | Counted as distinct (factor 2): conservative |
| Pair-object targets | §21.5 lets an ancestor delegator revoke "clearance edges, authority edges **and pairs**" in its subtree. The alphabet counts only halves. **Undercount** unless pair revocation is shown observationally identical to a half (HR9-01 (b)) |
| Own leaf pair | 2 targets (renunciation of either half). The delegate row allows edges only, not the pair. Correct |

### 7.3 Target universe — the counterexample (HR9-01)

The budget rule (§9.7 step 0):

- `issued_reservations(parent) + 1 + template.child_subtree_budget ≤ budget(parent)`;
- `budget(ROOT ESC) = D_max`;
- `budget(CHILD ESC) = min(template.child_subtree_budget, profile.D_max)`,
  "fixed when the ESC is created";
- the reservation is recorded "against the parent **ESC's** budget";
- "a child's issuances never change its parent's or siblings' remaining
  budget" (TST-CB-106).

A RETRY, CONTINUATION or FORK of a task is a **new ESC** with identical
bindings, including the same `lineage_pair_id` and the same
`DelegatedExecutionBinding` (§9.3 step 12, §9.5 rule 4, §9.8). Nothing in r7
makes such an ESC inherit its predecessor's `issued_reservations` or share a
ledger with it. Each successor ESC therefore starts with a fresh budget.

Construction:

- Root ESC P: `D_max(P) = 4`.
- P issues one child C with a template whose `child_subtree_budget = 3`.
  P reserves `1 + 3 = 4` and the claimed subtree bound (4 pairs) is
  exhausted.
- C's profile allows `max_retries = 2` and `max_forks = 1`, so C's task can
  have `K_C = 4` ESCs, all bound to C's pair.
- Each of those ESCs has a budget of 3 and issues 3 grandchildren (with
  `N_c ≥ 3`, templates with `child_subtree_budget = 0`).

P's lineage subtree now holds `1 + 4·3 = 13` descendant pairs, not 4. P is
"an ancestor delegator in that lineage" (§21.5), so every grandchild edge is
a legal class B target for P. Each grandchild task's own retries compound
the count again at the next depth.

Effect on P's termination slot, with `B = 13`:

| Alphabet | Size | Bits |
|---|---|---|
| Formula `2·(1+D_max)` | 10 | `⌈log2(1+10·13)⌉ = ⌈log2 131⌉ = 8` |
| Actual halves `2·(1+13)` | 28 | `⌈log2(1+28·13)⌉ = ⌈log2 365⌉ = 9` |
| Actual with pair objects `2 + 3·13` | 41 | `⌈log2(1+41·13)⌉ = ⌈log2 534⌉ = 10` |

The formula undercounts each termination slot by 2 bits in this example.
The gap grows with depth and with per-task retry multiplicity.

The same per-ESC reservation also means:

- `D_max` is not "the maximum number of descendant delegations that may
  ever exist in the ESC's delegation subtree" (§9.11);
- the "per root lineage" bound of §32 and INV-CB-106 is not `D_max`. Root
  retries and forks each receive `D_max` of their own.

A retry `P′` of P shares P's pair. If "that ESC's own delegation subtree"
(§21.5) is read by lineage, which is the only structural definition given,
`P′` may also target P's children, so `P′`'s alphabet is larger than
`2·(1+D_max)` even at depth 1.

### 7.4 Verdict

The bucket bound is correct. The per-slot structure is correct. The target
alphabet, and so the second term of `C_T7`, is **not** a true conservative
upper bound on the modeled observables. See HR9-01.

---

## 8. Delayed T-9 effect and frozen-contract compatibility

### 8.1 What the frozen contracts say

v0.2.5 §11 Revocation:

- "**Who:** HUMAN_OWNER (any edge); the edge's delegator; any ancestor
  delegator in that lineage; the delegate may renounce its own edge";
- "**Effect:** immediate at commit; irreversible; idempotent … All
  descendants become `NOT_EFFECTIVE`";
- "**Descendants.** An upstream revocation invalidates descendants **at
  evaluation**".

Q10: "Whole-edge, irreversible, immediate".

§17: `revoke` is "atomic with revocation insert + audit event + watermark
increment".

The JSON manifest lists the authorized revokers and
`delegate_may_renounce_own_edge: true`. v0.2.5.1 contains only pure types
(`RevocationRecord` is v0.2.5.2, not implemented). The v0.2 contract has no
revocation-timing clause.

### 8.2 What r7 changes

For class B/C (model-controlled T-9) acts, r7 does **not** change the
semantics of the v0.2.5 `revoke()` operation or of the evaluator:

- the v0.2.6 revocation path records a durable pending T-9 record;
- it calls the unchanged v0.2.5 `revoke()` at `e(t)` (§9.11, CR-LIN-01);
- that call is immediate at its commit and cascades to descendants at
  evaluation, exactly as v0.2.5 requires.

The frozen text fixes store semantics, what happens **once a revocation is
committed**. It does not fix when a trusted caller acting on an agent's
request must commit it. v0.2.5 defines no agent-facing request interface;
T-9 is a v0.2.6 mechanism.

### 8.3 Classification

The delay is a **usage restriction on when v0.2.6 invokes an unchanged
v0.2.5 operation**. It is the same kind of restriction as the HR5-11 T-9
scoping, which §39.1 already records as "strengthening (usage restriction
on which v0.2.5 revocations an ESC can invoke; no contract change)" and
which HR5–HR8 accepted.

- Owner revocations (the v0.2.5 HUMAN_OWNER revoker) stay immediate
  (class A).
- The v0.2.5 revoker set is not widened.
- Revocation stays irreversible.
- Nothing is re-parented.
- v0.2.6 checks are **stricter** than the v0.2.5 store between `e(t)` and a
  late scheduler write, because pending records are treated as effective
  at `≥ e(t)`. That is an additive conjunct, not a relaxation.

The out-of-limits class C case ("no descendant-visible revocation before
natural expiry") means an agent's renunciation is not written to the store
in that case. This is also a restriction on what an ESC can invoke (the
renouncing ESC still stops at once). It is not an amendment: v0.2.5 grants
the delegate a *permission* to renounce and does not oblige v0.2.6 to
forward every request.

**Verdict: COMPATIBLE. No frozen-contract amendment is required.**

Three precision gaps remain:

- §39.1 has no row for the delayed and out-of-limits-suppressed invocation.
  Its "No v0.2.6 rule conflicts" statement relies on the reader making the
  argument above;
- the RevocationRecord `revoked_at` value and the epoch increment for a
  late or recovered application are unstated;
- the renunciation-record semantics outside limits are unstated.

These are recorded as HR9-03 and HR9-02. None is freeze-blocking, because
the design does not contradict a frozen rule. Each gap is a documentation or
precision gap.

### 8.4 Pending T-9 record (brief §19)

| Property | r7 text | Status |
|---|---|---|
| Durable | "recorded at once as a durable pending T-9 record" | ✓ |
| Append-only | not stated | ✗ (HR9-02) |
| Target fixed | "naming its target and `e(t)`" | ✓ |
| Effect time fixed | `e(t)` recorded | ✓ |
| Survives restart | "A pending record survives restart; one whose boundary has passed is applied immediately on recovery" | ✓ |
| Not cancellable or rewritable by the model | not stated. No cancel operation is defined, and "No un-revoke" covers committed revocations only | ✗ (HR9-02) |
| Exact effect at the boundary even if the scheduler is late | "Every v0.2.6 check at trusted time `≥ e(t)` treats the pending record as effective even if the scheduler has not yet written it, so the effect time is exactly `e(t)` and never depends on scheduler delay" | ✓ |

No scheduler timing channel replaces the bucket timing.

### 8.5 Self-renunciation consistency (brief §20)

r7 states: "descendants depend on their ancestor **pairs** (§34 step 3), not
on the parent ESC's state. §9.3 step 6 'parent must not be REVOKED' means
the parent's pair is ineffective at `now`, as its parenthesis states."
Checked:

- §9.3 step 6 CHILD requires the pair chain, not a LIVE parent ESC;
- §34 step 3 walks `ancestor_pairs_effective`;
- T-7 step 1 requires the **issuing** parent to be LIVE. That only prevents
  the ended parent from issuing more children, which is consistent.

An ENDED parent therefore leaves descendants valid until `e(t)`. **Logically
consistent.**

Two edge cases:

- **Renunciation in the same bucket as a pending child ESC creation.**
  Both take effect at the same boundary. The pending record is effective at
  `≥ e(t)`, so `issue_esc` is denied. The outcome is still an element of the
  counted `(target, bucket)` set.
- **FORK siblings sharing the renounced leaf.** They are not descendants.
  They stop at `e(t)`, not at once, so they get no unquantized signal.
  Correct.

### 8.6 Self-renunciation outside `H` / `R_max` (brief §21)

The act is coherent and compatible with the authority algebra. Not writing
the revocation only leaves an attenuated edge effective until its fixed
expiry, and it never widens anything.

Alternate observable channels:

- **Parent ESC end time.** The renouncing ESC is ENDED immediately. ESC
  status and coarse timestamps are §14.8 control-plane observables. That
  observable already exists for any parent that simply finishes. The same
  model can end its ESC at any time by completing, so self-renunciation adds
  no new value and no new channel. The design's sentence "None of this is
  visible to a descendant" is slightly overstated (HR9-02 asks for a
  qualification), but the channel model does not undercount because of it.
- **Retries of the renouncer's own task.** For the out-of-limits case it is
  unstated whether a durable record blocks a retry from re-binding the
  renounced pair (HR9-02). This affects the durability of a voluntary
  reduction, not a channel. A retry's re-binding is observable only to
  control-plane components.

### 8.7 Class A cannot be forged (brief §22)

The class A triggers are:

- owner acts through the OwnerChannel;
- trusted-clock expiry fixed at issuance;
- agent lifecycle events (registry, CR-04);
- policy, objective or activation revocation (owner acts);
- taint-log loss;
- epoch regression.

T-9 is the only agent entry point to revocation, and every T-9 act is class
B or C (§7.3 T-9: "every T-9 act of an ESC is model-controlled"). A model
can deliberately TERMINATE its own ESC, for example by exceeding the
denied-request rate (§32). That ends the ESC, not a pair, so it has no
descendant-visible effect. The class is fixed by the trusted caller path.
It is never a request field. **✓**

---

## 9. HR8-03 — network taint

| Requirement (brief §25) | r7 | Status |
|---|---|---|
| `L_net_max` persisted before launch | `deliver()`: "record invocation(g) as PENDING with (…, L_net_max, network_destination_set_digest, policy refs …)"; read back after restart (TST-CB-081) | ✓ |
| Authorized-destination digest persisted | `network_destination_set_digest` | ✓ |
| TNL records the connected resource before response bytes reach the worker | "durably records each connected canonical resource BEFORE forwarding any response byte to the worker" (§34, §17.6 rule 3, CR-NET-01) | ✓ |
| Pending invocation reserves ceiling space | `reserved(esc)` = ⊔ of persisted `L_net_max` of PENDING invocations; the tool pre-check includes it | ✓ |
| Other deliveries include the reservation | `request_context` step 7, `deliver()`, §14.3 step 1 | ✓ |
| Actual taint joins the latest durable `H_exec` | transaction 1: "joined against the LATEST durable H_exec … never a pre-tool snapshot" | ✓ |
| Append on exception / timeout / crash / kill / restart | outcome ∈ {SUCCEEDED, TOOL_FAILED, TIMED_OUT, CRASHED, KILLED, OWNING_ESC_REVOKED, OWNING_ESC_TERMINATED, RECOVERED_AFTER_RESTART}; append "before any require or early return, in every ESC state"; transaction 1 "never rolled back by any later DENY" | ✓ |
| Fallback to `L_net_max` | "records lost → conservative maximum" | ✓ |
| Predecessor final taint unavailable until every invocation is accounted | §14.4 "Final H_exec (r7)"; recovery "for every PENDING invocation before any successor ESC of the task is issued" | ✓ |

**Failure path (brief §26).** A tool reads protected network content and
then crashes. Recovery or post-execution runs transaction 1. The TNL
records exist because they were written before any byte was forwarded, so
`delta = ⊔labels(N)` is appended. If the records were lost, `L_net_max` is
appended. `H_exec` gains the taint, and no information-flow history
disappears. **✓**

**Interleaving (brief §27).** Invocation pending with reservation `R`. A
delivery `L2` commits after passing
`within(H ⊔ L2 ⊔ R)`, so `H′ = H ⊔ L2`. The tool then finishes with
`N ⊑ R`. The final taint is `H′ ⊔ N`, joined against the latest `H_exec`.
Because `H′ ⊔ N ⊑ H ⊔ L2 ⊔ R` and the predicate is antitone,
`within(H′ ⊔ N)` holds except for the expiry conjunct. The expiry conjunct
is evaluated at `inv.committed_at`, as documented. No stale snapshot is
used. **✓**

Minor note (INFO, HR9-06): emissions made **while** an invocation is
pending are labeled `H_exec` without `reserved(esc)`. TST-CB-081 correctly
requires the append "before the failure is surfaced". Progress timing of a
running tool is not otherwise excluded from the agent's view. This falls
within the accepted timing residual.

**HR8-03: RESOLVED_IN_R7.**

---

## 10. HR8-04 — RequiredActivationSet

`RequiredActivationSet(op)` is computed by the broker from the sink, the
trusted sink target and the adapter registration. It is never supplied by
the requester (§40.F table). It includes:

- the `BROKER_BASE` wiring;
- CR-CB-04 for model and working-state sinks;
- CR-CB-02 and CR-ART-01 for PERSIST;
- for tool sinks, CR-ING-01, CR-ART-01 for an artifact-producing adapter,
  and the CR-ISO-01 capability mode (plus CR-CB-08 for ISO-SECRET);
- CR-EGR-01 for external sinks;
- the CR-API-01 display mode for `USER_DISPLAY`;
- CR-CB-05 for executor actions;
- containment-only prerequisites.

It is checked at:

- step 0;
- step 5;
- every delivery commit;
- the pre-execution commit, which records `(activation_record_id,
  activation_revision, digests)`;
- `complete_tool_invocation()`, which requires still-valid **and** latest
  revision;
- `ingest_tool_result()`.

If it is undeterminable, the operation is DENY.

**Brief §29.** The broker path is valid and the ISO-TOOL capability-mode
activation is revoked → step 5 DENY (`CB_ACTIVATION_NOT_CONTAINED`).
TST-CB-105 "Component chain". **✓**

**Brief §30 (mid-execution loss).** Transaction 1 still appends the taint.
Transaction 2 fails the snapshot check, marks `ACCOUNTED_NOT_COMPLETED` and
binds nothing. `ingest_tool_result()` refuses both on `invocation_completed`
and on the snapshot. The post-execution commit still occurs. **✓**

**Brief §31 (dynamic expansion):**

| Path | Covered by |
|---|---|
| Redirect | Same sink and adapter; every hop is TNL-mediated and must be destination-authorized (§16.5); no new gated component |
| Provider fallback | Needs a new grant (INV-CB-065), so a new step-5 RAS |
| Tool subprocess | A subprocess means ISO-TOOL (§6.5), so the CR-ISO-01 capability mode is in the RAS |
| Secret resolution | ISO-SECRET + CR-CB-08 |
| User display | CR-API-01 display mode |
| Artifact persistence | CR-ART-01 |
| External egress | CR-EGR-01 |

Behaviour cannot expand beyond the computed set without a new sink target,
which means a new grant, or a different adapter class, which the adapter
registration fixes. The "undeterminable → DENY" rule fails closed.

**HR8-04: RESOLVED_IN_R7.**

---

## 11. HR8-05 — `P_max` and shared quotas

- `P_max` is per ESC. "The parent's proposal counter is incremented in its
  OWN durable commit before evaluation; that commit is not undone by any
  later DENY … read only by this parent ESC" (§9.7 step 0). Step 5 excludes
  it from "nothing exists".
- Every T-7 bound counts issuances only (except the ESC's own `P_max`). The
  window bound is per ESC. The per-lineage bound is a partitioned
  reservation. "No T-7 outcome of an ESC depends on another ESC's issuances
  or denials" (INV-CB-106, §32, §38.2).
- TST-CB-106: the sibling probe outcomes are identical across P's
  variations; the counter survives DENY and restart.

The shared-quota channel HR8-05 named is closed.

*Note:* the partition is per ESC, not per lineage pair. That is what makes
the subtree bound fail under retries (HR9-01). A correction for HR9-01 that
shares a ledger across ESCs of one pair must not reopen an inter-ESC quota
channel; see HR9-01 "Correction".

**HR8-05: RESOLVED_IN_R7.**

---

## 12. HR8-06 / HR8-07

- **HR8-06** (epoch-keyed pools and caches): recorded in §38.2 as a timing
  residual and in §38.1 as optional hardening. No evidence of a larger
  effect: an epoch advance still changes no decision (§31 item 3).
  **RECORDED_ONLY (INFO).**
- **HR8-07** (ConfinementRecord environment and launcher digests): recorded
  in §38.1 as CR-ISO-01 hardening. The record writer is TCB.
  **RECORDED_ONLY (INFO).**

No escalation.

---

## 13. INV-CB-048

The final text requires the documented bound to include "every
agent-controlled child/descendant-visible issuance, cancellation,
self-renunciation and delegated-edge revocation signal permitted by the
policy". It fixes `B = ⌈H/g⌉ + 1`, quantization, the horizon, `R_max`, and
immediate class A.

It then asserts the numeric bound with the target term
`2 · (1 + D_max)`. As shown in §7.3, the policy permits:

- descendant pairs beyond `D_max` in P's lineage subtree, through retries,
  continuations and forks of descendant tasks;
- pair-object revocation targets.

The invariant's own completeness clause is therefore not met by its own
formula.

**INV-CB-048: INCOMPLETE** (HR9-01).

## 14. INV-CB-075

It covers:

- creation;
- every committed delivery;
- denial when `H ⊔ L ⊔ reserved(esc)` exceeds the ceiling;
- `reserved(esc)` defined over persisted `L_net_max`;
- the post-execution append being within the ceiling by construction;
- the impossible case appending and terminating, never dropping.

This is consistent with §14.3, §14.7 and §34. TST-CB-075 r7 is behavioural.

**INV-CB-075: VALID.**

## 15. INV-CB-081

It covers:

- the enforced readable universe;
- the pre-execution checks over ARS, `L_net_max` and other reservations;
- persisted `L_net_max`;
- the post-execution commit for every end state;
- the append first and unconditionally against the latest durable taint;
- the `L_net_max` fallback;
- binding only in the post commit with digest match;
- no owner-ceiling substitute.

The invariant's parenthetical end-state list omits "kill", which §34
includes, but "every end state" governs. TST-CB-081 r7 covers exception,
timeout, kill, crash, interleaving, the `L_net_max` boundary, persistence
and restart.

**INV-CB-081: VALID.**

## 16. INV-CB-105

| Required coverage (brief §10) | Present |
|---|---|
| Exact policy bindings | ✓ "ActivationPolicyBindings (the exact `(kind, id, version, digest)` …)" |
| Global version not a cause | ✓ "A later or different global SecurityPolicyVersion … does not deactivate" |
| Activation lifecycle | ✓ ACTIVE / REVOKED / SUPERSEDED scoped to that activation |
| Rollback | ✓ (d) epoch regression |
| Digest changes | ✓ (b), including a bound policy object's digest |
| Prerequisite activation states | ✓ "its prerequisite activations are valid"; (c) |
| RequiredActivationSet | ✓ "validate **every activation in the operation's RequiredActivationSet**" |

The invalidation list (a)–(d) is exhaustive and agrees with `valid(a, t)`.

**INV-CB-105: VALID.**

## 17. INV-CB-106

It covers:

- idempotency;
- the broker-set proposer;
- single use;
- a complete `T7Policy`;
- a private `P_max` committed before evaluation and not undone;
- `N_c`, `H` and the per-ESC window;
- no dependence on another ESC.

The phrase "per root lineage through a partitioned subtree budget" is true
in that some finite per-lineage bound exists, but that bound is not `D_max`
(§7.3). The invariant does not state `D_max` as the value, so the text is
not false, but HR9-01's fix will touch it.

**INV-CB-106: VALID** (with a dependency on the HR9-01 correction).

---

## 18. LineagePair regression

r7 changes that touch the lineage:

- the pending T-9 effect time;
- the renouncing ESC stopping at once;
- `R_max` / `D_max` checks in T-7 step 0;
- the reservation insert in step 5.

Unchanged:

- no pair search;
- parent-bound pairs;
- the leaf-parent checks;
- `pair.issuer_event == deb.issuance_event`;
- leaf uniqueness;
- the approval digest;
- the ancestor walk;
- rule 5 "revocation of either ends access" (now at `e(t)` for class B/C,
  immediate for class A).

| Attack | Result under r7 |
|---|---|
| Root substitution / sibling substitution / mixed halves | Unchanged checks → DENY |
| Parent revoked (class A) during issuance | Immediate; T-7 step 1 / `issue_esc` step 6 / ancestor walk → DENY |
| Parent renounces (class C) in the same bucket as its T-7 | Pending record effective at `≥ e(t)`; child ESC creation (`≥ e(t_T7) = e(t)`) → DENY |
| Parent renounces in a later bucket | Child may start at `e(t_T7)` and is REVOKED at `e(t)`; revocation is never lost and never reversed |
| Pending record lost across restart | Durable; applied on recovery if `e(t)` passed; v0.2.6 checks treat it as effective regardless of scheduler lag |
| Replay / idempotency | Unchanged |

The delay affects only voluntary, model-controlled reductions, and by at
most `g`. No pair can be bound, shopped or resurrected that could not be
before.

`LINEAGEPAIR R7 REGRESSION-FREE`

(HR9-01 concerns the subtree **budget** and channel accounting, not the
LineagePair binding.)

---

## 19. Read-confinement regression

| Former blocker | r7 status |
|---|---|
| Unknown readable universe → DENY (HR6-01) | Unchanged (§17.6 rule 2a, §17.9, `deliver()` `ars is None → DENY`) |
| No owner-ceiling escape hatch | Unchanged. `L_net_max` and `reserved(esc)` are proven maxima used only for pre-checks and reservations. Labels still come from TNL-recorded resources |
| GitReadClosure (HR6-02) | Unchanged (§17.11) |
| ConfinementRecord | Unchanged. Still required by `complete_tool_invocation()` transaction 2 and `ingest_tool_result()` |
| Level 2R restrictions (HR7-03, HR6-12) | Unchanged (§6.5, §18.5) |

The r7 edits to §17.6 rule 3 and §34 only add accounting. No read path was
widened. **Regression-free.**

---

## 20. Activation regression

| Channel | r7 |
|---|---|
| Global epoch advancement | "An epoch **advance** revokes nothing"; `valid()` checks only `≥` |
| Global SecurityPolicyVersion advancement | Not a conjunct; never compared |
| Unrelated activation approval | Creates a new snapshot; harmless (§40.F, E1, E5) |
| Unrelated policy update | Changes no lifecycle state except an explicitly stated supersession effect |
| Activation lifecycle change | Does not create a new SecurityPolicyVersion |
| T-9 / ordinary revocation | Never deactivates |

No global counter under another name was found. **Regression-free.**

---

## 21. Invariant and test accounting

Counted mechanically from §33 and §36, not from §0.8:

- §33 has **106** invariant rows, IDs 001–106, no duplicates.
- **105 active.** INV-CB-030 is `**withdrawn**`.
- **No new ID** in r7.
- Status column "rev r7": **048, 075, 081, 105, 106** (5 rows). This matches
  §0.8 and the §33 totals paragraph exactly.
- §36 has **105** `TST-CB-NNN` definition rows (lines 5486–5590), all
  inside §36. No duplicates.
- The set difference between active invariant IDs and test IDs is empty:
  exactly one test per active invariant.
- No test-definition row exists outside §36.

| Revised test | Consistent with final invariant text | Behavioural |
|---|---|---|
| TST-CB-048 | Consistent with INV-CB-048 as written. Inherits its gap: no retry/fork-of-descendant fixture and no pair-object target (HR9-01) | Yes (real-store, adversarial decoder) |
| TST-CB-075 | ✓ | Yes |
| TST-CB-081 | ✓ | Yes |
| TST-CB-105 | ✓ Cases A–D, E (digests only), E1–E5, component chain; no global-version equality expectation remains | Yes (real policy store and startup validator) |
| TST-CB-106 | ✓ | Yes |

**TST-CB-048 against brief §23:**

| Required | Present |
|---|---|
| Mid-bucket start; just-after / just-before boundary | ✓ |
| Self-renunciation, authority and clearance halves | ✓ |
| Restart with a pending revocation | ✓ |
| Beyond horizon; beyond `R_max` | ✓ |
| Direct-child cancellation | ✓ (target-choice and r6 clauses) |
| Grandchild / deeper revocation | ✓ |
| Target choice | ✓ |
| Owner revocation not delayed | ✓. System class A (lifecycle, expiry) is not separately tested (minor) |
| `D_max` exceeded | ✓ |
| Decoder / channel bound | ✓, but measured against the formula that HR9-01 shows undercounts |

**TST-CB-105 Cases E1–E5:** all present in §36, and each matches its
requirement:

| Case | Requirement |
|---|---|
| E1 | Unrelated approval → ACTIVE; no 11-vs-13 comparison |
| E2 | Bound dependency revoked → invalid; others ACTIVE |
| E3 | Digest mismatch → invalid |
| E4 | `RETAIN` → ACTIVE and I@4 still evaluated; `INVALIDATE` → deactivated; missing effect → T-5 rejected |
| E5 | A2 approval leaves A1 ACTIVE; A1 revocation leaves A2 ACTIVE |

---

## 22. Dependency graphs

**Build graph (§40.E):** every edge still points to a strictly lower tier.

- GATE-CONTAIN ← EGR-01a (T0), LEG-01a (T1), IFR (T0), LOG-01 (T1),
  act(CR-ISO-01 restriction mode). The restriction modes activate on their
  own merge only.
- r7 added no edge.
- CR-LIN-01 (T4) now also carries the pending-T-9 applier and "the
  renouncing ESC stopped at once". CR-ESC-01 (T6) carries `R_max`
  accounting and bucket-boundary effect.

**Activation graph:** unchanged by r7 apart from wording; acyclic.

**Result: both graphs acyclic; GATE-CONTAIN cycle-free.**

*INFO (HR9-05):* "the renouncing ESC stopped at once", assigned to CR-LIN-01,
needs the ESC store that CR-ESC-01 builds, and CR-ESC-01 depends on
CR-LIN-01. No edge encodes this, so no cycle exists. Placing the ESC-side
effect in CR-ESC-01, or stating that CR-LIN-01 exposes only the pending
store and applier, avoids an implied back-edge.

---

## 23. Frozen-contract compatibility

| Contract | r7 impact | Amendment needed? |
|---|---|---|
| v0.2 | §8/§10 strengthened; no revocation-timing clause exists | No |
| v0.2.3 | Router default never relied on | No |
| v0.2.4 | Identifiers unchanged | No |
| v0.2.5 | §11 `revoke()` semantics (immediate at commit, cascade at evaluation, irreversible, idempotent) unchanged. r7 restricts **when** v0.2.6 invokes it for model-controlled T-9, and suppresses out-of-limits requests. That is a usage restriction of the same kind as HR5-11 (§8.3) | No. §39.1 should state it (HR9-03) |
| v0.2.5.1 | `AuthorityScope`, `RevocationRecord` types unchanged | No |

**No amendment to any frozen v0.2.x contract is required.** AMD-025-01
remains uncreated and unnecessary.

---

## 24. Owner decisions (not made here)

| # | Decision | Genuine policy? |
|---|---|---|
| 1 | `T7Policy` numerical values (`N_c`, `P_max`, `n_T`, `g`, `H`, `R_max`, `D_max`), template contents and `child_subtree_budget` | **Not yet.** The technical rule that turns these values into a sound bound is incomplete. The formula must account for descendant pairs created by retries, continuations and forks, and for pair-object targets (HR9-01). Once that rule is fixed, choosing values is pure policy |
| 2 | ApprovalRequirement vocabulary and each class's requirement set | Yes. Set inclusion is fixed |
| 3 | CR classification from the §40.F procedure applied to reviewed manifests, recording CR-NET-01 `InternalEndpointPolicy` under a gated mode | Yes. R1–R8 and the procedure are deterministic |
| 4 | Each component's `policy_dependencies` and, for each successor policy version, `RETAIN_EXISTING_BINDINGS` vs `INVALIDATE_EXISTING_BINDINGS` | Yes. No default exists, and the lifecycle semantics are fixed |
| 5 | Earlier open dispositions (§44.5: correction dispositions, LineagePair realization, §14.9 default labels, environment vocabulary, network registry pin) | Yes |

---

## 25. New HR9 findings

### HR9-01 — The subtree budget does not bound descendant pairs across RETRY/CONTINUATION/FORK ESCs, and T-9 pair-object targets are uncounted; the `C_T7` target term is not an upper bound

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR8 (HR8-02; the target term r7 introduced)
- **Section:** §9.7 step 0 and step 5 (per-ESC reservation); §9.11
  (`D_max` definition, target universe, formula); §9.3 step 12 and §9.8
  (successor ESCs bind identical fields); §21.5 (revoker rows: "Clearance
  edges, authority edges and pairs in that ESC's own delegation subtree";
  "Targets are limited to … the at most `D_max` descendant pairs"); §14.8;
  §32 (`T7Policy` and per-root-lineage rows); §38.2
- **Invariant:** INV-CB-048 (and INV-CB-106's per-lineage wording)
- **Attack / contradiction:**
  - **(a) Budget reset on successor ESCs.** The reservation is recorded
    against the parent **ESC**. A child ESC's budget is fixed "when the ESC
    is created". A RETRY, CONTINUATION or FORK of a descendant task is a new
    ESC with the same pair and binding, and nothing carries the
    predecessor's reservations forward. With `D_max(P) = 4`, one child C
    with `child_subtree_budget = 3`, and C's task allowing 3 successor ESCs,
    P's lineage subtree reaches 13 descendant pairs (§7.3). P may revoke
    every one as "an ancestor delegator". The alphabet `2·(1+D_max) = 10`
    should be ≥ 28. Retries at each deeper level compound this. The same
    reset gives each retry or fork of the root task its own `D_max`, so the
    §32 "per root lineage" bound is not `D_max`. A successor `P′` sharing
    P's pair can also target P's children if "own delegation subtree" is
    read by lineage.
  - **(b) Pair objects.** §21.5 lets the delegator or ancestor delegator
    revoke **pairs** as well as either edge. The formula counts two targets
    per descendant pair, treating the authority and clearance halves as
    distinguishable. It does not count the pair object and does not show
    that revoking the pair is observationally identical to revoking a half.
- **Impact:**
  - The per-slot termination term undercounts by `⌈log2⌉` of the alphabet
    ratio: 2 bits per slot in the §7.3 example, more with depth.
  - The value the policy store shows the owner at T-5, and which
    INV-CB-048 asserts, is therefore still not a conservative upper bound.
    That is the property HR8-02 required.
  - Confidentiality impact is bounded and of the same order as the accepted
    residual, but the accepted number is wrong.
- **Correction (for the design author; options, not decisions):**
  1. Make descendant accounting per lineage pair or binding rather than per
     ESC, while still meeting HR8-05. For example, a successor ESC inherits
     its predecessor's issued reservations, and a FORK receives an explicit
     partition of the remaining budget at fork time. State that same-task
     sequential inheritance is not an inter-ESC channel, or bound it.
     **Or** have the policy store compute an effective descendant bound
     `D_eff` that multiplies by `1 + max_retries + max_continuations +
     max_forks` at every level, and use it in the target term.
     **Or** restrict class B targets to edges the revoking ESC itself
     issued. The target term then becomes `2·(1 + N_c)` plus successor
     rules.
  2. Either count pair-object targets (`2 + 3·D` targets) or remove pair
     objects from the T-9 target vocabulary (halves only).
  3. Define "that ESC's own delegation subtree" for ESCs that share a pair.
  4. Restate `D_max`, the §32 per-root-lineage row, INV-CB-048 and, if
     needed, INV-CB-106.
  5. Extend TST-CB-048 with a descendant-task retry/fork fixture and a
     pair-object target, with the decoder bound measured over them.
- **Freeze blocker:** YES. It fails the freeze criteria "T-7 channel is a
  true conservative upper bound", "HR8-02 RESOLVED_IN_R7" and "INV-CB-048
  acceptable". The correction is a narrow text change.
- **Implementation blocker:** YES (CR-ESC-01, CR-LIN-01, CR-POL-01)
- **Deployment blocker:** NO

### HR9-02 — Pending T-9 record and out-of-limits renunciation semantics are under-specified

- **Severity:** LOW
- **Category:** NEW (r7 text)
- **Section:** §9.11 "Quantization"; §7.3 T-9; §21.3 rule 5; §21.5; CR-LIN-01;
  INV-CB-090
- **Invariant:** INV-CB-048, INV-CB-090
- **Attack / contradiction:** gaps in the r7 text:
  1. The pending record is not stated to be insert-once and append-only,
     or to be neither cancellable nor rewritable by the model or any
     non-owner path. The channel proof assumes it; the text does not say
     it.
  2. For a class C act outside `H` or beyond `R_max`, it is unstated
     whether any durable record exists, whether it blocks new ESCs of the
     renouncer's task from re-binding the renounced pair (the in-limits
     text says they are blocked), and whether it is ever written to the
     stores.
  3. The `RevocationRecord.revoked_at` value and the §31 epoch increment
     for an application at or after `e(t)` are unstated. v0.2.5 §10 forbids
     a `now` below the store's clock high-water mark, so the write time
     must be the actual time.
  4. INV-CB-090 and INV-CB-066 were not revised to mention the class B/C
     effect time.
  5. The sentence "None of this is visible to a descendant" should say
     that the renouncer's ESC status remains a §14.8 observable, equivalent
     to the parent finishing.
  6. The channel proof's injectivity also relies on T-9 request order and
     pending-record ids not being descendant-visible (§7.2). This is not
     stated.
- **Impact:** implementation drift. A cancellable pending record would not
  enlarge the counted value set, but it would contradict "no un-revoke" in
  spirit. The out-of-limits gap weakens the durability of a voluntary
  reduction only.
- **Correction:** state items 1–6 explicitly. Revise INV-CB-090 and extend
  TST-CB-048 or TST-CB-090 (attempted cancellation of a pending record;
  retry after an out-of-limits renunciation).
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-LIN-01, CR-ESC-01)
- **Deployment blocker:** NO

### HR9-03 — §39.1 has no compatibility row for the delayed invocation of v0.2.5 `revoke()`

- **Severity:** LOW
- **Category:** NEW (documentation of frozen-contract compatibility)
- **Section:** §39.1; §9.11; §21.5; v0.2.5 §11 and Q10
- **Invariant:** INV-CB-090
- **Attack / contradiction:** v0.2.5 §11 says revocation takes "Effect:
  immediate at commit", and the delegate may renounce. r7 postpones, and
  outside limits suppresses, the v0.2.6 invocation of `revoke()` for
  model-controlled T-9 acts. §8.3 argues this is compatible as a usage
  restriction, as with HR5-11. §39.1 records the HR5-11 restriction but not
  this one, and still asserts "No v0.2.6 rule conflicts".
- **Impact:** a reviewer or implementer could read r7 as silently
  redefining v0.2.5 revocation timing. There is no security impact.
- **Correction:** add a §39.1 row: "Model-controlled T-9 revocations are
  invoked on the unchanged v0.2.5 `revoke()` at the bucket boundary, or not
  at all outside limits; owner revocations stay immediate — usage
  restriction; no contract change." Reference v0.2.5 §11 and the JSON
  `revocation` block.
- **Freeze blocker:** NO (compatibility holds; this is documentation)
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR9-04 — Per-object REVOKED / EXPIRED policy lifecycle is not an input to ESC or T-7 effectiveness

- **Severity:** LOW
- **Category:** NEW (interaction of the r7 policy-object lifecycle with
  pre-existing ESC checks)
- **Section:** §29.4 (policy objects and snapshots); §40.F lifecycle table;
  §34 step 2 (`esc.security_policy_version revoked`); §9.3 step 4; §9.7
  step 3
- **Invariant:** INV-CB-034, INV-CB-093
- **Attack / contradiction:**
  - r7 lets the owner revoke an individual object version, for example
    `TaskProfile P@11` or an EnvironmentClass version. It also says a
    snapshot revocation revokes only the objects that snapshot introduced.
  - A LIVE ESC recorded under a later snapshot S13 that carried P@11
    unchanged is checked only for "S13 revoked" (§34 step 2). It keeps
    running under a REVOKED profile.
  - T-7 re-checks "template approved", but a LIVE parent ESC's own REVOKED
    profile or environment version is not an explicit input.
- **Impact:** an owner's emergency revocation of a policy object may not
  stop executions bound to it. Other immediate levers exist (objective,
  pair or activation revocation), and nothing widens, so this is
  availability of the owner's intent, not escalation.
- **Correction:** state whether an ESC's recorded object versions
  (TaskProfile, template, EnvironmentClass, destination authorization) are
  checked for `REVOKED` / `EXPIRED` at every decision and at T-7 (making
  the ESC REVOKED), or state explicitly that per-object revocation affects
  only new bindings and new ESCs.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ESC-01, CR-POL-01)
- **Deployment blocker:** NO

### HR9-05 — CR-LIN-01 scope names an ESC-store effect built later by CR-ESC-01

- **Severity:** INFO
- **Category:** EDITORIAL (DAG hygiene)
- **Section:** §40.B CR-LIN-01, CR-ESC-01; §40.E
- **Invariant:** —
- **Attack / contradiction:** "the renouncing ESC stopped at once" is placed
  in CR-LIN-01 (Tier 4), but the ESC store is CR-ESC-01 (Tier 6, which
  depends on CR-LIN-01). No edge encodes this, so the graph is still
  acyclic.
- **Impact:** none if implementers read it as CR-ESC-01's responsibility.
- **Correction:** move the ESC-side effect to CR-ESC-01, or state that
  CR-LIN-01 provides only the pending store and applier.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR9-06 — Emissions during a pending tool invocation exclude the reservation

- **Severity:** INFO
- **Category:** NEW (residual clarification)
- **Section:** §13.5; §14.7; §34 `emit()`, `complete_tool_invocation()`
- **Invariant:** INV-CB-008, INV-CB-081
- **Attack / contradiction:** while an invocation is PENDING, `emit()`
  labels output `H_exec`, without `reserved(esc)`. The agent cannot see the
  tool's result or failure before transaction 1 (TST-CB-081: the append
  happens "before the failure is surfaced"). It can observe elapsed time.
- **Impact:** within the accepted timing side-channel residual (§38.2).
- **Correction:** optional. Label emissions `⊒ H_exec ⊔ reserved(esc)`
  while invocations are pending, or state the residual.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 1 (HR9-01) · LOW 3 (HR9-02,
HR9-03, HR9-04) · INFO 2 (HR9-05, HR9-06) · total 6.

---

## 26. Design freeze blockers

| ID | Why it blocks freeze |
|---|---|
| **HR9-01** | The r7 T-7 channel bound, which INV-CB-048 asserts and the owner is asked to approve, is not a conservative upper bound. The target term assumes at most `D_max` descendant pairs, but per-ESC budgets reset on successor ESCs of descendant tasks, and T-9 can also target pair objects. HR8-02 is therefore only PARTIALLY_RESOLVED |

**Freeze-standard scorecard (brief §42)**

| Criterion | Status |
|---|---|
| 0 CRITICAL | ✓ |
| 0 HIGH | ✓ |
| 0 freeze-blocking MEDIUM | ✗ (HR9-01) |
| HR8-01 RESOLVED_IN_R7 | ✓ |
| HR8-02 RESOLVED_IN_R7 | ✗ (PARTIALLY_RESOLVED; residual HR9-01) |
| Policy dependency binding coherent | ✓ |
| T-7 channel a true conservative upper bound | ✗ (HR9-01; `B` itself is correct) |
| Delayed class B/C revocation compatible with frozen contracts | ✓ (documentation gap HR9-03) |
| HR8-03 / HR8-04 fixes coherent | ✓ |
| INV-CB-048 / 075 / 081 / 105 / 106 acceptable | ✗ for 048 (INCOMPLETE); 075, 081, 105, 106 VALID |
| LineagePair regression-free | ✓ |
| Read confinement regression-free | ✓ |
| Activation model regression-free | ✓ |
| No frozen-contract amendment required | ✓ |

## 27. Implementation blockers (separate from freeze)

In addition to every row of design §43.1, all of which remain:

- HR9-01 (CR-ESC-01, CR-LIN-01, CR-POL-01);
- HR9-02 (CR-LIN-01, CR-ESC-01);
- HR9-04 (CR-ESC-01, CR-POL-01).

None of the §43.1 machinery exists.

## 28. Deployment blockers (separate)

Every §43.2 row, unchanged. The "live" rows (R-01..R-09, R-11, R-13,
R-22..R-26, R-29, R-30) are pre-existing runtime defects that no design
revision fixes. No HR9 finding adds a deployment blocker.

---

## 29. Final status

r7 fixes what HR8 found in these areas:

- **Activation.** There is one exact-binding model. The global
  SecurityPolicyVersion is audit-only. There is an explicit per-object
  lifecycle with no default supersession effect. Unrelated policy evolution
  leaves activations ACTIVE, and exact dependency loss invalidates them.
  HR8-01 is resolved.
- **Tool network taint (HR8-03).** `L_net_max` is persisted, the ceiling is
  reserved, and the append is first and unconditional against the latest
  `H_exec` on every end state.
- **Activation coverage (HR8-04).** RequiredActivationSet is used
  throughout.
- **Shared quotas (HR8-05).** `P_max` is private and quotas are no longer
  shared.
- **Channel coverage.** Self-renunciation and descendant-edge revocation
  are quantized, horizon-limited, `R_max`-bounded and counted in kind.
  `B = ⌈H/g⌉ + 1` is a proven bound for every start offset.
- **Frozen contracts.** The delayed class B/C effect is compatible: it is a
  usage restriction on when the unchanged v0.2.5 `revoke()` is invoked.
- **Regression.** LineagePair, read confinement and activation show no
  regression. The accounting is exact.

One MEDIUM defect prevents READY. The new target term of the T-7 channel
bound assumes at most `D_max` descendant pairs. Budgets are reserved per
ESC, and retries, continuations and forks of descendant tasks each get a
fresh budget, so the lineage subtree P can revoke exceeds `D_max`. T-9 pair
objects are also uncounted. The bound shown to the owner is therefore still
not a conservative upper bound, which was the purpose of HR8-02. The
correction is a narrow text change. A focused verification of that delta,
together with HR9-02..04, should then suffice.

```text
R7 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

READY would have meant only that the technical design is ready for the
owner's formal freeze decision. It would not have meant frozen,
implementation-authorized, deployed or secure in production.

> No v0.2.6 production implementation has been authorized or created.

---

## Appendix A — Read-only validation

Commands were run from `C:\Users\Gyuro\jarvis-os` with
`.venv/Scripts/python.exe`, before this file was written. The pytest run
started before this file existed.

| Command | Result |
|---|---|
| `python scripts/check_v013_freeze_baseline.py` | exit 0 — `v0.1.3 FREEZE BASELINE CHECK: OK` (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `python scripts/check_v020_contract.py` | exit 0 — `v0.2.0 CONTRACT CHECK: OK` |
| `python scripts/check_v023_router_contract.py` | exit 0 — `v0.2.3 ROUTER CONTRACT CHECK: OK` |
| `python scripts/check_v024_agent_contract.py` | exit 0 — `v0.2.4 AGENT CONTRACT CHECK: OK` |
| `python scripts/check_v025_design_contract.py` | exit 1 — `DISCREPANCY FOUND`, solely 8 × "file outside the v0.2.5.1 allowlist is new/modified" for the eight untracked v0.2.6 documents (expected) |
| `python -m pytest -q -p no:cacheprovider` | **1 failed, 2234 passed, 1 warning** (373 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`: the same expected v0.2.5 allowlist discrepancy caused by the untracked v0.2.6 documents. This HR9 file also appears in its list because the run overlapped with writing it. This matches the HR7/HR8 baseline (1 failed, 2234 passed) |

No validator, test or configuration was modified.

## Appendix B — Integrity

Re-verified at the end of the review (see the terminal report). The design
and HR2–HR8 are unchanged from the §2 hashes. HEAD is unchanged and there
are no tracked changes. The only new file is this HR9 document. No commit,
push or merge was made.
