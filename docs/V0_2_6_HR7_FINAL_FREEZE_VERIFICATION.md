# Jarvis OS v0.2.6 — HR7 Final Freeze Verification of Design Revision r5

```text
subject                        = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r5)
subject status on entry        = CORRECTED R5 — PENDING HR7 FINAL FREEZE VERIFICATION
prior reviews checked          = HR2 (docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md)
                                 HR3 (docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md)
                                 HR4 (docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md)
                                 HR5 (docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md)
                                 HR6 (docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md)
review type                    = final independent security design review (read-only)
design_modified                = false
hr2_to_hr6_modified            = false
code_tests_validators_modified = false
opendex_modified               = false
final_status                   = R5 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

Section numbers (§N) refer to the r5 design unless another document is
named. Finding IDs `HR7-NN` are new to this review.

---

## 1. Independence

This session did **not** author any of the following:

- design revisions r1, r2, r3, r4 or r5;
- HR2, HR3, HR4, HR5 or HR6.

It started with no conversation history. It had no access to the drafting
or review sessions and worked only from repository contents. Every
conclusion below was re-derived from the r5 text, and from code at HEAD
where a factual claim needed checking. The correction record (§0.6) and
the design's own status words ("closes", "corrected", "RESOLVED") were not
treated as evidence.

**Limitation.** This review uses the same model family (Claude) as the
earlier reviews (HR3-16, HR4-12, HR5-16, HR6 §1). It is session-independent
but not organizationally independent. The design's recommendation (§38.2,
§44.5) for a human security review of §6, §8, §9, §16.5/§16.7,
§17.6/§17.9–§17.11, §18.2–§18.5, §21.3 and §40.F before freeze still stands.

---

## 2. Repository state

Inspected read-only before any file was written.

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `13796dcd61015098429f343e2fb982a9c75698bb` |
| `origin/master` | `13796dcd61015098429f343e2fb982a9c75698bb` (= HEAD) |
| Tag at HEAD | `v0.2.5.1` |
| Tracked changes (`git diff`, `git diff --cached`) | none |
| Untracked (`git status --short -uall`) | exactly six v0.2.6 documents: the design, HR2, HR3, HR4, HR5, HR6 |
| Production-code changes | none |

This matches the expected state. Nothing was normalized.

**SHA-256 at start of review**

| File | Role | SHA-256 |
|---|---|---|
| `docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md` | r5 design | `cbff474db4de5f7fb740ac00922e2cd4a3605338a7724f85aed3602aa203ae64` |
| `docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` | HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| `docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md` | HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| `docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |
| `docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` |
| `docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md` | HR6 | `42b170a580dba800fa310735c4ca0267083aa2beab0fb033fbebeeb289b4f07e` |

The HR2–HR5 hashes equal the values HR6 recorded, so those documents are
unchanged since HR6.

**OpenDex** (`C:\Users\Gyuro\opendex-reference`): HEAD
`3e898343d1127c8d5075b459acdd55da83b83f04` (the value in design §41);
`git status --short` is empty. No OpenDex file was opened or modified.

---

## 3. Materials reviewed

- **r5 design:** read in full (lines 1–5936), including §0.6, every
  normative section, the §33 invariant table, the §34 procedure, the §36
  test table and §40.
- **HR6:** read in full.
- **HR2–HR5:** headers and hashes only, for traceability. HR6 and §0.5/§0.6
  carry every earlier finding forward explicitly.
- **Code:** `app/authority_contracts/contracts.py::AuthorityScope` was
  checked. Its fields are `schema_version`, `vocabulary_version`,
  `permission_ceiling`, `action_types`, `objective_ref` and `expires_at`.
  This is relevant to the §9.11 template, see HR7-11.
- **Mechanical checks of the design text:**
  - §33 has 106 invariant rows with no duplicate IDs;
  - §36 has 105 test rows, TST-CB-001..106 without TST-CB-030, contiguous,
    with no duplicates;
  - TST-CB-097..106 are defined only inside §36 (lines 4964–4973); every
    other occurrence is a reference.

---

## 4. HR6-01 verification — unknown readable universe

The rule `unknown actual readable universe = DENY` is stated normatively
and consistently in these places:

