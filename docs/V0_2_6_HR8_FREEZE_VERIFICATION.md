# Jarvis OS v0.2.6 — HR8 Final Freeze Verification of Design Revision r6

```text
subject                        = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r6)
subject status on entry        = CORRECTED R6 — PENDING HR8 FREEZE VERIFICATION
prior reviews checked          = HR2 (docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md)
                                 HR3 (docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md)
                                 HR4 (docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md)
                                 HR5 (docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md)
                                 HR6 (docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md)
                                 HR7 (docs/V0_2_6_HR7_FINAL_FREEZE_VERIFICATION.md)
review type                    = independent technical freeze verification (read-only)
design_modified                = false
hr2_to_hr7_modified            = false
code_tests_validators_modified = false
opendex_modified               = false
final_status                   = R6 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

Section numbers (§N) refer to the r6 design unless another document is
named. Finding IDs `HR8-NN` are new to this review.

---

## 1. Independence

This session authored **none** of the following:

- design revisions r1, r2, r3, r4, r5 or r6;
- HR2, HR3, HR4, HR5, HR6 or HR7.

It started with no conversation history and had no access to any drafting
or review session. It worked only from repository contents. The design
records (§0.7) that r6 and HR7 were written in the same prior session. This
session is neither of those.

The design's correction record (§0.7), its "corrected"/"closes" wording and
the §44.5 statement "no known freeze-blocking MEDIUM issues after r6" were
**not** treated as evidence. Every conclusion below was re-derived from the
r6 text, and from code at HEAD where a factual claim needed checking.

**Limitation.** This review uses the same model family (Claude) as HR2–HR7.
It is session-independent but not organizationally independent. This is a
process limitation, not a technical defect. The design's recommendation
(§38.2, §44.5) for a human security review before freeze still stands.

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
| Untracked (`git status --short -uall`) | exactly seven v0.2.6 documents: the design, HR2, HR3, HR4, HR5, HR6, HR7 |

This matches the expected state. Nothing was normalized.

**SHA-256 at start of review**

| File | Role | SHA-256 |
|---|---|---|
| `docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md` | r6 design | `1397db59982e3e514d31b686efcdb8a33a74489bea5e6aa5a8d39c447f9057e6` |
| `docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` | HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| `docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md` | HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| `docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |
| `docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` |
| `docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md` | HR6 | `42b170a580dba800fa310735c4ca0267083aa2beab0fb033fbebeeb289b4f07e` |
| `docs/V0_2_6_HR7_FINAL_FREEZE_VERIFICATION.md` | HR7 | `91e8d19eec8e98f38e7203b1f58d5181c2f25329c094de32fef53575fcecad64` |

The HR2–HR6 hashes equal the values HR7 recorded, so those documents are
unchanged since HR7. The design hash differs from HR7's r5 hash
(`cbff474d…`), as expected for r6.

**OpenDex** (`C:\Users\Gyuro\opendex-reference`): HEAD
`3e898343d1127c8d5075b459acdd55da83b83f04` (the value in design §41);
`git status --short` is empty. No OpenDex file was opened or modified.

---

## 3. Materials reviewed

- **r6 design:** read in full (lines 1–6411). This covers §0.7, every
  normative section, the §33 invariant table, the §34 procedure, the §36
  test table, §40.E/§40.F and §43–§45.
- **HR7:** read in full.
- **HR6:** not re-read. HR7 §7 and §22 give the HR6-04 → HR7-01 history
  in enough detail, and the design's §0.6 note records the r6 supersession.
- **HR2–HR5:** headers and hashes only.
- **Code:** `app/authority_contracts/contracts.py::AuthorityScope` still
  carries `objective_ref: ObjectiveRef` and `expires_at: datetime` (lines
  225–226). This is relevant to HR7-11.
- **Mechanical checks of the design text:**
  - §33 has 106 invariant rows, all IDs 001–106, no duplicates. 105 are
    active; INV-CB-030 is withdrawn.
  - The status column reads "rev r6" for exactly 048, 062, 076, 079, 081,
    097, 102, 105, 106 (9).
  - §36 (lines 5130–5337) has 105 test-definition rows: TST-CB-001..106
    without 030, no duplicates. No definition row exists outside §36.

---

## 4. HR7-01 — activation / revocation separation (primary gate)

### 4.1 Three concepts, verified separate

| Concept | r6 text | Separate? |
|---|---|---|
| (A) Monotonic epoch | §31 item 3: "a rollback and staleness anchor, not a revocation signal"; "An epoch **advance** revokes nothing by itself"; only regression is a failure. §40.F `valid(a,t)`: `current_epoch ≥ anchor_epoch ∧ current_epoch ≥ a.monotonic_epoch_at_approval` | ✓ |
| (B) Per-activation lifecycle | §40.F `ActivationLifecycleRecord`: append-only chain per `activation_record_id`, states ACTIVE / REVOKED / SUPERSEDED, a per-activation `activation_revision` ("NOT a global counter"). Changes only by an explicit owner act scoped to that activation | ✓ |
| (C) Ordinary revocation | §7.3 T-9, §21.5 "Effect", §31 item 3, §40.F "Ordinary events": a T-9 or an authority/clearance/pair/grant/objective revocation affects only its lineage and dependants; "never deactivate a component" | ✓ |

The r5 rule "epoch advances past a record's activation epoch → deactivate"
is gone from every normative location. It appears only in historical notes
(lines 285, 5872, 5959). §37 item 47 now forbids it, together with "a
global counter with the same semantics under another name".

### 4.2 The original HR7-01 attack (brief §6)

1. Activation A (CR-CB-04) is ACTIVE.
2. Agent X performs a valid T-9 renunciation.
3. §21.5 increments the global epoch.
4. A is otherwise unchanged.

Evaluating `valid(A, t)`:

- the latest lifecycle record is still ACTIVE, because no owner act
  touched it;
- the digests are unchanged;
- no policy approval was revoked;
- the prerequisites are unchanged;
- `current_epoch ≥ monotonic_epoch_at_approval`, so there is no rollback.

**A remains ACTIVE.** §34 step 0 `activation_state_valid()` passes. No
unrelated gated route or execution stops. Only X's lineage and its bound
ESCs become REVOKED (§21.3 rule 5). TST-CB-105 Case A asserts exactly
this, including across a restart. **✓**

### 4.3 Explicit activation revocation (brief §7)

