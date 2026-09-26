# Jarvis OS v0.2.6 — Post-Correction Security Verification (HR4)

```text
subject                     = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md (revision r2)
prior reviews verified      = HR2 (docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md)
                              HR3 (docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md)
review type                 = security verification only
design_modified             = false
hr2_modified                = false
hr3_modified                = false
code_modified               = false
tests_or_validators_modified= false
opendex_opened_or_modified  = false
final_status                = POST-CORRECTION DESIGN NOT READY — FURTHER CORRECTIONS REQUIRED
```

---

## 1. Independence statement

- This verification was performed in a **fresh session**. That session did
  **not** author the original v0.2.6 design (r1), HR2, HR3, or the corrected
  design (r2). It had no access to any of those conversations. It saw only
  the repository.
- The correction record (design §0, §44) was treated as a **claim to test**,
  not as evidence. Every "resolved" status was re-derived from the r2 text,
  the frozen contracts and the code.
- **Remaining limitation (HR4-12).** This reviewer is an AI model, very
  likely from the same model family as the authors of r1, HR2, HR3 and r2.
  Session independence holds. Organizational and model-diversity
  independence do not. HR3-16's recommendation stands: a human security
  review of §6 (TCB and isolation), §8 (owner channel), §9 (ESC) and §21.3
  (LineagePair) is recommended before any freeze.

## 2. Repository state

Verified read-only at the start of the review:

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `13796dcd61015098429f343e2fb982a9c75698bb` |
| `origin/master` | `13796dcd61015098429f343e2fb982a9c75698bb` (equal to HEAD) |
| Tags at HEAD | `v0.2.5.1` |
| Tracked changes | none |
| `git status --short -uall` | `?? docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md`<br>`?? docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md`<br>`?? docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` |
| Unexpected changes | none |

The three expected v0.2.6 artifacts exist. None is tracked. No production
code is modified.

**SHA-256 before review:**

| File | SHA-256 | Lines |
|---|---|---|
| Corrected design (r2) | `23a798d1d11b469d4cca7bea58966096015fb92923f911ff525cdecc99beb7f1` | 3,158 |
| HR2 | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` | 1,357 |
| HR3 | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` | 1,352 |

The after-review hashes are in §39.

## 3. Documents and code inspected

**Read in full:** the r2 design (3,158 lines), HR2 (1,357 lines), HR3
(1,352 lines).

**Frozen contracts:**

- `V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md`: §7–§12, §26–§37 in full;
  the rest by outline.
- `V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md`: §3.1–§3.5, §4–§17,
  §20 (DI-17), §22 (R-10), §24, Parts II P–S, Part III in full.
- `V0_2_5_1_AUTHORITY_CONTRACTS_AND_ALGEBRA.md` and
  `V0_2_3_PROVIDER_ROUTER_SECURITY_CONTRACT.md`, for the points in §31.
- `V0_2_4_AGENT_IDENTITY_AND_REGISTRY_SECURITY_CONTRACT.md`, for the
  deferred scopes.

**Code, checked only to test integration assumptions:**

| Area | Files | What was checked |
|---|---|---|
| API | `app/api/routes.py`, `app/schemas/projects.py` | `/chat` flow (R-03); `ProjectOut` returns `objective` and `description` |
| Planner persistence | `app/orchestration/dispatcher.py`, `app/schemas/tasks.py` | Task rows are written from model `TaskPlan` (R-05) |
| Providers | `app/agents/providers.py::get_default_provider` | Live cloud path, no router (R-08, R-09) |
| Router | `app/providers/routing_contracts.py` | `privacy_requirement` default; `allowed_provider_ids` is **provider**-granular |
| Data model | `app/database/models.py` | Every `Text` content column and every table (§16) |
| Decision intelligence | `app/decision_intelligence/*` (by grep) | Which modules write action-pipeline tables |

OpenDex was **not** opened, read or modified.

## 4. Correction-pass integrity verification

| Claim in r2 | Verified? | Notes |
|---|---|---|
| Header: not frozen, nothing authorized | Yes | Header and trailer agree |
| HR2/HR3 preserved unchanged | Yes | Hashes stable across the review (§39) |
| 75 invariant IDs, 74 active, INV-CB-030 withdrawn | **Yes, independently enumerated** | 75 rows; statuses: kept 18, rev 26, withdrawn 1, adopted 19, adopted (rev) 5, new 6 |
| Every active invariant has a TST-CB row | **Yes** | 74 active invariants ↔ 74 TST rows, one-to-one. TST-CB-030 is withdrawn into TST-CB-023. |
| No reference treats INV-CB-030 as active | Yes | The only references are withdrawal notes and "absorbs 030" |
| No undefined invariant IDs referenced | Yes | Every `INV-CB-NNN` referenced is in 001–075 |
| "No v0.2.6 rule conflicts with a frozen v0.2.x contract" (§39) | **Partly** | See HR4-01 (v0.2 §10 laundering and the v0.2.5 CR-01 requester semantic) and §31 |
| "No unresolved HIGH known to the author" (§44.5) | **Not confirmed** | Three HIGH design findings (§32) |
| The phrase "trusted orchestration" replaced by a named creator | **Mostly** | The ESC Issuer is named (§9.3). The phrase survives in §26.2 as the persistence trigger, with no named component (HR4-09). |

## 5. HR3 HIGH findings: verification

| Finding | Status | Corrected sections | Corrected invariants | Future tests | Remaining implementation prerequisite | Remaining deployment prerequisite | Still blocks freeze? |
|---|---|---|---|---|---|---|---|
| HR3-01 no immutable ESC / no creator | **PARTIALLY_RESOLVED** | §9, §19, §21.3 | 005, 046, 061 | 005, 046, 061 | CR-ESC-01 | Broker integrated only after CR-ESC-01 | **YES**, through HR4-01 and HR4-02 |
| HR3-02 non-durable taint | **RESOLVED_IN_DESIGN** | §14 | 008, 047, 069, 075 | 008, 047, 069, 075 | CR-TAINT-01 | — | No. Residuals HR4-02 (predecessor list) and HR4-05 (ceiling definition) are tracked separately. |
| HR3-03 labels lost outside the broker | **PARTIALLY_RESOLVED** | §17, §18 | 050, 073, 074 | 050, 073, 074 | CR-ART-01, CR-LEG-01, CR-SINK-01 | Live unlabeled stores (R-04, R-06) | **YES**, through HR4-03 and HR4-04 |
| HR3-04 tool reads labeled from H_exec | **RESOLVED_IN_DESIGN** for reviewed adapters | §16 | 062 | 062 | CR-ING-01 | — | No for the HIGH. The connector resource-identity residual is HR4-07 (MEDIUM, freeze-blocking text). |
| HR3-05 model output selects control values | **PARTIALLY_RESOLVED** | §7, §9.3–§9.4, §20 | 049, 061, 071 | 049, 071 | CR-ESC-01 | R-05 live | **YES**. Agent, purpose and approval class are fixed. The objective binding, root-versus-child classification and predecessor list still come from a Task row the planner writes (HR4-02). |
| HR3-06 TASK_INSTRUCTION upgrade | **RESOLVED_IN_DESIGN** | §23.2, §9.3 step 13 | 011, 025, 072 | 011, 072 | v0.2.6.6 assembler; CR-CB-04 | — | No |
| HR3-07 isolation over-promise | **RESOLVED_IN_DESIGN** | §6, §25 item 3, §29.1 | 002, 023, 024, 033, 052, 068 | 002, 024, 052, 068 | CR-ISO-01, CR-CB-08 | Live (R-11) | No. The OwnerChannel isolation-dependency gap is HR4-08 (not freeze-blocking). |
| HR3-08 owner channel absent | **RESOLVED_IN_DESIGN** | §8 | 004, 057, 067 | 057, 067 | CR-PRN-01, CR-OWN-01, CR-API-01, v0.2.5 CR-03 | Live (R-01, R-02) | No |
| HR3-09 default-allow egress | **RESOLVED_IN_DESIGN** | §24, §15.4–§15.5 | 027, 028, 058, 063, 065 | 027, 028, 058, 063, 065 | CR-EGR-01 (01a first) | Live (R-08, R-09) | No |

## 6. HR3 remaining findings: verification

| Finding | Status | Evidence | Still blocks freeze? |
|---|---|---|---|
| HR3-10 existential authority check | **RESOLVED_IN_DESIGN** | `has_any_effective_lineage` is gone. §34 step 3 and the delivery commit check the ESC's named authority leaf, clearance leaf and pair. | No. How the pair is **selected** is the new defect HR4-01. |
| HR3-11 grant ↔ router binding | **RESOLVED_IN_DESIGN** | `ProviderTarget(provider_id, model_id, …)` in the grant; router selection before grant; dispatch = bound; new grant on re-selection | No |
| HR3-12 caller-controlled scope | **RESOLVED_IN_DESIGN** (derivation rule) | §9.3 step 3; §15.2; INV-CB-064 | No. The live defect remains a deployment blocker. |
| HR3-13 no canonical owner | **RESOLVED_IN_DESIGN** | §8.1; INV-CB-067; multi-user explicitly deferred | No |
| HR3-14 legacy stores missing from CRs | **PARTIALLY_RESOLVED** | §17.5 and §18 cover tasks, agent_runs, memory, evidence and audit. They omit the action-pipeline tables and other content columns (HR4-04). | **YES**, through HR4-04 |
| HR3-15 schema inconsistencies | **RESOLVED_IN_DESIGN** | Grant has `environment_class` and typed `sink_target`; request has `uses`; `DERIVE` removed | No |
| HR3-16 review independence | **UNRESOLVED (process item)** | This review has the same limitation (HR4-12) | Not a design defect. A human review is recommended. |