- §17.9 normative rule 2;
- §17.6 rule 2a;
- §6.5 ("No unconfined protected-content execution … There is no third
  option");
- §16.2;
- §34 `deliver()`: `ars is None → DENY(CB_READ_SET_INCOMPLETE)` before
  execution;
- §34 behaviour table;
- §35.2 `CB_READ_SET_INCOMPLETE`;
- INV-CB-097, INV-CB-081, INV-CB-062;
- §37 item 42;
- TST-CB-097, TST-CB-081.

The `completeness` field is removed from `AuthorizedReadSet`, so no
INCOMPLETE state can exist.

**Substitution paths tested**

| Candidate substitute | r5 treatment | Result |
|---|---|---|
| Owner-selected label ceiling | Withdrawn by name (§17.6 rule 2a, §17.9, INV-CB-097 "no owner-selected-ceiling exception"); TST-CB-097 requires that an owner-approved ceiling still DENY | Closed |
| Adapter-selected ceiling / registration | "A registration's declaration is only the request from which the boundary is built; it is never evidence" (§16.2); tool-chosen labels ignored (§17.6 rule 1) | Closed |
| Source-policy guess | Source policy labels *resources* inside the enforced universe; it never establishes the universe | Closed |
| Tool-reported read set | "never security evidence" (§17.9, INV-CB-097, §37 item 35) | Closed |
| Post-hoc observed-read set | The Mediated Reader read log is "audit evidence only — it never replaces or narrows the entry set" (§17.9). The Trusted Network Layer (TNL) connection record *is* used post hoc. It is the complete mediator's own record, not a tool report. Network reach is also bounded before execution by the invocation's authorized destinations, and the record only **adds** labels. It is not a substitute for confinement | Closed (see HR7-08(c) for a taint-accounting point) |
| `⊔ source_label(adapter input policy)` term (§17.6) | A join term only. It can raise, never lower, and readability is still bounded by the ARS and runtime image | Not an escape hatch |

**Timing.** DENY happens before protected execution: `deliver()` denies at
`bind_read_set` inside the pre-execution delivery commit, before the tool
starts.

**Verdict HR6-01: RESOLVED_IN_R5.**

---

## 5. HR6-02 verification — GitReadClosure

§17.11 replaces the r4 view ("the managed repository and the entries")
with an explicit TCB-computed `GitReadClosure`. The rules:

- the worker can read **only** the closure plus the runtime image;
- every protected resource in the closure is an ARS entry and joins the
  label;
- the preferred realization is a synthetic per-operation repository built
  by the Git View Builder;
- a whole-repository view is allowed only if every object, ref, reflog,
  index and metadata file is bound, the output joins the whole repository,
  and no configuration or secret resource other than the fixed launcher
  configuration is reachable.

**Surfaces checked**

| Surface | Treatment | Status |
|---|---|---|
| Requested working-tree files | Closure entries (ArtifactRef, file identity, digest) | ✓ |
| Index | In the closure if read; joins its label | ✓ |
| Refs, packed refs, HEAD | Only named/resolved refs; HEAD as required metadata | ✓ |
| Object database, loose objects | Each traversed object, bound, by object id | ✓ |
| Packs and pack indexes | Synthetic view writes loose objects; "a pack … is never exposed as a whole" | ✓ |
| Unreachable objects, reflog, stash, other branches | Absent from the synthetic view. In the whole-repo view each must be bound and joined | ✓ |
| Alternates | Suppressed (`objects/info/alternates`, `GIT_ALTERNATE_OBJECT_DIRECTORIES`) and absent from the view | ✓ |
| Submodules, `.gitmodules` | Submodules suppressed. `.gitmodules` is a tree/working-tree file, so it is either in the closure (and joined) or unreadable | ✓ |
| Attributes (`.gitattributes`, `info/attributes`), ignore files | Not named individually. Covered by "anything readable by Git that can influence its output belongs to the closure", and by confinement: a file outside the closure does not exist in the view. Built-in conversions (eol, `working-tree-encoding`) act only on closure content | ✓ (by the property) |
| System/global/local configuration, `include`/`includeIf` | Suppressed; only the fixed launcher configuration, which is itself in the closure | ✓ |
| Hooks, filters, textconv, diff/merge drivers, aliases | Suppressed ("no configuration-driven program execution") | ✓ |
| Credential helpers, askpass, pager, editor, ssh command, gpg program, `insteadOf`, fsmonitor | Suppressed | ✓ |
| Environment (`GIT_*`, `HOME`/`XDG_CONFIG_HOME` defaults) | Only the launcher allow-list. Default user-level files (for example `~/.config/git/attributes`) are unreachable under 2R | ✓ (by confinement) |
| External commands | Every executed binary is fixed by the Tool Launcher; a missed helper still cannot exceed the 2R view | ✓ |

**Verdict HR6-02: RESOLVED_IN_R5.** For the availability consequences see
§12 and HR7-10.

---

## 6. HR6-03 verification — T-7 template channel

| Requirement | r5 | Status |
|---|---|---|
| Finite owner-approved set | `child_delegation_templates` in the TaskProfile; its size is bounded (§32); templates are sealed policy records (CR-POL-01) | ✓ |
| Model selects only a reference | `child_delegation_template_ref` is the only T-7 selector. The r4 free selectors are removed, and a proposal carrying them is `CB_MALFORMED_REQUEST` (§9.6, §9.7 step 2) | ✓ |
| Template fixes every security-sensitive parameter | Authority scope, clearance, redelegation, `max_duration`. Destinations, environment, approval class, persistence, ceiling and provider/model class come through the named child profile | ✓ |
| No free authority, clearance or destination subset | Yes ("No free subsets", §9.11) | ✓ |
| No free timestamp | Expiry is `min(parent redelegable expiry, bucket(now) + template.max_duration)` from the trusted clock | ✓ |
| No free persistence or environment value | Both come from the child profile | ✓ |
| Deterministic expiry | Yes, given trusted `now` and the policy granularity | ✓ |
| Checks unchanged | check-not-clip and every §9.10 row still run; a template that does not fit a parent is DENY, never clipped | ✓ |

The channel bound is analysed in §13. It is honest in structure but misses
one signal (T-9 cancellation) and does not operationally define `B`
(HR7-04, LOW).

**Verdict HR6-03: RESOLVED_IN_R5** (LOW residual HR7-04).

---

## 7. HR6-04 verification — activation

What r5 fixes:

- activation is defined semantically (§40.F, INV-CB-105);
- merged-but-disconnected requires nine conditions; an import test is
  explicitly insufficient;
- every CR has an `ActivationManifest`;
- `IntegrationActivation` binds the code, manifest, migration-set and
  configuration digests, the policy version, prerequisites, isolation
  level, epoch and owner event;
- startup revalidation is specified;
- runtime prerequisite loss is specified;
- gated migrations are held out of the live head;
- every CR is classified;
- the §40.E sentence is corrected.

TST-CB-105 was extended with cases (a)–(f), digest mismatch, runtime loss
and an unmanifested surface.

**A new defect is introduced by the epoch binding (HR7-01).**

- `activation_epoch` is "revocation epoch at approval" (§40.F).
- Runtime loss includes "the epoch advances past a record's activation
  epoch".
- TST-CB-105 requires deactivation when "the revocation epoch advances past
  the record's".
- §31 item 3 and §21.5 make **every** revocation (clearance, delegation,
  pair, grant, objective, T-9 renunciation) increment that same global
  epoch.

Read literally, the first routine revocation anywhere deactivates every
gated path and terminates every in-flight ESC system-wide. Class M can
trigger it (see HR7-01).

**Verdict HR6-04: PARTIALLY_RESOLVED** (residual HR7-01, freeze-blocking).

---

## 8. HR6-05 verification — handles and standard streams

§18.5 defines two models.

**Level 2R/3 workers (model A):**

- a fresh worker per invocation;
- an explicit inherited-handle list, default none (IPC, ARS handles and
  write view only);
- no inherited stdin/stdout/stderr (each is null or a registered pipe to
  ingestion or `DIAGNOSTIC_STORE`);
- an allow-listed environment;
- the handle-list digest is recorded in the ConfinementRecord.

**Level 1 trusted TCB code hosting no untrusted/model-controlled code
execution (model B):**

- the guard is active from process start;
- an admission audit makes any unadmitted write-capable handle or stream
  disqualifying;
- `sys.stdout`/`sys.stderr` and descriptors 1/2 are replaced before
  admission.

**Both models:** a trusted top-level error boundary covers `sys.excepthook`,
`threading.excepthook`, `sys.unraisablehook`, the asyncio handler,
`warnings.showwarning`, `faulthandler` and the logging last-resort handler.
If the boundary fails, the process terminates without text.

**Attacks traced**

| Attack | Outcome |
|---|---|
| Parent stdout/stderr | Not inherited (2R); replaced before admission (Level 1) |
| Open DB handle, `.env` handle, inherited socket, pipe, file mapping, child-process handle | Not in the explicit list → not inherited; startup refused if present (TST-CB-099) |
| Library cache/log handle opened at import | Admission audit → process ineligible (TST-CB-100) |
| Uncaught exception echoing model output (main thread, thread, asyncio) | Error boundary emits only `SecurityError`; raw text goes only to `DIAGNOSTIC_STORE` (TST-CB-099) |
| `warnings`, third-party `print`, `faulthandler` | Routed by the boundary and stream replacement |

**Two-model coherence (brief §23).** No text claims both that ambient
authority is trusted and that untrusted connector/tool code runs in the
same process. Untrusted and model-controlled *code* is model A only (§6.5,
§18.5). The agent harness processes model-controlled *content*, not code.

**Verdict HR6-05: RESOLVED_IN_R5.**

---

## 9. HR6-06 verification — normative test table

- TST-CB-097..106 are defined in §36 at lines 4964–4973. §36 declares
  itself the only normative definition.
- §0.5 now contains only references (lines 166–178). No conflicting
  duplicate exists: grep finds no second definition row.
- §36 has 105 rows, 001–106 without 030, contiguous.
- `ARTIFACT_READ` is in the closed §14.1 `delivery_kind` vocabulary.

**Verdict HR6-06: RESOLVED_IN_R5.**

---

## 10. HR6-07..12 verification

| HR6 | r5 | Verdict |
|---|---|---|
| HR6-07 pool scope, resolve-before-authorize, resolver egress | §16.7 steps 2 and 7 and "Resolver egress"; INV-CB-102; TST-CB-102 (zero DNS queries, scoped pools, epoch/version) | **RESOLVED_IN_R5** (the invariant text omits resolver egress: HR7-09, INFO) |
| HR6-08 version-pinned comparands, approval class | `EnvironmentClassRef(id, policy_version, definition_digest)` and destination `(id, version, digest)` in the ESC and binding; comparisons use recorded definitions (§9.3 steps 10–11, §9.7 step 4); approval-class row in §9.10 | **RESOLVED_IN_R5** (strictness-order constraint: HR7-06, LOW) |
| HR6-09 proposer binding | §9.7 step 2 `proposer_esc_id == parent_esc_id`; step 0 global single-use; TST-CB-106 | **RESOLVED_IN_R5** (the source of `proposer_esc_id` is unspecified: HR7-05, LOW) |
| HR6-10 telemetry fields | §18.3: TCB-issued, store-validated ids; TCB-computed counters; per-event enumerated keyed digests with justification; TST-CB-099 | **RESOLVED_IN_R5** |
| HR6-11 ID namespace | SR1-NN rename (§0.6, §44.4 line 5757) | **RESOLVED_IN_R5** |
| HR6-12 runtime image | §6.5 2R row: digest-pinned image outside managed stores, `jarvis.db`, `.env` and repo roots; job objects are resource limits only; no package-wide grant reaches protected locations | **RESOLVED_IN_R5** (non-filesystem OS state: HR7-03, LOW) |

---

## 11. Readable-universe and confinement analysis

### 11.1 Proven-maximum rule (brief §6)

§17.9 permits `L_read_max = ⊔ label(r), r ∈ R` only when all of these hold:

- `R` is established by the boundary's own configuration (handles, view,
  mounts, egress policy), "never by a declaration or an owner choice";