An owner act appends REVOKED to A's chain. `valid(A)` is then false, and A's
paths deactivate: no further grant or delivery, and A's in-flight ESCs are
TERMINATED. Other activations keep their own chains, so they stay ACTIVE
unless A is one of their declared prerequisites (`valid(B)` requires "every
prerequisite … still active"). TST-CB-105 Case B asserts this. A lifecycle
change by anything other than an owner act is rejected. **✓**, subject to
HR8-01 (§22) on how the policy-version conjunct interacts with a lifecycle
change.

### 4.4 Supersession (brief §8)

- A superseding activation is a **new** `IntegrationActivation` with its
  own `owner_event_id` and all its own bindings. It names its predecessor
  (`superseded_by_activation_record_id`).
- The predecessor's chain gets a SUPERSEDED entry. Lifecycle states are
  "irreversible", and the chain is append-only and hash-linked
  (`prev_entry_digest`, `entry_digest`).
- Replaying revision 1 (ACTIVE) after supersession has two outcomes:
  - inside a consistent store, "latest" is SUPERSEDED, so the replay is
    invalid;
  - through a restore, the store epoch falls below the anchor, because the
    SUPERSEDED act incremented the epoch. That is `CB_EPOCH_REGRESSION`,
    DENY everything.
- Stale lifecycle state therefore fails closed. **✓**

*Minor (not a finding):* uniqueness of `(activation_record_id,
activation_revision)` is implied by the hash chain but not stated as a
constraint. The implementation should enforce it.

### 4.5 Rollback (brief §9)

- An activation is approved at E=50. The restored store reports 42, and the
  anchor requires ≥ 50. Then `current_epoch < monotonic_epoch_at_approval`
  and it is below the anchor: `CB_EPOCH_REGRESSION`, DENY everything, and
  startup fails closed (§40.F, §31 item 4, TST-CB-105 Case C). **✓**
- The current epoch is 51 because of an unrelated revocation. Then
  `51 ≥ 50` is "normal, subject to the other conjuncts", and the activation
  stays valid. **✓**

The distinction is explicit and deterministic: only `<` is an
epoch-related failure.

### 4.6 Verdict

The defect HR7-01 named is **completely removed**: activation validity no
longer depends on the revocation epoch advancing, and every normative
location that encoded the r5 rule is corrected.

A structurally similar problem remains through a **different** global
quantity, the SecurityPolicyVersion (see HR8-01). It is a separate trigger
and is not the defect HR7-01 named, so it is reported as a new finding.

**HR7-01: RESOLVED_IN_R6.**

---

## 5. HR7-02 — ConfinementRecord bindings

r6 adds:

- `worker_identity` (process identity + launcher nonce; the Mediated
  Reader session at Level 1);
- `policy_version`;
- `environment_digest` and `launcher_config_digest`;
- `result_digest` and `output_digests`.

`ingest_tool_result()` now requires:

- `cr.worker_identity == supervised_worker(invocation_id)`;
- `cr.policy_version == ars.policy_version`;
- `digest(content) == cr.result_digest`;
- `invocation_completed(invocation_id)`.

`complete_tool_invocation()` requires the same worker and policy checks and
`every output digest ∈ cr.output_digests`. The tool-result ProvenanceRecord
records `authorized_read_set_id` and `confinement_record_id` (§13.1, §34).
The read-set / confinement identities are bound through
`cr.authorized_read_set_id == ars.id` and the `(esc_id, invocation_id)` ARS
lookup.

**Attack: a CLEAN record of invocation X presented with the result of
invocation Y.**

| Presentation | Blocking check | Result |
|---|---|---|
| `invocation_id = Y`, content of Y, CR of X | CR looked up by Y's id, so X's record is never retrieved; `cr.authorized_read_set_id == ars(Y).id` | DENY |
| `invocation_id = X`, content of Y | `digest(content) ≠ cr(X).result_digest` | DENY |
| `invocation_id = X`, content of X, but ARS lookup for another ESC | `ars.esc_id != esc_id` | DENY |
| Bytes from a different worker process | `worker_identity` mismatch | DENY |

All are `CB_CONFINEMENT_UNVERIFIED`: the result is discarded and nothing is
bound. **✓**

*Note (INFO, HR8-07):* the recorded `environment_digest` and
`launcher_config_digest` are never compared with an expected value.

**HR7-02: RESOLVED_IN_R6.**

---

## 6. HR7-03 — non-filesystem OS state

The §6.5 Level 2R row, §17.9 `ReadableUniverse`, CR-ISO-01 and INV-CB-097
now state three things.

First, a worker can read **no** OS state except these four sets:

- (a) its AuthorizedReadSet view;
- (b) TNL-mediated network resources;
- (c) its fresh write view;
- (d) its runtime image.

Second, every one of these channels must be closed or proven free of
protected information:

- the registry;
- the clipboard;
- desktop/window/UI objects;
- other processes' information and memory;
- named kernel objects;
- shared memory;
- other components' pipes and IPC endpoints;
- `/proc`, sysfs and device/host information.

Third, the fail-closed rule is explicit: "A channel neither closed nor
proven ⇒ ReadableUniverse(x) is unknown ⇒ DENY before execution" (§17.9,
also §6.5 and TST-CB-097).

This is the required security property, stated as a closure rule rather
than an enumeration. A channel the list happens to omit still falls under
"no OS state other than (a)–(d)". That makes it a sufficiently precise
design requirement. The implementation obligation sits in CR-ISO-01.
TST-CB-097 (iso) plants protected markers in the listed channels.

**HR7-03: RESOLVED_IN_R6.**

---

## 7. Runtime image (brief §17)

| Requirement | r6 | Status |
|---|---|---|
| Read-only | "a read-only, digest-pinned runtime image" (§6.5) | ✓ |
| Digest-pinned | ✓ (`runtime_image_ref` in the ARS and ConfinementRecord) | ✓ |
| Explicitly classified non-protected | "carries an explicit owner-approved non-protected classification" (§6.5, INV-CB-097) | ✓ |
| Outside managed stores, `.env`, database, repository roots | "lies outside every managed store, `jarvis.db`, `.env` and every repository root" (§6.5) | ✓ |
| Copied repository content not an untracked channel | "content derived from a `REPOSITORY` or any other protected compartment is not eligible for the image without" that classification; "registered, proven free of protected content" | ✓ |

The image is excluded from `AccountedReadUniverse` only because it is
registered, digest-pinned, proven free of protected content **and**
classified. A copy of repository content is therefore either classified by
an owner act bound to that image, or ineligible (DENY). It cannot become an
untracked read channel. TST-CB-097 covers an unclassified
`REPOSITORY`-derived image.

---

## 8. HR7-04 — T-7 policy values and `B`

Every channel variable is an owner-approved `T7Policy` value fixed before
execution (§9.4, §9.11, §32, INV-CB-048):

| Variable | Definition | Missing → |
|---|---|---|
| `N_c` | `= max_child_issuances` | T-7 ineligible (`CB_POLICY_UNAPPROVED`, §9.7 step 0) |
| `P_max` | `≥ N_c`; proposals evaluated, issued or denied | ineligible |
| `n_T` | `= |child_delegation_templates|`, finite, bounded (§32) | ineligible |
| `g` | bucket granularity of the trusted clock, `> 0` | ineligible |
| `H` | decision horizon for T-7 and parent-initiated child cancellation | ineligible |
| `B` | `⌈H/g⌉`, derived, never chosen | — |

No model-selected bound exists.

The quantization points are:

- child ESC creation only at the next bucket boundary (§9.3 step 12);
- expiry uses `bucket(now)`;
- a parent's cancellation of edges it delegated takes effect at the next
  boundary (§7.3 T-9).

TST-CB-048 exercises every bound.

What remains incomplete is the **coverage** of the channel model. Two
parent-initiated, child-observable revocation paths are neither quantized
nor counted, and `B` is off by one for an unaligned horizon (HR8-02).

**HR7-04: PARTIALLY_RESOLVED** (residual HR8-02).

---

## 9. HR7-05 — proposer identity

- §9.6 defines `proposer_esc_id | OWNER_CHANNEL_SESSION` as "BROKER-SET
  metadata, never content — equal to the proposal item's store-set
  `created_by_esc` (§12.1)".
- §9.7 step 2 compares `item_store.created_by_esc(proposal_ref) ==
  parent_esc_id`. It never reads a content field.
- §12.1 makes `created_by_esc` a broker field.

**Attack:** P2 writes a proposal whose text claims `proposer_esc_id = P1`,
and P1 cites it. The broker-set creator is P2, so the result is DENY
(`CB_MALFORMED_REQUEST`). TST-CB-106 r6 asserts this case and its mirror.
INV-CB-079 and INV-CB-106 state the rule.

**HR7-05: RESOLVED_IN_R6.**

---

## 10. HR7-06 — approval requirements

The attenuation rule:

- `ApprovalRequirements` is a finite set over a closed, versioned
  vocabulary.
