# Jarvis OS v0.2.6 — HR6 Final Security Design Verification

```text
subject                        = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r4)
subject status on entry        = CORRECTED R4 — PENDING HR6 FINAL DESIGN VERIFICATION
prior reviews checked          = HR2 (docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md)
                                 HR3 (docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md)
                                 HR4 (docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md)
                                 HR5 (docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md)
review type                    = security design verification only
design_modified                = false
hr2_hr3_hr4_hr5_modified       = false
code_tests_validators_modified = false
opendex_modified               = false
final_status                   = R4 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

Section numbers (§N) refer to the r4 design unless another document is
named. Finding IDs `HR6-NN` in this document are new. They are unrelated to
the r1 self-review IDs "HR6-01..22" that the design withdrew in §44.4 (see
HR6-11).

---

## 1. Independence

This session did **not** author:

- design revisions r1, r2, r3 or r4;
- HR2, HR3, HR4 or HR5.

It had no access to the drafting or review conversations. It worked only
from the repository contents. Every claim was re-derived from the r4 text
and, where needed, from the code at HEAD. The correction record (§0.5) and
the design's self-assessments ("closes", "RESOLVED") were not taken as
evidence.

**Limitation.** This review uses the same model family as the earlier
reviews (HR3-16, HR4-12, HR5-16). It is not organizationally independent.
The design's recommendation for a human review of §6, §8, §9, §16.5/§16.7,
§17.6/§17.9/§17.10, §18.2–§18.4 and §21.3 still stands.

---

## 2. Repository state

Inspected read-only at the start of this review.

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `13796dcd61015098429f343e2fb982a9c75698bb` |
| `origin/master` | `13796dcd61015098429f343e2fb982a9c75698bb` (= HEAD) |
| Tag at HEAD | `v0.2.5.1` |
| Tracked changes (`git diff`, `git diff --cached`) | none |
| Untracked (`git status --short -uall`) | the r4 design, HR2, HR3, HR4, HR5 (5 files, all under `docs/`) |
| Production-code modifications | none |

This matches the expected baseline. Nothing was normalized.

**SHA-256 at start of review**

| File | Role | SHA-256 |
|---|---|---|
| `docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md` | r4 design | `05672f95ab6fc82390eccfdb980ad961677568ccb56b39994761f31f27d636a9` |
| `docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` | HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` |
| `docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md` | HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` |
| `docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` |
| `docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md` | HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` |

**OpenDex** (`C:\Users\Gyuro\opendex-reference`): Git HEAD
`3e898343d1127c8d5075b459acdd55da83b83f04` (same value as design §41),
`git status` clean. A content hash was taken over all 40,795 non-`.git`
files: `7d373682c17e0e674671c97ee9bd9417e222873e2b3774b74ce9fcb84ecb0905`.
No OpenDex file was modified. §38 re-checks this hash.

---

## 3. Materials reviewed

- **r4 design:** read in full (lines 1–5211).
- **HR5:** §26 findings HR5-01..HR5-07 in full; structure, verdicts and
  required corrections for HR5-08..16.
- **HR2/HR3/HR4:** headers and independence statements only, for
  traceability. The r4 design and HR5 carry every earlier finding forward
  explicitly.
- **Frozen contracts, for compatibility:**
  - v0.2.5 design: principal-cycle rule T-06 and the "never searched"
    parent rule HR-22;
  - v0.2.5.1 `app/authority_contracts/contracts.py`: the `AuthorityScope`
    fields, `ACTION_TYPE_VOCABULARY` and `PTier`;
  - v0.2 / v0.2.3 / v0.2.4 contracts, through the read-only validators
    (§37).
- **Code:** inspected only to check r4 assumptions. `AuthorityScope`
  carries `expires_at: datetime` and `action_types: frozenset[str]`, which
  matters for HR6-03.

---

## 4. HR5-01 verification — enforced tool reads

The r4 correction adds four things:

- the `AuthorizedReadSet` (ARS), built by the Tool Launcher, a TCB
  component (§17.9);
- the Mediated Reader for reviewed in-process adapters;
- the OS-enforced Level 2R view for every other tool (§6.5 ISO-TOOL);
- filesystem and archive confinement (§17.10).

**What now holds**

| Requirement | r4 | Verdict |
|---|---|---|
| A declared read set is never proof | §17.6 rule 2, §17.9 normative rule, INV-CB-097, forbidden design 35 | ✓ |
| The Tool Launcher produces an ARS before execution | §17.9 construction steps 1–3; §34 `deliver()` | ✓ |
| Reviewed in-process adapters read only through the Mediated Reader | §6.5 conditions; §17.9 step 3; Mediated Reader returns bytes, never paths | ✓ (against class M, as stated) |
| Other tools run under an enforcing boundary | §6.5 ISO-TOOL → Level 2R; "a tool that fits neither is not enabled" (§17.9) | ✓ as a rule, but contradicted by §17.6 rule 2a (HR6-01) |
| Subprocesses cannot bypass | §6.5: a subprocess forces ISO-TOOL; §18.4: subprocess creation restricted in 2R | ✓ |
| Symlinks, junctions, hardlinks, reparse points, aliases, TOCTOU | §17.10 table: every component checked, handle-based identity, digest-verified read, link count 1, same volume, ADS/8.3/case handling | ✓ |
| Archive member reads included | §17.10 archive rules: members are ARS entries; the trusted extractor enumerates them; the output directory is fresh | ✓ |
| Actual influencing reads determine provenance | Labels come from the enforced readable set, which must be ⊇ the actual reads (§17.6 closing paragraph) | ✓ only if view = entries. False for Git (HR6-02) and for INCOMPLETE sets (HR6-01) |

### Critical question — is the conservative-ceiling path sound?

**No.** §17.6 rule 2a, INV-CB-097 and INV-CB-081 allow this when the
boundary "cannot guarantee a complete readable set":

> artifact creation is DENY, **unless the adapter's registration names an
> explicit, owner-approved conservative maximum** … and every output is
> labeled at least that ceiling.

The rule's own example is "an adapter at Level 1 that uses a library with
ambient file access, or a subprocess not confined at Level 2R". Such an
adapter can reach everything the Jarvis OS account can reach:

- every managed store at every label;
- `jarvis.db`, including broker-owned and legacy stores;
- `.env`, which holds raw secrets. Secrets are not items (§25), so no
  `ContextLabel` can bound them.

A finite owner-chosen ceiling over that universe is unsound. Nothing in r4
requires the ceiling to dominate the enforced reachable universe. The
required implication is:

`unknown actual read set → (the enforcement boundary proves a bounded resource universe U whose every element has a label ⊑ ceiling, and U contains no secret-bearing, broker-owned or legacy store) ∨ DENY`

It is **not stated**. The §16.2 adapter-level ceiling for untrusted
connectors is sound because it is defined as the join over what the
Level 3 sandbox makes reachable. Rule 2a does not import that definition.

The path also contradicts other parts of r4:

- **§6.5:** "any tool that does not meet every condition is ISO-TOOL and
  runs only at Level 2R". A Level 1 ambient adapter may therefore not run
  at all.
- **§17.9:** "a tool that fits neither is not enabled".
- **§34 `ingest_tool_result()`:** labels tool *results* from `ars.entries`
  only and never checks `ars.completeness`. Rule 2a covers only artifacts,
  and `deliver()` checks INCOMPLETE only under `has_persistent_effect`.
  §16.2's formula lists "an INCOMPLETE read set" as a join term, but the
  normative procedure omits it. An INCOMPLETE read tool's result is
  therefore labeled from the declared-and-resolved entries alone. That is
  exactly the HR5-01 defect, for the result channel.

→ **HR6-01**.

A second gap is in the one tool family r4 details, Git (§17.9): "its view
limited to **the managed repository and the entries**". The worker can
read every object in the repository: other branches, packs, reflog,
stash, unreachable objects. The labels are computed only from the entries
(staged tree and parent commit, §17.6 rule 2). Readable view ⊋ label
basis, which contradicts §17.9 step 3 ("cannot open any other file") and
the ISO-TOOL claim of defending against the tool code's own over-reads.
→ **HR6-02**.