- `R` is finite and registered;
- every label is known;
- `R` excludes `.env`, credentials, process memory, arbitrary host files,
  security, broker-owned and legacy stores, and unknown network sources.

If `R` cannot be established, the result is DENY.

The only user of the rule is the untrusted-connector ceiling (§16.2). In
§34 `ingest_tool_result()`, `proven_maximum(adapter_id)` with no
established `R` returns NO_FLOW. That state should be unreachable, because
the connector could not have started without an ARS. This is
belt-and-braces, not an escape hatch.

Owner-approved **source policies** label external resources, including
`InternalEndpointPolicy` targets. This is ordinary classification of a
confined resource, not a substitute for confinement.

**No wording recreates the r4 escape hatch.**

### 11.2 ConfinementRecord (brief §7)

| Required binding | Field | Status |
|---|---|---|
| Invocation identity | `invocation_id` (never reused, §21.6) | ✓ |
| Worker identity | — | **missing** (HR7-02) |
| Isolation class | `required_isolation_class`, `actual_isolation_class`, `enforcement` | ✓ |
| AuthorizedReadSet / ReadableUniverse | `authorized_read_set_id`, `network_resources_digest`, `runtime_image_ref` | ✓ |
| Start / end | `started_at`, `ended_at` (whole execution) | ✓ |
| Policy version | — (the ARS carries it; the record does not) | **missing** (HR7-02) |
| Execution / ESC | `esc_id` | ✓ |
| Violations | `status`, `violation_codes` | ✓ |
| Launcher/environment digest | `inherited_handle_list_digest` only; no environment allow-list or launcher-configuration digest | **partial** (HR7-02) |

**Replay.** A record from invocation A cannot authorize invocation B:

- lookup is by B's `invocation_id`;
- `cr.authorized_read_set_id == ars.id` is required;
- the ARS is looked up by `(esc_id, invocation_id)` and must match
  `adapter_id`;
- every id is store-generated and never reused.

**Missing or invalid record.** The result is discarded and no artifact is
bound (§17.6 rule 6, §34 steps 1–5). The record is not bound to the result
bytes or the worker process. Soundness therefore rests on TCB code routing
only the supervised worker's IPC output into `ingest_tool_result`. That is
acceptable under the TCB assumption, but should be made explicit (HR7-02).

### 11.3 ReadableUniverse vs ProvenanceUniverse (brief §8)

The requirement is:

`ReadableUniverse \ (WriteView ∪ RuntimeImage) = AccountedReadUniverse`.

It is enforced for labels, because `ingest_tool_result` joins every
`r ∈ U` and `ArtifactDerivation.read_set = U`.

| Resource | Class | Treatment |
|---|---|---|
| Readable but never opened | Protected source | Joined (conservative) |
| Opened but omitted from derivation | — | Impossible: the label basis is the whole U, not the opened set |
| Runtime image, helper binaries, libraries | Trusted execution infrastructure | Readable, not accounted; must be proven free of protected content. Jarvis source code is `REPOSITORY` CONFIDENTIAL by §15.5, so a worker harness copied from the repository needs an explicit classification (HR7-03) |
| Fixed Git/launcher configuration | Control-plane input | In the closure; Jarvis-written; no protected content |
| Configuration file of a tool (other) | Protected source or runtime image | Must be one or the other; nothing else is readable |
| Archive member | Protected source | ARS entries; archive label ⊒ members |
| Environment value | Control-plane input | Launcher allow-list only; no secrets |
| Subprocess output | Derived | Stays inside the worker. Stdout/stderr returned to Jarvis are ingestion |
| Network response | Protected source (new ingestion) | TNL record ⊆ authorized destinations; source policy label |
| Non-filesystem OS state (registry, clipboard, desktop/UI objects, other processes, named kernel objects, `/proc`) | Not classified | **Not named in the 2R property** (HR7-03, LOW) |

The provenance **record** of a tool-result item (§13.1) has no field
naming the ARS or ConfinementRecord. The label covers U, but the provenance
universe cannot be reconstructed from the record (HR7-02).

### 11.4 `ingest_tool_result` trace (brief §9)

| Required gate | §34 | Status |
|---|---|---|
| 1 Invocation known | ARS lookup by `(esc_id, invocation_id)`; adapter match | ✓ |
| 2 ARS verified | Same | ✓ |
| 3 Isolation class verified | `actual ≥ required` | ✓ |
| 4 Whole-execution confinement | `covers_entire_execution` | ✓ |
| 5 ConfinementRecord valid | Exists, ARS match, `CLEAN` | ✓ |
| 6 Provenance covers readable universe | `provenance_sources ⊆ U`, and the label joins all of U | ✓ |
| 7 No violation | `status == CLEAN` | ✓ |

**Attack:** the tool exits successfully but has no ConfinementRecord.
`cr is None` leads to `INGESTION_DENIED`, `discard(content)` and `NO_FLOW`.
**Result discarded. ✓**

### 11.5 ArtifactDerivation (brief §10)

The artifact path in `deliver()` has the same logic:

- `cr` must be valid and `cr.authorized_read_set_id == ars.id`, else
  `CB_CONFINEMENT_UNVERIFIED` and nothing is bound;