- `ApprovalClass = (id, policy_version, requirements, requirements_digest)`.
- Attenuation is `requirements(child) ⊇ requirements(parent)`, a partial
  order. An incomparable or smaller set is DENY.
- The ordinal is withdrawn (§9.10, §37 item 48).
- It is applied in T-7 step 4 and re-checked in ESC Issuer step 5.

**Test (brief §23):**

| Parent requires | Child requires | Result |
|---|---|---|
| {OWNER_CONFIRMATION, HIGH_RISK_REVIEW} | {OWNER_CONFIRMATION} | ⊉ → DENY (`CB_APPROVAL_NOT_ATTENUATED` / `ESC_APPROVAL_NOT_ATTENUATED`) ✓ |
| {OWNER_CONFIRMATION, HIGH_RISK_REVIEW} | {OWNER_CONFIRMATION, HIGH_RISK_REVIEW, SECOND_FACTOR} | ⊇ → passes this dimension ✓ |
| Incomparable sets under any label (LOW/HIGH) | | DENY ✓ |

**Version pinning (brief §24):**

- The ESC records `approval_class = (approval_class_id, policy_version,
  requirements_digest)` (§9.2).
- T-7 and the ESC Issuer compare against "the parent's RECORDED class …
  never the id re-read under a later policy" (§9.3 step 5, §9.7 step 4,
  §9.10).
- A later redefinition with fewer requirements is compared against the
  recorded set and is DENY (TST-CB-076 r6).
- The child side is evaluated at T-7 under the current policy and again at
  `issue_esc` under the versioned profile ref. Both checks must pass, so a
  redefinition between them fails closed.

**HR7-06: RESOLVED_IN_R6.** Attenuation is sound.

---

## 11. HR7-07 — containment-only classification

### 11.1 R1–R8 and the procedure

§40.F defines R1–R8 and a first-match procedure applied per CR and per
mode: activation-gated → trust anchor → containment-only → owner-control.
The procedure decides from the reviewed manifest, not the CR name. A
mismatch reclassifies the CR, "never downwards" (§37 item 49). The
procedure is deterministic given a manifest.

### 11.2 Attempts to expose a capability through a containment-only CR (brief §25)

| Attempt | Blocking property |
|---|---|
| New agent-visible API / route | R1 |
| New tool / adapter | R1 |
| New destination | R2 |
| New persistent sink | R3 (TCB-only stores allowed only if agents/models cannot reach them except through gated paths) |
| Broader filesystem access | R4 |
| Broader network access | R2 (only narrows or mediates) and R7 (TCB control traffic only, covered by owner authorization) |
| New authority / clearance / destination authorization / approval / policy | R5 |
| Model-call capability | R1 (model capability), R2 (new model) |
| Broker-labeled content to a live component | R6, and rule 1 of the procedure (activation-gated) |

A mode with any such surface fails R1–R8. Rule 1 then makes it
activation-gated. **✓**

### 11.3 CR-ISO-01 mode by mode (brief §26)

| Mode | Classification in r6 | Correct? |
|---|---|---|
| ISO-TCB Level 2 store-owning broker process | Containment-only under R7 (local, authenticated, TCB-only IPC; agents reach it only through the TCB harness) | ✓ removes agents' DB handles; carries no new capability |
| Level 2R Tool Launcher / restricted-worker mechanism and runtime image | Containment-only ("enables no adapter by itself") | ✓ |
| ISO-TOOL adapter enablement, ISO-SECRET, ISO-CONN, ISO-DEV | Activation-gated (§40.E, §40.F table) | ✓ |
| CR-CB-08 (secret-resolving adapters) | Activation-gated (rule 1) | ✓ |

### 11.4 CR-NET-01 and CR-ACT-01 (brief §27)

**CR-NET-01, mediation mode.** The TNL sits on an existing outbound path
and only narrows it: canonicalization, deny rules and pinned connect (R2).
Its new egress, upstream resolver queries, goes only to owner-configured
resolvers and only for already-authorized names (R7). With no resolver
configured it denies everything. This satisfies R1–R8.

CR-NET-01 also defines `InternalEndpointPolicy` records. An internal
endpoint is a new reachable destination. The deterministic procedure
already makes any manifest surface that *enables* such an endpoint
activation-gated (rule 1). In practice it is usable only by adapters that
are themselves gated (CR-ING-01). This is not a defect. For clarity the
owner-decision 3 review should record the internal-endpoint capability as
part of a gated mode, not as "mediation".

**CR-ACT-01.** The validator, manifests and lifecycle records only refuse
or deactivate (R8). The owner act that *creates* an IntegrationActivation
is a T-5 policy act (CR-POL-01, a trust anchor). Each activated component
is still classified by its own manifest. This satisfies R1–R8.

### 11.5 GATE-CONTAIN cycle (brief §28)

GATE-CONTAIN depends on:

- EGR-01a, LEG-01a, IFR and LOG-01 (all containment-only, activating on
  merge);
- "ISO for the path being activated". The §40.F table defines this as the
  isolation **level**, i.e. `act(CR-ISO-01 restriction modes)`.

The ISO capability-enablement modes depend on GATE-CONTAIN and on
`act(CR-ISO-01 restriction modes)`. None of the gate's own prerequisites
needs the gate in its restriction-only mode. **Acyclic.**

*Editorial suggestion (not a finding):* §40.E line 5651 should read
"(+ act(CR-ISO-01 restriction mode providing that level))" so that the
acyclicity does not depend on the §40.F table.

**HR7-07: RESOLVED_IN_R6.** Classification is deterministic and, on the
manifests described, safe.

---

## 12. HR7-08 — §34 procedure

| Required element | r6 | Status |
|---|---|---|
| Activation check before any context decision | `request_context` step 0: `activation_state_valid(BROKER_PATH, now)`; re-run by `deliver()` (steps 0,2,3,4,5,7) and by `complete_tool_invocation()` (steps 0,2) | ✓ (scope of "path": HR8-04) |
| Pre-execution tool commit | `deliver()`: ARS bound, `L_net_max` computed, flow and ceiling checks over ARS ∪ `L_net_max`, ARTIFACT_READ taint for ARS entries, invocation recorded PENDING, then release | ✓ |
| `complete_tool_invocation` post-execution commit | Separate serialized transaction after the worker exits: revalidation, CR validation, `⊔labels(N) ⊑ L_net_max`, network taint extension, output digest check, derivation and binding, COMPLETED | ✓ |
| `L_net_max` | "proven maximum (§17.9) of the source-policy labels of every canonical destination the invocation may reach"; "a destination without a known label is not reachable"; undeterminable → DENY | ✓ |
| Post-execution network taint extension | `taint_log.append(…, delta=⊔labels(N))`, "always, result-returning or not" | ✓ with edge cases (HR8-03) |

**Attack (brief §29):** a tool reaches an authorized network source after
initial approval.

1. The pre-execution check already included `L_net_max ⊒ label(source)`.
2. The TNL records the connection (it is the only network path).
3. `complete_tool_invocation` appends `label(source)` to H_exec **before**
   any artifact is bound. `ingest_tool_result` refuses until
   `invocation_completed`, so the taint is in place before any result can
   be ingested or delivered.

**✓**

**Network maximum (brief §30).** `L_net_max` is computed from the source
policies of the authorized destination set. That set is finite, because
destination authorizations bind exact `(scheme, host, port)` and redirect
hops must themselves be authorized (§16.5 item 2). It is a proven maximum,
not a guessed ceiling. A recorded network label outside `L_net_max` gives
`CB_CONFINEMENT_UNVERIFIED`, and no output is bound. Since the TNL connects
only to authorized destinations, that case arises only from a policy change
between the two commits.

**HR7-08: RESOLVED_IN_R6.** The requested elements are all present. Two new
LOW precision gaps are recorded as HR8-03 and HR8-04.