## 7. HR2 residual verification

| HR2 | r2 treatment | Status | Remaining design issue |
|---|---|---|---|
| HR2-08 floor abuse / taint DoS | §13.6 closed narrowing table; §14.7 ceiling | RESOLVED_IN_DESIGN | The ceiling's own definition is ambiguous (HR4-05). Oversight-agent exclusion is a LOW residual (HR4-10). |
| HR2-09 control-plane implicit flows | §14.8, S-28, INV-CB-048 | RESOLVED_IN_DESIGN | `usage_records` token counts are an unlisted size observable (HR4-04, minor) |
| HR2-10 rollback | §31 | RESOLVED_IN_DESIGN | Limits are honestly stated |
| HR2-11 TOCTOU boundary | §14.3 delivery commit; point of no return at step 6 | RESOLVED_IN_DESIGN | — |
| HR2-12 audit semantics / leakage | §30.2–§30.4 | RESOLVED_IN_DESIGN | INV-CB-035 wording versus best-effort denials (HR4-09, LOW) |
| HR2-13 resource bounds | §32, taint-snapshot references | RESOLVED_IN_DESIGN | Numbers deferred (acceptable) |
| HR2-14 declassification canonicalization | §13.7 items 2–5 | RESOLVED_IN_DESIGN | Whitespace-pattern and linguistic-steganography residual not stated (HR4-11, LOW) |
| HR2-16 node identity / offline | §28 | RESOLVED_IN_DESIGN | — |
| HR2-17 deletion overstated | §27 | RESOLVED_IN_DESIGN | — |
| HR2-18 persistence order / rule scope | §26.1–§26.2 | RESOLVED_IN_DESIGN | The persistence trigger component is unnamed (HR4-09, LOW) |
| HR2-19 CD-01 vs v0.2 §8; `memory_scope` | §21.2–§21.3, §39 | **PARTIALLY_RESOLVED** | `memory_scope` is mapped and v0.2 §8 is classified. The coupling record's selection and issuance rules are incomplete (HR4-01, HR4-06). |
| HR2-23 inaccurate observations | §4.3 R-01..R-21 | **PARTIALLY_RESOLVED** | The facts omit the decision-intelligence content stores (HR4-04) |
| HR2-26 instruction memory / quoted owner text | §26.4 | RESOLVED_IN_DESIGN | — |

HR2-20, 21, 22 and 24 are correctly carried as stated residuals. HR2-25 is a
process item, as HR3-16 is. **HR2 design-freeze blockers still open:** HR2-19
and HR2-23, both through HR4 findings.

## 8. ExecutionSecurityContext analysis

**Properties verified:**

| Property | Verdict | Where |
|---|---|---|
| Created before protected execution | Yes | §9.3 step 14 precedes any grant; `request_context` requires a LIVE ESC |
| Created only by a trusted deterministic component | Yes, **as a component** (the ESC Issuer). **Not as to its inputs**: see HR4-02. | §9.3 |
| Insert-once, immutable | Yes. State is computed, never stored. | §9.5 rule 1; INV-CB-061 |
| Durable | Yes (CR-ESC-01) | §9.2 |
| Bound to one execution | Yes. Retries are new ESCs. | §9.5 rules 3–4 |
| Not built from model-controlled security values | **No, for three inputs.** Step 2 takes `task.objective_ref`, step 6 takes the root-versus-child classification, and step 12 takes `task.prior_attempt_escs`, all from a Task record whose writer is unspecified and is today model-driven (R-05). | HR4-02 |

**Field-by-field manipulation attempts:**

| Field | Attack | Result |
|---|---|---|
| `principal` | Planner marks a task "root" or names a creating action | **Succeeds in text.** Classification comes from the Task record (HR4-02). The principal is also not required to match the pair's lineage (HR4-01). |
| `agent` | Planner sets `agent_type` | Blocked. The TaskProfile decides; a contradiction is DENY (step 5). |
| `authority_leaf_id`, `clearance_leaf_id` | Request carries them | Blocked (`CB_MALFORMED_REQUEST`) |
| Same leaves | Child task resolved to an unrelated pair | **Succeeds** (HR4-01) |
| `objective_ref` | Task row names another ObjectiveVersion | **Not prevented** (HR4-02). The scope then follows that objective. |
| `task_ref` | Swap the Task row after issuance | Blocked. `task_record_digest` is bound. |
| `purpose_class` | Planner or request supplies it | Blocked (TaskProfile) |
| Project/workspace, compartments | Request or HTTP ids | Blocked. Canonical chain from the ObjectiveVersion; mismatch → DENY. Only as trustworthy as the objective choice (HR4-02). |
| `node` | Non-`LOCAL` value | Blocked (malformed) |
| `environment_class` | Agent claims a sandbox | Blocked. The TCB launcher records it and it must equal the profile's class. |
| Provider/egress | Agent names a provider | Blocked. Profile ∩ current authorizations; router selection; grant binding. |
| `security_policy_version` | Older policy | Blocked (high-water mark) |
| Revocation epoch | Store restore | Detected when the anchor survives (§31) |
| Integrity / `initial_label` | — | Not attacker-controlled, but its **source labels are undefined** (HR4-05) |

**Retries, forks, continuation, children, replay:**

- *Retry and continuation:* a new ESC; fields must equal the predecessor's;
  taint is inherited. Sound, **if** the predecessor set is trusted (HR4-02).
  The laundering chain *RESTRICTED → crash → retry → prior output → emit*
  fails anyway, because prior output can reach the retry only as an item,
  and items carry their stored labels (§13.5, INV-CB-074).
- *Fork / child:* HR4-01.
- *Replay:* ESC ids are insert-once, grants are store-held, and ESCs are
  never re-opened after restart (§14.4). Sound.

**No ContextRequest can override any ESC field.** Every removed field makes
the request malformed (§19), and the selector is confined to the ESC's
compartments. Confirmed.

## 9. LineagePair analysis

| Question | Verdict |
|---|---|
| Action authority remains a distinct semantic type | Yes. `AuthorityScope` v1 is unchanged. |
| Context authority remains a distinct semantic type | Yes. `ContextClearance` has its own order and meet, and no join. |
| Both atomically bound into one ESC | Yes: `lineage_pair_id` plus both leaf ids |
| Neither leaf can change during execution | Yes (insert-once ESC) |
| Revocation of either causes denial | Yes. §34 step 3, the delivery commit, INV-CB-066. The ESC becomes REVOKED permanently. |
| Delegation cannot widen either | Per edge, yes (check-not-clip on each side). **Per execution, no:** a child execution can be bound to a pair that was not attenuated from its delegator (HR4-01). |
| `memory_scope` explicit | Yes: `PERSIST` ∈ sinks, `persist_compartments`, `max_persistence` |
| No ambiguity versus v0.2 §8 semantics | Mostly. §39 classifies the design as an explicit refinement. One ambiguity remains: `ESC.principal` versus the v0.2.5 CR-01 "requesting principal" (HR4-01, part C). |

**Attacks:**

| Attack | Result |
|---|---|
| Authority leaf A + clearance leaf B from unrelated lineages | Blocked at issuance: same delegate and objective, and parent consistency (rule 2). **Not stated:** each leaf may appear in **at most one** pair (HR4-06). |
| Stale authority + current clearance | Blocked (pair ineffective) |
| Current authority + revoked clearance | Blocked |
| Child using the parent's clearance but a different authority | Blocked at issuance (rule 2), **but not at ESC selection** (HR4-01) |
| Clearance shopping | Blocked, since exactly one pair must match. A low-authority parent can, however, create a second pair for the same (agent, objective, profile) and so deny service to the owner's own lineage (HR4-01). |
| Lineage replay | Revoked pairs are never effective. Id non-reuse is not stated for pairs or clearances (HR4-06). |
| Lineage substitution | **Succeeds** (HR4-01) |

**Is `AMD-025-01` needed?** **No.** A side record that references v0.2.5 edge
ids needs no change to `DelegationRecord`, `AuthorityScope` or
`RootAuthorization`.

The pair does add two obligations on v0.2.5.2 that r2 does not list:

- issuance of the authority edge inside a transaction that also inserts the
  clearance edge and the pair;
- an owner-act digest covering both halves, because v0.2.5
  `root_request_digest` covers only `(delegate, scope, redelegation)`.

Both are additive implementation obligations, not semantic changes (HR4-06).

## 10. Objective integrity

Attack: the owner grants authority for O v1, the objective text changes, and
the existing authorization is reused.

- A new version is a new `ObjectiveRef`. Pairs and edges bound to v1 fail
  step 7 (`objective_ref` equality).