- the output label is `⊔labels(U) ⊔ H ⊔ …`.

"The tool said it only read A" is ignored everywhere (§17.6 rule 1,
§17.9). **✓**

The pseudo-code places the post-execution registration inside the
pre-execution transaction, with a comment to the contrary. The
post-execution commit's revalidation set is not written out (HR7-08(b)).

---

## 12. GitReadClosure analysis

### 12.1 Synthetic view (brief §12)

The Git View Builder:

- reads each closure object through the Mediated Reader, digest-verified
  against its binding;
- writes loose objects, the needed refs and the fixed configuration into a
  fresh `EPHEMERAL_WORKSPACE`.

It cannot copy anything that is not a bound closure element. Specifically,
it never copies:

- global or system configuration (never read);
- credentials;
- unmanaged metadata;
- whole packs.

Every copied resource is a closure element and therefore an ARS entry
("containing only the closure"). **✓**

### 12.2 Whole-repository fallback (brief §13)

All three conditions are conjunctive, and any unbound object leads to
`CB_ARTIFACT_UNBOUND` and DENY. The output joins the entire repository.
This is confidentiality-safe and availability-heavy: every output of a
repository that ever held RESTRICTED content is RESTRICTED. The design
states this cost and prefers the synthetic view. **Acceptable.**

### 12.3 Hostile test (brief §14)

Setup: `public.txt` INTERNAL, `secret.txt` RESTRICTED. The operation
targets `public.txt`.

| Access route | Synthetic view | Whole-repo view |
|---|---|---|
| Working tree | `secret.txt` not materialized unless in the closure | Bound and joined → RESTRICTED |
| Object store (`cat-file` on the blob id) | Blob absent → fails | Joined → RESTRICTED |
| Other branch, history, `log -p --all` | Refs/objects absent | Joined |
| Stash, reflog | Absent | Joined |
| Pack read directly | No pack exposed | Joined |

An INTERNAL output is impossible in every variant, and TST-CB-098 asserts
exactly this. **✓**

**Label propagation.** When the closure contains a tree or the index
naming `secret.txt` (its path and blob id), those objects carry
RESTRICTED-or-higher labels by induction over the §17.6 join. Every Jarvis
Git write is an ArtifactDerivation joining its whole universe. The outputs
of an ordinary `public.txt` commit in such a tree are therefore RESTRICTED.
This is safe, but the synthetic view avoids whole-repository taint only
partially (HR7-10, INFO).

---

## 13. T-7 template and channel analysis (brief §16)

The stated bound is
`max_child_issuances · (⌈log2(n_T+1)⌉ + ⌈log2(B)⌉)` bits per parent ESC.