---

## 13. HR7-09, HR7-10, HR7-11

### HR7-09 — INV-CB-102

Final text (§33): authorization of `(scheme, host, port)` "before any
resolution (an unauthorized name causes no DNS query)".

| Required clause | Present |
|---|---|
| Destination authorization before DNS | ✓ |
| Trusted resolver only | ✓ ("resolution happens only through the trusted resolver") |
| Resolver upstream only to owner-configured resolvers | ✓ |
| No tool/library/env/DoH override | ✓ ("never a resolver chosen by a tool, library, environment variable or DNS-over-HTTPS") |
| Pool requester scope | ✓ (adapter, internal-endpoint policy) |
| Policy version | ✓ |
| Revocation state | ✓ (epoch in the pool key; "revocation state is re-checked in every delivery commit") |
| No uncontrolled second resolution | ✓ |
| Peer check, redirect/new-connection re-validation | ✓ |

**INV-CB-102: VALID.** **HR7-09: RESOLVED_IN_R6.** TST-CB-102 r6 adds the
env/library/DoH and revoked-authorization pool cases.

### HR7-10 — synthetic Git view availability

§17.11 and §38.2 now state the availability cost: trees and the index name
every tracked path, so a commit in a tree that also holds RESTRICTED
content yields RESTRICTED outputs. Confidentiality is unchanged and
conservative. This is correctly **not** a freeze blocker.

**HR7-10: RECORDED_ONLY** (informational; the requested note is present).

### HR7-11 — template `objective_ref`

- §9.11: `authority_scope` is an "exact v0.2.5.1 value except expires_at
  and objective_ref (both derived at T-7 … objective_ref = parent ESC's)".
- §9.7 step 4: `objective_ref = parent.objective_ref  # derived, never
  fixed in the template`.
- TST-CB-079 r6 checks that a template storing a different `objective_ref`
  still yields the parent's.

A template cannot be replayed across objectives. The v0.2.5.1
`AuthorityScope.objective_ref` field is unchanged (verified in code).

**HR7-11: RESOLVED_IN_R6.**

---

## 14. T-7 residual channel (brief §19–§21)

### 14.1 Is the stated bound an upper bound on the stated choices?

The stated observable per issued child is:

- the template `t` (`n_T` values);
- the issuance bucket `b` (`B` values);
- the cancellation value `c ∈ {never} ∪ B buckets`.

A parent's complete observable T-7 outcome is a sequence of at most `N_c`
such triples, ordered by issuance. This sequence determines:

- issue or don't-issue per slot;
- the child count;
- the order, including any within-bucket order revealed by store-generated
  ids.

Map each outcome injectively to a slot vector of length `N_c`: slot `i`
holds `⊥` or `(t, b)`, and separately `c`. The number of distinct outcomes
is then at most `((1 + n_T·B)·(1 + B))^{N_c}`. Since
`log2(xy) ≤ ⌈log2 x⌉ + ⌈log2 y⌉`, the capacity satisfies

`C_T7 ≤ N_c · (⌈log2(1 + n_T·B)⌉ + ⌈log2(1 + B)⌉)`.

The formula overcounts a cancellation for a "don't-issue" slot and a
cancellation bucket before issuance. That is harmless, because the formula
is conservative. **For the signals the design enumerates, the bound is a
sound upper bound.**

| Signal (brief §20) | Covered |
|---|---|
| Ordering | ✓ (ordered slot vector) |
| Child count | ✓ |
| Issue / don't issue | ✓ (the `1+` term) |
| Template | ✓ |
| Issuance timing | ✓ (bucketed), subject to the off-by-one below |
| Cancellation (direct child edge) | ✓ (bucketed `1 + B` term) |

The design does not claim zero capacity (§9.11 "The channel is **not
zero**", §14.8, §38.2, §37 item 44).

### 14.2 Omitted signals

Three signals fall outside the stated bound. They are reported as HR8-02.

**(a) The parent's self-renunciation cascades to every descendant,
unquantized.**

- T-9 lets the delegate "renounce its own clearance edge or authority edge
  of its own ESC" (§21.5 table).
- §21.3 rule 5: revoking a pair's edge makes the pair ineffective and
  "Descendant pairs become ineffective with it".
- The children's ESCs are REVOKED on their next check (§34 step 3 ancestor
  walk, INV-CB-066), so their emissions stop.

The bucket rule covers only "a parent's revocation of edges it delegated
to a child" (§7.3 T-9, §9.11). The horizon `H` also covers only "T-7
issuance and parent-initiated child cancellation". A renunciation of the
parent's **own** leaf is neither, so it takes effect immediately and at any
time while children live. Receivers at the children's destinations observe
the stop time at their own resolution. The information is roughly
`log2(child lifetime / observation jitter)` bits per parent ESC, with no
`B` bound.

**(b) Revocation of deeper descendants' edges, unquantized.**

§21.5 lets "the edge's delegator, **or an ancestor delegator** in that
lineage" revoke edges "in that ESC's own delegation subtree". A parent P can
therefore revoke the edge its child C delegated to a grandchild G. That is
not "an edge it delegated to a child", so it is not bucketed and not
counted. G's destinations observe it.

**(c) `B = ⌈H/g⌉` undercounts by one for an unaligned horizon.**

`bucket(now)` truncates the trusted clock to multiples of `g`, but the
horizon starts at `parent.created_at`, which is not bucket-aligned. An
interval `[c, c+H)` meets up to `⌈H/g⌉ + 1` buckets. Example: `g = 5`,
`H = 10`, `c = 2` gives issuance buckets {0, 1, 2}, three values against
`B = 2`. The per-decision timing term is understated, most visibly for
small `B`.

Because of (a) and (b), INV-CB-048's statement "the T-7 channel is bounded
per parent ESC by `N_c · (…)`" is false as written. The value the policy
store would show the owner at T-5 (owner decision 1) is not an upper bound.

### 14.3 `P_max` (brief §21)

Within one parent, denied proposals create nothing and are invisible to
children and destinations. Their timing effect is absorbed because child
creation is quantized. The r6 "0 additional" row is correct **for
children and destinations**.

Denials do become observable through a **shared** quota. The per-root-lineage
and per-window bounds (§9.7 step 0, §32, INV-CB-106) are shared among ESCs
of one root lineage. A sibling S that probes T-7 learns from its own
`CB_RESOURCE_BOUND_EXCEEDED` when P's issuances consumed the shared quota,
at P's unquantized commit time. If the lineage or window bound also counts
*evaluated proposals*, S also learns P's denied-proposal count. The design
does not say which quantity these bounds count.

This inter-ESC channel is bounded by S's own probe budget (`P_max(S)` binary
outcomes). It is not counted or stated anywhere, so it is recorded as LOW
(HR8-05).

---

## 15. Approval attenuation

See §10. Sound. The owner decision (vocabulary and class requirement sets)
is pure policy content once the set-inclusion rule is fixed, and the design
fixes it.

---

## 16. Containment-only classification

See §11. Deterministic and safe on the described manifests. The owner
decision (outcome of the procedure) is legitimate policy.

---

## 17. §34 tool / network procedure

See §12. The pre- and post-execution commits are coherent in structure. Two
LOW precision gaps remain:

- the taint-ceiling claim across interleaved deliveries, the conditional
  append and the unpersisted `L_net_max` (HR8-03);
- the single `BROKER_PATH` activation check (HR8-04).

---

## 18. INV-CB-102

VALID (see §13).

---

## 19. INV-CB-105

Brief §13 requires the invariant to state each of the following. Checked
against the final text:

| Required statement | INV-CB-105 text | Present |
|---|---|---|
| Unrelated epoch advance does not invalidate | "an unrelated monotonic epoch increase … does not deactivate an IntegrationActivation" | ✓ |
| Unrelated T-9 does not invalidate | "a T-9 renunciation or any ordinary authority, clearance, pair, grant or objective revocation does not deactivate" | ✓ |
| Explicit lifecycle revocation does | "(a) an explicit owner lifecycle change (REVOKED/SUPERSEDED) scoped to that activation" | ✓ |
| Rollback does | "(d) epoch regression (DENY everything)"; "has not regressed below the anchor or `monotonic_epoch_at_approval`" | ✓ |
| Digest mismatch does | "(b) a changed bound digest" | ✓ |
| Real prerequisite loss does | "(c) loss of a real prerequisite (then the affected gated paths deactivate or the runtime stops)" | ✓ |
| Startup and runtime revalidation | "startup and every broker decision validate this state" | ✓ |

The invariant gives an **exhaustive** invalidation list: "it becomes
invalid only through (a)…(d)". That list agrees with the normative
predicate `valid(a, t)` in §40.F.

**INV-CB-105: VALID.** It is no longer AMBIGUOUS.

However, TST-CB-105 Case E, §35.2, §30.1 and §40.F startup step 4 add a
policy-version equality condition. That condition is **not** in INV-CB-105
or `valid(a, t)` and contradicts both. This is HR8-01; the fix belongs in
those texts, not in the invariant.

**TST-CB-105 (brief §14):**

| Case | Present in §36 | Correct |
|---|---|---|
| A — unrelated T-9 → ACTIVE | ✓ (plus owner revocation of an unrelated pair/grant/clearance/objective; restart) | ✓ |
| B — explicit revocation → deactivate | ✓ (others stay ACTIVE; non-owner lifecycle change rejected) | ✓ |
| C — rollback → DENY | ✓ | ✓ |
| D — prerequisite loss → deactivate / fail closed | ✓ (Monitor stop, EGR-01a disabled, LOG-01 failure, isolation unavailable, policy version revoked) | ✓ |
| E — changed code/manifest/config digest → old activation invalid | ✓ | ✓ for digests; **✗ for the "(or a different policy version …)" clause** (HR8-01) |

The HR7-01 rule ("epoch advances past … → deactivated") is explicitly
withdrawn from the test. TST-CB-105 no longer encodes **that** defect.

---

## 20. LineagePair regression

r6 changes relevant to T-7 and the ESC Issuer:

- step 0: `T7Policy` completeness, the horizon and `P_max`;
- step 2: `created_by_esc`;
- step 4: derived `objective_ref` and set-inclusion approval;
- ESC Issuer step 5: set semantics;
- ESC Issuer step 12: child ESC not before the next bucket boundary.

§9.3 step 6, §21.3 and the pair digest are unchanged. No check was removed.

| Attack | Blocking check (r6) | Result |
|---|---|---|
| Root substitution | CHILD path reads only `deb.child_lineage_pair_id`; `pair.parent_pair_id == parent.lineage_pair_id`; leaf parents = the parent's leaves; ROOT requires `parent_pair_id None ∧ issuer_event == admission event ∧ root_task_id == tcr.task_id` | DENY |
| Sibling substitution | `deb.task_id == tcr.task_id ∧ deb.child_profile_ref == tcr.task_profile_ref`; `pair.issuer_event == deb.issuance_event`; leaf uniqueness | DENY |
| Mixed authority/clearance | Both leaves only from the pair; each leaf in at most one pair; consistency of delegate/delegator/objective | DENY |
| Parent revocation | T-7 step 1 (parent LIVE, ancestors effective); `issue_esc` step 6 (parent not REVOKED); §34 step 3 ancestor walk; r6 bucket delay adds a window in which revocation also denies the child ESC | DENY |
| Grandchild delegation | Each generation checked against its immediate parent; transitive | Only the exact chain binds |
| Replay | Step 0 returns the existing binding (idempotent; `issue_esc` re-checks); a foreign parent is DENY; `proposal_ref` single-use; ids never reused | DENY / idempotent |

`LINEAGEPAIR R6 REGRESSION-FREE`

---

## 21. Read-confinement regression

| Former blocker | r6 status |
|---|---|
| Conservative-ceiling fallback (HR6-01) | Not reintroduced. `L_net_max` is a proven maximum over a finite, policy-labeled, TNL-enforced destination set, used only for pre-execution flow and ceiling checks. Labels still come from the TNL-recorded set, and results need a valid ConfinementRecord. §17.6 rule 2a, §17.9 and INV-CB-097 are unchanged in substance |
| Unknown readable universe executes | Not reintroduced. `ars is None → DENY(CB_READ_SET_INCOMPLETE)` before execution; r6 adds the OS-state closure rule, which only strengthens it |
| Git partial provenance (HR6-02) | Not reintroduced. §17.11 is unchanged except the availability note |
| Unconfined tool execution | Not reintroduced. §6.5 "no third option" is unchanged |

HR6-01 and HR6-02 remain closed.

---

## 22. Invariant audit

### 22.1 Accounting (counted from §33, not from §0.7)

- 106 invariant rows, IDs 001–106, no duplicates.
- **105 active**; INV-CB-030 is withdrawn and not reused.
- **No new ID** in r6.
- Status column "rev r6": **048, 062, 076, 079, 081, 097, 102, 105, 106**
  (9).

This matches §0.7 and the §33 totals paragraph exactly.

### 22.2 r6-revised invariants

| ID | Class | Reason |
|---|---|---|
| INV-CB-048 | **INCOMPLETE** | Every `T7Policy` variable, bucket quantization and the cancellation term are present. But the claim that the T-7 channel "is bounded per parent ESC by `N_c · (…)`" omits parent self-renunciation and subtree revocation (unquantized, cascading to descendants), and `B` is off by one for an unaligned horizon (HR8-02) |
| INV-CB-062 | **VALID** | Enforced universe; ConfinementRecord with worker, policy and result-digest match; provenance references; proven maximum only for untrusted connectors |
| INV-CB-076 | **VALID** | Requirement-set inclusion against the recorded class; every other attenuation dimension unchanged |
| INV-CB-079 | **VALID** | Broker-set creator; template-derived scope, clearance, redelegation, expiry and `objective_ref` |
| INV-CB-081 | **VALID** | Pre-execution flow and ceiling over ARS ∪ `L_net_max`; post-execution taint by TNL labels "whether or not a result is returned"; outputs only in the post commit with digest match. The §34 pseudo-code does not fully honour "whether or not" on failure paths (HR8-03), but the invariant text is correct |
| INV-CB-097 | **VALID** | Four readable sets, "no other OS-readable state", closed-or-proven else DENY; runtime-image classification; full ConfinementRecord binding |
| INV-CB-102 | **VALID** | See §13 |
| INV-CB-105 | **VALID** | See §19. Exhaustive invalidation list consistent with `valid(a, t)`. The conflicting policy-version condition lives in other texts (HR8-01) |
| INV-CB-106 | **VALID** | Idempotency, broker-set proposer, single use, `T7Policy`, bounds. Which quantity the lineage/window bounds count is unstated (HR8-05, LOW) |

None of these is REDUNDANT or UNSOUND.

The other invariants touched by r6 prose (003–005, 021, 053, 066, 075, 090)
were read for coherence with §21.5 and §31. INV-CB-090 "increments the
epoch" is now harmless, because §31 item 3 defines the epoch as a rollback
anchor. INV-CB-075 is affected only through HR8-03.

---

## 23. Test audit

- §36 contains exactly one normative definition row per active invariant:
  105 rows, TST-CB-001..106 without 030. No row is defined outside §36.