- A task referencing v1 after supersession fails step 2 ("not superseded
  for new work").
- ESCs bind `objective_digest`, and every decision checks the objective
  (§34 step 2).
- The mutable `Project.objective` binds nothing.

**The attack fails.**

Remaining gaps:

- **HR4-02.** Which ObjectiveVersion a task uses comes from the Task row. An
  execution under O1 can create a Task naming O2 (v0.2.5 T-13 "objective
  switching", one level up).
- **HR4-09.** "Revoked" objective (`CB_OBJECTIVE_INVALID`) has no defined
  mechanism, and it is unstated whether supersession ends LIVE ESCs.
- **HR4-05.** The **label** of the ObjectiveVersion content item is
  unspecified, yet it seeds every ESC's `initial_label`.

**CR-OBJ-01 is sufficient** as a store prerequisite once those three points
are stated. Purpose derivation (TaskProfile, never text) is sound.

## 11. Control-plane / data-plane analysis (rebuilt)

| Data-plane source | Could become a control value via | r2 mechanism | Verdict |
|---|---|---|---|
| User prose | Objective text | T-2 owner act only | Sound |
| Planner output: agent selection | `agent_type` | T-1 profile; contradiction → DENY | Sound |
| Planner output: purpose | — | Profile only | Sound |
| Planner output: approval requirement | `requires_approval` | Profile approval class; a weaker claim → DENY | Sound |
| Planner output: dependencies | Edge | T-6, flows only | Sound |
| Planner output: **Task row fields** (objective ref, parent, root/child, predecessors) | ESC inputs | **None listed** | **Gap (HR4-02)** |
| Parent-model proposal of a **child delegation** (scope, clearance) | LineagePair | **Not in the "exhaustive" T-table** | **Gap (HR4-01).** INV-CB-071 as written forbids the child path that §9.5 rule 5 requires. |
| Model output | Any | Ingested UNTRUSTED; claims ignored | Sound |
| Web content, retrieval, tool results | Labels, instructions | Source policy; DATA_UNTRUSTED | Sound |
| Connector content | Its own label | Self-declared class ignored | Sound for the class. **Not for the resource identity** (HR4-07). |
| QA output, errors | Retry decisions, labels | Items ⊒ H_exec; closed codes | Sound |
| Memory | Instructions | INSTRUCTION removed | Sound |
| Task text | TASK_INSTRUCTION | Structured fields only | Sound |
| Source-policy selection | — | Trusted adapter + resource id | See HR4-07 |
| Node identity | — | Fixed `LOCAL` | Sound |
| Provider selection | — | Router on broker-derived requirements | Sound |
| Label construction | — | Broker only; floors narrow | Sound |
| Owner identity | Body fields | Canonical record + OwnerChannel | Sound |

Deterministic policies may consume untrusted input as a selector (T-1). The
two gaps are places where untrusted input is itself treated as a trusted
binding.

## 12. TASK_INSTRUCTION analysis

- The channel admits only a deterministic rendering of ESC fields by
  reviewed templates (INTERNAL_RECORD).
- Planner prose, model-generated tasks, QA feedback and retrieval metadata go
  only in DATA_UNTRUSTED.
- The owner's objective content goes in OWNER_MESSAGE.
- Placement never raises integrity (INV-CB-072, INV-CB-011).

Injection attempts through a model-written task description, retrieved data
quoted into a task, and dependency output all land in DATA_UNTRUSTED.
Quoting inside owner messages takes `min(OWNER_ASSERTED, embedded)`. Pasted
text remains a stated residual.

**Resolved.** Prose cannot gain OWNER_ASSERTED or trusted-control integrity by
appearing in a task.

## 13. Durable taint analysis

| Aspect | Verdict |
|---|---|
| Authoritative store | The hash-chained taint log is part of the ESC (§14.1) |
| Persistence, restart, crash | Durable. Restart terminates LIVE ESCs. Continuation inherits. |
| Broker failover | Single node. The durable log survives. |
| Retry, continuation | Genesis ⊒ ⊔ of predecessors. The predecessor set's trust is HR4-02. |
| Fork, parent/child | The child has its own ESC. Child → parent is a flow, ceiling-checked. |
| Concurrent delivery, serialization | Per-ESC single writer. Emissions are computed inside the serialized section. |
| Delivery and output transactions | Delivery commit steps 1–5. Output is ingested with H read after the commit. |
| Taint ceiling | Semantics sound in direction, **definition ambiguous** (HR4-05) |

**Constructed chain:** RESTRICTED delivery commit (taint appended) → crash
→ restart (ESC TERMINATED) → retry ESC with genesis ⊒ RESTRICTED → prior
output (an item labeled ⊒ RESTRICTED if emitted after the delivery) →
emission labeled ⊒ RESTRICTED.

**The output cannot become less restrictive.** Delivery cannot precede taint
durability: release is step 6, after commit.

**Exact point of no return:** §14.3 step 6. Content is released into the sink
after the commit of the transaction that revalidated, consumed, appended
taint and wrote the release audit record. For external sinks it is the
transmission, after dispatched = bound verification.

**Minor text inconsistency (HR4-09):** §14.1 and §14.5 name taint causes
`TOOL_RESULT` and `CHILD_RESULT`, but §34 appends only `DELIVERY`, because
results reach the ESC through a grant. The safe reading is that every result
is delivered, and so tainted, before the agent sees it. The text should say
so.

## 14. Taint DoS

- A malicious agent can read only items within its clearance whose delivery
  keeps `H ⊑ taint_ceiling`. Deliveries beyond the ceiling are denied, not
  absorbed.
- The ceiling comes from the owner-approved TaskProfile, clamped by
  clearance. The agent can neither raise nor lower it.
- A child cannot poison its parent beyond the parent's ceiling (TC-42).
- Denials are uniform to the requester (`DENIED`/`NOT_AVAILABLE`). The
  ceiling's own denial code appears only in audit. No classification oracle
  beyond the accepted side-channel model was found.

Verdict: sound, **subject to HR4-05**. If the ceiling is under-specified, an
implementer may make it vacuous (no DoS protection) or deny-all (no work).

## 15. Tool-ingestion and source-policy analysis

**Tool reads (§16.2):** `L = source_label(policy(adapter, resource)) ⊔
H_exec_at_invocation`. The design:

- ingests broker-side;
- delivers results only through grants;
- makes unclassifiable resources NO_FLOW;
- forbids adapters from reaching broker-owned or legacy stores.

This covers file reads, DB queries, browser reads, connector reads,
subprocess output (no such tool exists yet) and external API responses.
**The label is not derived merely from H_exec.**

**Malicious connector claiming `source_type = PUBLIC`:** the self-declared
class is ignored. Selection uses the registered adapter id, the resource
identity "as resolved by the trusted adapter interface", and the
owner-approved table under the current policy version. Unknown means NO_FLOW.

**The residual (HR4-07):** for an **untrusted** connector (ISO-CONN), the
resource identity is reported by the connector itself across the IPC
boundary. A hostile connector can say it read `public-feed/…` while
returning the bytes of a confidential mailbox it can also reach. The
contract must require:

- for untrusted connectors, a label derived from the **adapter-level
  ceiling** (the ⊔ over every resource that connector can reach), or from a
  resource identity observed outside the connector (for example, an egress
  proxy's final URL origin);
- for web fetch, the final origin after redirects.

## 16. Persistent artifact and sink-mediation analysis

**Round-trip test:** classified context → write artifact → end execution →
re-read in a new execution.

- **Direct write, then re-read:** blocked. Binding ⊒ writer's H; the
  re-ingestion join.
- **Edited, renamed or copied by a non-Jarvis process** inside a
  Jarvis-controlled location: non-ingestible, since there is no matching
  (locator, digest) binding.
- **Same path, changed bytes:** non-ingestible.
- **Alternate encoding or serialization made outside Jarvis:** unbound, so
  non-ingestible.
- **Copied, moved, archived, committed or otherwise re-materialized by a
  Jarvis adapter whose effect reads a bound artifact:** **laundered.**
  §17.2 sets the new binding's label to "⊒ the writer's H_exec", and a
  path-only argument does not raise H (HR4-03). S-30 "Git commits: local
  commit = artifact binding" is the concrete instance.
- **"Jarvis-controlled location"** is not a defined, protected set (HR4-03).

**What artifact identity means in r2:** a (keyed canonical-locator digest,
content digest) pair. It is not a path alone. That is correct. It fails
closed for external edits. It does not follow data moved by Jarvis's own
adapters.

**Sink inventory versus the repository.** S-01..S-31 cover prompts,
research queries, tool arguments and results, tasks, agent runs, memory,
evidence, reports, audit, logs, exceptions, files, caches, embeddings,
display, HTTP, connectors, exports, browser state, other agents and
processes, subprocesses, observables, backups, Git and node transfer.

The following **existing** content-bearing persistent columns are in no row
and no R-fact (HR4-04):

| Table (`app/database/models.py`) | Content columns | Written by |
|---|---|---|
| `action_plans` | `description`, `success_criteria`, `last_error` | decision_intelligence |
| `action_records` | `description`, `inputs_json`, `dependencies_json`, `expected_result`, `success_criteria`, `verification_method`, `last_error` | decision_intelligence |
| `action_approval_requests` | `reason`, `action_summary`, `risk_summary`, `proposed_inputs`, `expected_effect` | decision_intelligence |
| `approvals` | `requested_action`, `reason`, `decision_reason` | approval service (live) |
| `execution_attempts` | `error_message` | decision_intelligence |
| `execution_results` | `structured_output_json`, `side_effects_json`, `error_message` | decision_intelligence |
| `verification_results` | `expected`, `observed`, `issues_json` | decision_intelligence |
| `failure_records` | `message` | decision_intelligence |
| `replan_proposals` | `replacement_*`, `reason` | decision_intelligence |
| `tasks` | `input_data`, `success_criteria` (only output/description/error are listed) | orchestration (live) |
| `projects`, `workspaces` | `description`; `projects.objective` is returned by `GET /projects/{id}` | live API |
| `agents` | `description`, `configuration` | registry |
| `usage_records` | token counts per task (an output-size observable) | live |

The §18 catch-all ("not a permitted destination … every such flow is DENY";
legacy content is LEGACY_UNLABELED) keeps these fail-closed in principle.

Two problems remain:

1. The action-pipeline tables sit **on the exact path §22 composes with.**
   After v0.2.5 CR-01/CR-05 integration:
   - tool arguments that carry item content are persisted in
     `action_records.inputs_json`;
   - they are **displayed** to the approver in
     `action_approval_requests.proposed_inputs` / `action_summary`;
   - tool results are persisted in `execution_results.structured_output_json`.

   These are PERSIST and display flows with no sink mapping. The design must
   say whether they become item references (CR-LEG-01) and how approval
   display is mediated (USER_DISPLAY via OwnerChannel).
2. INV-CB-073 and INV-CB-074 claim completeness, and TST-CB-073 would test
   only the listed rows, which makes it tautological.

## 17. Owner and principal analysis

**The OwnerChannel contract (§8.2)** defines every required property:

- authentication of the human with a phishing-resistant factor;
- canonical `HUMAN_OWNER` mapping;
- session binding;
- expiry and re-authentication;
- an explicit act over canonical content, digest, destination and scope;
- single-use `owner_event_id` bound to the request digest;
- CSRF protection;
- audit-before-effect;
- device and remote rules;
- separation from agents.

**Before `OWNER_CHANNEL_READY`**, all of the following are DENY (§8.3,
INV-CB-057):

- declassification and endorsement;
- owner persistence;
- policy / TaskProfile / destination / source-policy approval;
- clearance roots;
- objective creation;
- node enrollment;
- self-improvement approval;
- owner-only release.

Every display is EXPORT, and so impossible. **Confirmed.**

**Bootstrap circularity.** `OWNER_CHANNEL_READY` requires a running
SecurityPolicyVersion that declares the channel enabled. Policy approval
requires the channel. r2 breaks the cycle by trusting the bootstrap-installed
policy (§6.3, §29.4). That is acceptable. It does not state:

- which `owner_event_id` the bootstrap policy carries;
- how the first high-water mark is anchored;
- which CR builds the policy store (HR4-08).

The precondition is still unambiguous in its fail-closed direction:
until all of that exists, everything owner-dependent is DENY.

**Isolation dependency.** Property 10 requires Level 2+ separation, but
CR-OWN-01 does not depend on CR-ISO-01 in §40.E (HR4-08).

**Principal model:**

- `User` rows, emails and `resolved_by` strings are never principals.
- The application user record, the authenticated owner session and the
  canonical `HUMAN_OWNER` principal are distinct (§8.1).
- Multi-user support is explicitly out of scope.

**Confirmed.**

## 18. Workspace / project analysis

Live-style attack: workspace A + project B + caller-controlled ids.

- §9.3 step 3 derives scope from the ObjectiveVersion's project → workspace
  → owner account → canonical owner.
- It requires equality with the ObjectiveVersion's recorded scope.
- It treats any disagreeing supplied id as DENY.
- The ObjectiveVersion's scope is verified at its creation (owner act).

Caller ids never establish ownership. **Sound**, with one caveat: the
objective itself is chosen by a Task-row field (HR4-02). The live `/chat`
defect (R-03, re-confirmed in `routes.py:152–200`) remains an integration and
deployment blocker (CR-API-01).

## 19. Egress / provider analysis

| Path | Result under r2 |
|---|---|
| Anthropic / OpenAI prompt | `MODEL_CLOUD` in label and clearance; destination authorization for the exact provider and model; terms eligible; covers level, compartments and purpose; bound in the grant; dispatch verified. Otherwise DENY. |
| Research provider | `TOOL_ARG_EXTERNAL` query: authorization plus `export_allowed` on H_exec |
| External tool | Same, plus action authority and approval before any ApprovalRequest |
| Fallback provider / retry on another model | New full decision and new grant; dispatch = bound |
| Exported file | `EXPORT` + `export_allowed` + `ExportDestination` authorization |

**Absence of exact authorization = DENY:** confirmed (INV-CB-063).

The authorization binds:

- provider and model (`ModelDestination`);
- destination identity digest;
- purpose;
- item coverage (level and compartments);
- the execution (through the grant's ESC and `destination_policy_ref`);
- retention and training terms (`provider_terms`, required for model and
  search destinations).

Routing cannot widen: the router gets broker-derived requirements, its
default is never used, and local unavailability is DENY.

**Compatibility note (HR4-13, INFO).** v0.2.3 `allowed_provider_ids` is
provider-granular. The router may pick any model of an allowed provider.
Model-level binding therefore depends on the post-selection check in §34
step 5, which r2 does perform. No v0.2.3 change is needed.

**RESTRICTED locality.** `DestinationAuthorization.max_level` "can never be
RESTRICTED", and a change requires a separately approved contract. Because
every external sink needs a covering authorization, RESTRICTED can reach no
external destination. An ordinary authorization cannot carry it.
**Confirmed** (§24.2, INV-CB-063, TST-CB-063).

## 20. Requested floor and declassification analysis

**Requested floor.** The requester may only:

- raise `level`;
- remove `MODEL_CLOUD`, `TOOL_ARG_EXTERNAL` and `EXPORT`;
- turn `export_allowed` from true to false;
- add AGENT exclusions other than its own agent and its parent chain.

Excluding the owner, removing owner-visibility sinks, altering purposes,
compartments, expiry, persistence, integrity or nodes, and producing
NO_FLOW are all rejected. The emission is then labeled `H_exec`, and the
rejection is audited. Contradictory floors normalize to NO_FLOW and are
rejected. **An agent can never modify authoritative metadata.** Confirmed.

LOW residual (HR4-10): an agent may exclude oversight agents (QA, reporting,
security-audit profiles), or raise the level above the reporting ESC's
clearance. That hides its output from automated oversight. It is fail-closed
(QA cannot pass what it cannot read), but it is a sabotage vector.

**Declassification.** What an owner act approves:

- the exact canonical bytes (NFC, invisible, bidi and private-use
  characters rejected, line endings normalized, closed content type);
- bound to the source item, provenance and label digests;
- the exact target label;
- the destination authorization when it is release-specific.

| Transformation | Covered by an existing approval? |
|---|---|
| Whitespace change, Unicode normalization, alternate serialization | Canonicalized first, so only equal canonical bytes match. Any other byte difference invalidates the act. |
| Equivalent text, summary, paraphrase, extracted fact, partial excerpt, OCR of a screenshot | No. Each is a new derived item (⊒ H_exec) and needs its own act. Screenshots have no canonical text type, so they are not declassifiable. |

Every declassification:

- creates a **new** item;
- leaves the source unchanged;
- lowers confidentiality only by owner act;
- keeps integrity equal to the source's (endorsement is a separate act,
  capped at OWNER_ASSERTED);
- retains provenance (`declassified_from`, `owner_event_id`).

**Confirmed.**

LOW residual (HR4-11): canonicalization does not render trailing spaces,
whitespace runs or mixed-script homoglyphs visibly. It cannot stop
linguistic steganography in model-authored candidates. The residual should
be stated, since the owner is the last line of defence.

## 21. Audit analysis

**Release fails closed when audit fails.** The release audit record is
written inside the delivery commit (step 4) before commit and release. If
audit is unavailable, the release is DENY (`CB_AUDIT_UNAVAILABLE`). The
ALLOW → audit fails → release sequence is impossible as specified.

**Mandatory versus best-effort events** are distinguished (§30.2):

- mandatory: release events;
- best effort: denials, which still stand;
- continue: diagnostics.

INV-CB-035's "every decision produces an audit event" reads as mandatory
for denials too. That is a wording conflict (HR4-09).

**Minimization.** Audit holds ids, codes, versions, label digests and keyed
HMAC digests only. Content, titles, objective text, reasons, exception text
and unkeyed low-entropy digests are forbidden. Audit is RESTRICTED/AUDIT.
The `CONTEXT_ACCESS_DENIED` withheld-id list is confined to the restricted
view. **Audit does not become a shadow content store.**

Implementation note: "same transaction" requires the audit log and the
broker stores to commit atomically (one database, or two-phase commit).

## 22. Anti-rollback analysis

**What the contract guarantees locally:**

- a monotonic policy high-water mark;
- revocable, never-reloadable approvals;
- a monotonic revocation epoch recorded in grants and ESCs;
- an external anchor compared at start and at every delivery commit;
- regression → deny everything;
- epochs, versions, sequence numbers and owner-event ids never repeat.

A DB restore with the anchor intact is detected (TST-CB-053).

**What remains a deployment limitation (§31 item 6):** a whole-machine
snapshot that also rolls back the anchor. It needs a hardware counter or a
remote witness. r2 states this honestly and claims no class-R resistance
without it. **Confirmed.**

## 23. Isolation and secret analysis

The threat model is now honest (§6.2):

- **class M:** defended in contract;
- **C-conn:** only at ISO-CONN, and connectors stay disabled until then;
- **C-in and C-os:** TCB compromise, explicitly out of contract;
- **NODE:** not applicable in single-node.

No claim is made that a Python reference monitor stops hostile in-process
Python (§6.1, §6.5).

| Component | Required class | Verdict |
|---|---|---|
| Normal model agents | ISO-AGENT, Level 1 | Adequate against M |
| Trusted tool adapters | TCB-reviewed; Level 1, or Level 2 when secret-bearing | Adequate |
| Untrusted connectors | ISO-CONN, Level 3, no credentials | Adequate. HR4-07 on labeling. |
| Secret-using workers | ISO-SECRET, Level 2, audience enforced outside at Level 3 | Adequate |
| Self-improvement / code execution | ISO-DEV, Level 3 (Level 4 for production data) | Adequate |

CR-ISO-01 is a sufficient prerequisite, with INV-CB-068 refusing capabilities
until it exists. The one ordering gap is the OwnerChannel's Level-2
requirement (HR4-08).

**SecretRef.** r2 no longer treats a SecretRef as protection against hostile
in-process code (§25 item 3).

Leakage through a malicious adapter (errors, logging, command lines,
environment, URLs, headers, telemetry, output, exception strings) is
addressed by:

- reviewed ISO-SECRET adapters only;
- external egress enforcement;
- closed error codes;
- value scrubbing (necessary but not sufficient);
- no credentials ever reaching untrusted connectors.

A hostile adapter holding a raw secret is explicitly out of contract
(INV-CB-024). **Confirmed honest.**

## 24. Single-node analysis

`NodeRef = {LOCAL}`. Every constructible label, clearance, grant, ESC and
SecretRef names only `LOCAL`. `CROSS_NODE_TRANSFER` and `REPLICATED` are not
constructible. Any other node reference is malformed, whether it appears in:

- a label;
- a grant;
- a request;
- a destination;
- a cross-node sink.

There is no configuration string from which a trusted remote node can be
constructed, because the vocabulary has one value. The prerequisites for a
second node are listed (§28.2). **Confirmed.**

## 25. Resource bounds and label algebra

**Resource bounds (§32).** Every dimension has a reviewed bound, and
exceeding it is DENY, never truncation. That covers:

- the provenance DAG, via taint-snapshot references and bounded walks;
- compartments and excluded principals;
- label fan-in;
- grants per ESC and issuance rate;
- taint-log length;
- denied-request rate;
- audit aggregation;
- replay attempts;
- artifact-lineage depth;
- selector size.

The numbers are deferred. No algorithmic ambiguity was found. Snapshot
references remove the O(n²) provenance growth.

**Label algebra (re-derived independently):**

| Dim | Domain | Restriction order | ⊔ | Safe empty | Conflict |
|---|---|---|---|---|---|
| label_version | exact int | equality | equal or NO_FLOW | — | mismatch → NO_FLOW |
| level | 4-value chain | ≤ | max | — | — |
| compartments | bounded set | ⊆ | ∪ | ∅ = no requirement | — |
| integrity | 4-value chain | ≥ (lower = more restrictive) | min | — | — |
| sinks | non-empty set | ⊇ | ∩ | ∅ → NO_FLOW | — |
| nodes | `{LOCAL}` | ⊇ | ∩ | ∅ → NO_FLOW | — |
| purposes | non-empty set | ⊇ | ∩ | ∅ → NO_FLOW | — |
| excluded_principals | bounded AGENT set | ⊆ | ∪ | ∅ = none excluded | never HUMAN_OWNER |
| persistence_ceiling | 6-value chain | ≥ | min | — | — |
| expires_at | aware UTC | ≥ | min | — | — |
| export_allowed | bool | true → false | AND | — | — |

The product is a join-semilattice:

- ⊔ is commutative, associative and idempotent;
- NO_FLOW is absorbing;
- restriction is monotonic;
- `F(L1 ⊔ L2) = F(L1) ∩ F(L2)`.

**There is no fictitious identity element.** One would need
`expires_at = +∞`, which is not representable. r2 correctly avoids needing
one: H_exec is seeded from `initial_label`, and the grant label is the ⊔ of a
non-empty set.

**`export_allowed` versus the external sinks is consistent everywhere:**

| Sink | Requirement |
|---|---|
| `MODEL_CLOUD` | Sink in label and clearance + destination authorization (not `export_allowed`) |
| `TOOL_ARG_EXTERNAL` | `export_allowed` + authorization |
| `EXPORT` | `export_allowed` + authorization |

The same rule appears in §12.2, §13.6, §15.4, §22 and §23.3, TC-02 and
INV-CB-028. No contradiction was found.

**New ambiguities from the correction pass:**

1. §12.2 opens with "an empty set means no flow", while compartments and
   excluded principals may be empty (meaning "no requirement"). INV-CB-015
   repeats the blanket wording (HR4-09).
2. The taint ceiling is a label, but "clamped by clearance" has no defined
   operator between the label order and the clearance order, and its
   `expires_at` / `excluded_principals` / `persistence_ceiling` dimensions
   are undefined for a static TaskProfile (HR4-05).

## 26. Gate / egress decision model

```text
permit(op) ⇔ AuthorityGate ∧ ContextGate ∧ BoundaryGate ∧ EnvironmentGate ∧ EgressGate
```

Destination authorization is **its own gate** (EgressGate). The label and
clearance parts of external flows (`MODEL_CLOUD`/`TOOL_ARG_EXTERNAL`/`EXPORT`
∈ sinks, `export_ok`) sit inside BoundaryGate's `flow()`.

The same checks appear consistently in:

- §15.4;
- §22;
- §24.2 "effective destination permission";
- §34 `request_context` steps 5 and 7;
- §34 `deliver()`.

§34 step 5 checks `dest.effective(now)` and does not name terms eligibility
separately. Read with §24.2, "effective" must include terms eligibility, and
the text should make that explicit (folded into HR4-09).

No two sections give contradictory formulas. The model is deterministic
(INV-CB-038).

## 27. Grant / TOCTOU analysis

| Attack | Result |
|---|---|
| Capability replay | Store-held; one-shot consumed atomically in the delivery commit (TST-CB-021 concurrency) |
| Revocation between issue and delivery | Delivery re-runs steps 0, 2, 3, 4, 5 and 7 inside the commit |
| Identity or execution substitution | Grant bound to `esc_id`; harness binding checked |
| Destination or provider substitution | Typed `sink_target`; dispatch = bound (both inside the commit and immediately before transmission) |
| Item substitution | `item_ids` bound; content immutable per id; read under the same snapshot |
| Policy change | Step 0 re-run (≥ high-water mark); revoked version → DENY |
| Stale epoch | Anchor comparison at every delivery commit |
| Concurrent use | Per-ESC serialization; single-writer transaction |

The transaction boundary is the delivery commit, and release follows it. The
only residual is the declared post-commit window, which mirrors v0.2.5 R-10.
**Sound.**

## 28. Invariant audit (74 active)

| Class | Count | Invariants |
|---|---|---|
| VALID | 61 | 001–004, 006–014, 016–029, 031–034, 036–045, 047, 048, 051–060, 063–068, 070, 072 |
| AMBIGUOUS | 3 | 015 (empty-set wording), 035 ("every decision produces an audit event" vs best-effort denials), 075 (ceiling definition, HR4-05) |
| INCOMPLETE | 9 | 046 and 061 (pair selection and Task inputs, HR4-01/02); 049 (objective and lineage via Task row, HR4-02); 050 (effect-side reads, HR4-03); 062 (connector resource identity, HR4-07); 069 (predecessor set, HR4-02); 071 ("exhaustive" table omits child delegation and Task creation, HR4-01/02); 073 and 074 (inventory omissions, HR4-04) |
| UNSOUND | 0 | — |
| REDUNDANT | 1 | 005 (subsumed by 046). It does not conflict and is kept for traceability. |

Total: 61 + 3 + 9 + 0 + 1 = **74**.

- There are no duplicate semantics that conflict.
- 023 and 052 overlap. 052 adds the untrusted-connector prohibition, so the
  two are complementary.
- There are no undefined ids, and INV-CB-030 is not referenced as active.
- Every active invariant is testable.

## 29. Test-mapping audit

All 74 active invariants map one-to-one to a TST-CB row. Coverage of the
named hazards:

| Hazard | Covered by |
|---|---|
| Concurrency | 008, 021 |
| Restart | 047 |
| Replay | 010, 021, 022, 053 |
| Persistent re-ingestion | 050 |
| Egress fallback | 065 |
| Owner authentication | 057, 067 |
| Cross-workspace denial | 016, 064 |
| Real isolation (marked iso) | 002, 033, 052 |

**Tests that would not prove their property as written:**

| Test | Problem |
|---|---|
| TST-CB-005 / 046 | No child-substitution case: a child Task must never bind a pair not attenuated from the delegating ESC's pair; two child pairs for one triple; a principal/leaf mismatch (HR4-01) |
| TST-CB-061 / 049 / 069 | No forged Task-row fields (objective_ref of another objective, root/child flag, predecessor list omitted) (HR4-02) |
| TST-CB-050 | No adapter copy/move/archive/commit of a bound artifact (HR4-03) |
| TST-CB-062 | No lying-connector resource identity and no redirect case (HR4-07) |
| TST-CB-073 | **Tautological.** It checks only the §18 rows. It must enumerate every content-bearing column and route from the schema and router (HR4-04). |
| TST-CB-035 | "Exactly one audit event per decision" conflicts with flood aggregation |
| TST-CB-075 | Cannot be written deterministically until the ceiling is defined (HR4-05) |
| TST-CB-068 | "Checked by the design validator" is a document check, not enforcement |

**Mocked-away enforcement.** Stages v0.2.6.3–.5 run on in-memory fakes. They
prove algebra and decision logic, not durability or isolation. TST-CB-047,
053, 055 and the (iso) tests must be re-run against the real stores and
sandboxes at v0.2.6.9 and at capability enablement. r2 marks only the (iso)
tests this way.

**Verdict:** every active invariant has a future test, but **not all are
meaningful yet**. Eleven tests need strengthening, listed above.

## 30. Change-request dependency graph

The graph was reconstructed independently from §40.A–§40.E:

- **No cycles.** Every edge points to a lower tier.
- **No runtime integration before its prerequisites.** Tier 8 depends on
  everything.
- **No stage temporarily widens access.** CR-EGR-01a (containment) is
  Tier 0. CR-API-01 is Tier 2, before any broker runtime. Legacy content is
  non-disclosable by rule, so it is contained before any broker read.
  CR-CB-08 follows CR-ISO-01.
- Owner authentication (Tier 1) and provider containment (Tier 0) come early
  enough.

**Ordering and catalogue gaps (HR4-08, MEDIUM, not freeze-blocking):**

1. **No CR owns the SecurityPolicyVersion store and policy-activation owner
   act (T-5).** TaskProfiles (CR-ESC-01), destination authorizations
   (CR-EGR-01), source policies (CR-ING-01) and persistence rules all live
   in it. `OWNER_CHANNEL_READY` itself is declared by it.
2. **CR-OBJ-01 (Tier 2) creates ObjectiveVersions with
   `allowed_task_profiles`, but TaskProfiles are created by CR-ESC-01
   (Tier 3).** The objective store cannot validate its references.
3. **CR-OWN-01 property 10 requires Level-2 separation,** but CR-OWN-01 does
   not depend on CR-ISO-01.
4. **Bootstrap:** the initial policy's `owner_event_id` and the first
   high-water-mark anchoring are unspecified.

**Prerequisite classification:**

| Kind | Items |
|---|---|
| Design prerequisites (before freeze) | Text corrections for HR4-01..07 |
| Implementation prerequisites | v0.2.5.2/.3, v0.2.5 CR-01..CR-05, CR-PRN-01, CR-OWN-01, CR-API-01, CR-EPOCH-01, CR-OBJ-01, CR-ESC-01, CR-TAINT-01, CR-ING-01, CR-ART-01, CR-EGR-01, CR-LEG-01, CR-ISO-01, CR-SINK-01, CR-CB-01..08, the policy-store CR (HR4-08) |
| Deployment prerequisites | Owner authentication and API authorization live (R-01..R-04, R-13); CR-EGR-01 (R-08, R-09); CR-CB-03/06 (R-07); CR-ISO-01 + CR-CB-08 (R-11); CR-ESC-01 (R-05); a hardware or remote anchor for any rollback claim; at-rest encryption for device-local claims; §28.2 before any second node |

## 31. Frozen-contract compatibility

| Area | Finding |
|---|---|
| CD-01 / LineagePair vs v0.2 §8 | Explicit refinement requiring owner approval (§39). No modification of v0.2.5 or v0.2.5.1. |
| LineagePair selection vs **v0.2 §10** ("no authority laundering"; one lineage "under whose objective/task scope the action was actually requested") | **Conflict in the r2 procedure** (HR4-01): a child can run under a pair unrelated to its delegator |
| `ESC.principal` vs **v0.2.5 §7 / CR-01** requesting principal ("leaf delegate must equal the requesting principal") | **Ambiguous** (HR4-01 part C). If `ESC.principal` (the delegator) is the CR-01 requester of the child's Actions, every child Action fails `DELEGATE_MISMATCH`. If the agent is the requester, `principal` is a new concept that r2 must name. |
| `memory_scope` | Mapped (clearance PERSIST fields). Compatible with the v0.2.5 deferral. |
| ObjectiveRef | Compatible. CR-OBJ-01 realizes the store that v0.2.5 §13 left as an integration precondition (v0.2.5 anticipated v0.2.8; doing it earlier is not a conflict). |
| Principal types | Compatible: `{HUMAN_OWNER, AGENT}`, one configured owner (v0.2.5 §4, HR-19) |
| Delegation issuance | Compatible, **if** v0.2.5.2 `issue()` can join an enclosing transaction and the owner act's digest covers the whole pair. Additive obligations, not amendments (HR4-06). |
| Provider router | Compatible. The default is unchanged and never relied on. `allowed_provider_ids` is provider-granular; model binding is post-selection (HR4-13). |

**Required future amendment:** none. AMD-025-01 remains optional and
unnecessary for security, and it is correctly deferred rather than silently
applied.

## 32. New HR4 findings

### HR4-01: Child execution lineage is selected by search, not bound to the delegating lineage — authority/clearance laundering

- **Severity:** HIGH
- **Category:** RESIDUAL-HR3 (HR3-01, HR3-10; HR2-19)
- **Affected sections:** §9.3 steps 6–7; §9.5 rule 5; §21.3 rules 1–5; §7.3; §39
- **Affected invariants:** INV-CB-046, INV-CB-061, INV-CB-066, INV-CB-071; v0.2 §10; v0.2.5 §7 (CR-01)
- **Exploit or contradiction:**
  - **A. Substitution.** Step 7 selects "the unique effective pair for
    (agent, objective_ref, task_profile)". It does **not** require that the
    pair belongs to the Task, that `pair.parent_pair_id` equals the parent
    ESC's pair for a child, or that the pair is a root pair for an
    owner-initiated task. §9.5 rule 5 ("a LineagePair attenuated from the
    parent's") is therefore not enforced by the procedure.

    Setup:
    - Objective O has profiles `P_ORCH` (agent jarvis, allowed child
      `P_FIN`) and `P_FIN` (agent finance, `FINANCIAL`).
    - The owner issued root pair `R_fin` for (finance, O, P_FIN) and
      `R_orch` for (jarvis, O, P_ORCH), whose clearance excludes
      `FINANCIAL`.

    Attack:
    1. Injection steers the orchestrator ESC to create child Task T with
       profile `P_FIN`. The edge is allowed (T-6).
    2. No child pair is required before the Task exists.
    3. The ESC Issuer finds `R_fin` as the unique pair and binds T to it.
    4. T now executes with finance's full root authority and `FINANCIAL`
       clearance, on work the orchestrator initiated and shaped. The
       orchestrator could never have delegated that authority.

    This is the v0.2 §10 pattern: "A asks B, which has broader capability"
    must not grant A's request B's authority.
  - **B. Collision.** If the parent does issue a child pair `C` (≤ R_orch),
    there are now two effective pairs for the triple. T **and every
    owner-initiated finance task** become `ESC_LINEAGE_AMBIGUOUS`. A
    lower-authority lineage can deny service to a higher one. Fail-closed,
    but it also shows the selection key is wrong.
  - **C. Principal semantics.** For a child, `ESC.principal =
    cr01_requester(creating action)` is the delegator. v0.2.5 requires the
    leaf delegate to equal the requesting principal of each Action, and
    nothing requires the pair's authority lineage to pass through
    `ESC.principal`. Either every child Action fails `DELEGATE_MISMATCH`, or
    `principal` means something v0.2.5 does not define.
  - **D. Exhaustive table.** Issuing a child pair turns a parent-model
    proposal (child scope and clearance) into control-plane records. That is
    not a T-row in §7.3, so INV-CB-071 as written forbids the child path
    that §9.5 rule 5 requires.
- **Security impact:** delegation widening at execution level; authority
  and clearance laundering across agents; DoS of owner lineages.
- **Required correction:**
  1. Bind the pair to the Task, insert-once, by the trusted issuance path:
     root tasks carry an owner-issued root pair; child Tasks carry the child
     pair issued **in the same transaction** as the Task. Replace search by
     lookup.
  2. Require `pair.parent_pair_id == parent_esc.lineage_pair_id` and
     `pair.issuer_event == parent_esc` for children, and `parent_pair_id =
     None` with an owner event for roots.
  3. Require the authority lineage to pass through `ESC.principal`.
  4. Define `principal` against the v0.2.5 CR-01 requesting principal.
  5. Add a T-row for child delegation issuance: parent proposal → check-not-
     clip against the parent pair's redelegable authority **and** clearance,
     and profile ∈ `allowed_child_profiles`.
  6. Add tests for A–C.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR4-02: ESC Issuer trusts Task-record fields that have no trusted writer

- **Severity:** HIGH
- **Category:** RESIDUAL-HR3 (HR3-01, HR3-05)
- **Affected sections:** §7.1 (the Task record is absent from the table); §9.2 `task_ref`, `principal`, `predecessor_esc_ids`; §9.3 steps 1, 2, 6, 12; §10.2 rule 5; §14.5
- **Affected invariants:** INV-CB-049, INV-CB-061, INV-CB-069, INV-CB-070, INV-CB-071
- **Exploit or contradiction:**
  - The ESC Issuer reads all of the following from the Task record:
    - `objective_ref` (step 2);
    - `proposed_task_profile_id` (step 4, the intended T-1 selector);
    - the owner-initiated versus delegated-child classification and
      `creating_action` (step 6);
    - `parent`;
    - `prior_attempt_escs` (step 12).
  - r2 never says who writes these fields. Today Task rows are written by
    `persist_plan` from model `TaskPlan` output, with workspace and project
    taken from the HTTP request (R-05; re-verified in
    `orchestration/dispatcher.py`).
  - Only the profile id is authorized as a planner-influenced input (T-1).
  - Consequences:
    - an execution bound to objective O1 can create a Task naming O2 (another
      owner project). The ESC is then issued under O2's scope, pairs and
      destinations, which is objective switching (v0.2.5 T-13);
    - a planner-written "root" flag makes the principal the canonical owner;
    - an omitted predecessor list skips taint inheritance. That is defence in
      depth only, because items keep their labels, but it violates
      INV-CB-069's premise.
- **Security impact:** the primary HR4 claim ("bound by trusted control-plane
  state") is false for the objective binding, the principal classification
  and the predecessor linkage.
- **Required correction:**
  1. Add Task control fields to §7.1.
  2. `objective_ref` = the creating ESC's (or the owner act's) objective, never
     a proposal field.
  3. Root tasks are created only from an ObjectiveVersion by the trusted
     issuance path. Children only by the delegation path (HR4-01).
  4. Predecessor links are written only by the trusted retry/continuation
     scheduler.
  5. Mark all of these fields insert-once and covered by `task_record_digest`.
  6. Everything else in a Task row is data plane.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR4-03: Artifact bindings take the writer's H_exec only, so adapter effects that read bound artifacts launder labels

- **Severity:** HIGH
- **Category:** RESIDUAL-HR3 (HR3-03)
- **Affected sections:** §17.2 ("the binding's label is ⊒ the writer's H_exec"); §17.3; §15.4 `TOOL_ARG_INTERNAL`; §18 S-16, S-30; §34 `deliver()` `artifact_registry.bind(...)`
- **Affected invariants:** INV-CB-050, INV-CB-006, INV-CB-028
- **Exploit or contradiction:**
  1. ESC E has INTERNAL taint and sees only file names.
  2. E invokes a copy, move, archive or local git-commit adapter on
     `/sandbox/a.txt`, which is bound CONFIDENTIAL `REPOSITORY(r)`, writing
     `/sandbox/b.txt` (or a commit). The arguments are path strings
     (INTERNAL), so the flow is allowed.
  3. The adapter reads `a.txt` inside its effect. No result is ingested, so
     §16.2 never applies.
  4. The new binding gets label ⊒ E's H_exec, which is INTERNAL.
  5. A later ESC re-ingests `b.txt` with join = INTERNAL. It then persists
     or pushes it (S-30 "push: EXPORT" checks the commit binding's
     `export_allowed`).

  The principle (§17.1: an artifact "that contains or derives from protected
  context keeps a durable binding to its label") and the concrete rule
  disagree. The concrete rule launders. "Jarvis-controlled location" is also
  undefined, so the boundary between `TOOL_ARG_INTERNAL` and `EXPORT` is
  implementer-chosen.
- **Security impact:** downgrade and cross-compartment disclosure of
  persistent data without an owner act, which is exactly the property HR3-03
  required.
- **Required correction:**
  1. Binding label ⊒ writer's H_exec ⊔ the binding/source label of **every
     resource the adapter's effect reads**.
  2. Adapters declare their effect-side read set in the reviewed ToolRegistry.
     An undeclared or unclassifiable read makes the write DENY.
  3. Commits and archives join every included file's binding.
  4. Define the set of Jarvis-controlled locations as an owner-approved,
     protected policy artifact. A write anywhere else is EXPORT.
  5. Add tests.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR4-04: Sink and legacy inventory omits existing content stores, including the action pipeline §22 composes with

- **Severity:** MEDIUM
- **Category:** RESIDUAL-HR3 (HR3-14; HR2-23)
- **Affected sections:** §4.3; §17.5; §18; §40 (CR-LEG-01, CR-SINK-01); §22 point 5
- **Affected invariants:** INV-CB-073, INV-CB-074
- **Exploit or contradiction:**
  - The tables in §16 of this review (`action_records`,
    `action_approval_requests`, `execution_results`, `approvals`, …) persist
    tool arguments, tool results, approval display text and error messages.
  - After CR-01/CR-05 integration, item-bearing tool arguments land in
    `action_records.inputs_json`. They are shown to the approver via
    `proposed_inputs`/`action_summary`, and results land in
    `execution_results.structured_output_json`.
  - The §18 catch-all makes these DENY, which would make the §22 action
    composition unimplementable as written, or lead an implementer to
    persist them unlabeled.
  - `tasks.input_data`/`success_criteria`, `projects.description`/`objective`
    (returned by `GET /projects/{id}`), `workspaces.description`,
    `agents.configuration` and `usage_records` (an output-size observable)
    are also missing.
  - TST-CB-073 is tautological against an incomplete list.
- **Security impact:** an unlabeled persistence path on the authorized action
  pipeline; approval display outside `USER_DISPLAY`; a false completeness
  claim.
- **Required correction:**
  1. Add rows and R-facts for every listed table and column.
  2. Specify that action-pipeline content becomes item references (CR-LEG-01
     scope) and that approval display is `USER_DISPLAY` via the OwnerChannel.
  3. Classify `usage_records` as B-class with a bounded observable.
  4. Make TST-CB-073 enumerate columns and routes from the schema and router.
- **Freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR4-05: Taint ceiling and initial label are under-specified

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected sections:** §9.2 (`initial_label`, `taint_ceiling`); §9.3 step 13; §9.4; §10.1; §14.7
- **Affected invariants:** INV-CB-075, INV-CB-047, INV-CB-008
- **Exploit or contradiction:**
  - **(a) Clamping is undefined.** "Clamped by clearance" has no defined
    operator: the ceiling lives in the label restriction order, and the
    clearance is a permission set.
  - **(b) Static dimensions break the check.** For a static TaskProfile
    label, `expires_at`, `excluded_principals` and `persistence_ceiling` make
    `H ⊔ L ⊑ ceiling` either deny-all (every item expiring before the
    profile's ceiling date fails) or vacuous (an implementer sets a far-past
    expiry, or skips dimensions).
  - **(c) Initial label sources are unspecified.** `label(ObjectiveVersion
    content)` and `label(trusted task control fields)` have no specified
    source policy.
    - If the objective text is labeled like owner conversation (RESTRICTED
      `USER_PRIVATE`, export false, §15.5), every ESC is born RESTRICTED:
      no research query, no `PERSIST` beyond SESSION, clearance needs
      `USER_PRIVATE` everywhere.
    - If the owner may choose a lower label, the owner act must bind it.
- **Security impact:** INV-CB-075 cannot be implemented deterministically.
  Either availability collapses, or the DoS protection is illusory. The
  objective label decides every execution's egress.
- **Required correction:**
  1. Define the ceiling per dimension: level, compartments, integrity, sinks,
     purposes, nodes and export as fixed profile values; `expires_at`
     computed per ESC, or excluded from the ceiling check; excluded
     principals and persistence explicitly stated.
  2. Define clamping as a per-dimension operation.
  3. Specify the ObjectiveVersion content label as part of the owner act.
  4. Specify the label of rendered control fields (for example INTERNAL,
     canonical-scope compartments, INTERNAL_RECORD).
- **Freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR4-06: LineagePair issuance obligations are incomplete

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected sections:** §21.2–§21.3; §40.A (v0.2.5.2); §39.2
- **Affected invariants:** INV-CB-046, INV-CB-066, INV-CB-022
- **Exploit or contradiction:** r2 says the pair "requires only" stable edge
  ids and revocation and lifecycle events from v0.2.5.2. It also needs:
  1. **Leaf uniqueness.** Each authority leaf and clearance leaf may appear
     in at most one pair. This is not stated, so re-pairing an effective
     clearance edge with another authority edge is not excluded by text.
  2. **Enclosing transaction.** v0.2.5.2 `issue()` must participate in an
     enclosing transaction with the clearance and pair inserts. v0.2.5 §17
     defines `issue` atomicity only with its own record and audit.
  3. **Owner digest.** The owner act for a root pair must bind a digest over
     the authority request, the clearance request and the TaskProfile.
     v0.2.5 `root_request_digest` covers only `(delegate, scope,
     redelegation)`.
  4. **Clearance revocation.** The set of clearance revokers and
     no-un-revoke are not specified. (v0.2.5 §11 defines them for authority
     edges only.)
  5. **Id non-reuse.** Clearance and pair ids must never be reused.
- **Security impact:** pair consistency and owner-intent binding depend on
  implementer choices.
- **Required correction:** state items 1–5 in §21.3 and add them to the
  v0.2.5.2 prerequisites in §40.A as additive obligations. AMD-025-01 is not
  required.
- **Freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR4-07: Source-policy selection trusts connector-reported resource identity

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected sections:** §16.2; §6.2 (C-conn); §6.5 ISO-CONN
- **Affected invariants:** INV-CB-062
- **Exploit or contradiction:**
  1. A hostile ISO-CONN connector that can reach a public feed and a
     confidential mailbox reports "resource = public-feed/item-9".
  2. It returns mailbox bytes.
  3. The broker selects the PUBLIC source policy.

  Sandboxing the connector's code does not make its **metadata** trustworthy.
  Separately, web fetches that follow redirects must label by the final
  origin.
- **Security impact:** downgrade at ingestion once untrusted connectors are
  enabled.
- **Required correction:**
  - For untrusted adapters, derive the label from the adapter-level ceiling
    (the ⊔ over every resource class reachable under its credentials and
    network policy), or from a resource identity observed outside the
    adapter.
  - Trusted adapters report the final resolved identity.
  - Add both cases to TST-CB-062.
- **Freeze blocker:** YES (text)
- **Implementation blocker:** YES
- **Deployment blocker:** NO (connectors stay disabled until ISO-CONN)

### HR4-08: CR catalogue and dependency graph omissions

- **Severity:** MEDIUM
- **Category:** NEW
- **Affected sections:** §8.2 property 10; §8.3; §29.4; §31; §40.B; §40.E
- **Affected invariants:** INV-CB-034, INV-CB-054, INV-CB-057
- **Exploit or contradiction:**
  1. No CR builds the SecurityPolicyVersion store or the policy-activation
     owner act (T-5), although TaskProfiles, destination authorizations,
     source policies, persistence rules and `OWNER_CHANNEL_READY` all live
     in it.
  2. CR-OBJ-01 (Tier 2) references TaskProfiles that are created only by
     CR-ESC-01 (Tier 3).
  3. CR-OWN-01 requires Level-2 separation (property 10) without depending
     on CR-ISO-01.
  4. The bootstrap policy's `owner_event_id` and the first high-water-mark
     anchoring are unspecified.
- **Security impact:** risk of an implementation order in which the owner
  channel or policy activation exists without its isolation or anchoring. No
  widening was found, because all of these fail closed.
- **Required correction:** add CR-POL-01 (policy store and activation, below
  CR-OBJ-01 and CR-ESC-01); add the edge CR-OWN-01 ← CR-ISO-01 (or scope
  property 10); specify the bootstrap record.
- **Freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR4-09: Textual inconsistencies introduced or kept by the correction pass

- **Severity:** LOW
- **Category:** REGRESSION (items 1–2) / NEW
- **Affected sections:** §12.2; §14.1; §14.5; §24.2; §26.2; §30.2; §34; §35.2
- **Affected invariants:** INV-CB-015, INV-CB-035, INV-CB-070
- **Exploit or contradiction:**
  1. §12.2: "an empty set means no flow" versus compartments and exclusions
     that may be empty.
  2. Taint causes `TOOL_RESULT`/`CHILD_RESULT` versus `DELIVERY`-only in
     §34.
  3. INV-CB-035 "every decision produces an audit event" versus best-effort,
     aggregated denials (TST-CB-035 says "exactly one").
  4. "Trusted orchestration" persists as the unnamed persistence trigger
     (§26.2).
  5. `CB_OBJECTIVE_INVALID` "revoked" with no objective revocation mechanism.
     Supersession's effect on LIVE ESCs is unstated.
  6. §34 step 5 does not name terms eligibility (§24.2).
- **Security impact:** implementer ambiguity. No exploit found.
- **Required correction:** align the wording.
- **Freeze blocker:** NO
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR4-10: Requested floors can hide output from oversight agents

- **Severity:** LOW
- **Category:** NEW
- **Affected sections:** §13.6
- **Affected invariants:** INV-CB-051
- **Exploit or contradiction:** a floor may exclude any AGENT except the
  emitter and its parent chain, including QA, reporting or security-audit
  profiles. It may also raise the level above a reporting ESC's clearance.
  Output then escapes automated review. This is fail-closed: work cannot
  complete.
- **Security impact:** sabotage of oversight and availability. No
  confidentiality loss.
- **Required correction:** forbid excluding principals of profiles marked as
  oversight in the TaskProfile policy, or document the residual.
- **Freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR4-11: Declassification canonicalization residuals not stated

- **Severity:** LOW
- **Category:** NEW (residual of HR2-14)
- **Affected sections:** §13.7 item 2; §38.2
- **Affected invariants:** INV-CB-059
- **Exploit or contradiction:** trailing spaces, whitespace runs, mixed-script
  homoglyphs and word-choice steganography survive canonicalization and are
  not visibly rendered.
- **Security impact:** covert payload through the only release valve, bounded
  by owner review.
- **Required correction:** render whitespace visibly; reject mixed-script
  confusables; state the linguistic-steganography residual.
- **Freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR4-12: Review independence limitation

- **Severity:** INFO
- **Category:** RESIDUAL-HR3 (HR3-16)
- **Affected sections:** §38.2; §44.5
- **Affected invariants:** —
- **Exploit or contradiction:** shared model-family blind spots.
- **Security impact:** undiscovered defects.
- **Required correction:** a human review of §6, §8, §9 and §21.3 before
  freeze.
- **Freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR4-13: Router allow-list is provider-granular

- **Severity:** INFO
- **Category:** NEW
- **Affected sections:** §24.4
- **Affected invariants:** INV-CB-065
- **Exploit or contradiction:** v0.2.3 `allowed_provider_ids` cannot restrict
  models.
- **Security impact:** none, provided the §34 step-5 post-selection check
  stays mandatory.
- **Required correction:** state that model-level eligibility is enforced
  after router selection and never delegated to the router.
- **Freeze blocker:** NO
- **Implementation blocker:** NO
- **Deployment blocker:** NO

**Counts:** CRITICAL 0 · HIGH 3 · MEDIUM 5 · LOW 3 · INFO 2 (13 findings).

## 33. Freeze blockers

| Source | IDs |
|---|---|
| HR4 | HR4-01, HR4-02, HR4-03 (HIGH); HR4-04, HR4-05, HR4-06, HR4-07 (MEDIUM, text-only) |
| Carried through them | HR3-01, HR3-03, HR3-05 (PARTIALLY_RESOLVED HIGH); HR3-14; HR2-19; HR2-23 |

**Freeze-criteria check:**

| Criterion | Met? |
|---|---|
| No unresolved CRITICAL design finding | Yes |
| No unresolved HIGH design finding | **No** (HR4-01..03) |
| ESC semantics unambiguous | **No** (HR4-01, HR4-02, HR4-05) |
| Owner-channel precondition unambiguous | Yes |
| LineagePair coherent | **No** (HR4-01, HR4-06) |
| Taint restart semantics coherent | Yes |
| Persistent artifact labels cannot be laundered | **No** (HR4-03) |
| Source-policy selection trusted | Partly (HR4-07) |
| Egress defaults deny | Yes |
| Complete sink mediation specified | **No** (HR4-04) |
| Single-node limitation explicit | Yes |
| Invariant/test mapping internally consistent | Yes as a mapping. 11 tests need strengthening (§29). |
| Frozen-contract compatibility clear | **No** (HR4-01 vs v0.2 §10 and v0.2.5 CR-01) |

## 34. Implementation blockers

- Every CR in r2 §43.1 (CR-ESC-01, CR-TAINT-01, CR-OBJ-01, CR-OWN-01,
  CR-PRN-01, v0.2.5.2/.3, v0.2.5 CR-01..CR-05, CR-ING-01, CR-ART-01,
  CR-EGR-01, CR-LEG-01, CR-CB-01..08, CR-EPOCH-01, CR-SINK-01, CR-ISO-01).
- Numeric bounds.
- HR4-01..HR4-09.
- The new policy-store CR (HR4-08).

## 35. Deployment blockers

The live conditions are unchanged and **re-confirmed in code** where
inspected:

- unauthenticated API and caller-asserted approval identity (R-01, R-02);
- the `/chat` cross-workspace confused deputy (R-03, `routes.py:152–200`);
- unauthenticated disclosure of task content (R-04) and of project objective
  and description (`ProjectOut`);
- arbitrary `User` creation (R-13);
- unconditional cloud egress (R-08, R-09, `get_default_provider`);
- content in audit metadata (R-07);
- raw secrets and no isolation (R-11);
- model output selecting agent identity and the approval flag (R-05,
  `dispatcher.persist_plan`).

Also blocking:

- no rollback anchor;
- no at-rest encryption;
- any second node;
- HR4-01, HR4-02, HR4-03, HR4-04 and HR4-08.

## 36. LineagePair recommendation

**REVISE LINEAGEPAIR**

The realization is right in kind:

- separate types and algebras;
- one coupling record;
- both leaves fixed in the ESC;
- revocation of either ends access;
- `memory_scope` mapped;
- no change to frozen v0.2.5 or v0.2.5.1.

**AMD-025-01 is not required**, and option C gives no security property the
pair cannot give.

As written, however:

- the pair is **selected by search** rather than bound to the Task and to
  the delegating lineage, which permits laundering (HR4-01);
- its issuance obligations (leaf uniqueness, the enclosing transaction, the
  owner digest over both halves, clearance revocation, id non-reuse) are
  incomplete (HR4-06).

Both are text revisions within the LineagePair design. AMD-025-01 was not
created.

## 37. Final HR4 status

**POST-CORRECTION DESIGN NOT READY — FURTHER CORRECTIONS REQUIRED**

Three HIGH design findings remain open:

- HR4-01: child lineage substitution and laundering;
- HR4-02: Task-record control fields have no trusted writer;
- HR4-03: artifact label laundering through adapter effects.

Four MEDIUM text-level freeze blockers remain as well (HR4-04..07).

**Six of nine HR3 HIGHs are resolved in design:** HR3-02, 04, 06, 07, 08 and
09. HR3-01, HR3-03 and HR3-05 are partially resolved.

No fundamental redesign is required. The architecture holds:

- the label lattice;
- conjunctive gates with a separate EgressGate;
- store-held grants and delivery commits;
- durable taint;
- the owner-channel precondition;
- default-deny egress;
- honest isolation scoping;
- single-node.

Every open item is correctable in contract text.

## 38. Read-only validation (commands and results)

Run with `.venv/Scripts/python.exe` before the HR4 file was placed in `docs/`:

| Command | Result |
|---|---|
| `scripts/check_v013_freeze_baseline.py` | exit 0: OK (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `scripts/check_v020_contract.py` | exit 0: OK |
| `scripts/check_v023_router_contract.py` | exit 0: OK |
| `scripts/check_v024_agent_contract.py` | exit 0: OK |
| `scripts/check_v025_design_contract.py` | exit 1: DISCREPANCY FOUND. The three untracked v0.2.6 documents are outside the v0.2.5.1 allowlist (expected). |
| `python -m pytest -q -p no:cacheprovider` | exit 1: **1 failed, 2234 passed, 1 warning** (308 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`, for the same allowlist reason. |

No validator or test was modified.

## 39. Review artifact integrity

SHA-256 after the review, recomputed before finishing:

| File | Before | After | Changed? |
|---|---|---|---|
| Corrected design | `23a798d1…beb7f1` | `23a798d1d11b469d4cca7bea58966096015fb92923f911ff525cdecc99beb7f1` | no |
| HR2 | `ec7d9f31…b9b2e` | `ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e` | no |
| HR3 | `081c8993…ee58` | `081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58` | no |

The only file added by this review is
`docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md`. There was no commit,
no push and no merge.

No v0.2.6 production implementation has been authorized or created.