| Candidate signal | Covered? |
|---|---|
| Issue vs don't issue | ✓ (`+1` term per slot) |
| Number of issuances | ✓ (slots up to `max_child_issuances`) |
| Ordering of children | ✓ (the per-slot sequence is already in the product) |
| Template choice | ✓ |
| Proposal/issuance timing | ✓ (`B`). **But `B` is not operationally defined**: the child, or a receiver at destination D, can observe creation and activity time at fine resolution, so "distinguishable buckets" depends on an observation granularity the design does not fix. §9.11 requires the bound to be computed at policy approval, so `B` must be computable (HR7-04) |
| Repeated failed / rejected proposals | Not observable by the child or its destinations (denials go to restricted audit); their only effect is timing, inside `B` |
| Cancellation / revocation of an issued child | **Not covered.** T-9 lets the parent revoke edges it delegated. Whether and when a child is revoked is observable at D (the child's emissions stop), adding up to `⌈log2(B+1)⌉` bits per child (HR7-04). Under HR7-01 as written, a revocation is also globally observable |
| Choice of task content | Not in the bound; correctly so. The proposal is an item ⊒ parent H_exec and is flow-checked |
| Child task ids | Store-generated (§21.6); no signal |
| Destination-denial behaviour | Reveals template content only |

**Assessment.** The bound is structurally honest and states that the
channel is non-zero. It omits the cancellation term and leaves `B`
undefined. Both are LOW and affect a stated residual, not a guarantee.
**Honest enough for freeze once HR7-04 is corrected.** It is not
freeze-blocking on its own.

---

## 14. Activation analysis (brief §17–§20)

**Semantic activation (brief §17).** Checked against each attack surface:

| Surface | Covered by §40.F / manifest |
|---|---|
| FastAPI route registration | routes |
| Startup hook | startup_hooks |
| Entry point | entry_points |
| Scheduler | schedulers |
| Worker | workers |
| Plugin discovery | plugin declarations |
| Migration | migrations + migration-set digest |
| Configuration default | configuration switches/defaults + digest |
| Provider registration | providers |
| Dependency injection | DI bindings |
| Import-time patch | patches / import-time effects |
| Signal handler | signal handlers |
| Filesystem watcher | watchers |
| Network listener | listeners |

The catch-all "any import-time side effect … whether or not live code
imports it" makes the definition observable-effect based. **✓**

**ActivationManifest (brief §18).**

- It is per CR/component and digest-bound.
- An unmanifested surface is refused by the Monitor and the component
  stays inactive; the surface is unknown, so the result is DENY.
- It is protected control-plane state: CR-POL-01 stores manifest digests,
  it is recorded in `IntegrationActivation`, and trust-anchor digests go
  into `OWNER_BOOTSTRAP`.

**✓**

**IntegrationActivation binding (brief §19).** All eleven required
elements are present. A changed code, manifest, migration or configuration
digest invalidates the record. **✓**

**Startup and runtime loss (brief §20).**

- Startup recomputes and validates; on a mismatch the component stays
  inactive, or startup fails closed.
- Runtime loss triggers continuous attestation, then deactivation (no
  grant or delivery, in-flight ESCs TERMINATED) or a stop.

Two gaps:

- **HR7-01 (MEDIUM, freeze-blocking):** the epoch condition deactivates on
  every revocation.
- **HR7-08(a) (LOW):** §34's normative step 0 has no activation/GATE-CONTAIN
  precondition. Monitor loss is caught indirectly by
  `registry_monitor.admitted()`; loss of EGR-01a or LOG-01 is not checked
  in §34.

**Classification.** Every CR is assigned to exactly one class.
"Containment-only" requires a "manifest whose every surface is a
restriction", but "restriction" is undefined. CR-ISO-01 introduces a
store-owning broker process, IPC endpoints, the Tool Launcher and worker
creation. CR-NET-01 introduces resolver egress. CR-IFR-01 and CR-ACT-01
introduce hooks, a monitor and a validator. None of these is literally a
restriction (HR7-07, LOW; this bears on owner decision 3).

**GATE-CONTAIN coherence and cycles.**

- `GATE-CONTAIN` depends on EGR-01a, LEG-01a, IFR, LOG-01 (and ISO for the
  path). All are containment-only and activate on merge. None depends on a
  gated CR, on `OWNER_CHANNEL_READY` or on an owner record.
- CR-ACT-01 depends on POL and IFR (merged). Trust anchors depend on
  bootstrap. Owner-control and gated CRs depend on `OWNER_CHANNEL_READY`
  and/or GATE-CONTAIN.

Every edge was re-checked against the tier table. Both graphs are
**acyclic**, and the ordering is coherent. Apart from HR7-01, GATE-CONTAIN
is coherent.

---

## 15. Handle and diagnostic analysis

See §8. The model is sound as a contract:

- default-empty inheritance;
- standard streams null or mediated;
- a pre-existing unadmitted handle disqualifies the process;
- the error boundary is the only path out for uncaught failures.

INV-CB-099 carries each of these. The remaining obligations are
implementation work (CR-IFR-01, CR-LOG-01, CR-ISO-01).

---

## 16. Invariant audit

### 16.1 Accounting (verified from §33, not the correction report)

- 106 invariant rows and 106 distinct IDs;
- **105 active**: INV-CB-030 is withdrawn and its ID is not reused;
- no new ID in r5;
- rows whose status column contains "rev r5":
  **048, 062, 076, 079, 081, 097, 098, 099, 102, 104, 105, 106 = 12.**

This matches §0.6 and the §33 totals paragraph exactly.

### 16.2 Classification of the invariants in scope

| ID | Class | Reason |
|---|---|---|
| INV-CB-097 | **VALID** | Requires DENY before execution for an unknown or unbounded readable universe; proven maximum only from a boundary-established finite universe; explicitly no owner-ceiling exception; results and artifacts need a whole-execution ConfinementRecord. The HR6 UNSOUND clause is gone. |
| INV-CB-098 | **VALID** | "Resources included in provenance are never fewer than the resources the Git/tool sandbox can actually read"; the Git view is exactly the closure, or the whole repository fully bound and joined; no partial-file-list assumption. |
| INV-CB-099 | **VALID** | Covers telemetry field constraints, stdout, stderr, warnings, uncaught exceptions, raw tracebacks, protected diagnostics, the explicit handle list and admission ineligibility. |
| INV-CB-102 | **INCOMPLETE (LOW)** | Covers authorize-before-DNS, pinned connect, peer check, re-validation and scoped pools (adapter, internal-endpoint policy, policy version, epoch). The resolver-egress rule (owner-configured upstream only) is only in §16.7 and TST-CB-102 (HR7-09). |
| INV-CB-105 | **AMBIGUOUS** | Semantic activation, manifest, digests, configuration, migrations, prerequisites, startup validation and runtime loss are all present. "Validates … revocation epoch" is resolved by §40.F and TST-CB-105 as "deactivate when the epoch advances", which conflicts with §31/§21.5 (HR7-01). |
| INV-CB-106 | **VALID** | Idempotency, proposer binding, single use and bounds are all present. The implementation must source "proposer" from broker-set metadata (HR7-05). |

None of these is REDUNDANT.

The other r5-revised invariants were read for coherence:

- 048, 062, 076, 079, 081 and 104 are consistent with §9.10, §9.11,
  §16.2 and §17.6/§17.9;
- INV-CB-076 and INV-CB-079 depend on the approval-class order (HR7-06)
  and on the source of the proposer id (HR7-05).

---

## 17. Test audit (brief §32)

| Property | Test | Behavioural? |
|---|---|---|
| Unknown readable universe | TST-CB-097: DENY before execution with or without an owner ceiling; zero bytes read from `.env`/`jarvis.db` in the fixture (iso) | Yes |
| Git over-read | TST-CB-098: same-branch, other branch, stash, reflog, unreachable pack; `show`, `cat-file`, direct pack read, `log -p --all`; INTERNAL forbidden (iso) | Yes |
| Inherited handle | TST-CB-099: worker with an unlisted terminal/log/pipe handle → startup refused (iso) | Yes |
| Unmanaged standard streams | TST-CB-099 | Yes |
| Exception leakage | TST-CB-099: main thread, `threading`, asyncio, `warnings`, `print`, `faulthandler`, boundary failure | Yes |
| Activation via startup hook, migration, entry point | TST-CB-105 (a)–(f) | Yes; an import test explicitly does not satisfy it |
| Changed code or manifest digest | TST-CB-105 digest-mismatch clause | Yes |
| Cross-scope pooled connection | TST-CB-102 | Yes, with zero DNS queries asserted at the test resolver |
| Foreign T-7 proposal; reused proposal | TST-CB-106 | Yes (real-store) |
| Template channel | TST-CB-048, 079: free selectors rejected; byte-identical child values except template; measured capacity ≤ bound | Yes |

The tests exercise behaviour against real boundaries, not document text.

**Gaps:**

- TST-CB-105 **mandates** the HR7-01 defect ("revocation epoch advances
  past the record's → deactivated"). It needs a counter-case: an unrelated
  revocation must not deactivate.
- No test for T-9 cancellation timing or a defined `B` (HR7-04).
- No test for non-filesystem OS state in 2R (HR7-03).
- No test for a proposal whose content field names the parent as proposer
  while the broker-recorded creator differs (HR7-05).

---

## 18. LineagePair regression

r5 changes to T-7:

- step 0 adds global `proposal_ref` uniqueness;
- step 2 adds the proposer check and rejection of removed fields;
- step 3 adds the template lookup;
- step 4 takes values from the template, with version-pinned comparands and
  approval attenuation.

§9.3 step 6, §21.3 and the pair digest are unchanged. No check was
removed.

| Attack | Blocking check | Result |
|---|---|---|
| Root-pair substitution | CHILD path reads only `deb.child_lineage_pair_id`; `pair.parent_pair_id == parent.lineage_pair_id`; ROOT requires `parent_pair_id None` ∧ `root_task_id == tcr.task_id` | DENY |
| Sibling substitution | `deb.task_id == tcr.task_id`; `pair.issuer_event == deb.issuance_event`; leaf uniqueness | DENY |
| Mixed pair | Leaves only from the pair; each leaf in at most one pair; both leaf parents = the parent's leaves | DENY |
| Parent revocation | T-7 step 1 (parent LIVE, ancestors effective); `issue_esc` (parent not REVOKED); §34 step 3 ancestor walk | DENY |
| Grandchild delegation | Each generation checked against its immediate parent; transitive | Only the exact chain binds |
| Replay | Step 0 returns the existing binding (harmless; `issue_esc` re-checks); a foreign parent is DENY; ids never reused | DENY / idempotent |

`LINEAGEPAIR R5 REGRESSION-FREE`

---

## 19. Network regression

Every r4 first-hop protection is still present in §16.7:

- canonicalization (step 1);
- authorization before DNS (new step 2);
- trusted resolution only;
- every-address inspection (step 3);
- special/private/metadata/host-own denial (policy);
- pinned connect, with no second resolution (step 5);
- peer check before any byte (step 6);
- redirect and new-connection re-validation (step 7, repeating steps 1–6,
  so every redirect hop is also authorized before resolution);
- resolver egress restricted to owner-configured resolvers.

Step 4 still re-applies the destination authorization and the address
policy after resolution. **No weakening.**

---

## 20. Child attenuation regression

| Dimension | r5 | Status |
|---|---|---|
| Destinations | ⊆ parent, now by recorded `(id, version, digest)` | Unweakened (strengthened) |
| Environment | ≼ the parent's recorded definition | Unweakened (strengthened) |
| Persistence | `≤ min(parent_profile, K_parent)` unchanged | Unweakened |
| Taint ceiling upper bounds | Unchanged | Unweakened |
| Provider/model | Meet rule unchanged | Unweakened |
| Approval class | New row | Added; sound only under HR7-06's order constraint |
| Template values | Still check-not-clip against the parent's leaves | Unweakened |

If the policy version advances between T-7 and `issue_esc`, the child's
`EnvironmentClassRef` no longer matches and the result is DENY. That is
fail-closed.

---

## 21. Owner decisions (not made here)

| # | Decision | Assessment |
|---|---|---|
| 1 | ChildDelegationTemplate model and the stated T-7 residual bound | Normal owner policy decision, compatible with READY. **Technical precondition:** the bound must be computable, so `B` must be defined and the cancellation term added (HR7-04). |
| 2 | Approval-class strictness order | Policy content, but with a technical constraint: "stricter" must mean *requires at least every requirement of* (inclusion). A total order over non-nested classes would let a "stricter" child drop a parent requirement (HR7-06). With that constraint stated, this is an ordinary owner decision. |
| 3 | CR classification (CR-ISO-01, CR-NET-01, CR-ACT-01 as containment-only; the trust-anchor class) | Mostly an owner decision, but its technical coherence depends on a definition of a "restriction-only" manifest that the design does not give (HR7-07). CR-ISO-01 in particular adds processes and IPC endpoints. The owner should decide with that definition in hand. Merges are separately owner-authorized, so this is not a freeze blocker. |

---

## 22. New HR7 findings

### HR7-01 — Activation validity is tied to the global revocation epoch: any revocation deactivates every gated path

- **Severity:** MEDIUM
- **Category:** NEW (introduced by the r5 HR6-04 correction)
- **Section:** §40.F (`IntegrationActivation.activation_epoch`, "Startup
  validation", "Runtime loss of a prerequisite"); CR-ACT-01; §31 item 3;
  §21.5 "Effect"; §7.3 T-9; §30.1 `INTEGRATION_ACTIVATION_DENIED`;
  TST-CB-105 "Runtime loss"
- **Invariant:** INV-CB-105 (also in tension with INV-CB-090 and the §21.5
  scoping)
- **Attack or contradiction:**
  1. `activation_epoch` is the revocation epoch at approval.
  2. §40.F lists "the epoch advances past a record's activation epoch" as a
     lost prerequisite, and TST-CB-105 requires deactivation in that case.
  3. §31 item 3 makes every revocation increment that one global epoch:
     clearance, delegation, pair, grant, policy, destination
     authorization, objective. So do T-9 renunciations (§21.5).
  4. T-9 is available to agents ("an agent's request to give up authority
     or clearance"). A prompt-injected agent (class M) can renounce its own
     leaf.
  5. That increments the epoch. Every gated CR's record is then stale.
     Every gated path deactivates and every in-flight ESC in the
     installation becomes TERMINATED. After any restart, startup
     validation keeps them inactive until the owner re-approves every
     gated CR.
- **Impact:**
  - A class-M-triggerable, installation-wide denial of service.
  - A globally observable one-bit signal from any execution to all others.
  - The gated runtime is non-operational after its first routine
    revocation.
  - It contradicts §21.5 ("revocation of either half kills the pair",
    scoped to that lineage) and the intent of TC-42.
  - Confidentiality is not weakened: the failure is closed.
- **Required correction:**
  - Activation validity must depend on the record itself not being revoked
    or superseded (by owner act), and on epoch **non-regression**
    (store epoch ≥ anchor and ≥ `activation_epoch`). It must never depend
    on the epoch *advancing*.
  - Use `activation_epoch` only to detect rollback of the record.
  - Correct §40.F, CR-ACT-01, the INV-CB-105 clause "validates … revocation
    epoch", and TST-CB-105.
  - Add a TST-CB-105 counter-case: an unrelated revocation (T-9
    renunciation, grant or pair revocation) must **not** deactivate gated
    paths. Revocation of the activation record or an epoch regression
    must.
- **Freeze blocker:** YES. The invariant and normative test encode an
  activation rule that contradicts the revocation model, so the brief's
  "activation model is sound" criterion fails. The fix is a narrow text
  change.
- **Implementation blocker:** YES (CR-ACT-01)
- **Deployment blocker:** YES

### HR7-02 — ConfinementRecord and tool-result provenance bindings are incomplete

- **Severity:** LOW
- **Category:** NEW
- **Section:** §17.9 ConfinementRecord; §13.1 ProvenanceRecord; §34
  `ingest_tool_result()`
- **Invariant:** INV-CB-097, INV-CB-062
- **Attack or contradiction:**
  - The record does not bind the worker/process identity, the policy
    version, the environment allow-list or launcher-configuration digest,
    or a digest of the result/output bytes.
  - Soundness therefore relies on TCB code passing only the supervised
    worker's IPC output under that `invocation_id`.
  - The tool-result item's ProvenanceRecord has no ARS or ConfinementRecord
    reference, so the provenance universe of a result cannot be
    reconstructed from records. The label still covers U.
- **Impact:** a TCB routing bug could pair a CLEAN record with bytes from
  elsewhere. Audit reconstruction is weaker. Replay across invocations is
  already prevented.
- **Required correction:**
  - Add `worker_identity`, `policy_version`, `environment_digest`,
    `launcher_config_digest` and `result_digest` / `output_digests` to the
    record.
  - Require `digest(content) == cr.result_digest` in `ingest_tool_result`.
  - Add `authorized_read_set_id` and `confinement_record_id` to the
    tool-result ProvenanceRecord.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ING-01, CR-ISO-01)
- **Deployment blocker:** NO

### HR7-03 — The Level 2R property does not name non-filesystem OS-readable state

- **Severity:** LOW
- **Category:** NEW
- **Section:** §6.5 Level 2R row; §17.9 ReadableUniverse; CR-ISO-01
- **Invariant:** INV-CB-097
- **Attack or contradiction:**
  - §17.9 asserts the readable universe is exactly
    ARS ∪ network ∪ write view ∪ runtime image.
  - §6.5 restricts filesystem, network, environment, DB handles and IPC.
    It does not name the registry, clipboard, desktop/window/UI objects,
    other processes' information, named kernel objects, shared memory,
    pipes of other Jarvis components, or `/proc` and sysfs.
  - A hostile ISO-TOOL worker reading, for example, the clipboard (owner
    data outside the label universe) could return it in an INTERNAL
    result.
  - Separately, the runtime image must be "free of protected content", but
    §15.5 labels Jarvis source `REPOSITORY` CONFIDENTIAL. A worker harness
    copied from the repository needs an explicit classification.
- **Impact:** unlabeled influence is possible if CR-ISO-01 is implemented
  to the literal §6.5 list. The general INV-CB-097 wording ("bounds the
  tool's actual readability") covers it only implicitly.
- **Required correction:**
  - State that a 2R/3 worker can read **no** OS state other than the four
    sets.
  - Require CR-ISO-01 to enumerate and close the listed channels, or prove
    them free of protected information.
  - Classify the worker harness in the runtime image.
  - Add an (iso) case to TST-CB-097.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ISO-01)
- **Deployment blocker:** NO

### HR7-04 — T-7 residual bound omits child cancellation and leaves `B` undefined

- **Severity:** LOW
- **Category:** RESIDUAL-HR6 (HR6-03)
- **Section:** §9.11 residual table; §14.8; §38.2; §32
- **Invariant:** INV-CB-048
- **Attack or contradiction:**
  - The parent can revoke issued children through T-9. Whether and when is
    visible at the child's destinations: its emissions stop. This adds up
    to `⌈log2(B+1)⌉` bits per child and is not in the bound.
  - `B` ("distinguishable timing buckets") depends on the observation
    resolution of the child and of external receivers. The design does not
    fix that resolution, yet requires the bound to be computed at policy
    approval.
- **Impact:** the stated residual can be understated by roughly the timing
  term, and the policy-approval computation is underdetermined.
- **Required correction:**
  - Add a revocation term, or forbid parent revocation of children within
    a window.
  - Define `B` from the per-window bound and a stated observation
    granularity.
  - Extend TST-CB-048.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ESC-01, CR-POL-01)
- **Deployment blocker:** NO

### HR7-05 — The source of `TaskProposal.proposer_esc_id` is unspecified

- **Severity:** LOW
- **Category:** NEW (within the HR6-09 correction)
- **Section:** §9.6 TaskProposal; §9.7 step 2
- **Invariant:** INV-CB-106, INV-CB-079
- **Attack or contradiction:**
  - TaskProposal is untrusted data plane, and `proposer_esc_id` is one of
    its fields.
  - If the field is taken from content, a colluding ESC P2 can write
    `proposer_esc_id = P1` into its own proposal, and P1 then consumes it.
  - That reopens the cross-ESC outcome channel HR6-09 closed: P1 learns
    P2's template and profile choice from the T-7 outcome.
- **Impact:** a few bits per proposal across ESCs.
- **Required correction:** define the proposer as the broker-set
  `item.created_by_esc`, or the OwnerChannel session record for owner
  proposals, never a content field. Extend TST-CB-106.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ESC-01)
- **Deployment blocker:** NO

### HR7-06 — The approval-class "total strictness order" must be an inclusion order

- **Severity:** LOW
- **Category:** NEW
- **Section:** §9.2 `approval_class`; §9.4; §9.10 approval row; §9.3
  step 5; §9.7 step 4
- **Invariant:** INV-CB-076
- **Attack or contradiction:**
  - The design requires only `strictness(child) ≥ strictness(parent)` in a
    policy-defined **total** order.
  - Suppose two classes impose different, non-nested requirements (for
    example "owner approval for external sends" and "owner approval for
    financial actions"). A total linearization then lets a "stricter"
    child drop the parent's specific requirement.
  - This contradicts "a child can only add approval requirements".
  - The v0.2.5 per-Action approval still applies and limits the impact.
- **Impact:** an attenuation gap in the v0.2.6 approval-class layer,
  depending on policy content.
- **Required correction:**
  - Define strictness as requirement inclusion, i.e. a partial order.
  - Reject incomparable classes (DENY), as for environments.
  - Or require the policy's classes to be nested.
  - State this as a constraint on owner decision 2.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-POL-01, CR-ESC-01)
- **Deployment blocker:** NO

### HR7-07 — "Containment-only" (restriction-only manifest) is undefined; CR-ISO-01 does not fit it literally

- **Severity:** LOW
- **Category:** NEW
- **Section:** §40.E activation graph; §40.F classification table
- **Invariant:** INV-CB-105
- **Attack or contradiction:**
  - Containment-only CRs activate on merge "with a reviewed manifest whose
    every surface is a restriction".
  - CR-ISO-01 adds a store-owning broker process, IPC endpoints, the Tool
    Launcher and worker creation.
  - CR-NET-01 adds upstream resolver egress.
  - CR-IFR-01 and CR-ACT-01 add a process-wide guard, a monitor and a
    validator.
  - None of these is literally a restriction.
  - Either the gate can never be formed as written, or reviewers apply an
    unstated, looser criterion. A new IPC listener could then go live
    without an owner record.
- **Impact:** ambiguity in the classification the owner is asked to
  approve (decision 3). Merges still need separate owner authorization.
- **Required correction:** define a containment-only manifest as:
  - surfaces that remove, deny or confine flows, plus TCB-internal surfaces
    that carry no broker-labeled content;
  - no new external listener;
  - no egress other than owner-configured resolvers;
  - local, authenticated IPC endpoints only.

  Alternatively, reclassify CR-ISO-01's broker-process part.
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ACT-01, CR-ISO-01)
- **Deployment blocker:** NO