- Rows marked (rev r6) or carrying an r6 clause: 048, 062, 076, 079, 081,
  097, 102, 105, 106. These match the revised invariants.

| Test | Behavioural? | Gap |
|---|---|---|
| TST-CB-048 | Yes: adversarial decoder, bound per variable, bucket-aligned observation | No case for parent self-renunciation or subtree revocation timing, or for an unaligned horizon (HR8-02) |
| TST-CB-062 | Yes: wrong digest, worker or policy → discarded; provenance ids | — |
| TST-CB-076 | Yes: the HR7-06 examples, incomparable classes, redefinition | — |
| TST-CB-079 | Yes: derived `objective_ref` | — |
| TST-CB-081 | Yes: network-sourced taint without a result, ceiling DENY, outside-`L_net_max` label, post-commit binding, ESC revoked mid-run | No interleaved-delivery or failure-path taint case (HR8-03) |
| TST-CB-097 | Yes, (iso): OS-state channels with planted markers; unclassified image; record fields | — |
| TST-CB-102 | Yes: zero DNS queries, env/library/DoH resolvers, revoked authorization on a pooled connection | — |
| TST-CB-105 | Yes: cases A–E, manifest classification fixtures, step-0 behaviour | Case E's "(or a different policy version …)" clause encodes HR8-01. No case that a new SecurityPolicyVersion (e.g. approving a second activation) leaves existing activations ACTIVE |
| TST-CB-106 | Yes: broker-set proposer, `T7Policy`, `P_max` | — |

Every test exercises behaviour against real stores or boundaries, not
document text. TST-CB-105 cases A–D and the OS-state case of TST-CB-097 are
required to run against the real boundary, policy store and startup
validator.

---

## 24. New HR8 findings

### HR8-01 — IntegrationActivation policy-version binding is contradictory; one reading makes every policy approval deactivate every activation

- **Severity:** MEDIUM
- **Category:** NEW (in the r6 activation text; same property class as HR7-01)
- **Section:** §40.F `valid(a, t)` vs. §40.F "Startup validation" step 4;
  §35.2 `CB_ACTIVATION_NOT_CONTAINED`; §30.1 `INTEGRATION_ACTIVATED`;
  TST-CB-105 Case E; §29.4 / CR-POL-01 (IntegrationActivation and
  lifecycle records live in the policy store and are approved by T-5);
  §37 item 47
- **Invariant:** INV-CB-105 (whose own text is consistent; the tests and
  procedure contradict it)
- **Attack or contradiction:**
  1. `valid(a, t)` requires only that "a.security_policy_version's approval
     is not revoked, and the active policy still contains a". INV-CB-105
     lists the invalidation causes (a)–(d) as exhaustive, and none is "the
     policy version advanced".
  2. Four other normative places require the running policy version to
     **equal** the recorded one:
     - TST-CB-105 Case E: "an activation record approved … is presented
       with X′, M′, S′ or C′ (**or a different policy version**,
       prerequisite digest or isolation level) → the old record is
       invalid";
     - §35.2: "its record does not match the recomputed code, manifest,
       migration-set or configuration digests, **policy version** or
       prerequisites";
     - §40.F startup step 4: "validates the activation record … against
       all of these **and the current SecurityPolicyVersion**";
     - §30.1: "digests (recorded and recomputed), policy version".
  3. The SecurityPolicyVersion advances on every T-5 approval: a new
     TaskProfile, destination authorization, `T7Policy` value, and **every
     IntegrationActivation approval**, since activations are "records in
     the owner-approved policy (T-5)". It is a global monotone counter.
  4. Under the equality reading:
     - approving activation A2 invalidates A1;
     - any owner policy edit deactivates every gated component and
       terminates its in-flight ESCs;
     - if a lifecycle change is itself recorded as a new policy version,
       revoking A (Case B) also deactivates every other activation.
     This contradicts Case B ("other components' activations stay ACTIVE"),
     brief §7, and §37 item 47 ("A global counter with the same semantics
     under another name is equally forbidden").
  5. An implementer must satisfy both `valid()` and Case E and cannot.
- **Impact:**
  - Availability only; fail closed.
  - Only the owner can trigger it, not class M, so it is less severe than
    HR7-01.
  - Under the equality reading the gated runtime cannot hold two
    activations approved in different policy versions, and every policy
    update requires re-approving every activation.
  - It is a normative contradiction in the activation model, the exact area
    the freeze criterion "activation model is sound" and brief §7 test.
- **Required correction:**
  - Make `valid(a, t)` the single rule.
  - State that the recorded `security_policy_version` is used only to
    locate the approving policy and check it is not revoked, and that the
    active version must still contain `a`.
  - State that later policy versions carry activations forward and never
    invalidate them by advancing.
  - Remove "or a different policy version" from TST-CB-105 Case E, or
    restate it as "a record whose policy-version field differs from the
    owner-approved record".
  - Align §35.2, §30.1 and startup step 4.
  - State whether a lifecycle change creates a new SecurityPolicyVersion.
  - Add TST-CB-105 cases:
    - approving an unrelated TaskProfile or a second activation (new
      SecurityPolicyVersion) leaves A1 ACTIVE;
    - revoking A1 leaves A2 ACTIVE even though the policy version
      advanced.
- **Freeze blocker:** YES. It is a contradiction between the normative
  validity predicate and the normative test and startup procedure of the
  activation model, of the same kind as HR7-01. The fix is a narrow text
  change.
- **Implementation blocker:** YES (CR-ACT-01, CR-POL-01)
- **Deployment blocker:** YES (no gated CR may be deployed while activation
  validity is ambiguous with respect to policy-version advancement)

### HR8-02 — T-7 residual bound omits parent self-renunciation and subtree revocation (unquantized) and undercounts `B`

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR7 (HR7-04)
- **Section:** §7.3 T-9; §9.11 T7Policy / Quantization / residual table;
  §14.8; §21.3 rule 5; §21.5 revoker table; §32 `T7Policy` row; §38.2
- **Invariant:** INV-CB-048
- **Attack or contradiction:** see §14.2.
  - **(a)** A tainted parent P holds a less-tainted child C whose clearance
    permits a destination D that P's taint forbids. C emits to D
    continuously. At a time `t` of P's choosing, P renounces its own
    authority or clearance leaf (T-9). §21.3 rule 5 makes C's pair
    ineffective immediately. C's next delivery commit fails and D observes
    the stop at `≈ t`. This path is not quantized (the bucket rule covers
    only "edges it delegated to a child") and is not limited to `H`.
  - **(b)** The same holds for P revoking an edge its child delegated to a
    grandchild, which §21.5 permits to "an ancestor delegator in that
    lineage".
  - **(c)** `B = ⌈H/g⌉` undercounts by one when `parent.created_at` is not
    bucket-aligned.
- **Impact:**
  - Per parent ESC, an extra channel of about `log2(child lifetime /
    observation jitter)` bits for (a), plus one per revoked descendant edge
    for (b).
  - The stated bound, which INV-CB-048 asserts and which the policy store
    shows the owner at T-5 (owner decision 1), is therefore **not** a
    conservative upper bound. The design's claim that "a child, or a
    receiver at any destination, can … distinguish at most `B` timing
    values per decision" is false for these decisions.
  - Confidentiality impact is bounded and of the same order as the
    accepted residual, but the accepted number is wrong.
- **Required correction:**
  - Apply the bucket-boundary rule and the horizon `H` to **every**
    ESC-initiated (T-9) revocation whose effect reaches any descendant.
    This includes the effect of a self-renunciation on descendant pairs.
    The renouncing ESC itself may still stop at once.
  - Either restrict ESC-initiated subtree revocation to edges the ESC
    delegated directly, or count each additional revocable descendant
    edge.
  - Add one `⌈log2(1 + B)⌉` term per parent for self-renunciation, and
    restate the bound.
  - Define `B` as `⌈H/g⌉ + 1`, or align the horizon start to a bucket
    boundary.
  - Extend TST-CB-048 with self-renunciation, grandchild-edge revocation
    and unaligned-horizon cases.
- **Freeze blocker:** YES. The brief's READY criterion "T-7 channel bound is
  conservative" fails, and INV-CB-048 states a bound that does not hold.
  The correction is a narrow text change.
- **Implementation blocker:** YES (CR-ESC-01, CR-LIN-01, CR-POL-01)
- **Deployment blocker:** NO

### HR8-03 — Post-execution network-taint commit: unpersisted `L_net_max`, unchecked ceiling across interleaved deliveries, conditional append

- **Severity:** LOW
- **Category:** NEW
- **Section:** §34 `deliver()` (tool branch), `complete_tool_invocation()`;
  §17.6 rule 3
- **Invariant:** INV-CB-081, INV-CB-075, INV-CB-069
- **Attack or contradiction:**
  - **(i)** `complete_tool_invocation` compares against `inv.L_net_max`,
    but `deliver()` records the pending invocation only "with (ars.id,
    g.id)". The value, or the authorized destination set and policy
    version it was computed under, is not persisted.
  - **(ii)** The pre-execution ceiling check covers
    `H_pre ⊔ ARS ⊔ L_net_max`. Deliveries to the same ESC can commit while
    the tool runs, and each is checked without `L_net_max`. The post
    append of `⊔labels(N)` is then **not** ceiling-checked against
    `H_post`. `within_taint_ceiling` is closed under ⊔ except for
    sink-emptiness (NO_FLOW when `required_sinks = ∅`) and the expiry
    conjunct. So "the ceiling still holds" (§17.6 rule 3, §34 comment) is
    not guaranteed, and INV-CB-075 can be violated.
  - **(iii)** The append happens after two conditions:
    `require ⊔labels(N) ⊑ L_net_max` and the re-run of steps 0/2, which
    returns early for a REVOKED or TERMINATED ESC. A crash or restart
    during a tool run therefore TERMINATES the ESC without the network
    labels. A CONTINUATION then inherits a final H_exec that omits them,
    despite "always, result-returning or not".