**Verdict HR5-01: PARTIALLY_RESOLVED.** The architecture is right: the
ARS, the Mediated Reader, Level 2R and §17.10 confinement are sound
against the HR5-01 attack family. The fallback and the Git view reopen the
defect, and one freeze criterion is "read-set enforcement is sound".

---

## 5. HR5-02 verification — logs, CLI, diagnostics

| Requirement | r4 | Verdict |
|---|---|---|
| Content-bearing by default | §18 class B requires a closed type; §18.3: logs/CLI/debug/exception logging "not globally content-free"; INV-CB-073, INV-CB-099 | ✓ |
| Only schema-constrained telemetry is content-free | §18.3: Security Telemetry API with a registered schema per event code | ✓ (see HR6-10 for field-level hardening) |
| Raw `str(exc)` prohibited from telemetry | §18.3 rejection list; `SecurityError(code, correlation_id)`; §35.1 item 4 | ✓ |
| Raw diagnostics are protected information | §18.3: diagnostic item into `DIAGNOSTIC_STORE` labeled ⊒ H_exec (or RESTRICTED AUDIT) | ✓ |
| stdout is not the owner | §18.3 terminal table; S-49; INV-CB-099 | ✓ |
| Redirected stdout/stderr does not escape | §18.3: redirected output is EXPORT unless the target is the registered `DIAGNOSTIC_STORE`; stdout is EXPORT, so content is never written there | ✓ at contract level; Level 1 mechanism gap in HR6-05 |
| CLI display through an authorized sink | Developer console = EXPORT; only an OwnerChannel client is `USER_DISPLAY` | ✓ |

**Attack traced:** protected objective → `logger.info(objective=…)` →
terminal, file or collector.

1. Security-sensitive components may log only through the Telemetry API.
   The API rejects the `objective` field (`CB_TELEMETRY_CONTENT_REJECTED`)
   and never falls back.
2. In other code, the handler set is allow-listed and verified at startup
   (§18.4 item 5).
3. A content-bearing log is a sink. It is reachable only as a `PERSIST`
   into `DIAGNOSTIC_STORE`. Stdout, a file or a collector is EXPORT and
   needs `export_allowed` plus a destination authorization.
4. The Runtime Registry Monitor refuses unregistered handlers.

The logger path is closed.

The residual paths are writes that bypass `logging`:

- uncaught-exception tracebacks via `sys.excepthook` / `threading.excepthook`;
- `warnings` output;
- `print` inside third-party libraries;
- `faulthandler`;
- handles opened before content arrives.