### HR7-08 — Omissions in the §34 normative procedure

- **Severity:** LOW
- **Category:** NEW
- **Section:** §34 `request_context()` step 0, `deliver()`; §17.6 rule 3;
  §17.9 construction step 2
- **Invariant:** INV-CB-105, INV-CB-081, INV-CB-008
- **Attack or contradiction:**
  - **(a)** Neither step 0 nor the `deliver()` re-run checks
    GATE-CONTAIN / activation state. Loss of EGR-01a or LOG-01 is enforced
    only by §40.F prose.
  - **(b)** The artifact registration and ConfinementRecord lookup are
    written inside the pre-execution delivery transaction, with only a
    comment saying they happen later. The post-execution "effect's own
    delivery commit" and its revalidation set are not specified.
  - **(c)** For artifact-producing tools, TNL-recorded network resources
    join the output label but never extend the ESC's taint and never face
    `flow()` or the ceiling. §17.6 rule 3 says the taint grows by the read
    labels because the agent observes the effect's outcome. That outcome
    is an unaccounted signal of a few bits per invocation.
- **Impact:** implementer confusion, and a small unaccounted observable.
- **Required correction:**
  - Add an activation/GATE-CONTAIN precondition to step 0.
  - Write the post-execution commit explicitly: revalidation, CR check,
    binding, and a taint extension by network-resource labels (or a
    ceiling check over the authorized destinations' proven maximum before
    execution).