- **Impact:** mostly availability and invariant consistency. Outputs are
  not bound and results are not ingested on those paths. There is a small
  unaccounted observable for a continuation.
- **Required correction:**
  - Persist `L_net_max` with the pending invocation.
  - Append the TNL-recorded labels unconditionally, first in the post
    commit and before any `require`; alternatively, append `L_net_max`
    conservatively in the pre-execution commit.
  - Either serialize deliveries to an ESC with a pending invocation, or
    re-check the ceiling at post time and TERMINATE the ESC on violation.
  - Extend TST-CB-081.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ING-01, CR-ART-01, CR-TAINT-01)
- **Deployment blocker:** NO

### HR8-04 — `activation_state_valid(BROKER_PATH)` names one path; tool and ingestion operations depend on other gated components

- **Severity:** LOW
- **Category:** NEW (within the HR7-08(a) correction)
- **Section:** §34 step 0; `deliver()` tool branch; `ingest_tool_result()`;
  §40.F "Runtime invalidation"
- **Invariant:** INV-CB-105
- **Attack or contradiction:**
  - Step 0 checks only `BROKER_PATH`. A `TOOL_ARG_*` delivery also relies
    on CR-ING-01, CR-ART-01 and an activation-gated CR-ISO-01
    capability-enablement mode. Suppose the owner revokes the ISO-TOOL
    capability-mode activation while `BROKER_PATH` stays valid. §34 then
    contains no check that stops the tool delivery.
  - Step 5 `isolation_available_for` and `ars.isolation_class available`
    test the isolation **level**, not the capability-mode activation.
  - §40.F says "affected gated paths are deactivated", but the normative
    procedure does not say how.
  - `ingest_tool_result` has no activation check. It is protected
    indirectly by `invocation_completed`, which re-ran step 0.
- **Impact:** a revoked capability-mode activation could still be exercised
  through a broker path that remains valid, if the implementation follows
  §34 literally.
- **Required correction:** define `activation_state_valid(op)` over the set
  of gated components the operation uses:
  - the broker path;
  - for tool sinks, CR-ING-01, CR-ART-01 and the relevant CR-ISO-01
    capability mode;
  - for external sinks, CR-EGR-01.
  Call it with that set in step 0, `deliver()` and
  `complete_tool_invocation()`.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ACT-01)
- **Deployment blocker:** NO

### HR8-05 — Shared per-root-lineage / per-window T-7 bounds form an uncounted inter-ESC channel; the counted quantity is unstated

- **Severity:** LOW
- **Category:** NEW
- **Section:** §9.7 step 0; §9.11 residual table ("Denied proposals … 0
  additional"); §32; INV-CB-106
- **Invariant:** INV-CB-048, INV-CB-106
- **Attack or contradiction:** see §14.3.
  - A sibling S probing T-7 learns P's issuance count and commit timing
    (unquantized) through `CB_RESOURCE_BOUND_EXCEEDED` on the shared
    lineage/window quota.
  - If those bounds count evaluated proposals, S also learns P's denied
    proposals.
  - Separately, "counted whether issued or denied" for `P_max` needs a
    durable counter write that survives the DENY path, while §9.7 step 5
    says "any failure → nothing exists".
- **Impact:** at most `P_max(S)` bits per probing ESC. The channel is not
  counted or stated.
- **Required correction:**
  - State that lineage/window bounds count issuances only.
  - Apply shared-quota effects at bucket boundaries, or partition the
    lineage quota per parent at issuance.
  - Record the residual in §38.2.
  - Specify that the `P_max` counter commits independently of the DENY
    outcome.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ESC-01)
- **Deployment blocker:** NO

### HR8-06 — Epoch-keyed pools and caches make every revocation weakly observable to all executions

- **Severity:** INFO
- **Category:** NEW
- **Section:** §16.7 step 7; §26.5; §31 item 3; §38.2
- **Invariant:** INV-CB-043, INV-CB-102
- **Attack or contradiction:**
  - Pooled connections and cache entries are keyed by the global epoch and
    re-validated after any increment.
  - A T-9 by any ESC therefore causes re-handshakes and cache misses for
    all executions, a latency blip visible installation-wide.
  - This is the residual observable HR7-01 described, much weakened
    (timing, not deactivation).
- **Impact:** falls within the accepted "timing, size and resource side
  channels" residual (§38.2).
- **Required correction:** none for freeze. Consider keying pool and cache
  validity by the scoped revocation state they depend on, rather than the
  global epoch.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR8-07 — ConfinementRecord environment and launcher digests are recorded but never verified

- **Severity:** INFO
- **Category:** NEW
- **Section:** §17.9 ConfinementRecord; §34 `ingest_tool_result()`,
  `complete_tool_invocation()`
- **Invariant:** INV-CB-097
- **Attack or contradiction:** `environment_digest` and
  `launcher_config_digest` are bound into the record but not compared with
  the launcher's approved configuration for the adapter.
- **Impact:** none under the TCB assumption, since the supervisor writes the
  record. It is a defence-in-depth gap only.
- **Required correction:** optionally require both digests to equal the
  registered values for `(adapter_id, policy_version)`.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 2 (HR8-01, HR8-02) · LOW 3
(HR8-03, HR8-04, HR8-05) · INFO 2 (HR8-06, HR8-07) · total 7.

---

## 25. Design freeze blockers