The contract covers them (INV-CB-100, layer C: "content-bearing output is
possible only through a surface the Monitor admitted"). The Level 1
mechanism r4 describes does not (HR6-05). That is an implementation
blocker, not a contract defect.

**Verdict HR5-02: RESOLVED_IN_R4.**

---

## 6. HR5-03 verification — information-flow registry

| Layer | r4 | Distinct? |
|---|---|---|
| A build-time discovery | §18.2 table: ORM, migrations, router, ToolRegistry, log emitters and payload keys, logging config, subprocess/tempfile/socket/SDK call sites. "Not authorization" | ✓ |
| B startup registration | Every component registers every surface before activation; Monitor matches against the approved registry; mismatch → component inactive. "Not authorization" | ✓ |
| C runtime enforcement | Runtime Registry Monitor; unregistered → `CB_SINK_UNREGISTERED`; eligibility attestation before delivery | ✓ — the only authorization |

The critical property is stated normatively: an unregistered source, sink
or store cannot receive or emit protected content (§18 preamble, §18.4,
INV-CB-100).

**Challenge set**

| Surface | r4 handling | Result |
|---|---|---|
| Temp files | Only in `EPHEMERAL_WORKSPACE`; the temp-directory settings of content-holding processes point there; other locations are unregistered (§18.4 item 1, S-53) | ✓ |
| Dynamically created cache | Unregistered → DENY; caches are derived items (§26.5) | ✓ |
| Provider SDK cache | Disabled or mediated, verified at startup; else the configuration is ineligible (item 2, S-54) | ✓ |
| Python library cache | "library-generated file" → DENY (§18.4 box, S-56) | ✓ contract; Level 1 detection gap for handles opened before content arrives (HR6-05) |
| Dynamically registered route | Refused unless it matches the approved registry (item 4) | ✓ |
| Browser download | Named unknown sink → DENY; S-24 disabled | ✓ |
| Plugin-created DB table | "dynamic table/column" → DENY; plugins cannot self-certify | ✓ |
| Subprocess pipe | Registered per adapter; stdout/stderr are ingestion; unregistered → DENY (item 3, S-55) | ✓ |
| Runtime-loaded connector | Inactive until registered by the human-gated workflow; ISO-CONN | ✓ |
| New serializer | "dynamically added HTTP serializer" → DENY | ✓ |

**Verdict HR5-03: RESOLVED_IN_R4** (with implementation finding HR6-05).

### 6.1 Registry bootstrap order (§10 of the brief)

The race to check:

1. a component starts;
2. its logger, cache or temp subsystem initializes;
3. protected content arrives;
4. registry admission happens later.

r4 blocks step 3 before step 4:

- delivery only into a process whose **complete** sink surface was admitted
  and attested (§18.4 eligibility);
- components with any missing surface stay inactive (layer B);
- the guard is installed "before any component loads".

The residual: the guard denies unregistered targets only "**while protected
content is present in the process**". A library that opens a cache, log or
temp handle at import time (step 2, before any content) is not denied, and
the Monitor never learns of that handle. When content arrives later,
writes go to the already-open handle. Hooking file-open calls does not
catch those writes. The eligibility attestation is then wrong. The fix is
to make pre-activation opens disqualifying (HR6-05). Startup is otherwise
fail-closed: an unmatched surface keeps the component inactive, and an
unattested process is ineligible.

### 6.2 Runtime registry trust (§11 of the brief)

A plugin, connector, tool, route, serializer, handler or dynamic model
"cannot self-certify a sink as safe or content-free". Registration is a
request matched by the Monitor against the owner-approved registry, which
is a protected artifact loaded under the high-water mark (§18.2, §18.4
item 4, INV-CB-100). A self-declared `CONTENT_FREE` gains nothing unless
the approved registry already classifies that exact surface as B with a
closed-type proof. **Sound.**

---

## 7. HR5-04 verification — Trusted Network Layer

§16.7 procedure, checked element by element:

| Check | r4 | Verdict |
|---|---|---|
| Scheme canonicalization | Allow-list `{https}`; `http` only per exact authorization; others rejected on every hop | ✓ |
| Hostname canonicalization | Lower-case A-labels; empty labels, trailing-dot ambiguity, percent/backslash in host → rejected | ✓ |
| IDN normalization | UTS-46 non-transitional; invalid/mixed IDN rejected | ✓ |
| Port | Normalized; authorizations bind `(scheme, host, port)` | ✓ |
| Userinfo | Rejected | ✓ |
| IPv4 literal forms | Only 4 decimal octets without leading zeros; octal/hex/integer/short/mixed rejected | ✓ |
| IPv6 | Bracketed, RFC 5952, zone ids rejected | ✓ |
| IPv4-mapped / embedded IPv6 | Mapped, translated, 6to4, Teredo, NAT64 embedded addresses inspected | ✓ |
| DNS result set | Every A/AAAA answer; any denied answer denies the destination | ✓ |
| Private / special-use | Globally-reachable-unicast rule per pinned IANA registries + platform deny list | ✓ |
| Host-own addresses | Denied, including every Jarvis listening address/port | ✓ |
| Cloud metadata | Denied for every connector; no InternalEndpointPolicy may name it | ✓ |
| Connection pinning | Socket connects to the validated IP; SNI/cert/Host use the canonical name | ✓ |
| Peer validation | Actual remote address = validated before any request byte | ✓ |
| Redirect re-evaluation | Steps 1–6 per redirect; scheme and downgrade rules | ✓ |
| No uncontrolled second lookup | Required; a stack that cannot connect to a pre-validated address is ineligible | ✓ |

No protected byte is sent before these checks succeed: step 6 happens
before any request byte, and the EgressGate / delivery commit precedes
transmission (§14.3, §34 step 5).

### 7.1 DNS rebinding

Lookup 1 returns a public IP; policy allows it; lookup 2 would return
`127.0.0.1`.

- The procedure instance connects only to the address validated in step 3.
  No second resolution happens before connect.
- Step 6 aborts if the peer differs.
- A later lookup is a new procedure instance and is re-validated.

**Fails closed.**

**Pool reuse.** Reuse is allowed only for identical
`(scheme, canonical host, port, validated address, TLS identity)`.
Per-delivery destination authorization is re-checked in the delivery
commit (§14.3 step 1), so a revoked authorization cannot ride a pooled
socket. Two problems remain:

- The pool key omits the requester's address scope. An address that is
  permitted only for adapter A under an `InternalEndpointPolicy` can be
  reused by adapter B without step 4 being re-run for B.
- The pool key omits the network-policy version and epoch.

→ **HR6-07 (LOW)**. Two further LOW points in the same finding:

- Resolution (step 2) happens **before** the destination-authorization
  check (step 4), so hostnames that are never authorized still cause DNS
  queries. That is a small DNS-exfiltration channel.
- The trusted resolver's upstream traffic is not modeled as egress.

### 7.2 Policy pinning (§14 of the brief)

- The IANA registries are used "in the policy's pinned version".
- The platform deny list lives in policy (§38.1, CR-NET-01), so it is
  versioned under the SecurityPolicyVersion and high-water mark.
- Host-own and listening addresses are observed at runtime. They only
  add denials, so they cannot make a decision more permissive.

Decisions are reproducible for a given policy version. **Adequate.**

### 7.3 Internal-network exception (§15 of the brief)

The `InternalEndpointPolicy`:

- is owner-approved and separately scoped;
- names the exact `(scheme, address, port)` **and** the exact adapter;
- can never name a metadata endpoint;
- can never be received by a web, search, research or ordinary connector
  adapter (§16.7);
- does not replace the §24 destination authorization. Step 4 requires
  both, and child destinations attenuate.

**Explicit, purpose-bound, least-privilege: yes.** Pool scoping is the
only caveat (HR6-07).

**Verdict HR5-04: RESOLVED_IN_R4.**

---

## 8. HR5-05 verification — delegated child attenuation

| Dimension | r4 rule (T-7 step 4, re-verified by the ESC Issuer, §9.3 steps 10–11) | Verdict |
|---|---|---|
| Destinations | `child_profile.destination_ids ⊆ parent.destination_policy_ref.ids`, check-not-clip; ESC Issuer re-checks `dest ⊆ parent` | ✓ |
| Provider / model | Meet of parent destinations, child profile, owner destination policy (terms) and item labels; local models via `local_model_ids ⊆`; profile naming is never authorization | ✓ |
| External tool audience / export target | `ToolDestination` / `ExportDestination` are destination ids → covered by ⊆ | ✓ |
| Persistence | `child ≤ min(parent_profile, K_parent)` | ✓ |
| Taint ceiling upper bounds | `max_level` ≤, allowed compartments ⊆ | ✓ |
| Environment / isolation | `child_env ≼ parent_env` | ✓ (see §8.1) |
| Authority / clearance | Unchanged r3 check-not-clip | ✓ |

A child profile alone cannot widen any listed dimension.

Two LOW gaps (HR6-08):

- **Comparands are not version-pinned.** `EnvironmentClass` has no version
  or digest, and the ESC records only the class id. A later
  SecurityPolicyVersion can redefine the same id, so "≼ parent" is
  evaluated against a definition the parent never ran under. The same
  applies to destination-authorization ids versus versions.
- **`approval_class` is not in the attenuation table.** A child profile
  with a weaker approval class than the parent's is not addressed.

**Verdict HR5-05: RESOLVED_IN_R4.**

### 8.1 Environment order (§17 of the brief)

`E1 ≼ E2` ("E1 at least as restrictive") holds iff all of:

- `E1.isolation_level ≥ E2.isolation_level`, with 1 < 2 < 2R < 3 < 4;
- `permitted_sinks ⊆`;
- `network_reach ≤`;
- `secret_capability ≤`;
- `local_model_ids ⊆`;
- `fs_capability ⊆`;
- `subprocess_allowed ⇒`.

Every conjunct points the same way: higher isolation or fewer
capabilities. The order is a product of partial orders, so it is a
partial order. Incomparable pairs are rejected. The direction is
**correct**: `child ≼ parent` means the child is no less isolated and no
more powerful.

| Case | Failing conjunct | Result |
|---|---|---|
| Parent 2R restricted worker → child Level 1 in-process | `1 ≥ 2R` false | DENY |
| Parent local-only → child cloud-capable | `network_reach AUTHORIZED_EXTERNAL ≤ LOCAL_ONLY` false; also destinations ⊆ | DENY |
| Parent no-secret → child `SECRET_CAPABLE` | `secret_capability` | DENY |
| Parent `network_reach = NONE` → child networked | `network_reach` | DENY |

### 8.2 Owner escalation rule (§18 of the brief)

Escalation is "a new owner act modeled as a new ROOT admission (T-8)".
No path upgrades a child in place:

- the ESC, the DelegatedExecutionBinding, the TCR and the pair are
  insert-once with no update path;
- T-8 creates a new task id, a new TCR and a new root pair under a unique
  `admission_owner_event_id` and a pair approval digest bound to that
  task;
- the ESC Issuer resolves a ROOT only through `tcr.root_lineage_pair_id`
  with `parent_pair_id = None`, so a child's pair cannot be reused as a
  root.

The new root gets a new, independently authorized security context.
**Sound.**

---

## 9. HR5-06 / HR5-07 verification

### 9.1 HR5-06 — T-7 idempotency and bounds

- **Idempotency.** T-7 step 0 returns an existing binding for
  `(parent_esc_id, proposal_ref)`. The key is a DB unique constraint inside
  the serializable T-7 transaction, so a replay after an uncertain commit
  either finds the committed binding or re-runs a transaction that commits
  at most once. Duplicate children or pairs are impossible.
- **Id reuse.** Parent ESC ids are never reused (§21.6), so recreating a
  "parent execution identity" produces a new ESC id and cannot collide.
- **Replay against a revoked parent.** Returning an existing binding is
  harmless: `issue_esc` re-checks that the parent is not REVOKED and that
  every ancestor pair is effective.
- **Gap.** T-7 does not require `proposal.proposer_esc_id == parent_esc_id`.
  A parent can name another ESC's proposal item (HR6-09, LOW).
- **Bounds.** Per ESC (`max_child_issuances`), per root lineage and per
  window. ✓
- **Bandwidth.** The accounting states only the profile-choice term. It
  claims selector content is "a narrowing choice from closed vocabularies",
  which is false. See §9.3 and HR6-03.

**Verdict HR5-06: PARTIALLY_RESOLVED** (not a freeze blocker; HR5 also did
not rate it one).

### 9.2 HR5-07 — containment gate

See §15. Ordering is correct and the graph is cycle-free. The
merged/activated boundary and the activation record are under-specified
(HR6-04).

**Verdict HR5-07: PARTIALLY_RESOLVED** (implementation and deployment
blocker, not a freeze blocker).

### 9.3 Child taint residual (§20 of the brief)

The two flows are separated correctly:

- **Explicit delivery.** The TaskProposal is labeled ⊒ the parent's
  H_exec, and child results and descriptions are flows checked against
  the child's clearance and ceiling (§14.5, §23.5, INV-CB-041). Sound.
- **Implicit in the decision.** The residual consists of:
  - whether T-7 is issued;
  - how often;
  - which allowed profile is chosen;
  - the **selector values**;
  - timing.

The selectors are not closed vocabularies:

- `AuthorityScope.expires_at` is a `datetime`
  (`app/authority_contracts/contracts.py`), and `ContextClearance.expires_at`
  is an aware UTC datetime.
- `action_types` is any non-empty subset of a 14-element vocabulary
  (≈14 bits).
- The clearance chooses subsets of compartments, sinks and purposes, plus
  level, persistence, export and redelegation depth.

The child can observe most of these through its own ALLOW/DENY outcomes:

- ALLOW vs DENY on context requests reveals clearance membership;
- action-gate outcomes reveal scope.

It can then emit what it learns at its own, lower taint to any destination
in `child_destinations ⊆ parent_destinations`. The parent's H_exec may
forbid that destination (for example an INTERNAL parent tainted
CONFIDENTIAL with a cloud destination).

A conservative estimate is tens of bits per issuance beyond the
`⌈log2(|allowed_child_profiles|+1)⌉` term. That is multiplied by
`max_child_issuances`, which has no design-level cap, and bounded only
further by the per-lineage and per-window policy values.

The channel is bounded, so it is not unbounded as in HR5. But it is **not
the "few bits" low-bandwidth residual the design says it accepts**, and the
stated bound omits its largest term. → **HR6-03 (MEDIUM, not a freeze
blocker).**

---

## 10. Read-set / isolation analysis

### 10.1 Level 2R as a security property (§5 of the brief)

§6.5 and CR-ISO-01 require all of the following, each OS-enforced:

- filesystem **read** limited to the ARS (pre-opened handles or a
  read-only view);
- **write** limited to registered outputs and the ephemeral workspace;
- **network** only through the Trusted Network Layer / egress proxy;
- an allow-listed **environment** (no secrets, no proxy variables);
- **no handle or path** to SQLite or any security store;
- **controlled IPC** only.

The design explicitly says a plain same-user process is not sufficient
(§6.5 Level 2 row; forbidden design 36). The property is stated as a
security property and is unambiguous.

Windows-oriented review:

- **AppContainer / restricted token.** Suitable for removing ambient file
  and network authority. The "job object" example does not restrict the
  filesystem. It is harmless only because the property, not the example,
  is normative.
- **Runtime image.** Any real worker must read its interpreter, system
  DLLs and tool binaries. An AppContainer can also read locations granted
  to `ALL APPLICATION PACKAGES`. "Its only filesystem access is the set of
  handles" is not literally implementable. The property needs an explicit
  runtime-image allowance proven to contain no protected content (HR6-12,
  LOW).
- **Handle inheritance.** The contract ("no handle or path to SQLite")
  requires an explicit inherited-handle list, for example
  `PROC_THREAD_ATTRIBUTE_HANDLE_LIST`. That is an implementation
  obligation and is implied by the stated property.
- **Junctions / reparse points.** Handled at every path component (§17.10).
  With pre-opened handles, relative opens are still access-checked against
  the restricted token.
- **Child processes.** Restricted-token and AppContainer restrictions are
  inherited. §18.4 says subprocess creation is restricted.
- **Git helpers.** See §10.2.

### 10.2 Git and external tool execution (§6 of the brief)

The responsible layer is identified: the Tool Launcher supplies a "fixed,
reviewed Jarvis-supplied configuration and an empty hooks path", and the
Level 2R boundary is the backstop (§17.9).

Named as disabled:

- repository-local configuration;
- `includeIf`;
- hooks;
- clean/smudge and diff filters;
- `core.fsmonitor`;
- submodules;
- alternates;
- LFS;
- credential helpers.

Not named:

- system and global configuration (`GIT_CONFIG_NOSYSTEM`,
  `GIT_CONFIG_GLOBAL`);
- `diff.external` / `GIT_EXTERNAL_DIFF`, `difftool`, `textconv`;
- `core.pager`, `core.editor`, `sequence.editor`, `GIT_ASKPASS`;
- `core.sshCommand` / `GIT_SSH*`;
- `gpg.program` (commit signing);
- `url.*.insteadOf`;
- aliases;
- `GIT_DIR` / `GIT_WORK_TREE` / `GIT_EXEC_PATH`.

Git also cannot be told to ignore `.git/config`. "Repository-local
configuration disabled" is realizable only because a managed repository's
`.git/config` is written solely by Jarvis (a managed store), and dangerous
keys are overridden by command-line configuration.

Because every helper runs inside the Level 2R worker, a missed helper
cannot exceed the worker's view, network or environment. So the security
property is complete **if** the view equals the ARS. It does not today
(HR6-02). The helper list should be stated as a property ("no
configuration-driven program execution; every program invoked is a fixed
launcher-chosen binary"). That is folded into the HR6-02 correction as a
non-blocking item.

Archivers and converters: subprocess → ISO-TOOL → 2R. Member enumeration is
done by the trusted extractor. ✓

---

## 11. Runtime registry analysis

See §6. The three layers are distinct. Only layer C authorizes. Unknown
means DENY. Self-certification is refused. A component with any
unregistered surface stays inactive. A process that is not fully admitted
is ineligible. The two Level 1 detection gaps (pre-content handles, and
standard streams / exception hooks) are HR6-05. The contract is
fail-closed.

---

## 12. Logging analysis (security telemetry schema, §8 of the brief)

Attempts to smuggle content through "safe" fields:

| Field | r4 constraint | Residual |
|---|---|---|
| Correlation id | `SecurityError(code, correlation_id)`; diagnostic correlation ids are store-generated, never reused (§21.6) | ✓ |
| Object id | "opaque object ids" | Not required to be TCB-issued and validated against their store. An id-shaped caller string (the v0.2.4 identifier set allows words) could carry content. → HR6-10 |
| Event code | Closed per registered event | ✓ |
| Numeric counter | "bounded counters and bucketed durations" | Bounded, but the rule does not say values must be computed by TCB code from non-content quantities. A bounded 32-bit counter is 32 bits. → HR6-10 |
| Keyed digest | HMAC with a TCB-held key "where correlation is justified" | Not enumerated per event; the membership-oracle risk for low-entropy values is not assessed per field. → HR6-10 |
| Policy version | Integer from the policy store | ✓ |

The shape is closed (schema per event code; fields outside it are
rejected), and free strings are rejected. The id/counter/digest hardening
is LOW, because security-sensitive emitters are reviewed TCB code and
class M does not choose those values directly.

---

## 13. Network analysis

See §7. First-hop and rebinding protection are sound. HR6-07 (LOW) covers:

- pool scoping;
- resolve-before-authorize ordering;
- resolver egress.

---

## 14. Delegation attenuation

See §8 and §9.3. Capability attenuation is sound: destinations,
environment, provider/model, persistence and ceiling. The implicit-flow
residual is mis-bounded (HR6-03). Version-pinning of comparands and
`approval_class` are HR6-08.

---

## 15. Containment-gate analysis

### 15.1 Activation graph reconstruction (§40.E, §40.F)

```text
containment-only (activate on merge): EGR-01a, LEG-01a, IFR-01, LOG-01, CB-03, CB-06, API-01 (route restrictions)
GATE-CONTAIN := active(EGR-01a) ∧ active(LEG-01a) ∧ active(IFR-01) ∧ active(LOG-01) ∧ ISO(level for path)
gated: ESC-01, TASK-01, TAINT-01, CB-02, CB-04, CB-05, ING-01, ART-01, EGR-01, LEG-01, v0.2.6.9
       each ⇐ GATE-CONTAIN ∧ CR-ACT-01 record ∧ act(own deps)
```

**Every gated CR that moves broker-labeled content into live code** is
behind the gate: CB-02, CB-04, CB-05, ING-01, ART-01, EGR-01, LEG-01,
ESC/TASK/TAINT wiring and v0.2.6.9. The HR5-07 window cannot open:

- under EGR-01a, a content-bearing execution has no external path;
- under LEG-01a, its outputs cannot reach class-Q columns, legacy audit
  writers or unauthenticated routes;
- under IFR-01 and LOG-01, unknown sinks and log paths are denied.

**CRs that are neither listed as gated nor as containment-only:**

- CR-PRN-01, CR-EPOCH-01, CR-POL-01, CR-OWN-01;
- CR-OBJ-01, CR-LIN-01, CR-NET-01, CR-ISO-01;
- CR-CB-07, CR-CB-08;
- v0.2.5 CR-01..05.

On inspection, none wires broker-labeled content into an uncontained live
path:

- OWN/OBJ create owner-typed content in mediated stores, reachable by
  agents only via gated ESC/CB-04;
- NET/ISO only restrict;
- CB-08 moves credentials, not content;
- CB-07 changes identity binding only.

So the ordering is **safe**. The classification is still implicit, and
INV-CB-105 makes it the implementer's judgement → HR6-04 (item 3).

### 15.2 Merged vs activated (§22 of the brief)

§40.F defines "merged" as "no live module imports or calls it", proved by
a structural import test. That does not cover live-behavior changes that
need no import from live code:

- **Alembic migrations.** They run on `alembic upgrade head` whatever
  imports exist. A merged CR-LEG-01 data migration would convert or move
  legacy content without an activation record.
- **Packaging entry points / plugin discovery** and FastAPI router
  auto-inclusion.
- **Startup hooks, background workers and scheduled tasks** registered by
  configuration.
- **Changes to shared configuration defaults or dependency manifests**
  (protected targets, §29.3). A new dependency is code that runs at
  import.
- **Provider patching** (monkey-patching at import of a merged module
  pulled in transitively by a test or a script).

→ **HR6-04**.

### 15.3 Activation record (CR-ACT-01, §23 of the brief)

`IntegrationActivation` is an owner act (T-5) in the policy store. The
audit event records the CR id, record id, policy version, prerequisite
status codes and `owner_event_id`.

Not bound:

- the component **version/digest** (an approval of CR-CB-04 version X
  keeps activating a later, differently reviewed CR-CB-04);
- the **environment / deployment** it applies to;
- the **epoch**.

Startup refuses if prerequisites are unmet. **Loss of a prerequisite
after startup** (for example the Runtime Registry Monitor fails, or
EGR-01a is disabled by a configuration change) is not specified. There is
no statement that gated paths are deactivated or the runtime stops.
→ HR6-04.

Also, §40.E says "**Every** activation also needs an owner-approved
`IntegrationActivation` record". §40.F says containment-only CRs "may
activate on merge". The §40.F wording is the safe one. If §40.E governed,
the gate would depend on `OWNER_CHANNEL_READY`. That is not circular, but
it would delay containment. → HR6-04 (editorial).

### 15.4 Circularity (§24 of the brief)

GATE-CONTAIN ← EGR-01a (no deps), LEG-01a ← IFR, IFR (no deps),
LOG-01 ← IFR, CB-06, and ISO (no deps).

- None of these is gated.
- CR-LOG-01 does not wait for `DIAGNOSTIC_STORE`, which comes from the
  gated CR-ART-01. It drops raw diagnostics until then (§40.B).
- CR-ACT-01 ← POL, IFR, and neither depends on the gate.
- `OWNER_CHANNEL_READY` ← PRN, ISO, POL, OWN, and none depends on the
  gate.

**No cycle.** The build graph was checked tier by tier: every edge points
to a strictly lower tier. **Acyclic.**

---

## 16. LineagePair regression

The r4 changes are additive:

- `root_task_id` on ROOT pairs;
- unique constraints on `TCR.root_lineage_pair_id` and
  `TCR.admission_owner_event_id`;
- the child pair digest also covers destinations, environment and
  proposal ref;
- `(parent_esc_id, proposal_ref)` unique on the binding.

No r3 check was removed from §9.3 step 6, §9.7 or §21.3.

| Attack | Blocking check(s) | Result |
|---|---|---|
| Child root-pair substitution | CHILD path reads only `deb.child_lineage_pair_id`; requires `pair.parent_pair_id == parent.lineage_pair_id`; ROOT requires `parent_pair_id None` ∧ `root_task_id == tcr.task_id` | DENY |
| Sibling pair substitution | `deb.task_id == tcr.task_id`; `pair.issuer_event == deb.issuance_event` (unique per T-7); leaf-uniqueness | DENY |
| Mixed authority/clearance halves | Leaves taken only from the pair; each leaf named by at most one pair ever; both leaves' parents = parent's leaves; same delegate/delegator/objective | DENY |
| Parent revocation before child issuance | T-7 step 1 (parent LIVE, every ancestor pair effective); `issue_esc` (parent not REVOKED; ancestors effective); every decision re-checks ancestors (§34 step 3) | DENY |
| Three-generation delegation | Each generation's `parent_pair_id` = immediate parent's pair; ancestors walked to the root; transitive attenuation | Only the exact chain binds |
| Pair replay | Ids never reused; revoked pairs never effective; epoch recorded at issue | DENY |

**LINEAGEPAIR R4 REGRESSION-FREE**

---

## 17. TaskControl regression

- §9.3 step 1: "The Task row is NOT read here."
- Step 3 compares ids only against "the recorded proposal".
- Step 5 reads `item_store.get(tcr.proposal_ref)`, the immutable proposal
  recorded at admission, and states "the live Task row is NOT read".
- §9.6 class A says the same. INV-CB-049 and INV-CB-078 were revised to
  match.
- TST-CB-078 requires that mutating the live row changes neither the
  fields nor the DENY outcome.
- A proposal requesting stronger approval is ignored; approval comes only
  from the profile.

No live mutable Task field is authoritative. **No regression.** The only
remaining effect: an untrusted proposal author can make its own ESC
creation DENY by recording a contradictory agent. That is self-denial of
service by the proposer (parent or planner under owner review), which is
acceptable.

---

## 18. Bootstrap review (HR5-15)

Checked:

- human presence (WebAuthn UV / keystore user presence);
- runtime, API and tool workers stopped, verified by the enrollment tool;
- anchor-last ordering.

In `ENROLLED_PENDING_ANCHOR` the store has committed but the channel is
not `OWNER_CHANNEL_READY` and admits no owner act. Recovery may finish
only the anchor step, only for the same `bootstrap_event_id`.

Half-commit states:

| State | Outcome |
|---|---|
| Store committed, anchor absent | No owner act; completion only for the same event, and it registers nothing new |
| Anchor `ENROLLED`, store `UNENROLLED` or different event | Epoch regression → DENY everything |
| Anchor written, final store transition not done | Still `ENROLLED_PENDING_ANCHOR` → no owner act; recovery completes step 3 |
| Reinstall | New installation identity; old stores never loaded as security state |

No half-committed state enables an owner act.

Two points, neither a flaw:

- "the same local-presence conditions" for recovery does not say whether
  user verification is repeated. Nothing new is registered in recovery,
  so this is non-material.
- Deleting the anchor and restoring an `UNENROLLED` store would permit
  re-enrollment. That needs anchor rollback (class R / C-os), which §31
  item 6 already states as out of claim.

**Not a freeze blocker. No material flaw.**

---

## 19. New invariant audit (097–106)

| ID | Class | Reason |
|---|---|---|
| 097 | **UNSOUND** | Final clause "or labeled at an explicit owner-approved conservative ceiling" is permitted without requiring the ceiling to dominate a boundary-proven reachable universe (HR6-01) |
| 098 | VALID | Complete alias/TOCTOU/archive list; enforceable at the Mediated Reader and 2R view |
| 099 | **INCOMPLETE** (LOW) | Correct classification; telemetry "opaque ids" and counters not required to be TCB-issued/computed (HR6-10) |
| 100 | VALID | Correct runtime property. The Level 1 mechanism gap is an implementation obligation (HR6-05), not an invariant defect |
| 101 | VALID | First hop included; mapped/embedded forms; scoped internal exception; metadata never |
| 102 | **INCOMPLETE** (LOW) | Covers new connections; pooled-connection reuse across requester scope and policy version not addressed (HR6-07) |
| 103 | VALID | ⊆ parent; meet for model authorization |
| 104 | VALID | Order direction correct. Version pinning of the class (HR6-08) is a LOW refinement |
| 105 | **INCOMPLETE** | Ordering correct; "merged" defined only by imports; activation record lacks component digest/environment/epoch and post-startup loss handling (HR6-04) |
| 106 | VALID | Unique key + serializable transaction; bounds. Proposer binding (HR6-09) is a LOW refinement |

No invariant is REDUNDANT. 097 overlaps 081 and 062 but adds the
enforced-set requirement, which is its purpose.

---

## 20. Revised r4 invariant audit

Counted from the final r4 §33 table itself, not from the correction
report. Rows whose status contains "rev r4":

`046, 048, 049, 050, 062, 073, 076, 078, 080, 081, 082, 084, 085, 087, 090, 091, 092` → **17**.

- **INV-CB-049 is revised** ("adopted (rev r4)"). Its text now says
  contradiction checks use the recorded proposal and that the live Task
  row is not read.
- §0.5 and the §33 totals paragraph both say 17 and list the same IDs.
  The design itself is internally consistent.
- The 16-versus-17 discrepancy is not present in the repository documents.

**Totals:** 106 IDs (106 table rows), **105 active** (INV-CB-030
withdrawn), 10 new (097–106).

Content notes on the revised set:

- 062 and 081 carry the HR6-01 ceiling clause;
- 050's "enforced AuthorizedReadSet" is affected by HR6-02 for Git.

The rest are coherent.

---

## 21. Future-test quality

| Area | Test(s) | Tests enforcement behavior? |
|---|---|---|
| Symlink/junction escape | TST-CB-098 (+081) | **Yes**: blocked before any byte enters the tool; 8.3/ADS/case/Unicode; TOCTOU; must run against the real boundary (§36 r4 note) |
| Undeclared reads | TST-CB-097 | **Yes** for declared ≠ enforced. **But** it codifies the unsound path ("with a registered ceiling → every output ⊒ that ceiling"), so it would pass an unsound implementation (HR6-01) |
| Archive traversal | TST-CB-098, 081 | **Yes** |
| Temp sink / SDK cache / subprocess pipe | TST-CB-100 | **Yes**; "against the real runtime guard, not a document check" |
| Logging leakage | TST-CB-099, 073 | Mostly. Covers the telemetry API and the dev-CLI stdout. Missing: uncaught-exception tracebacks, `warnings`, third-party `print`, and handles pre-opened before content (HR6-05) |
| First-hop SSRF | TST-CB-101 | **Yes**, asserted at the socket layer |
| DNS rebinding | TST-CB-102 | **Yes**, with a controllable resolver. Missing: cross-adapter pool reuse (HR6-07) |
| Child destination escalation | TST-CB-103 | **Yes**, including the HR5-05 replay |
| Child environment escape | TST-CB-104 | **Yes**, including incomparable classes. Missing: redefinition of a class id between policy versions (HR6-08) |
| Activation before containment | TST-CB-105 | Partly. Structural import test only; no migration / entry-point / startup-hook case; no post-startup prerequisite loss (HR6-04) |
| T-7 replay | TST-CB-106 (real-store) | **Yes**, including after an uncertain commit |
| Sibling substitution, three generations, parent revocation mid-issuance | TST-CB-076 (extended) | **Yes** |
| Git view over-read | none | **Missing** (HR6-02) |
| Selector-encoded T-7 channel | TST-CB-048 counts issuances only | **Missing** (HR6-03) |

**Structural defect (HR6-06, LOW).** TST-CB-097..106 are defined **only**
in §0.5. Their rows sit inside the HR5 correction table between HR5-15 and
HR5-16, and have 3 cells in an 8-column table. The §36 test table ends at
TST-CB-096, although §36 states that "every active invariant has at least
one negative test (TST-CB-NNN tests INV-CB-NNN)". The IDs map 1:1, so the
mapping is recoverable. The authoritative table is incomplete.

Also, `deliver()` appends `delivery_kind = ARTIFACT_READ`, which is not in
the closed §14.1 `delivery_kind` vocabulary.

**Overall:** the r4 tests meaningfully test enforcement behavior, not
configuration text. They do not yet cover the HR6-01..05 gaps, and
TST-CB-097 currently accepts the unsound ceiling path.

---

## 22. New HR6 findings

### HR6-01: The INCOMPLETE-read-set "conservative ceiling" path is unsound and contradicts §6.5 and §17.9

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR5 (HR5-01)
- **Affected sections:** §17.6 rule 2a; §17.9 (`completeness` field, "a
  tool that fits neither is not enabled"); §6.5 (ISO-TOOL rule); §16.2
  formula; §34 `deliver()` and `ingest_tool_result()`; §35.2
  `CB_READ_SET_INCOMPLETE`; TST-CB-097, TST-CB-081
- **Affected invariants:** INV-CB-097, INV-CB-081, INV-CB-062
- **Attack / contradiction:**
  1. Rule 2a lets an adapter whose reads the boundary cannot confine run
     with outputs labeled at an owner-chosen ceiling. Its own example is a
     Level 1 adapter using a library with ambient file access, or an
     unconfined subprocess.
  2. That adapter's reachable universe is the whole OS account:
     RESTRICTED/FINANCIAL/USER_PRIVATE stores, `jarvis.db`, and `.env`
     secrets, which no label can bound.
  3. Class M steers it to read such a resource. For example, a converter
     or template library follows an include or external reference.
  4. The output is bound at the (lower) ceiling. For tool **results**,
     `ingest_tool_result()` never checks `completeness`, so the result is
     labeled from the entries alone.
- **Impact:** a persistent label downgrade and possible secret exposure
  through an honest adapter driven by class M. This is the HR5-01 defect
  class, reopened by the fallback. It also contradicts §6.5 and §17.9,
  which forbid such an adapter from running at all.
- **Correction required (either):**
  - **(a)** delete the ceiling alternative: INCOMPLETE ⇒ DENY for both
    artifacts and results; a Level 1 adapter can never be INCOMPLETE (it
    is ISO-TOOL); or
  - **(b)** allow it only when the enforcement boundary (Level 2R/3)
    proves a bounded resource universe U (every readable handle/view
    element and every reachable network destination), U contains no
    secret-bearing, broker-owned or legacy store, and the ceiling is
    ⊒ ⊔ label(r) for r ∈ U — computed, not owner-asserted.

  In both cases:
  - make `ingest_tool_result()` apply the same rule;
  - state the implication
    `unknown actual reads → proven maximum label of the enforced universe ∨ DENY`
    in INV-CB-097;
  - change TST-CB-097 to reject an owner ceiling that does not dominate
    U.
- **Freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO (only `file.create_sandboxed` exists; blocks
  enabling any other adapter)

### HR6-02: The Git ISO-TOOL view ("the managed repository and the entries") exceeds the AuthorizedReadSet used for labeling

- **Severity:** MEDIUM
- **Category:** NEW (within the HR5-01 correction)
- **Affected sections:** §17.9 "Git and repository tools"; §17.6 rule 2
  (`git_commit()` reads the staged tree and parent commit); §17.7 Git rows;
  §6.5 ISO-TOOL claim
- **Affected invariants:** INV-CB-097, INV-CB-081, INV-CB-050
- **Attack / contradiction:** a managed repository holds a RESTRICTED
  FINANCIAL blob on another branch (or in stash, reflog or unreachable
  pack objects). An INTERNAL ESC runs a Git operation whose ARS entries
  are the `main` tree and parent. The 2R worker's view is the whole
  repository, so the Git process (or anything it spawns) can read the
  FINANCIAL objects. Output and result labels join only the entries. The
  readable view is larger than the label basis, which contradicts §17.9
  step 3 ("cannot open any other file") and the ISO-TOOL guarantee against
  the tool code's own over-reads.
- **Impact:** within ISO-TOOL's stated threat model (hostile or defective
  tool code in the worker), labels can be lower than what the worker could
  read. This breaks the "readable set ⊇ actual reads" argument that §17.6
  relies on.
- **Correction required:**
  1. The view must equal the ARS entries. For Git, either:
     - make the entries the entire repository object store and metadata
       (refs, packs, reflog, stash, config), with the label joining every
       binding in it (or the repository's `max_label`); or
     - export only the needed objects into a fresh per-invocation
       repository.
  2. Non-blocking, same pass: restate Git helper suppression as a
     property. No configuration-driven program execution (system/global
     config, external diff, textconv, pager, editor, askpass, ssh command,
     gpg program, `insteadOf`, aliases, `GIT_*` variables). Every executed
     binary is fixed by the Tool Launcher. Add a Git over-read test.
- **Freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO (no Git adapter exists)

### HR6-03: The T-7 implicit-flow bandwidth bound omits selector entropy; "closed vocabularies" is factually wrong

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR5 (HR5-06)
- **Affected sections:** §14.8 (T-7 paragraph), §32 T-7 row, §38.2 T-7
  residual, §9.7 steps 2/4
- **Affected invariant:** INV-CB-048
- **Attack:**
  1. A parent whose H_exec forbids destination D (e.g. CONFIDENTIAL,
     `MODEL_CLOUD` not in its sinks) still has D in its destination set.
     It encodes data in T-7 selectors: `AuthorityScope.expires_at` (a
     datetime), the `action_types` subset (~14 bits), `permission_ceiling`,
     and the clearance's compartment/sink/purpose subsets, level,
     persistence, export and expiry.
  2. The child starts at its own low genesis. It learns the selector
     values from its ALLOW/DENY outcomes and sends them to D.
  3. Per issuance this is tens of bits, times `max_child_issuances`,
     which has no design-level cap.
- **Impact:** a covert channel larger than the "few bits per execution"
  residual the design accepts. It is still bounded (per ESC, lineage and
  window), so it is not HR5's unbounded case. The owner would accept a
  residual whose bound is mis-stated.
- **Correction required:** do one of the following:
  - quantify the selector entropy observable by a child and state the
    total bound;
  - restrict T-7 selectors to profile-enumerated scope/clearance
    templates, with expiry from a bucketed set, so the "closed
    vocabularies" claim becomes true;
  - adopt HR5-06 item 3 (child genesis ⊒ the confidentiality projection
    of the parent's H at T-7) for profiles whose destinations the
    parent's taint forbids.

  Extend TST-CB-048 accordingly.
- **Freeze blocker:** NO (residual accounting; correct in the same pass)
- **Implementation blocker:** YES (CR-ESC-01)
- **Deployment blocker:** NO

### HR6-04: Merged-vs-activated and the activation record are under-specified

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR5 (HR5-07)
- **Affected sections:** §40.E activation graph and "Every activation"
  sentence; §40.F definitions, CR lists and mechanism; CR-ACT-01
- **Affected invariant:** INV-CB-105
- **Contradictions / gaps:**
  1. "Merged" is proved only by a structural import test. Alembic
     migrations run regardless of imports; so do packaging entry points,
     router auto-inclusion, startup hooks, background workers, and
     configuration or dependency-default changes. A merged-but-inactive
     CR-LEG-01 data migration would change live content without an
     activation record.
  2. `IntegrationActivation` does not bind the component version/digest,
     the environment or the epoch. Loss of a GATE-CONTAIN prerequisite
     after startup has no specified behavior.
  3. Eleven CR families are neither "gated" nor "containment-only" (§15.1).
  4. §40.E says every activation needs a record; §40.F says
     containment-only CRs activate on merge.
- **Impact:** the gate ordering itself is sound. An implementation can
  still activate live behavior outside the gate through a non-import
  channel, or reuse an activation approval for different code.
- **Correction required:**
  - define "activation" as any change to live behavior, and list at least
    imports, calls, route registration, startup hooks, migrations,
    workers, background tasks, entry points, provider patching and
    configuration/dependency defaults;
  - migrations of gated CRs apply only under an activation record;
  - bind activation records to `(CR id, component digest, policy version,
    prerequisites, environment, epoch, owner_event_id)`;
  - on runtime loss of a prerequisite, deactivate gated paths or stop
    (fail closed);
  - classify every CR;
  - fix the §40.E sentence;
  - extend TST-CB-105 with migration, entry-point and prerequisite-loss
    cases.
- **Freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR6-05: The Level 1 runtime sink guard misses pre-content handles and standard streams

- **Severity:** MEDIUM
- **Category:** NEW (HR5-02/HR5-03 mechanism)
- **Affected sections:** §18.4 Level 1 guard ("while protected content is
  present"), §18.3 terminal table, §18.4 item 5, CR-IFR-01, CR-LOG-01
- **Affected invariants:** INV-CB-100, INV-CB-099 (contract correct;
  mechanism incomplete)
- **Attack:**
  1. A library opens a cache, log or temp file at import, before any
     protected content exists. The guard permits it.
  2. After admission, content written through that open handle bypasses
     open-time audit hooks.
  3. Separately, an uncaught exception (for example a pydantic validation
     error echoing model output) is printed by `sys.excepthook` or
     `threading.excepthook` to stderr. So are `warnings` and third-party
     `print` output. None of these is a `logging` handler or a file open.
- **Impact:** protected content reaches unregistered sinks in Level 1
  processes that were attested as fully admitted. This is exactly the
  honest-library-mistake class the guard is meant to cover.
- **Correction required:**
  - the guard is active from process start;
  - any unregistered write-capable handle or stream existing at
    admission makes the process ineligible;
  - `sys.stdout`/`sys.stderr` are replaced by Monitor-issued guarded
    handles in content-holding processes;
  - `sys.excepthook`, `threading.excepthook`, the asyncio exception
    handler, `warnings.showwarning` and `faulthandler` route to
    `SecurityError` / telemetry or to `DIAGNOSTIC_STORE`;
  - extend TST-CB-099 and TST-CB-100.
- **Freeze blocker:** NO (the invariants state the property)
- **Implementation blocker:** YES (CR-IFR-01, CR-LOG-01)
- **Deployment blocker:** NO (covered before integration by CR-SINK-01)

### HR6-06: Test-table and vocabulary bookkeeping

- **Severity:** LOW
- **Category:** CONSISTENCY
- **Affected sections:** §0.5 table (TST-CB-097..106 rows embedded, wrong
  column count); §36 (table ends at 096); §14.1 `delivery_kind` vs §34
  `ARTIFACT_READ`
- **Correction:**
  - move TST-CB-097..106 into §36;
  - add `ARTIFACT_READ` to §14.1, or reuse `TOOL_RESULT`.
- **Freeze blocker:** NO (fix before the freeze record)
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR6-07: Trusted Network Layer — pool scoping, resolve-before-authorize, resolver egress

- **Severity:** LOW
- **Affected sections:** §16.7 steps 2–4 and 7; §24.2
- **Affected invariants:** INV-CB-102, INV-CB-101
- **Issue:**
  - pooled connections are keyed without requester scope (adapter /
    `InternalEndpointPolicy`) or policy version and epoch, so adapter B
    can reuse A's internally-scoped connection without step 4 being
    re-run for B;
  - resolution precedes the authorization check, so unauthorized
    hostnames generate DNS queries;
  - upstream resolver traffic is not modeled.
- **Correction:**
  - key pools by the requester's authorization scope, policy version and
    epoch, or re-run step 4 on reuse;
  - check `(scheme, host, port)` authorization before resolution;
  - state the resolver's egress.
- **Freeze / implementation / deployment blocker:** NO / YES (CR-NET-01) / NO

### HR6-08: Attenuation comparands not version-pinned; approval class not attenuated

- **Severity:** LOW
- **Affected sections:** §9.2 `environment_class`, §9.10 `EnvironmentClass`,
  §9.7 step 4, §9.3 steps 10–11
- **Affected invariants:** INV-CB-104, INV-CB-103, INV-CB-076
- **Issue:**
  - the ESC and binding record the environment class id only, with no
    version or digest, so a new policy version can redefine the id and
    the "≼ parent" check compares against a definition the parent never
    ran under (the same applies to destination-authorization id versus
    version);
  - `approval_class` is not in the attenuation table.
- **Correction:**
  - record `(id, policy_version, digest)` for the environment class and
    the destination versions, and compare against the parent's recorded
    versions;
  - require `child.approval_class` to be at least as strict as the
    parent's, or state that it can only add to the v0.2.5 approval
    requirement.
- **Freeze / implementation / deployment blocker:** NO / YES / NO

### HR6-09: T-7 proposal not bound to its proposer

- **Severity:** LOW
- **Affected section:** §9.7 steps 0–2
- **Affected invariant:** INV-CB-106
- **Issue:** T-7 does not require `proposal.proposer_esc_id == parent_esc_id`.
  A parent may cite another ESC's proposal item. That creates an outcome
  oracle on foreign item content and a confused-deputy use of another
  execution's selectors.
- **Correction:**
  - require the proposer to equal the parent;
  - make a proposal consumable by T-7 at most once.
- **Freeze / implementation / deployment blocker:** NO / YES / NO

### HR6-10: Security Telemetry field constraints

- **Severity:** LOW
- **Affected section:** §18.3 security telemetry row
- **Affected invariant:** INV-CB-099
- **Issue:**
  - id fields are not required to be TCB-issued and validated;
  - counters are not required to be TCB-computed from non-content
    quantities;
  - keyed-digest fields are not enumerated per event with an oracle
    justification.
- **Correction:** state all three constraints in the telemetry schema
  contract.
- **Freeze / implementation / deployment blocker:** NO / YES (CR-LOG-01) / NO

### HR6-11: Finding-ID namespace collision

- **Severity:** INFO
- **Issue:** §44.4 uses "HR6-01..22" for the withdrawn r1 self-review.
- **Recommendation:** in r5 traceability, refer to this review's findings
  as "HR6 (final verification) HR6-NN", or rename the r1 IDs "SR1-NN".
- **Blockers:** none

### HR6-12: The Level 2R filesystem property needs an explicit runtime-image allowance

- **Severity:** LOW
- **Affected sections:** §6.5 Level 2R row, CR-ISO-01
- **Issue:** "its only filesystem access is the set of handles or the
  read-only view" is not implementable literally. Every worker must read
  its interpreter, libraries and tool binaries. AppContainers can read
  `ALL APPLICATION PACKAGES` locations. The "job object" example does not
  restrict the filesystem.
- **Correction:**
  - define a read-only runtime image, proven free of protected content
    and outside every managed store, `jarvis.db`, `.env` and the
    repository root;
  - require an explicit inherited-handle list;
  - drop or qualify the job-object example.
- **Freeze / implementation / deployment blocker:** NO / YES (CR-ISO-01) / NO

**Severity counts:** CRITICAL 0 · HIGH 0 · MEDIUM 5 (HR6-01..05) · LOW 6
(HR6-06..10, HR6-12) · INFO 1 (HR6-11).

---

## 23. Design freeze blockers

| ID | Why it blocks freeze |
|---|---|
| **HR6-01** | Freeze criterion "read-set enforcement is sound" and "HR5-01 RESOLVED_IN_R4" fail. INV-CB-097 permits an unsound label path, and the normative procedure omits the rule for tool results |
| **HR6-02** | The same criterion. The only concretely specified ISO-TOOL view contradicts the enforced-set rule |

HR6-03..05 are MEDIUM but do not block freeze. The relevant invariants
state the correct property, or the item is residual accounting. They
should be corrected in the same pass.

**Freeze-criteria scorecard**

| Criterion | Status |
|---|---|
| No CRITICAL / HIGH design blocker | ✓ |
| No unresolved freeze-blocking MEDIUM | ✗ (HR6-01, HR6-02) |
| HR5-01..05 RESOLVED_IN_R4 | ✗ (HR5-01 PARTIALLY_RESOLVED); 02–05 ✓ |
| Runtime registry fail-closed | ✓ (contract); HR6-05 is implementation |
| Read-set enforcement sound | ✗ |
| First-hop networking sound | ✓ |
| Child attenuation sound | ✓ (capabilities); residual mis-bounded (HR6-03) |
| Containment gate correctly ordered | ✓ (acyclic); HR6-04 is implementation/deployment |
| LineagePair no regression | ✓ |
| Invariant/test mappings coherent | ✓ by ID; misplaced table (HR6-06, LOW) |
| Frozen-contract compatibility intact | ✓ |

---

## 24. Implementation blockers (separate from freeze)

These are in addition to every §43.1 row, all of which remain:

- HR6-01, HR6-02, HR6-03, HR6-04, HR6-05, HR6-07, HR6-08, HR6-09, HR6-10,
  HR6-12;
- the design's own §43.1 list (no ESC, taint, policy, lineage,
  task-control, registry, launcher, Mediated Reader, Level 2R, telemetry,
  network layer or activation machinery exists).

## 25. Deployment blockers (separate)

- Every §43.2 row, unchanged. All "live" rows (R-01..R-09, R-11, R-13,
  R-22..R-26, R-29, R-30) are pre-existing runtime defects. No design
  revision fixes them.
- **HR6-04:** no live-touching CR may be deployed until "activation"
  covers migrations and other non-import channels, and activation records
  are digest-bound.

---

## 26. Frozen-contract compatibility

- **v0.2 §8/§10:** r4 strengthens them. T-7 attenuates every execution
  dimension, and pairs are never searched, matching v0.2.5 HR-22.
- **v0.2.5 rules r4 relies on:**
  - the principal-cycle rule (T-06 / `PRINCIPAL_CYCLE`), used by §9.7
    step 3;
  - check-not-clip issuance.
- **v0.2.5.1 contracts are unchanged.** The only interaction found:
  `AuthorityScope.expires_at` is a free datetime. That makes HR6-03 a
  design-accounting issue, not a contract change.
- **v0.2.3 router:** the `CLOUD_ALLOWED` default is still never relied
  on.
- **v0.2.4:** identifiers are unchanged.
- **T-9 ESC-scoping** is a usage restriction, not an amendment.

**No amendment to any frozen v0.2.x contract is required.** AMD-025-01
remains uncreated and unnecessary.

---

## 27. Final status

HR5-01 is only partially resolved (HR6-01, HR6-02). Read-set
enforcement, a mandatory freeze criterion, is not yet sound in the text.
The other HR5 freeze blockers (02–05) are resolved in r4. LineagePair and
TaskControl show no regression. The containment-gate ordering is safe and
acyclic.

```text
R4 DESIGN NOT READY — FURTHER CORRECTION REQUIRED
```

The two blocking corrections are narrow text changes: delete or properly
constrain rule 2a and apply it to results; make the Git view equal the
ARS. They should be made together with HR6-03..06 and verified in a
focused follow-up.

> No v0.2.6 production implementation has been authorized or created.

---

## Appendix A — Read-only validation (§37 of the brief)

Commands were run from `C:\Users\Gyuro\jarvis-os` with `.venv/Scripts/python.exe`.

| Command | Result |
|---|---|
| `python scripts/check_v013_freeze_baseline.py` | exit 0 — `v0.1.3 FREEZE BASELINE CHECK: OK` (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `python scripts/check_v020_contract.py` | exit 0 |
| `python scripts/check_v023_router_contract.py` | exit 0 |
| `python scripts/check_v024_agent_contract.py` | exit 0 |
| `python scripts/check_v025_design_contract.py` | exit 1 — `DISCREPANCY FOUND`, solely "file outside the v0.2.5.1 allowlist is new/modified" for the five untracked v0.2.6 documents (this is the expected discrepancy and it occurred; this HR6 file was not yet written at that time and would be listed too) |
| `python -m pytest -q -p no:cacheprovider` | **2 failed, 2233 passed, 1 warning** (384 s). (1) `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository` — the same expected v0.2.5 checker discrepancy caused by the untracked v0.2.6 documents. (2) `tests/test_action_plan_orchestrator.py::test_two_concurrent_orchestrators_exactly_one_claims` — **passed on isolated re-run**; a timing-dependent concurrency test, flaky under full-suite load, unrelated to v0.2.6 (no code changed) |
| Re-run of the two failures in isolation | `1 failed, 1 passed` — only the expected v0.2.5 checker test fails |

No validator, test or configuration was modified.

## Appendix B — Integrity (§38 of the brief)

Re-verified at the end of the review:

| File | SHA-256 at end | Unchanged since start? |
|---|---|---|
| r4 design | `05672f95ab6fc82390eccfdb980ad961677568ccb56b39994761f31f27d636a9` | yes |
| HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` | yes |
| HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` | yes |
| HR4 | `d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c` | yes |
| HR5 | `921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd` | yes |

- HEAD is still `13796dcd61015098429f343e2fb982a9c75698bb`; no tracked changes.
- The only new file is this HR6 document.
- OpenDex `git status` is clean; HEAD is unchanged.
- No commit, push or merge was made.