- **Freeze blocker:** NO
- **Implementation blocker:** YES (CR-ING-01, CR-ART-01, CR-ACT-01)
- **Deployment blocker:** NO

### HR7-09 — The INV-CB-102 text omits resolver egress

- **Severity:** INFO
- **Category:** RESIDUAL-HR6 (HR6-07)
- **Section:** §33 INV-CB-102; §16.7
- **Invariant:** INV-CB-102
- **Attack or contradiction:** the rule "trusted resolver upstream only to
  owner-configured resolvers; never DoH/tool/environment resolvers" is in
  §16.7 and TST-CB-102 but not in the invariant.
- **Impact:** none if §16.7 is followed. The invariant is less complete
  than its tests.
- **Required correction:** add the clause to INV-CB-102.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR7-10 — The synthetic Git view avoids whole-repository taint only partially

- **Severity:** INFO
- **Category:** NEW (availability note)
- **Section:** §17.11 preferred realization; §17.7 Git rows
- **Invariant:** INV-CB-098
- **Attack or contradiction:**
  - Most operations need the index or trees, and these name every tracked
    path and blob id.
  - Their labels therefore carry the join of every tracked file.
  - A commit to `public.txt` in a tree that also holds `secret.txt` yields
    RESTRICTED outputs.
- **Impact:** confidentiality-safe, with an availability cost. HR5-13 is
  already deferred.