| ID | Why it blocks freeze |
|---|---|
| **HR8-01** | The normative activation-validity predicate (`valid(a, t)`, INV-CB-105) and the normative test and startup procedure (TST-CB-105 Case E, §40.F step 4, §35.2) disagree on whether a policy-version advance invalidates an activation. Under the stricter reading every T-5 approval, including approving another activation, deactivates every gated component. That is the pattern §37 item 47 forbids |
| **HR8-02** | INV-CB-048 and §9.11 state a T-7 channel bound that is not an upper bound. Parent self-renunciation and subtree revocation reach descendants unquantized and outside `H`, and `B` undercounts for an unaligned horizon. The brief's criterion "T-7 channel bound is conservative" fails |

**Freeze-standard scorecard (brief §41)**

| Criterion | Status |
|---|---|
| No CRITICAL design blocker | ✓ |
| No HIGH design blocker | ✓ |
| No freeze-blocking MEDIUM | ✗ (HR8-01, HR8-02) |
| HR7-01 RESOLVED_IN_R6 | ✓ |
| INV-CB-105 sound | ✓ (VALID) |
| TST-CB-105 no longer encodes the old defect | ✓ for the epoch defect; Case E adds a policy-version analogue (HR8-01) |
| INV-CB-102 complete enough | ✓ (VALID) |
| T-7 channel bound is conservative | ✗ (HR8-02) |
| Approval attenuation coherent | ✓ |
| Containment-only classification deterministic | ✓ |
| §34 tool/network commit flow coherent | ✓ in structure (LOW precision gaps HR8-03, HR8-04) |
| LineagePair regression-free | ✓ |
| Read-confinement / Git blockers closed | ✓ |
| No frozen-contract amendment needed | ✓ |

---

## 26. Owner decisions (not made here)

| # | Decision | Assessment |
|---|---|---|
| 1 | Template model, `T7Policy` values (`N_c`, `P_max`, `n_T`, `g`, `H`) and the resulting stated T-7 bound | A legitimate policy decision **once the technical bound is correct**. It is not yet: the formula the policy store would compute omits the self-renunciation and subtree-revocation paths and undercounts `B` (HR8-02). The missing technical rule is to quantize, horizon-limit and count every ESC-initiated revocation that reaches a descendant, and to define `B` for an unaligned horizon. With that rule fixed, choosing the values is pure policy |
| 2 | ApprovalRequirement vocabulary and each class's requirement set | Legitimate policy/configuration. The technical rule (set inclusion over the recorded class; incomparable → DENY) is complete |
| 3 | CR classification resulting from the §40.F procedure | Legitimate. R1–R8 and the first-match procedure are deterministic. Record the `InternalEndpointPolicy` capability under a gated mode (§11.4) |

---

## 27. Implementation blockers (separate from freeze)

In addition to every row of design §43.1, all of which remain:

- HR8-01 (CR-ACT-01, CR-POL-01);
- HR8-02 (CR-ESC-01, CR-LIN-01, CR-POL-01);
- HR8-03 (CR-ING-01, CR-ART-01, CR-TAINT-01);
- HR8-04 (CR-ACT-01);
- HR8-05 (CR-ESC-01).

None of the §43.1 machinery exists: no ESC, taint, policy store, lineage,
task control, registry, launcher, Mediated Reader, Level 2R worker, Git
View Builder, telemetry, network layer or activation/lifecycle machinery.

## 28. Deployment blockers (separate)

- Every §43.2 row, unchanged. The "live" rows (R-01..R-09, R-11, R-13,
  R-22..R-26, R-29, R-30) are pre-existing runtime defects. No design
  revision fixes them.
- **HR8-01:** no gated CR may be deployed while activation validity is
  ambiguous with respect to SecurityPolicyVersion advancement.

---

## 29. Frozen-contract compatibility

- **v0.2.5.1 `AuthorityScope`:** unchanged. It still has `objective_ref`
  and `expires_at` (code lines 225–226). Templates pass values to the
  unchanged issuer, and `expires_at` and `objective_ref` are derived, not
  re-typed.
- **v0.2.5:** check-not-clip, principal repetition, T-9 as a usage
  restriction, the CR-01 requester binding and per-Action approval are all
  preserved. Approval-set inclusion only adds requirements.
- **v0.2.3:** the router default is never relied on.
- **v0.2.4:** identifiers are unchanged.
- **v0.2:** §8/§10 are strengthened.

None of HR8-01..07 needs a frozen-contract change. All corrections are
v0.2.6 text changes.

**No amendment to any frozen v0.2.x contract is required.** AMD-025-01
remains uncreated and unnecessary.

---

## 30. Final status

r6 does what HR7 asked on its primary finding:

- activation validity is now independent of revocation-epoch
  advancement;
- the epoch is only a rollback floor;
- an append-only per-activation lifecycle record carries owner revocation
  and supersession;
- ordinary and T-9 revocations never touch activations.

The HR7 attack and the brief's rollback, supersession and prerequisite-loss
constructions all behave as required. HR7-02, 03, 05, 06, 07, 08, 09 and 11
are resolved; HR7-10 is recorded. INV-CB-102 and INV-CB-105 are VALID.
LineagePair shows no regression. The HR6 read-confinement and Git blockers
remain closed. The invariant and test accounting are exact.

Two MEDIUM defects prevent READY:

- **HR8-01:** the activation model still contains a normative
  contradiction. The validity predicate lets policy versions advance, but
  the normative test, startup procedure and reason code invalidate an
  activation on any policy-version difference. Under that reading every
  owner policy approval, including approving a second activation,
  deactivates every gated component.
- **HR8-02:** the T-7 residual bound, which the owner is asked to approve,
  is not conservative. A parent's renunciation of its own leaf, or its
  revocation of deeper descendants' edges, reaches children unquantized
  and outside the horizon, and `B` undercounts for an unaligned horizon.

Both corrections are narrow text changes. A focused verification of that
delta, including HR8-03..05, should then be sufficient.

```text
R6 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

READY would have meant only that the technical review had passed and the
owner could decide whether to freeze. It would not have meant frozen,
secure, implemented or implementation-authorized.

> No v0.2.6 production implementation has been authorized or created.

---

## Appendix A — Read-only validation

Commands were run from `C:\Users\Gyuro\jarvis-os` with
`.venv/Scripts/python.exe`. The five validators ran before this HR8 file
was written. The pytest run overlapped with writing it.

| Command | Result |
|---|---|
| `python scripts/check_v013_freeze_baseline.py` | exit 0 — `v0.1.3 FREEZE BASELINE CHECK: OK` (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `python scripts/check_v020_contract.py` | exit 0 — `v0.2.0 CONTRACT CHECK: OK` |
| `python scripts/check_v023_router_contract.py` | exit 0 — `v0.2.3 ROUTER CONTRACT CHECK: OK` |
| `python scripts/check_v024_agent_contract.py` | exit 0 — `v0.2.4 AGENT CONTRACT CHECK: OK` |
| `python scripts/check_v025_design_contract.py` | exit 1 — `DISCREPANCY FOUND`, solely 7 × "file outside the v0.2.5.1 allowlist is new/modified" for the seven untracked v0.2.6 documents (expected) |
| `python -m pytest -q -p no:cacheprovider` | **1 failed, 2234 passed, 1 warning** (420 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`: the same expected v0.2.5 allowlist discrepancy caused by the untracked v0.2.6 documents. This HR8 file also appears in its list because the run overlapped with writing it. This matches HR7's baseline (1 failed, 2234 passed). The warning is a third-party `starlette`/`anyio` deprecation |

No validator, test or configuration was modified.

## Appendix B — Integrity

Re-verified at the end of the review (see the terminal report). The design
and HR2–HR7 are unchanged from the §2 hashes. HEAD is unchanged and there
are no tracked changes. The only new file is this HR8 document. No commit,
push or merge was made.