- **Required correction:** none for freeze. State this cost next to the
  "avoids permanent whole-repository taint" sentence.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

### HR7-11 — Template `authority_scope` must also derive `objective_ref`

- **Severity:** INFO
- **Category:** NEW
- **Section:** §9.11 ChildDelegationTemplate; §9.7 step 4
- **Invariant:** INV-CB-079
- **Attack or contradiction:**
  - v0.2.5.1 `AuthorityScope` carries `objective_ref` (verified in code).
  - The template stores the scope as an "exact value except expires_at".
  - A fixed `objective_ref` would make templates objective-specific, or
    make T-7 DENY through objective mismatch.
- **Impact:** fail-closed availability only; no frozen-contract change.
- **Required correction:** state that `objective_ref` is also derived from
  the parent ESC, like `expires_at`.
- **Freeze / implementation / deployment blocker:** NO / NO / NO

**Counts:** CRITICAL 0 · HIGH 0 · MEDIUM 1 (HR7-01) · LOW 7 (HR7-02..08) ·
INFO 3 (HR7-09..11) · total 11.

---

## 23. Freeze blockers

| ID | Why it blocks freeze |
|---|---|
| **HR7-01** | The freeze criterion "activation model is sound" fails. INV-CB-105 and normative TST-CB-105 encode deactivation on every revocation-epoch advance. This contradicts the revocation model (§21.5, §31) and gives class M an installation-wide denial of service. |

**Freeze-standard scorecard**

| Criterion | Status |
|---|---|
| No CRITICAL / HIGH design blocker | ✓ |
| No freeze-blocking MEDIUM | ✗ (HR7-01) |
| HR6-01 RESOLVED_IN_R5 | ✓ |
| HR6-02 RESOLVED_IN_R5 | ✓ |
| HR6-03/04/05 adequately resolved | 03 ✓ · 04 ✗ (PARTIALLY_RESOLVED, HR7-01) · 05 ✓ |
| INV-CB-097 sound | ✓ (VALID) |
| Git provenance / read confinement sound | ✓ |
| Activation model sound | ✗ (HR7-01) |
| Handle / diagnostic model sound | ✓ |
| Tests normatively specified | ✓ (TST-CB-105 must be corrected with HR7-01) |
| GATE-CONTAIN coherent | ✓ in ordering and acyclicity; ✗ in runtime-loss semantics (HR7-01) |
| LineagePair regression-free | ✓ |
| No frozen-contract amendment needed | ✓ |

---

## 24. Implementation blockers (separate from freeze)

In addition to every row of design §43.1, all of which remain:

- HR7-01 (CR-ACT-01);
- HR7-02 (CR-ING-01, CR-ISO-01);
- HR7-03 (CR-ISO-01);
- HR7-04 (CR-ESC-01, CR-POL-01);
- HR7-05 (CR-ESC-01);
- HR7-06 (CR-POL-01, CR-ESC-01);
- HR7-07 (CR-ACT-01, CR-ISO-01);
- HR7-08 (CR-ING-01, CR-ART-01, CR-ACT-01).

None of the §43.1 machinery exists: no ESC, taint, policy, lineage,
task-control, registry, launcher, Mediated Reader, Level 2R, Git View
Builder, telemetry, network layer or activation machinery.

## 25. Deployment blockers (separate)

- Every §43.2 row, unchanged. The "live" rows (R-01..R-09, R-11, R-13,
  R-22..R-26, R-29, R-30) are pre-existing runtime defects. No design
  revision fixes them.
- **HR7-01:** no gated CR may be deployed while activation validity is tied
  to epoch advancement.

---

## 26. Frozen-contract compatibility

- **v0.2.5.1 `AuthorityScope`:** unchanged. Templates pass values to the
  unchanged issuer. `expires_at` (and, per HR7-11, `objective_ref`) are
  derived, not re-typed.
- **v0.2.5:** check-not-clip, principal-repetition, T-9 as a usage
  restriction and the CR-01 requester binding are all preserved.
- **v0.2.3:** the router default is never relied on.
- **v0.2.4:** identifiers are unchanged.
- **v0.2:** §8/§10 are strengthened, since approval class and every other
  child dimension only attenuate.

**No amendment to any frozen v0.2.x contract is required.** AMD-025-01
remains uncreated and unnecessary. All HR7 corrections are v0.2.6 text
changes.

---

## 27. Final status

r5 resolves both HR6 freeze blockers:

- HR6-01: the unknown readable universe is DENY before execution, with no
  owner-ceiling exception and a sound proven-maximum rule;
- HR6-02: Git readability equals the closure, or the whole repository is
  joined.

r5 also resolves HR6-03, 05, 06 and 07–12. The invariant accounting is
exact. The r5 tests exercise behaviour. LineagePair, the network
protections and child attenuation show no regression.

The HR6-04 correction introduced one new freeze-blocking defect (HR7-01).
An activation record becomes invalid whenever the global revocation epoch
advances, and every revocation, including an agent's own T-9 renunciation,
advances it. The contract therefore deactivates the whole gated runtime on
the first routine revocation, and class M can trigger that. The failure is
closed and does not reduce confidentiality. It is still a contradiction in
a normative invariant and test, so the activation model is not sound as
written.

```text
R5 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

The required correction is narrow. Replace "epoch advances past the
record's activation epoch" with "the record is revoked or superseded, or
the epoch regresses", in §40.F, CR-ACT-01, INV-CB-105 and TST-CB-105, and
add the counter-case test. Correct HR7-02..08 (LOW) in the same pass. A
focused verification of that delta should then be sufficient.

READY would not have meant frozen, secure or implementation-authorized.
This status only records that the technical review required before the
owner's freeze decision has not yet passed.

> No v0.2.6 production implementation has been authorized or created.

---

## Appendix A — Read-only validation

Commands were run from `C:\Users\Gyuro\jarvis-os` with
`.venv/Scripts/python.exe`, before this HR7 file was written.

| Command | Result |
|---|---|
| `python scripts/check_v013_freeze_baseline.py` | exit 0 — `v0.1.3 FREEZE BASELINE CHECK: OK` (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `python scripts/check_v020_contract.py` | exit 0 — OK |
| `python scripts/check_v023_router_contract.py` | exit 0 — OK |
| `python scripts/check_v024_agent_contract.py` | exit 0 — OK |
| `python scripts/check_v025_design_contract.py` | exit 1 — `DISCREPANCY FOUND`, solely "file outside the v0.2.5.1 allowlist is new/modified" for the six untracked v0.2.6 documents (expected; this HR7 file did not yet exist and would also be listed) |
| `python -m pytest -q -p no:cacheprovider` | **1 failed, 2234 passed, 1 warning** (371 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`, the same expected v0.2.5 checker discrepancy caused by the untracked v0.2.6 documents. The flaky concurrency test HR6 observed did not fail in this run. |

No validator, test or configuration was modified.

## Appendix B — Integrity

Re-verified at the end of the review (see the terminal report). The design
and HR2–HR6 are unchanged from the §2 hashes. HEAD is unchanged and there
are no tracked changes. The only new file is this HR7 document. No commit,
push or merge was made.
