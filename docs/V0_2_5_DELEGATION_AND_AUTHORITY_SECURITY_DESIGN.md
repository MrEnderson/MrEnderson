# Jarvis OS v0.2.5 — Delegation + Authority Attenuation: Security Design

```text
status = DESIGN_ONLY
human_design_approval = APPROVED
design_approved = true
implementation_authorized = false
pipeline_integration_authorized = false
migration_authorized = false
frozen_code_changes_authorized = false
p5_execution_protocol_authorized = false
v0_2_6_authorized = false
```

`status = DESIGN_ONLY` means no runtime implementation exists. The Human
Owner has approved the design decisions DA-01..DA-10 (Part III). That is
**design approval only**: it authorizes no implementation, no pipeline
integration, no migration, no frozen-code change and no P5 execution.

**Phase:** v0.2.5 — architecture and security design only. No production
code, no `app/delegation/`, no migration, no change to any existing module.
**Predecessor:** v0.2.4 `d10fbbbf4b697eba822a89495ae0ebd276b3101d` (parent:
B-11 security fix `21dc3d022165162550ca24c518a0fb11f445238d`).
**Hostile review:** HR-1 applied. Findings, change log and approval questions are in Part II; changed text is tagged `[HR-xx]`.
**Human Owner design decisions:** DA-01..DA-10 approved (DA-03 with required rewording); recorded in Part III.
**Machine-readable companion:** `docs/v0.2.5_delegation_authority_design.json`
(checked by `scripts/check_v025_design_contract.py`).

> **Central invariant.** Delegation may preserve or reduce already-authorized
> scope. It may never create, amplify, infer, recover, combine, or
> manufacture authority that was not actually granted.
>
> `child_authority ⊆ parent_delegable_authority`, and along any chain
> `A0 ⊇ A1 ⊇ … ⊇ An`.

---

## 1. What was inspected (and what it means for delegation)

| System | File(s) | Finding relevant to delegation |
|---|---|---|
| v0.2 constitution | `docs/v0.2_architecture_security_contract.json` / `.md` | Already fixes: human owner is root of authority; agents hold delegated responsibility only; `child ⊆ parent_effective_authority`; effective authority = intersection, most restrictive wins; single lineage per action; no cross-delegation union; denial persistence keyed by action identity + semantic intent; approval bound to requesting agent; self-approval forbidden; protected targets for coding agents. v0.2.5 must implement these, not re-invent them. |
| Permission Engine | `app/decision_intelligence/permission_engine.py` | Authoritative, deterministic, never trusts agent-proposed levels; unknown `action_type` → BLOCK. Output `PermissionDecision(outcome, permission_level, risk_level, …)`. **`PermissionLevel` cannot distinguish P0 from P1 or P3 from P4** (P3 = `EXTERNAL_ACTION`/MEDIUM, P4 = `EXTERNAL_ACTION`/HIGH). → CR-02. |
| Approval Engine | `approval_engine.py`, `schemas.ApprovalRequest` | Approval binds to `action_id` + `action_hash`; bounded TTL; single-use consumption; self-approval check is `decided_by == requested_by` string equality only. → CR-03. |
| Action hash | `action_hash.py` | Allowlist: `action_type, tool_name, inputs, expected_result, permission_level, risk_level`. **Excludes requesting agent and any delegation** although the constitution requires approval to bind to the requesting agent. → CR-01. |
| Action / ActionRecord | `schemas.Action`, `database/models.ActionRecord` | Carries `agent_type` (a v0.1.3 dispatch type string), no requesting principal, no delegation reference; fixed DB columns — binding a delegation needs a migration. → CR-01. |
| Orchestrator | `action_plan_orchestrator.py` | Pipeline: eligibility → `evaluate_permission` → approval request (if REQUIRE_APPROVAL) → plan budget → `execute_action_durably`. Clock is injected (`clock()`), a usable trusted-time pattern. |
| Durable executor | `durable_action_executor.py` | Step C revalidates approval from the durable row and atomically consumes it before claim E; **the `PermissionDecision` is supplied by the caller**, not recomputed. → CR-05; this is where delegation revalidation (C′) belongs. |
| Budget | `budget.py` | Atomic reservation; **an unconfigured budget account is treated as unlimited.** Future delegated budgets must not inherit that semantic. |
| No denial store | (absent) | A rejected approval makes the Action terminal `REJECTED`; there is **no durable DenialRecord and no semantic-intent key** in v0.1.3. Denial persistence across rephrasing is currently unimplemented. |
| Legacy permissions | `app/security/permissions.py`, `app/agents/registry.py` | The legacy `app/orchestration` path grants standing `PermissionLevel`s by **agent type** (`AgentDescriptor.permissions`). Pre-existing "type grants permission" model; delegation must never consult it. |
| Providers v0.2.1–2.3 | `app/providers/*` | Provider/model ids are computational identity; router is independent; fallback cannot weaken constraints. |
| B-11 | `app/providers/frozen.py` | `FrozenDict`/`FrozenList` now block `|=`/`*=`; explicit base-class calls remain out of contract. |
| v0.2.4 | `app/agent_identity/*` | `AgentDefinition` is identity only; `AgentRegistry` is **in-memory**, immutable per id, exact-type + revalidated snapshot; `enabled` is eligibility, not permission; no lifecycle (disable/retire) mechanism exists yet. → CR-04. |

**Concepts that must stay distinct and are NOT duplicated here:** permission
classification (Permission Engine), approval (Approval Engine), spending and
action-attempt budgets (Budget), tool availability (ToolRegistry), executable
capability (ToolAdapters), provider/model capability (Provider Registry/Router),
identity (AgentRegistry). Delegation adds exactly one thing: **a bounded,
attributable upper limit on what a principal may request, and the lineage
that justifies it.**

---

## 2. Architecture options compared

| | A. Ceiling only | B. Structured capability scope | C. Capability tokens | D. Policy-intersection object | **E. Hybrid bounded AuthorityScope** |
|---|---|---|---|---|---|
| Security | Weak: P3 ceiling still permits any P0–P3 action type for any purpose | Good if closed | **Bearer risk**: possession = authority; copy/replay/forgery surface (contradicts DI-11) | Good in principle; policy language becomes an interpreter attack surface | Good: closed finite dimensions, positive allowlists |
| Complexity | Minimal | Medium–high (tends to grow) | High (signing, key mgmt → Credential Broker scope) | High (a policy DSL) | Low–medium |
| Auditability | High but uninformative | Medium | Low (who holds what?) | Low for humans | High: each dimension explainable |
| Revocation | Easy | Easy | Hard (tokens in the wild) | Easy | Easy (store-backed references) |
| Attenuation proof | Trivial | Per-dimension | Crypto-dependent | Requires policy containment — undecidable in general | **Per-dimension, decidable, property-testable** |
| Extensibility | Poor | Good | Good | Very good | Good via `schema_version` (new dimension = new version; old records fail closed) |
| P0–P5 compatibility | Direct | Direct | Indirect | Indirect | Direct (ceiling dimension) |
| Multi-business | None | Possible | Possible | Possible | Future dimension, explicit |
| Implementation risk | Low (but insufficient) | Medium | High | High | **Low–medium** |

**Selected: E — hybrid bounded AuthorityScope**, store-backed (not tokens),
meet-only algebra, closed dimensions. A is insufficient (a P3 ceiling would
let a research delegate `delete`). C is rejected on DI-11 (bearer tokens). D is
rejected because policy containment is not decidable in general and a DSL is
itself an attack surface. B is what E becomes if dimensions are allowed to grow
without a closed schema — E fixes the dimension set per `schema_version`.

---

## 3. Authority model

### 3.1 Seven distinct quantities (and who owns each)

| # | Quantity | Meaning | Computed by / owner |
|---|---|---|---|
| 1 | **Authority source** | The root grant a chain begins from | `RootAuthorization` issued by HUMAN_OWNER via the trusted non-agent layer (delegation store) |
| 2 | **Delegable authority** | What an edge's delegate may pass on: `redelegable_scope` (or none) | Delegation record (issuance validated by store) |
| 3 | **Delegated authority** | What an edge's delegate may itself request: `scope` | Delegation record |
| 4 | **Effective authority** | `meet(system_policy_ceiling, scope(e1), …, scope(en))` for the one named lineage, if every edge is effective at trusted time `t` | Delegation evaluator (pure) |
| 5 | **Required authority** | What the concrete action needs: P-tier + `action_type` + objective | Permission Engine classification (P-tier via CR-02) + Action binding |
| 6 | **Permission result** | `ALLOW / ALLOW_WITH_AUDIT / REQUIRE_APPROVAL / BLOCK` | Existing Permission Engine — unchanged |
| 7 | **Approval result** | Human decision on the exact action hash | Existing Approval Engine — unchanged |

Delegation owns 1–4 only. The gate is `required ≤ effective`; if false →
BLOCK before any approval request. If true, the existing Permission and
Approval Engines run exactly as today. **A delegated ceiling is never a
permission result** (DI-05): `required ≤ effective` is necessary, never
sufficient.

### 3.2 AuthorityScope (v0.2.5 dimensions)

| Dimension | Type | Order within dimension | Semantics |
|---|---|---|---|
| `schema_version` | `Literal[1]` | equality | Pins the dimension set; see §3.5 [HR-05]. |
| `vocabulary_version` | `int` | equality | Pins the meaning of every `action_types` string; see §3.6 [HR-09]. |
| `permission_ceiling` | `PTier` ∈ {P0,P1,P2,P3,P4} | total: P0 < … < P4 | Max tier the delegate may *request*. **P5 is not issuable to an agent in v0.2.5.** This is a new v0.2.5 policy decision (DA-03), not an existing constitutional rule. Agent P5 proposals stop at the authorization boundary: §3.7 [HR-12, DA-03]. |
| `action_types` | non-empty `frozenset[str]` over the pinned vocabulary (`read, internal_create, sandbox_create, external_modify, send, publish, delete, financial, install, privileged` + no-tool types `internal, no_op, manual, decision_only`) | subset | Only these action types may be requested. Each must be consistent with the ceiling (e.g. `publish` requires ceiling ≥ P4); inconsistent pairs are rejected at issuance rather than silently unusable. |
| `objective_ref` | `ObjectiveRef(objective_id, objective_version)` | equality of the pair | Bound purpose by durable **versioned** identity, never text [HR-10]. Identical for every edge of a lineage in v0.2.5 (sub-objectives are v0.2.8). |
| `expires_at` | aware UTC datetime (naive rejected) | earlier ≤ later | Required. Trusted clock only. Bounded by a max-TTL system policy. |

Earlier drafts and threat rows say `objective_id`; read it as `objective_ref`. Every dimension is **required**; none has a default.

**Record-level redelegation** (not a scope dimension, because it constrains
issuance rather than action): `redelegation: None | RedelegationPolicy(redelegable_scope, remaining_depth ≥ 1)`.

### 3.3 Order, meet, attenuation

- **Carrier set [HR-01].** `Auth = AuthorityScope ∪ {⊥}`. `⊥` (**NO_AUTHORITY**) is the explicit bottom: zero authority. It is an **internal algebraic sentinel and an evaluation outcome**. It is **never an issuable or storable `AuthorityScope`**: an issuance request that normalizes to `⊥` is rejected, so `AuthorityScope` keeps its non-empty invariants. `⊥` never means "no restriction" and is never confused with a missing value.
- **Order.** `leq(⊥, X)` holds for every `X`. `leq(X, ⊥)` holds only for `X = ⊥`. For scopes, `leq(A, B)` ("A grants no more than B") ⇔ `A.schema_version == B.schema_version ∧ A.vocabulary_version == B.vocabulary_version ∧ A.objective_ref == B.objective_ref ∧ A.ceiling ≤ B.ceiling ∧ A.action_types ⊆ B.action_types ∧ A.expires_at ≤ B.expires_at`. An unknown or mismatched version or dimension ⇒ **not comparable ⇒ treated as not-leq (fail closed)**.
- This is a **partial order** (a product of per-dimension orders, plus `⊥`). `{read}` and `{internal_create}` scopes are incomparable; they are never collapsed into a single "power level". The P-tier dimension alone is total; the scope is not.
- **Meet is total.** `meet(⊥, X) = ⊥`. For two scopes the meet is `⊥` if any version differs, if `objective_ref` differs, or if `A.action_types ∩ B.action_types = ∅`. Otherwise it is `(min ceiling, A.action_types ∩ B.action_types, same objective_ref, min expires_at, same versions)`, which is again a valid scope. So `(Auth, leq, meet)` is a genuine **meet-semilattice with bottom**. It is closed because the only values the scope invariants forbid (an empty action set, mixed objectives) map to `⊥`.
- **Closure answers.**
  - (A/C) Different objectives give `meet = ⊥`.
  - (B/D) Disjoint action types give `meet = ⊥`.
  - (E) `⊥` is first-class. At evaluation it yields `OUTSIDE_SCOPE` with reason `EMPTY_AUTHORITY`.
  - Expiry is deliberately kept out of the algebra. Time enters only through effectiveness at a trusted `t` (§10), so `leq` and `meet` stay time-free and deterministic.
- **No `join` / union is defined anywhere** (DI-06, constitution `cross_delegation_union_allowed=false`).
- **Attenuation at issuance is check-not-clip:** a child request is accepted only if `leq(request, parent.redelegable_scope)`; otherwise it fails `SCOPE_NOT_ATTENUATED`. Silent clipping would hide intent and make audit ambiguous.
- **Monotonic property (PO-01):** for every accepted issuance, `leq(child.scope, parent.redelegable_scope)` and `leq(parent.redelegable_scope, parent.scope)`, hence `leq(child.scope, parent.scope)`; by transitivity every lineage is non-increasing. At evaluation the effective scope is recomputed as a meet over the whole chain (PO-03), so even a record that bypassed issuance validation cannot widen anything. A per-hop `leq` violation found at evaluation is **rejected (`LINEAGE_INVALID`)**, never clipped. Check-not-clip holds at evaluation too [HR-16].

### 3.4 None / empty / missing / wildcard

| Case | Meaning |
|---|---|
| Missing scope field | Validation error. No field has an "unlimited" default. |
| `action_types = ∅` | Nothing allowed; rejected at issuance as meaningless. |
| `redelegation = None` | Redelegation forbidden. |
| `remaining_depth = 0` | Not representable (`redelegation` must then be `None`). |
| `"*"`, `"ALL"`, `"ANY"`, `"UNLIMITED"` | Rejected — not in any closed vocabulary. |
| Deferred dimension (tenant, resource, data class, budgets) | **Neither "unlimited" nor "delegated".** A v1 scope **grants zero authority** in every dimension it does not name. No other system may treat "delegation gate passed" as satisfying a tenant, resource, data or budget requirement. See §3.5 [HR-05]. |
| `⊥` | Zero authority. An internal sentinel and evaluation outcome; never stored and never issued (§3.3). |

### 3.5 Schema evolution and new dimensions [HR-05]

The earlier wording ("deferred dimensions are enforced by their owning
systems; delegation simply does not widen them") could be read as "a v1
record is silent about tenancy, so it is valid in every tenant". That reading
is **forbidden**:

1. **An absent dimension grants zero authority in that dimension, never ALL.**
   A v1 scope names no tenant, so it authorizes nothing that *requires* a
   tenant binding.
2. **Exact-version evaluation.** An evaluator for schema version N accepts
   only version-N records. Any other version returns
   `UNKNOWN_AUTHORITY_DIMENSION`, which fails closed.
3. **No automatic upgrade.** Adding `tenant_scope`, `resource_scope`,
   `data_classification_scope` (v0.2.6) or a budget dimension bumps
   `schema_version`. Every older record then becomes non-effective and must
   be **re-issued** by its delegator (for roots, by the owner). The v0.2.5
   design defines no upgrade function. A future one would need its own design
   review, and may only map each new dimension to its *most restrictive*
   value: the empty set, which is `⊥` for that dimension.
4. **No cross-system inference.** While a dimension is deferred, its owning
   system (Context Broker, tenancy, Budget) enforces it **without** treating
   the delegation result as evidence of permission.

This trades availability (mass re-issuance on every upgrade) for safety, on
purpose. It is decision DA-09.

### 3.6 Action-type vocabulary versioning [HR-09]

`action_types` strings only have meaning relative to the Permission Engine's
vocabulary (`_ACTION_TYPE_FLOOR` plus `_NO_TOOL_ACTION_TYPES`), which is a
private, unversioned dict today.

- **Adding** a new type cannot widen an old delegation, because scopes are
  positive allowlists.
- **Re-tiering or re-meaning** an existing type *could* widen one silently.
  Example: `external_modify` changed to cover irreversible edits.

Rule:
- Every scope pins `vocabulary_version`.
- Any change to the vocabulary (add, remove, or change a floor) bumps that
  version. Scopes pinned to a different version fail closed with
  `VERSION_MISMATCH`.
- Unknown strings are rejected at issuance and never authorized at
  evaluation.
- No wildcard exists.

Publishing a versioned vocabulary is part of CR-02.

### 3.7 Canonical P-tier and the P3/P4 problem [HR-02, HR-12]

**What the code does.**
- `PermissionLevel` has five values. P3 and P4 are both `EXTERNAL_ACTION`.
- `evaluate_permission` takes `max(action-type floor, tool default)` for
  **both** permission level and risk.
- So an `external_modify` (P3) action on a tool that declares `HIGH` risk is
  classified `EXTERNAL_ACTION/HIGH`, the same as `publish`.
- **`EXTERNAL_ACTION/LOW` is reachable,** contrary to the earlier draft: a
  tool declaring `EXTERNAL_ACTION/LOW` that supports `read` produces it.

**Canonical values.** `PTier` = {P0 … P5} are the **constitutional tier
names** (v0.2.0 `permission_compatibility.tiers`), not a second taxonomy.
`PermissionLevel` remains the Permission Engine's outcome-level enum. One
exhaustive, versioned mapping connects the two:

```text
required_tier = max(T_floor(action_type), T_class(decision))

T_floor:  internal|no_op|manual|decision_only → P0 ; read → P1 ;
          internal_create|sandbox_create → P2 ; external_modify → P3 ;
          send|publish|delete → P4 ; financial|install|privileged → P5 ;
          anything else → UNKNOWN (BLOCK)
T_class:  READ → P1 (P0 only if action_type is a no-tool type AND tool_name is None)
          WRITE → P2
          EXTERNAL_ACTION ∧ risk == MEDIUM → P3
          EXTERNAL_ACTION ∧ risk ∈ {LOW, HIGH, CRITICAL} → P4
          FINANCIAL_ACTION → P5 ; ADMIN → P5
          anything else → UNKNOWN (BLOCK)
```

**How this separates P3 from P4.**
- **P3 must be positively established.** Every other external
  classification is treated as P4.
- **Errors only over-classify.** A P3 action on a high-risk tool needs a P4
  ceiling.
- Because `T_floor` is part of the `max`, a `publish`, `send` or `delete`
  action can never compare as P3, whatever the tool declares.

**Residual risk.** Suppose an action is typed `external_modify` and its tool
*declares* `MEDIUM`, but actually has a consequential effect. By
construction that action is P3, and delegation cannot detect the semantic
mislabel. ToolRegistry declarations are therefore security-relevant to
delegation and must stay trusted, reviewed configuration.

**Ownership.**
- Before CR-02, the mapping is the single table above inside the delegation
  evaluator, tested exhaustively against every `(action_type, tool level,
  tool risk)` combination.
- CR-02 moves ownership into the Permission Engine, which then exposes
  `tier` on `PermissionDecision`.
- The interim table is safe, but it duplicates policy. That is why CR-02
  must land before integration.

**Excluding P5 [HR-12, DA-03].** Excluding P5 from delegation is a **new
v0.2.5 policy decision**. It is consistent with the v0.2.0 rules but not
required by them. The Human Owner approved it as DA-03, with this required
wording:

> **DA-03 (approved rule).** AI agents may never hold standing delegated P5 authority under v0.2.5. An AI agent may formulate or propose a P5 action, but v0.2.5 grants no authority to execute that action. Any future P5 execution path requires a separately designed, hostile-reviewed and Human-Owner-approved P5 authorization protocol.

It has a real consequence. In v0.1.3 an agent-originated `financial` action
reaches `REQUIRE_APPROVAL`, so a human can approve it. Once the delegation
gate is integrated before approval, **an agent can no longer originate any P5
action**. That is an intentional behavior change of the integration stage.

What v0.2.5 allows is a proposal, never authority:

```text
Agent P5 proposal   ≠  Agent P5 authority
Human approval      ≠  standing delegated P5 authority
P5 proposal         →  STOP at authorization boundary
```

- An agent may formulate a P5 action as a proposal (for example a P2 internal
  artifact). The proposal carries **zero** P5 authority.
- v0.2.5 defines **no path** from a P5 proposal to P5 execution. The proposal
  stops at the authorization boundary.
- Approval writes nothing to the delegation store and never changes a
  delegation ceiling. P5 is never a valid ceiling for an agent delegate.
- Any future P5 execution path needs a separately designed, hostile-reviewed
  and Human-Owner-approved P5 authorization protocol (OQ-10, **OPEN**). This
  design deliberately does not sketch that protocol.

Until such a protocol exists, P5 cannot be reached through agents at all.
That fails closed. The DA-03 hostile checks in Part III §V must all fail
closed.

### 3.8 System policy is a ceiling only [HR-07]

`SystemPolicyCeiling` is a **separate type**, not an `AuthorityScope`. Its
fields are `policy_version`, `max_tier_for_agents` (≤ P4),
`allowed_action_types`, `max_ttl`, `max_depth` and `vocabulary_version`. It
has no objective and no expiry, so it **cannot be evaluated on its own**.

- **No lineage means no authority.** The effective scope is defined only
  when a lineage exists, as the lineage meet clipped by the ceiling. With no
  lineage the result is `⊥`, never the ceiling: `ceiling ∩ nothing =
  nothing`.
- **Owner root above the ceiling.** If the owner issues P4 while policy
  allows only P2, **issuance is rejected**: check-not-clip applies to roots
  too. If policy is tightened *after* issuance, evaluation applies the meet,
  so the effective maximum drops to P2.
- **No override through a root.** The owner **cannot override system policy
  through a RootAuthorization.** Changing system policy is a separate,
  privileged policy-management action outside v0.2.5 (a protected-target
  change under `coding_agent_rules`).
- **Recorded policy.** Every `AuthorityEvaluation` records the
  `policy_version` it applied (a v0.2.3 lesson).

---

## 4. Principals and root authority

**PrincipalRef** = `(kind, id)` with `kind ∈ {HUMAN_OWNER, AGENT}`; `kind` is
part of identity, so `AGENT:"human.owner"` (a legal v0.2.4 agent_id) is never
the owner (T-41). `AGENT` ids must resolve in the trusted AgentRegistry;
`HUMAN_OWNER` ids must equal the single configured owner principal. The human
is **not** forced into `AgentDefinition`.

**SYSTEM_POLICY is not a principal and never grants.** It is a static,
reviewed ceiling (e.g. max tier issuable to agents = P4, max TTL, max depth)
that every effective scope is intersected with.

**Root problem ("who delegates to the top-level agent?")**: a chain's first
edge has `parent = RootAuthorization(owner_principal, owner_authorization_event_id)`
— an explicit, typed root, never `parent_agent_id = None`. Only the
HUMAN_OWNER, acting through the same trusted non-agent layer that already
owns `decide_approval()`, can issue a root. **No agent, title or system
component is an authority root.** A "Jarvis CEO" agent gets exactly what the
owner explicitly issued to it.

**Root trust dependency [HR-06].** v0.2.5 does **not** authenticate the
owner, and says so explicitly.

- **Nothing trusted identifies the owner today.** The Approval Engine's
  `decided_by` is a free string.
- **A RootAuthorization found in storage proves nothing by itself.** It is
  only as trustworthy as (a) the authenticated owner channel that created it
  and (b) the integrity of the store.

Minimum future provenance:
1. `issue_root` is callable **only** from the owner channel. No
   agent-reachable path (orchestrator, provider, tool or plan) may reach it.
2. `owner_authorization_event_id` is **unique across all roots**. One owner
   authorization mints exactly one root edge, so the event cannot be
   replayed to mint more (T-49).
3. `root_request_digest` is a canonical hash of the exact `(delegate, scope,
   redelegation)` the owner approved. The store recomputes it at issuance and
   at evaluation.
4. Write access to the database is equivalent to authority. That is a stated
   trust assumption: v0.2.5 has no signing. Cryptographic signing of roots is
   deferred and belongs with the Credential Broker.

Multiple owners are deferred. The `(kind, id)` principal model can express
them, but v0.2.5 accepts exactly one configured owner id.

**Principal identity [HR-17].** A principal is the pair `(kind, id)`. That
pair is used for:
- equality and hashing;
- serialization (`kind` is always emitted);
- continuity checks;
- cycle detection;
- self-delegation checks;
- revoker checks;
- audit output.

**No bare-string principal comparison is permitted anywhere.**
`HUMAN_OWNER:"alice"` ≠ `AGENT:"alice"`.

---

## 5. Proposed future contracts (documentation only — not implemented)

```python
# DESIGN SKETCH ONLY — not importable, not in app/.
_CFG = ConfigDict(frozen=True, extra="forbid", validate_default=True,
                  hide_input_in_errors=True, strict=True)

class PrincipalKind(str, Enum): HUMAN_OWNER = "HUMAN_OWNER"; AGENT = "AGENT"
class PTier(str, Enum): P0 = "P0"; P1 = "P1"; P2 = "P2"; P3 = "P3"; P4 = "P4"; P5 = "P5"

class PrincipalRef(BaseModel):
    model_config = _CFG
    kind: PrincipalKind
    id: str                      # AGENT: v0.2.4 agent_id rules; HUMAN_OWNER: configured owner id

class ObjectiveRef(BaseModel):          # [HR-10] durable, versioned, control-plane issued
    model_config = _CFG
    objective_id: str
    objective_version: int = Field(ge=1)

class AuthorityScope(BaseModel):
    model_config = _CFG
    schema_version: Literal[1]
    vocabulary_version: int       # [HR-09] pinned action-type vocabulary
    permission_ceiling: PTier     # P5 rejected when delegate.kind == AGENT
    action_types: frozenset[str]  # non-empty, closed vocabulary, tier-consistent
    objective_ref: ObjectiveRef
    expires_at: datetime          # aware UTC; naive rejected

# ⊥ (NO_AUTHORITY) is NOT an AuthorityScope instance: it is a module-level
# sentinel returned only by meet()/evaluate() [HR-01].

class SystemPolicyCeiling(BaseModel):   # [HR-07] ceiling only; never evaluable alone
    model_config = _CFG
    policy_version: int
    max_tier_for_agents: PTier          # <= P4
    allowed_action_types: frozenset[str]
    vocabulary_version: int
    max_ttl: timedelta
    max_depth: int

class RedelegationPolicy(BaseModel):
    model_config = _CFG
    redelegable_scope: AuthorityScope   # leq(redelegable_scope, scope)
    remaining_depth: int = Field(ge=1, le=SYSTEM_MAX_DEPTH)

class RootAuthorization(BaseModel):
    model_config = _CFG
    owner: PrincipalRef                  # kind must be HUMAN_OWNER
    owner_authorization_event_id: str    # UNIQUE across all roots [HR-06]
    root_request_digest: str             # canonical hash of (delegate, scope, redelegation) [HR-06]

class DelegationRequest(BaseModel):      # the ONLY input to issue(); untrusted until validated
    model_config = _CFG
    delegator: PrincipalRef
    delegate: PrincipalRef               # kind must be AGENT
    parent_delegation_id: str | None     # None ONLY together with a root authorization
    root: RootAuthorization | None       # exactly one of parent_delegation_id / root
    scope: AuthorityScope
    redelegation: RedelegationPolicy | None   # None = redelegation forbidden

class DelegationRecord(BaseModel):       # built ONLY by the store; never accepted as input
    model_config = _CFG
    delegation_id: str                   # store-generated uuid4; never caller-supplied; never reused
    delegator: PrincipalRef
    delegate: PrincipalRef
    parent: DelegationParentRef | RootAuthorization   # discriminated union, no None
    scope: AuthorityScope
    redelegation: RedelegationPolicy | None
    depth: int                           # 1 for a root edge
    issued_at: datetime                  # trusted clock
    # NO status, NO metadata, NO notes, NO approval-shaped field.

class RevocationRecord(BaseModel):
    model_config = _CFG
    revocation_id: str
    delegation_id: str
    revoked_by: PrincipalRef
    revoked_at: datetime                 # trusted clock
    reason_code: RevocationReason        # closed enum

class AuthorityEvaluation(BaseModel):    # NOT an approval, NOT a PermissionDecision
    model_config = _CFG
    outcome: Literal["WITHIN_SCOPE", "OUTSIDE_SCOPE", "LINEAGE_INVALID"]
    requesting_principal: PrincipalRef
    leaf_delegation_id: str | None
    lineage: tuple[str, ...]             # root → leaf delegation ids
    root_owner_event_id: str | None
    effective_scope: AuthorityScope | None
    required_tier: PTier | None
    required_action_type: str | None
    limiting_dimension: str | None       # which dimension decided OUTSIDE_SCOPE
    reason_codes: tuple[ReasonCode, ...] # closed enum, deterministic order
    evaluated_at: datetime               # the trusted snapshot used
    revocation_watermark: int            # store sequence number read
    policy_version: int                  # SystemPolicyCeiling applied [HR-07]
```

**Field table (DelegationRecord):**

| Field | Purpose | Trust source | Validation | Immutable | Security-critical | Optional | v0.2.5 |
|---|---|---|---|---|---|---|---|
| `delegation_id` | Reference | Store-generated | uuid4 format; uniqueness by store | yes | yes (identity, not authority) | no | yes |
| `delegator` | Who delegated | Store-checked principal | Resolves; active; equals parent edge's delegate (or owner for root) | yes | yes | no | yes |
| `delegate` | Who receives | Store-checked principal | AGENT; registered; enabled; ≠ delegator; not in lineage | yes | yes | no | yes |
| `parent` | Lineage link | Store | Existing effective record or RootAuthorization | yes | yes | no (typed root instead of None) | yes |
| `scope` | Acting bound | Request, checked | `leq(scope, parent.redelegable_scope)`; tier/action consistency; P5 ⇒ reject for agents | yes | yes | no | yes |
| `redelegation` | Onward bound | Request, checked | `redelegable_scope ≤ scope`; depth ≤ parent depth − 1 | yes | yes | yes (None = forbidden) | yes |
| `depth` | Chain length | Store-computed | parent.depth + 1 ≤ system max | yes | yes | no | yes |
| `issued_at` | Time of issuance | Trusted clock | aware UTC | yes | yes | no | yes |
| status | — | — | **Not stored**; computed | — | — | — | never |
| metadata / notes | — | — | **Not present** (T-26) | — | — | — | never |
| not_before | — | — | Omitted (effective at issuance) | — | — | — | deferred |
| budget/context/memory/tenant/resource | — | — | Deferred dimensions (§3.4) | — | — | — | deferred |

**No metadata at all.** v0.2.4 needed opaque descriptive metadata for
identities; a delegation needs none, and every free-text field is a smuggling
surface (`notes = "P5 approved"`). Human-readable explanation is generated
from typed fields.

**Secrets:** no field can hold a credential; `delegation_id` is not a secret
and not a credential (DI-11).

---

## 6. Trusted issuance, storage and trust boundaries

**Trusted:** records produced by the delegation store's `issue()`/`revoke()`;
the configured owner principal; system policy (reviewed configuration); the
AgentRegistry; the injected trusted clock.

**Untrusted (zero authority, however well-formed):** model output,
ProviderResponse content/structured_output/metadata, provider/model ids, web
or document content, files, messages, an agent's self-description, JSON
copies of real records, a known `delegation_id`, and *schema-valid*
`DelegationRecord`-shaped objects. **Schema-valid ≠ trusted-issued** (T-20):
the store never accepts a record as input; it only accepts a
`DelegationRequest` from a trusted caller and builds the record itself.

**Who may call `issue()`:** for root edges only the trusted non-agent owner
layer; for child edges only the control plane on behalf of an agent that is
the parent edge's delegate, with the parent edge effective and redelegable.
There is **no `AgentDefinition.delegate()`** and no agent-side API (T-01, §67).
The owner issues **root edges only**. The owner never needs to sit inside an
agent lineage, and a mid-chain owner edge would give one chain two roots.

**Issuance-time temporal bounds** (trusted `now`): `now < scope.expires_at ≤
parent.expires_at` (or `≤ now + SYSTEM_MAX_TTL` for a root). A record that is
already expired when issued is rejected, not stored.

**v0.2.4 / B-11 lessons, made requirements:** exact-type acceptance;
revalidation into store-owned snapshots; subclass, `model_construct` and
`model_copy(update=…)` records never admitted (T-27/T-28); security fields use
only `frozenset`/`tuple`/enums/scalars — no dicts or lists — and the contract
tests must include the full in-place mutation matrix (`|=`, `*=`, nested) and
hash/provenance stability (T-29, PO-14).

**v0.2.3 lessons:** every enum match is exhaustive with an explicit
fail-closed default (no `else: treat_as_P4`); the evaluation records the
system policy version it applied; hard constraints (lineage validity) are
checked before anything else; nothing — fallback, retry, replan — can weaken
a constraint.

---

## 7. Lineage

- An action names **exactly one leaf `delegation_id`** (CR-01 adds the field
  to Action and to the approval hash). The lineage is the unique parent walk
  from that leaf to its `RootAuthorization`.
- **Checks at every hop:**
  - the record exists in the trusted store, has the exact type, and
    revalidates;
  - it is not revoked;
  - `t < expires_at`;
  - neither delegator nor delegate has a lifecycle event since `issued_at`
    (§12);
  - `delegate(i) == delegator(i+1)`, compared as `(kind, id)` pairs
    (continuity, T-42);
  - no `(kind, id)` principal repeats **and** no `delegation_id` repeats
    (cycle detection checks both, T-06);
  - depth is consistent;
  - `objective_ref` is identical;
  - `leq(scope(i+1), redelegable_scope(i))` **and**
    `leq(redelegable_scope(i), scope(i))`, re-checked at evaluation, not only
    at issuance [HR-16];
  - `parent.issued_at ≤ child.issued_at`, and the parent's store sequence is
    lower than the child's. A parent pointer that points "forward" means the
    store is corrupt (T-56).
- **Checks on the whole chain:**
  - total length ≤ system max depth;
  - the chain terminates at a RootAuthorization whose owner is the configured
    owner, whose event id is unique, and whose digest matches (HR-06).
- **Parent pointers are immutable and followed, never searched [HR-22].**
  `parent_delegation_id` is part of the immutable record, and the walk
  follows it exactly. The evaluator never searches for "some valid parent",
  never substitutes an edge, and never tries a second route.
  Diamond case: D holds D←B←A and D←C←A. These are two distinct leaf records,
  and the action names exactly one of them, so the result is deterministic.
  The audit records that leaf and its full lineage (T-51).
- **Leaf delegate must equal the requesting principal** (T-05, T-19).
- **Requester trust [HR-03].** The requesting principal is **never read from
  Action or ActionPlan content**. `Action.agent_type` (default `"execution"`)
  is plan content, not a principal (T-44).
  **Today's `requested_by` is not trustworthy enough either.** It is:
  - a bare `str`;
  - defaulted to `owner`, which itself defaults to `"system"`;
  - persisted **only** on the ApprovalRequest row, not on `ActionRecord` or
    `ActionPlanRecord`;
  - supplied again by **whoever calls the orchestrator next**, so a resume or
    recovery can substitute a different requester for the same Action
    (T-46);
  - absent from `action_hash`.

  Requirements:
  1. The requester is a typed `PrincipalRef`, **bound once at Action
     creation** (insert-once, CR-01).
  2. Every later evaluation, resume, recovery and C′ check reads the
     requester **from that durable binding**, never from the current caller.
     If a caller supplies a requester that differs from the binding, the
     check fails `REQUESTER_UNBOUND`.
  3. **There is no default requester.** `"system"`, `owner` or an empty value
     holds no delegation, so the result is `NO_EFFECTIVE_DELEGATION`.
  4. **A future trusted principal context** (an authenticated invocation
     identity) is required. v0.2.5 does not have one. Until it exists, trust
     in the requester is trust in the calling code path, and no model, plan
     or tool output may reach that argument.

  The leaf `delegation_id` may come from content: it is only a lookup key,
  and an id that belongs to someone else fails `DELEGATE_MISMATCH`.
- Any failure ⇒ `LINEAGE_INVALID` / specific code; the evaluator never
  searches for "another lineage that works" (that would be a union).
- Record-level cycles are impossible by construction (a parent must exist
  before a child is issued; ids are store-generated); the evaluator still
  carries a visited set and a max-length bound so a tampered store cannot
  loop it (PO-13). Max depth is **not** relied on to hide cycles.

## 8. Multiple delegations, union, split

An agent may hold many delegations. Each action selects one; **no composition
is ever permitted in v0.2.5** (simplest fail-closed model; constitution
`cross_delegation_union_allowed=false`). Split-and-recombine (T-12) is made
**attributable**: both halves share the root and objective in their lineages.
**v0.2.5 cannot detect that two individually-permitted effects recombine a
denied intent** — that requires action-intent semantics owned by future
orchestration (v0.2.8) and a durable denial store. This is stated, not
overclaimed.

## 9. Redelegation and depth

Acting within scope never implies redelegating it. Redelegation requires an
explicit `RedelegationPolicy`; the child's `scope ≤ parent.redelegable_scope`,
the child's own `redelegable_scope ≤ child.scope`, and `child.remaining_depth
≤ parent.remaining_depth − 1`. Nothing resets per generation. System policy
caps absolute depth.

**Depth semantics, machine-checkable [HR-14].**
- `depth` is the 1-based position of an edge in its chain. A root edge has
  `depth = 1`.
- `remaining_depth` is the number of **additional edges allowed below this
  edge** in any chain that passes through it.

| Edge's `redelegation` | Additional edges allowed below it | Example |
|---|---|---|
| `None` | 0 (the delegate may act but cannot delegate) | Owner→CEO with `None`: CEO cannot issue |
| `remaining_depth = 1` | Exactly 1. A child may be issued, and the child's `redelegation` **must be `None`** | Owner→CEO(1)→CTO: CTO cannot issue |
| `remaining_depth = 2` | 2. The child's `remaining_depth` must be ≤ 1 | Owner→CEO(2)→CTO(1)→Dev: Dev cannot issue |
| `remaining_depth = 0` | Not representable (validation error). Use `None` | — |

Issuance checks, all re-checked by the evaluator:
- `child.redelegation is None` or `child.remaining_depth ≤
  parent.remaining_depth − 1`;
- `child.depth = parent.depth + 1`;
- `child.depth + (child.remaining_depth or 0) ≤ SYSTEM_MAX_DEPTH`.

## 10. Lifecycle, expiration, time

- **Stored:** immutable `DelegationRecord`s and `RevocationRecord`s,
  append-only. **Computed at time t:** `EFFECTIVE` or `NOT_EFFECTIVE(reason)`.
  No mutable status, no `ACTIVE/SUPERSEDED` flags, no state that implies
  execution. Changing authority = revoke + issue new (history preserved).
- **Historical vs effective:** records remain forever for audit; effectiveness
  is always recomputed.
- **Expiration:** `expires_at` required, bounded by max TTL; `t ≥ expires_at`
  ⇒ `DELEGATION_EXPIRED` (boundary is expired). No renewal in place.
- **Trusted time:** a Jarvis-side injected clock snapshot (the existing
  `clock()` pattern); model-supplied or request-supplied timestamps are never
  consulted; no clock ⇒ `CLOCK_UNTRUSTED` (fail closed). Skew tolerance: none
  in v0.2.5.
- **Timestamps [HR-15].**
  - Timestamps must be timezone-aware and are normalized to UTC. Naive
    datetimes are rejected at every boundary.
  - Comparison is by UTC instant.
  - Issuance requires `now < expires_at ≤ parent.expires_at`. For a root it
    requires `expires_at ≤ now + max_ttl`.
  - An expiry equal to the parent's is allowed. A child issued just before
    its parent expires is allowed, but can never outlive the parent.
  - When `now == expires_at`, the edge is expired.
- **Clock rollback [HR-15].** The store keeps a monotonic high-water mark:
  the latest trusted time it has recorded from issuance, revocation or
  evaluation events. Any evaluation or issuance whose `now` is below the mark
  fails `CLOCK_UNTRUSTED`, so a rollback cannot revive an expired edge
  (T-55). A forward jump only expires edges early, which is safe.
- **One-shot delegations: not in v0.2.5.** Single-use is already the
  semantics of an *approval* (consumed once); adding one-shot delegation
  would blur delegation and approval and require consumption state. A
  narrow scope + short TTL covers the use case.
- **Replay:** a delegation is reusable within scope until expiry/revocation;
  replaying a revoked/expired id restores nothing (ids never reused, no status
  to replay).

## 11. Revocation

- **Who:** HUMAN_OWNER (any edge); the edge's delegator; any ancestor
  delegator in that lineage; the delegate may renounce its own edge (only
  ever reduces). A child can never revoke an ancestor edge.
- **What:** whole edges only. There is no API to remove a dimension or a
  constraint, and scopes contain no negative constraints to remove — the
  "revoke deny-publish" attack (T-33) has no surface.
- **Effect:** immediate at commit; irreversible; idempotent (first record
  wins). All descendants become `NOT_EFFECTIVE (UPSTREAM_INEFFECTIVE)`;
  records are retained; descendants are **never re-parented** to a
  grandparent (R-03).
- **Unambiguous answers [HR-18]:**
  - **Duplicate revocations.** At most one *effective* RevocationRecord exists
    per `delegation_id`. Later attempts are idempotent no-ops, audited as
    `DUPLICATE_REVOCATION`.
  - **Conflicting revocations** cannot exist, because revocation has only one
    meaning.
  - **No un-revoke.** A revocation cannot itself be revoked. Re-granting
    means a new issuance.
  - **Reason code.** `reason_code` is required and comes from a closed enum,
    but it is **non-security**: it never changes the effect.
  - **Revoker authorization.** Checked separately from delegation authority.
    The allowed revokers are:
    - the owner;
    - the edge's delegator;
    - an ancestor delegator in *that* lineage;
    - the delegate, renouncing its own edge.
  - **Descendants.** An upstream revocation invalidates descendants **at
    evaluation**, without rewriting any record.
  - **IDs.** `revocation_id` is store-generated and never reused.
- **Why revocation can never widen authority:** effective authority is a meet
  over one lineage; revocation only removes edges; removing an edge can only
  make lineages invalid, never enlarge a meet.

## 12. Disabled / retired identities

**Final rule [HR-04]** (the options compared are below):

> An edge is effective at time `t` only if both of these hold for its
> delegator (when that is an agent) **and** its delegate:
> 1. the agent is currently enabled;
> 2. **no** lifecycle event (DISABLED or RETIRED) for that agent has a
>    timestamp in `[issued_at, t]`.
>
> **Re-enabling never restores an edge.** The delegator (or the owner, for a
> root) must issue a new one. Descendants of a non-effective edge are
> non-effective by the cascade.

| Option | Behavior | Verdict |
|---|---|---|
| A. Dynamic suspension: the evaluator reads only the current `enabled` flag | Disable followed by re-enable silently **resurrects** old delegations, even ones issued long ago to an identity that has since been compromised | **Rejected**: stale-authority resurrection (T-47). This was what the earlier draft actually did whenever CR-04's atomic revocation was missing. |
| B. Disable permanently invalidates, computed from lifecycle history | Any lifecycle event after issuance ends the edge for good. No cross-system write is needed. | **Selected.** Computed, crash-safe, and consistent with DI-07. |
| C. Explicit re-authorization | Required after B | **Selected as the recovery path** (re-issuance) |

Consequence: if CEO is disabled for five minutes, CTO loses its authority and
does **not** get it back when CEO is re-enabled. This availability cost is
intentional.

| Case | Behavior |
|---|---|
| Issue to a disabled delegate | Fail closed (`DELEGATE_INACTIVE`). Pre-issuing to an ineligible identity has no audit value. |
| Delegate disabled after issuance | The edge is permanently non-effective (`PRINCIPAL_LIFECYCLE_EVENT`). Re-enabling does not restore it. |
| Delegator disabled after issuance | Its edges and all their descendants are permanently non-effective. |
| Retired or removed identity | The records remain as history but are never effective. |

**Revocation is not disabling [HR-04].**
- *Revocation* is a permanent fact of delegation history about one edge. It
  lives in the delegation store.
- *Disabling* is a fact of identity lifecycle. It will be written by a future
  identity-lifecycle system.
- A disable makes the affected edges non-effective **by computation**. It
  writes no RevocationRecords, though it may emit an informational audit
  event.

**Dependency.** The rule needs a **durable, append-only history of agent
lifecycle events** (CR-04). v0.2.4 cannot disable an agent after
registration, so today the rule is trivially satisfied.
**Integration precondition:** no agent-lifecycle mechanism may be deployed
alongside delegation unless it records timestamped, append-only lifecycle
events. A mutable `enabled` flag alone is not enough.

## 13. Objective binding

Delegations bind to a durable `objective_id`, never to objective text; the
evaluator compares ids only (T-13).

**Trust and mutation [HR-10].**
- **Who creates ids.** Objective ids are created by the control plane or the
  owner, never chosen by a model. A syntactically valid id proves nothing:
  it must resolve in a future trusted objective store.
- **Versions.** Objective records must be **immutable per version**. Any
  material edit to text, scope or success criteria creates
  `objective_version + 1`. Delegations bind `ObjectiveRef(id, version)`, so
  editing an objective **never silently changes what an existing delegation
  authorizes**. Old delegations stay bound to the old version, and work on
  the new version needs re-issuance (T-54).
- **No sharing.** Two textual objectives never share an id and version.
- **Action binding.** The objective an action belongs to comes from the
  trusted plan linkage (the CR-01 binding), never from action content.
- **Dependency.** No objective store exists today. `ActionPlanRecord` has
  `decision_id` and `project_id`, but there is no objective entity. The store
  belongs to future orchestration (v0.2.8) and is an **integration
  precondition**. The v0.2.5 core does not build it. v0.2.5 does not create an objective
store; it requires that the id comes from trusted control-plane state (the
ActionPlan/Decision chain today) and is bound onto the Action by CR-01.
Rephrased objectives are different objectives only if a human issued a new
root for them — and that issuance flow must display prior denials (D-08).

## 14. Denial persistence

**Honest scope [HR-11].** v0.2.5 *itself* catches **no** denial laundering.
It supplies stable lineage keys. The only mechanical catch in the future is
an exact-payload match, and only after a DenialRecord store exists. The
v0.2.0 `denial_persistence_rules` covering reframing and splitting remain
**unmet** until a trusted action-intent identity exists. That identity must
not be an AI-judged "semantic equivalence" used as a security boundary.

v0.1.3 has no durable denial record. v0.2.5 contributes the **keys**: every
action's lineage yields `(root_delegation_id, objective_id)`, shared by every
descendant of a root. A future `DenialRecord(root_delegation_id,
objective_ref, action_hash, decided_by, decided_at)` checked in the pipeline
before approval-request creation would stop an **exact-payload** repeat under
redelegation, retry, a new agent, or a new model/provider. It would not stop
a reworded or modified payload [HR-11]. Rephrasing and split detection
require a trusted action-intent identity that v0.2.5 does not define.

| ID | Vector | Solvable with v0.2.5 lineage? | Notes |
|---|---|---|---|
| D-01 | denied -> rephrase | PARTIAL | Lineage gives the (root, objective) key; recognizing the same intent under new wording needs a trusted intent key owned by a future action-intent layer. v0.2.5 alone does NOT solve this. |
| D-02 | denied -> retry | EXACT-PAYLOAD ONLY; needs a future DenialRecord (not in v0.2.5) | The existing REJECTED Action is terminal. A *new* Action with a byte-identical payload has the same action_hash, so it would match a future DenialRecord keyed by (root, objective_ref, action_hash). Any payload change evades that [HR-11]. |
| D-03 | denied -> redelegate | EXACT-PAYLOAD ONLY; needs a future DenialRecord | Every descendant lineage shares the root delegation id, so the key is visible to all descendants. Matching is still by exact hash only. |
| D-04 | denied -> split | NO (attribution only) | Lineage attributes both halves to the same root/objective; detecting that halves recombine a denied intent is future orchestration policy. |
| D-05 | denied -> new agent | EXACT-PAYLOAD ONLY; needs a future DenialRecord | A new agent has no authority unless some root delegates to it. Under the same root, an identical payload matches. A different root needs human issuance, and that flow must show prior denials (a UX requirement, not an enforced check). A reworded payload evades it [HR-11]. |
| D-06 | denied -> new model | YES (structural) | Model identity never participates in authority or denial keys. |
| D-07 | denied -> new provider | YES (structural) | Provider identity never participates in authority or denial keys. |
| D-08 | denied -> new objective wrapper | PARTIAL | A new objective needs a human-issued root; the issuance flow must surface prior denials for the same intent key; automatic equivalence of objectives is future scope. |

## 15. Approval separation

- The delegation gate runs **after** `evaluate_permission` and **before**
  `create_approval_request`. An out-of-scope action is BLOCKed; **no approval
  request is ever created for it**, so no human click can turn an
  out-of-ceiling request into standing authority (T-09/T-10).
- Approving an in-scope P4 action authorizes **that action hash only**
  (existing engine). No store write happens on approval; the delegation is
  byte-identical afterwards (PO-07).
- If the owner wants an agent to do something outside its ceiling, the path
  is an explicit, separately audited **new delegation issued by the owner**
  (e.g. narrow action set, short TTL) — never a mutation of the old one.
- Delegation cannot manufacture approval: no approval-shaped field exists;
  CR-03 makes `decided_by` require a HUMAN_OWNER principal so a delegated
  helper's "approval" is rejected (T-43); CR-01 binds approval to requesting
  principal + leaf delegation, so B cannot consume A's approval (T-22).

## 16. P0–P5 integration and the future pipeline

```text
Action (with requesting_principal + leaf delegation_id: CR-01)
  → eligibility (existing)
  → evaluate_permission (existing; authoritative P-tier via CR-02)
  → [NEW] evaluate_effective_authority: required_tier ≤ ceiling
          ∧ action_type ∈ action_types ∧ objective matches ∧ lineage effective
          OUTSIDE_SCOPE / LINEAGE_INVALID → BLOCK (terminal, no approval request)
  → approval (existing, if REQUIRE_APPROVAL)
  → plan budget (existing)
  → durable executor: A,B,C (existing) → [NEW C′] re-resolve lineage with trusted
          clock + revocation watermark, recompute permission (CR-05)
          → E atomic claim (serialized with revocation writes) → F …
```

**Pipeline order compared [HR-25].**

| Option | Order | Assessment |
|---|---|---|
| A | identity → delegation → permission → approval | Delegation cannot know the required tier before classification, so it could only check "has *some* lineage". That pre-check is kept as a cheap early reject, but on its own it is insufficient. |
| B | identity → permission classification → delegation → approval | Correct for today's code. `evaluate_permission` is **pure classification plus an outcome**: it grants nothing and has no side effects. `apply_permission_decision` only records status, and no approval request exists before the gate. |
| C | classification split from authorization | B made explicit by CR-02, which exposes the tier as a classification. This is the long-term shape. |

**Selected: B now, C after CR-02.** The order is:
1. trusted requester binding;
2. `has_any_effective_lineage` pre-check;
3. `evaluate_permission` (classify);
4. delegation gate (`required ≤ effective`);
5. approval request, only if the gate passed.

An out-of-scope action never produces an ApprovalRequest row.

**Caller-supplied PermissionDecision [HR-08].** In the current code,
`execute_action_durably(action, decision)` runs its approval gate **only when
the caller-supplied `decision.outcome == REQUIRE_APPROVAL`**. A caller that
passes `ALLOW` for an external action skips approval today, and after
integration would also skip delegation. So C′ must:
1. run **before** gates A/B/C;
2. **recompute** `evaluate_permission(action, registry)` and the delegation
   evaluation from durable state (requester binding, leaf, trusted clock);
3. use the caller's `decision` **only** as a consistency check. Any mismatch
   in outcome, level or tier fails closed.

This is CR-05, and it is mandatory before integration.

The Permission Engine is **not** modified by delegation logic; it consumes
nothing from delegation. Delegation consumes the Permission Engine's output.
Interim (before CR-02): the exhaustive `required_tier = max(T_floor,
T_class)` mapping of §3.7, where every unlisted combination fails closed.
`EXTERNAL_ACTION/LOW` **is** reachable through tool configuration and maps
conservatively to P4 [HR-02]. (An earlier draft wrongly called it
unreachable.)

**Final authorization boundary (must be revalidated at C′):** agent active;
every lineage edge effective; lineage intact; not revoked; not expired at
trusted time; objective still bound; action type and tier within scope;
Permission Engine result; approval valid and unconsumed; budget.

**Caching:** none in v0.2.5. Any future cache must be keyed by the store's
revocation watermark and the trusted time snapshot.

## 17. Atomicity, concurrency, durability (future requirements)

| Operation | Must be atomic with | Invariant after crash |
|---|---|---|
| `issue` | parent-effectiveness read + record insert + audit event | No record without audit; no child of a revoked parent |
| `revoke` | revocation insert + audit event + watermark increment | Revocation either fully visible or absent |
| C′ + E | revocation-store read + execution claim | No execution claim after a committed revocation of any lineage edge |

Concurrency: simultaneous child issuances are independent (no shared budget
in v0.2.5); duplicate issuance produces two distinct records (ids are
store-generated; callers dedupe via idempotency keys if needed); revoke/issue
and revoke/execute serialize on the lineage. **Residual window:** a revocation
committed after claim E cannot retract an adapter effect already in flight.
Durable, atomic, idempotent and reconciled ≠ distributed exactly-once: no
multi-machine exactly-once guarantee is claimed. **Durability** needs a
durable AgentRegistry first (CR-04) so lineage references survive restarts;
no migration is created in this phase.

## 18. Security-target protection and self-modification

Delegation scopes cover action types, not repository targets. Modifying the
delegation system, Permission/Approval/Budget engines, contracts, validators,
frozen artifacts or migrations remains governed by the existing
`coding_agent_rules` (protected targets require a distinct human-gated
workflow). A future protected-target action class must be **non-delegable**
(DI-13) so "Developer edits evaluator → gains P5" (T-38) has no delegated
path; development authority ≠ deployment authority (SI-14).

## 19. Financial and AI budgets

No financial dimension in v0.2.5 and P5 is not issuable to agents, so a CFO
agent can never carry spending authority through delegation. Future budget
attenuation (`child ≤ parent remaining`, aggregate children ≤ parent) must use
the existing atomic reservation model **without** its "unconfigured =
unlimited" default. AI inference budgets (v0.2.7) are a separate system.

---

## 20. Invariants

| ID | Invariant |
|---|---|
| DI-01 | Delegation may preserve or reduce already-authorized scope; it never creates, amplifies, infers, recovers, combines or manufactures authority. |
| DI-02 | For every valid edge: scope(child) <= redelegable_scope(parent) in every dimension; for every chain: A0 >= A1 >= ... >= An. |
| DI-03 | The only authority roots are HUMAN_OWNER grants issued through the trusted non-agent layer; SYSTEM_POLICY is a ceiling every chain is intersected with, never a grantor. |
| DI-04 | Identity, title, role, display_name, metadata, provider, model and registration create zero authority. |
| DI-05 | A delegated ceiling is an upper bound, never a permission result; the Permission Engine still classifies every action. |
| DI-06 | Every consequential action names exactly one leaf delegation; its lineage is the only authority source considered; no union across lineages. |
| DI-07 | Delegation records are immutable and append-only; effective state is computed, never stored as mutable status. |
| DI-08 | Revocation removes whole edges only, is irreversible, and makes every descendant ineffective; descendants are never re-parented. |
| DI-09 | Delegation never carries, implies or widens approval; approval never mutates or widens a delegation. |
| DI-10 | Unknown, missing, ambiguous or unparseable security state fails closed; missing never means unlimited; there are no wildcards. |
| DI-11 | A delegation_id is a reference, never a bearer credential; trust comes only from the trusted store, never from field resemblance or schema validity. |
| DI-12 | Authority evaluation is deterministic for the same trusted records, system policy, registry state, objective, action requirements and trusted time snapshot. |
| DI-13 | Delegation cannot authorize modifying the delegation system, Permission/Approval/Budget engines, security contracts, validators, frozen artifacts or migrations as an ordinary change. |
| DI-14 | Future execution revalidates the complete lineage at the final authorization boundary with a trusted clock. |
| DI-15 | The authority algebra is closed with an explicit bottom ⊥ (zero authority). ⊥ is never issuable or storable and never means unrestricted. [HR-01] |
| DI-16 | The requesting principal is a typed PrincipalRef bound once, durably, when the Action is created. No later caller may substitute it, and no default requester holds authority. [HR-03] |
| DI-17 | Any lifecycle event of the delegator or delegate since issuance permanently ends an edge's effectiveness. Re-enabling never resurrects authority. [HR-04] |
| DI-18 | Authority is pinned to exact schema, action-vocabulary and objective versions. An absent or unknown dimension grants zero authority. [HR-05, HR-09, HR-10] |
| DI-19 | System policy is a typed ceiling that only narrows. It is never evaluable alone and never originates authority, and owner roots cannot override it. [HR-07] |

## 21. Hostile threat matrix

| ID | Attack | Precondition | Expected fail-closed behavior | Invariant | Enforcement owner | Test strategy |
|---|---|---|---|---|---|---|
| T-01 | Parent spoofing: agent claims 'my parent is jarvis.ceo' / reports_to=human.owner | Agent can emit arbitrary text/JSON | No lineage exists unless a trusted DelegationRecord chain resolves; claim is inert data (UNKNOWN_DELEGATION) | DI-11, PO-02 | delegation store + resolver (v0.2.5) | Feed claim through every public API; assert zero records and NO_EFFECTIVE_DELEGATION |
| T-02 | Role/title escalation: role=CEO/CFO/ROOT/OWNER/ADMIN | Registered agent with authority-sounding role | Zero authority; scope never derived from AgentDefinition fields | DI-04, PO-06 | v0.2.4 registry + v0.2.5 evaluator | Parametrized hostile roles; evaluation without delegation is NO_EFFECTIVE_DELEGATION |
| T-03 | Provider/model identity masquerade: provider_id or model_id equal to an agent_id or 'human.owner' | Provider/model registries contain colliding strings | No PrincipalRef is ever built from provider/model ids; namespaces distinct | DI-04, PO-10 | v0.2.5 contracts | Namespace-collision fixtures across ProviderRegistry/AgentRegistry/store |
| T-04 | Self-delegation A->A | Agent holds a redelegable scope | Issuance rejected (SELF_DELEGATION); evaluator also rejects tampered record | PO-13 | store + evaluator (v0.2.5) | Issue and tamper fixtures |
| T-05 | Sibling authority theft: Developer uses Finance's delegation (same parent) | Two children of one parent | Leaf delegate must equal requesting agent; siblings share no authority | DI-06 | evaluator (v0.2.5); orchestrator binding (integration) | Evaluate Finance's delegation_id as Developer -> DELEGATE_MISMATCH |
| T-06 | Cyclic delegation A->B->C->A | Redelegation permitted | Issuance rejects any delegate already present in the lineage (PRINCIPAL_CYCLE); record-level cycles impossible (append-only, parent must pre-exist); evaluator visited-set check | PO-13 | store + evaluator | Principal-cycle and tampered record-cycle fixtures |
| T-07 | Depth bypass by chaining further than allowed | remaining_depth=0 at a hop | Issuance rejected (DEPTH_EXCEEDED); child remaining_depth <= parent - 1 | DI-02 | store (v0.2.5) | Property test over random chains |
| T-08 | Redelegation without permission | Parent granted scope but redelegation=None | Issuance rejected (REDELEGATION_FORBIDDEN); acting scope never implies redelegable scope | DI-02 | store | Issue child from non-redelegable edge |
| T-09 | P3 -> P4 escalation | Leaf ceiling P3; action classified P4 | CEILING_EXCEEDED before any approval request is created; pipeline BLOCKs | DI-05, PO-01 | evaluator + integration gate | external_modify vs publish/send/delete fixtures |
| T-10 | P3 -> P5 escalation | Leaf ceiling P3; financial/install/privileged action | CEILING_EXCEEDED; P5 is not issuable to agents in v0.2.5 at all | DI-05 | store + evaluator | Issue P5 to agent -> rejected; evaluate P5 action -> CEILING_EXCEEDED |
| T-11 | Multiple-delegation union: X from A and Y from B combined | Agent holds two effective delegations | Each action names exactly one leaf; evaluation never consults a second lineage | DI-06 | evaluator + Action binding (CR-01) | Action needing X+Y under either lineage alone -> OUTSIDE_SCOPE |
| T-12 | Split-and-recombine: denied X+Y decomposed into child X and child Y | Parent can issue to two children | v0.2.5 makes it ATTRIBUTABLE (shared root/objective lineage); DETECTION of emergent composition is future action-intent/orchestration policy | DI-06, SI-21 | v0.2.8 orchestration + future intent layer (partial v0.2.5) | Lineage attribution test; composition detection explicitly out of v0.2.5 scope |
| T-13 | Objective switching: delegation for Objective A used for Objective B | Delegation bound to objective_id A | OBJECTIVE_MISMATCH; objective compared by durable id, never by text | DI-06 | evaluator + Action binding (CR-01) | Mismatched objective_id fixtures |
| T-14 | Tenant/business switching via namespace string | agent_id business.alpha.* acting for beta | No authority from strings; tenancy is a future explicit scope dimension added by schema version (old records then fail closed) | DI-10 | future tenancy phase; v0.2.5 schema versioning | Namespace-prefix fixtures grant nothing; unknown schema_version fails closed |
| T-15 | Disabled delegate | Delegate enabled=False | Issuance fails (DELEGATE_INACTIVE); evaluation also checks current enabled state | PO-05 | store + evaluator | Issue to disabled agent; disable after issue (future lifecycle) |
| T-16 | Disabled delegator | Delegator disabled after issuing | Its edges and all descendants become permanently NOT_EFFECTIVE (PRINCIPAL_LIFECYCLE_EVENT); re-enabling never restores them (lifecycle-history rule, HR-04) | PO-04 | evaluator + future agent lifecycle | Cascade fixtures |
| T-17 | Revoked delegation replay | Old delegation_id reused after revocation | REVOKED is permanent; ids never reused; replay yields NOT_EFFECTIVE | DI-08, DI-11 | store + evaluator | Revoke then evaluate; attempt re-issue with same id |
| T-18 | Expired delegation replay | Delegation past expires_at | EXPIRED at trusted clock; no renewal in place | DI-14 | evaluator | Frozen-clock boundary tests (== expires_at is expired) |
| T-19 | Forged delegation_id | Attacker guesses/knows an id | Id is a lookup key only; leaf delegate must equal requester; unknown id -> UNKNOWN_DELEGATION | DI-11 | evaluator | Random/known-foreign id fixtures |
| T-20 | Copied JSON delegation | Valid record serialized and re-submitted | Schema-valid != trusted-issued; store accepts only issue() inputs, never records | DI-11 | store | Round-trip JSON into every API -> rejected |
| T-21 | Model-generated delegation | Provider output contains delegator/delegate/permission | Untrusted data; no parsing path to the store | DI-11, SI-07 | store | ProviderResponse structured_output fixtures |
| T-22 | Approval laundering: A's approval for X used by B for Y | A holds APPROVED request for Action X | Existing binding already rejects Y (action_id + action_hash); CR-01 additionally binds requesting principal + delegation_id so B cannot consume A's approval even for identical X | DI-09 | approval engine (existing) + CR-01 | Cross-agent consumption fixtures after CR-01 |
| T-23 | Denial laundering | Action denied for agent A | See denial sub-matrix; v0.2.5 supplies lineage keys, not semantic matching | SI-21, PO-09 | future DenialRecord (approval/orchestration layer) using v0.2.5 lineage | Sub-matrix D-01..D-08 |
| T-24 | Provider fallback resets authority | Router falls back to another model | Authority references no provider/model; unchanged | PO-10, SI-11 | v0.2.5 contracts (structural) | Evaluate before/after routing change |
| T-25 | Agent model change resets authority | Agent's preferred model changes | Delegation binds agent_id only | PO-10 | v0.2.5 contracts | Structural + evaluation equality |
| T-26 | Metadata authority smuggling | Record carries notes/metadata | DelegationRecord has NO metadata; AuthorityScope is closed; free text impossible | DI-10 | contracts | extra=forbid fixtures incl. notes='P5 approved' |
| T-27 | Subclass smuggling (v0.2.4 B-01 class) | Subclass loosens extra/frozen, adds permission=P5 | Store/evaluator accept exact types only and revalidate into store-owned snapshots | PO-14 | store | Subclass fixtures per contract type |
| T-28 | model_construct / model_copy(update=) bypass | In-process caller builds unvalidated record | Store never accepts records; issue() builds records itself from validated requests; evaluator revalidates | PO-14 | store + evaluator | Bypass fixtures |
| T-29 | Mutable nested authority (B-11 class) | Scope contains mutable containers | Scopes use frozenset/tuple/enums only; no dict/list in security fields | PO-14 | contracts | Mutation matrix incl. \|=, *=, nested |
| T-30 | Unknown authority dimension | Record/schema from newer version or tampered | extra=forbid + schema_version whitelist -> UNKNOWN_AUTHORITY_DIMENSION | DI-10 | contracts + evaluator | Tampered dimension fixtures |
| T-31 | None / empty / missing confusion | Optional or empty fields | Every scope field required; empty action set = nothing; redelegation None = forbidden; no field means 'unlimited' | DI-10 | contracts | Explicit semantics table tests |
| T-32 | Wildcard escalation ('*', 'ALL', 'ANY', 'UNLIMITED') | String vocabularies | No wildcard exists; values validated against closed vocabularies | DI-10 | contracts | Wildcard strings rejected at issuance |
| T-33 | Constraint-removal escalation (revoke 'deny publish', keep grant) | Scope with negative constraints | Scopes are positive allowlists only; revocation is whole-edge; nothing to remove | DI-08 | contracts + store | No revoke-dimension API exists (structural) |
| T-34 | Revocation race (evaluate -> revoke -> execute) | Concurrent revocation | Final-boundary revalidation (C') inside the executor, serialized with revocation writes; residual in-flight window documented | DI-14 | integration (durable executor, separately authorized) | Deterministic interleaving tests in integration stage |
| T-35 | Stale cache of effective authority | Future caching layer | No caching in v0.2.5; any future cache keyed by revocation watermark + trusted time | DI-14 | future | Design requirement only |
| T-36 | New agent implicit inheritance ('cto.helper') | Agent registers a helper | Zero effective delegations until trusted issuance | PO-11 | store + evaluator | Register helper -> NO_EFFECTIVE_DELEGATION |
| T-37 | Same-role implicit inheritance | Two agents share role/display_name | Authority binds to agent_id + lineage only | PO-11, DI-04 | evaluator | Clone fixtures |
| T-38 | Security-engine self-modification (Developer edits evaluator to gain P5) | Coding agent with repository write | Protected targets not delegable as ordinary change; human-gated workflow (existing coding_agent_rules) | DI-13, SI-14, SI-16 | future protected-target policy + existing coding_agent_rules | Design requirement; protected-target action class in integration stage |
| T-39 | Financial-budget conflation (AI budget or CFO title implies spending) | Agent has model budget or CFO role | No financial dimension in v0.2.5; P5 not issuable to agents; business spend stays with Permission+Approval+Budget | SI-12 | future business-spend design | Structural absence tests |
| T-40 | AI-budget conflation (delegated ceiling implies model budget or vice versa) | Future v0.2.7 budgets | Delegation scope contains no inference budget; v0.2.7 budgets are separate and absence != unlimited there | SI-12 | v0.2.7 | Structural absence tests |
| T-41 | Principal-kind confusion: agent registered with agent_id 'human.owner' | v0.2.4 charset permits the string | PrincipalRef kind is part of identity; AGENT:'human.owner' is never HUMAN_OWNER | DI-03 | contracts | Collision fixture |
| T-42 | Chain discontinuity: edge i delegate != edge i+1 delegator | Tampered or mis-issued records | LINEAGE_INVALID; issuance requires delegator == parent.delegate | PO-13 | store + evaluator | Tamper fixtures |
| T-43 | AI 'approval' via delegated helper (self-approval through delegation) | Agent delegates to a controlled helper, treats helper output as approval | Approval requires a HUMAN_OWNER decided_by (CR-03); delegation has no approval semantics | DI-09, SI-13 | approval engine (CR-03) | decide_approval with AGENT principal rejected after CR-03 |
| T-45 | Algebra-bottom confusion: the meet of disjoint action sets or different objectives is treated as 'no restriction', or as undefined and then skipped | Two scopes in a lineage, or a scope against the ceiling | Meet is total; the result ⊥ → OUTSIDE_SCOPE (EMPTY_AUTHORITY) | DI-15, PO-15 | scope algebra (v0.2.5.1) | Property tests over disjoint and different-objective pairs |
| T-46 | Requester substitution on resume or recovery: a plan created for agent A is resumed by a caller passing requested_by=B | Today requested_by is supplied again on each call and is not persisted on the Action or Plan | The requester is read only from the insert-once binding; a mismatch → REQUESTER_UNBOUND | DI-16, PO-16 | integration (CR-01) + evaluator | Resume with a different requester; crash-recovery replay |
| T-47 | Disable/re-enable resurrection | The evaluator reads only the current enabled flag | Lifecycle-history rule: any event since issued_at ends effectiveness permanently | DI-17, PO-17 | evaluator + future lifecycle history (CR-04) | Disable then enable at each hop |
| T-48 | Old-schema new-dimension escalation: a v1 record is read as 'all tenants/resources/data classes' after v2 adds a dimension | Schema upgrade | Exact-version evaluation; an absent dimension grants zero; re-issuance required | DI-18, PO-18 | contracts + evaluator | v1-under-v2 fixtures |
| T-49 | Root-record forgery or owner-event replay: one owner authorization event is reused to mint several roots, or a root row is inserted with a copied event id | DB write access or a buggy caller | owner_authorization_event_id is unique across roots; root_request_digest is recomputed; issue_root is reachable only via the owner channel; DB integrity is a stated trust assumption | DI-03, PO-02 | store + owner channel | Duplicate event id; digest mismatch; call to issue_root from an agent path |
| T-50 | System-policy-as-grant bug: an empty lineage is evaluated as if it were the system ceiling | Permissive ceiling, no delegation | No lineage ⇒ ⊥; the ceiling has no objective or expiry and cannot be evaluated alone | DI-19, PO-19 | evaluator | Empty-store evaluation |
| T-51 | Diamond lineage union: D holds edges from both B and C (both from A), and the evaluator unions them or picks the best | Diamond graph | One named leaf; the walk follows immutable parents; no search; the audit records the chosen leaf | DI-06 | evaluator | Diamond fixtures asserting the second edge is never read |
| T-52 | Action vocabulary evolution: re-tiering or changing the meaning of an action_type string widens old delegations | Vocabulary change | vocabulary_version is pinned; any change bumps it; old scopes fail closed | DI-18 | contracts + CR-02 | Vocabulary-bump fixtures |
| T-53 | A caller-supplied PermissionDecision(ALLOW) bypasses approval and delegation at the executor | Direct caller of execute_action_durably | C′ recomputes permission and delegation before the gates; the caller's decision is only a consistency check | DI-14 | durable executor (CR-05) | Supplied ALLOW for an external action → fails |
| T-54 | Objective mutation under the same id: objective text or scope is edited after delegation | Mutable objective record | ObjectiveRef(id, version); edits create a new version; old delegations stay bound to the old version | DI-18 | future objective store (v0.2.8) + evaluator | Edit-objective fixtures |
| T-55 | Clock rollback revives an expired delegation | The trusted clock goes backwards | Monotonic high-water mark; now below the mark → CLOCK_UNTRUSTED | DI-14 | store + evaluator | Rollback fixtures |
| T-56 | Chain switching or a forward parent pointer: a tampered child points to a different or later-issued parent | Store tampering | The immutable parent pointer is followed exactly; parent.issued_at ≤ child.issued_at and sequence order are checked; no parent search | PO-13 | evaluator | Tamper fixtures |
| T-57 | Tier under-classification: an action that is conceptually P4 compares as P3 through the (level, risk) mapping | P3 and P4 share EXTERNAL_ACTION | required_tier = max(T_floor, T_class); P3 only for EXTERNAL_ACTION ∧ MEDIUM; LOW/HIGH/CRITICAL → P4. Residual: a tool that mis-declares its risk | DI-05 | evaluator mapping, then Permission Engine (CR-02) | Exhaustive table test over action_type × tool level × tool risk |
| T-44 | Requester self-assertion: Action/plan content names the requesting agent (e.g. agent_type='finance') so a foreign leaf delegation passes the delegate==requester check | Action/ActionPlan fields are model-influenced content | Requesting principal comes only from the control-plane invocation context (like today's requested_by); no content field is ever read as a principal | DI-04, DI-06, DI-11 | integration (CR-01) + evaluator signature | Evaluator takes requester as a separate trusted argument; fixtures where Action content names another agent -> DELEGATE_MISMATCH |

## 22. Revocation threat matrix

| ID | Threat | Design response |
|---|---|---|
| R-01 | Unauthorized revoker | Revoker must be HUMAN_OWNER, the edge's delegator, or an ancestor delegator in the lineage; otherwise REVOKER_NOT_AUTHORIZED. |
| R-02 | Child revokes parent constraint | Children are not ancestors of their parent edge; and scopes have no separable constraints to revoke (whole-edge only). |
| R-03 | Revocation restores authority accidentally | Revocation only ever removes edges; effective authority is a meet along one lineage; descendants are never re-parented; removing an edge can never enlarge any lineage's meet. |
| R-04 | Descendant survives invalid upstream | Effective state of an edge requires every ancestor edge effective (UPSTREAM_INEFFECTIVE). |
| R-05 | Stale revocation cache | No cache in v0.2.5; future caches must be invalidated by the revocation watermark. |
| R-06 | Replay of pre-revocation record | Revocation keyed by delegation_id is permanent; ids never reused; records carry no status to replay. |
| R-07 | Duplicate revocation | Idempotent: first RevocationRecord wins; later attempts are recorded as no-ops and never alter revoked_at. |
| R-08 | Revoke/issue race | Issuance of a child and revocation of its parent serialize on the parent edge; if revocation commits first, issuance fails UPSTREAM_INEFFECTIVE; if issuance commits first, the child is immediately ineffective by cascade. |
| R-09 | Revoke/evaluate race | Evaluation reads a consistent snapshot (records + revocations + watermark); result carries the watermark it used; final boundary re-evaluates. |
| R-10 | Revoke/execute race | Final-boundary check (C') and execution claim (E) occur in one serialized transaction with the revocation read; revocation after claim cannot retract an in-flight adapter effect (documented residual window). |

## 23. Security proof obligations

| ID | Obligation | Test strategy |
|---|---|---|
| PO-01 | No delegation increases any authority dimension. | Property test: for random parent scope P and random request R, attenuate(P, R) either raises or returns C with leq(C, P) true in every dimension. |
| PO-02 | Every effective delegation has a valid trusted HUMAN_OWNER root. | Resolver test: lineage walk terminates at a RootAuthorization issued by the configured owner principal; any other terminal fails closed. |
| PO-03 | Every child delegation is bounded by its complete ancestor chain, recomputed at evaluation, not trusted from issuance. | Store-tamper test: a record injected past issuance validation with scope wider than its parent's redelegable_scope is REJECTED (LINEAGE_INVALID) by the evaluator's per-hop leq check, never silently clipped (check-not-clip applies at evaluation too). |
| PO-04 | Revoked or expired upstream authority invalidates dependent effective authority. | Multi-hop test: revoke/expire each edge of A->B->C->D in turn; every descendant becomes NOT_EFFECTIVE with UPSTREAM_INEFFECTIVE. |
| PO-05 | Unknown state fails closed. | Exhaustive enum tests; unknown schema_version/dimension/status/principal kind; missing parent; corrupt lineage. |
| PO-06 | Identity/title/provider/model/metadata cannot create authority. | Structural tests: no scope field reads AgentDefinition role/display_name/metadata/provider preferences; hostile titles produce empty authority. |
| PO-07 | Approval cannot mutate standing delegation. | Approve an action, then evaluate a second identical-tier action: ceiling unchanged; no store write occurs on approval. |
| PO-08 | Delegation cannot manufacture approval. | Structural: DelegationRecord/AuthorityScope have no approval-shaped field; an approval-gated action within ceiling still requires REQUIRE_APPROVAL flow. |
| PO-09 | The lineage keys (root_delegation_id, objective_ref) are identical for every descendant, so a future exact-payload DenialRecord is visible across redelegation. (Downgraded [HR-11]: v0.2.5 does not itself stop a denied intent being requested again.) | Every descendant lineage yields the same root/objective key; an exact-hash denial fixture matches from any descendant; a reworded payload is asserted as a documented NON-catch. |
| PO-10 | Changing provider/model cannot change delegated authority. | Structural: no provider/model field participates in scope or evaluation; evaluation is identical across model swaps. |
| PO-11 | A new agent identity begins with no inherited delegation. | Register a clone (same role/display_name/preferences): zero effective delegations. |
| PO-12 | Authority evaluation is deterministic for the same trusted inputs. | Evaluate twice with identical snapshot/clock: byte-identical AuthorityEvaluation; permuted store insertion order gives identical result. |
| PO-13 | Every chain is principal-acyclic and continuous: delegate(edge i) == delegator(edge i+1), no principal repeats, self-delegation impossible. | Cycle and discontinuity fixtures at issuance and evaluation (store-tamper). |
| PO-15 | The algebra is closed: meet is total on AuthorityScope ∪ {⊥}; ⊥ is never issued, never stored, and never treated as unrestricted. [HR-01] | Property tests: meet is commutative, associative and idempotent over random scopes, including disjoint sets and differing objectives; meet ≤ both inputs; ⊥ is absorbing; issuance that normalizes to ⊥ is rejected. |
| PO-16 | The requester is bound once at Action creation and every later check reads that binding; no default requester holds authority. [HR-03] | Resume or recovery by a caller with a different requester → REQUESTER_UNBOUND; a 'system' or empty requester → NO_EFFECTIVE_DELEGATION. |
| PO-17 | An edge is effective only if neither delegator nor delegate has had a lifecycle event since issuance; re-enabling never restores it. [HR-04] | Disable then re-enable at every hop of a 10-hop chain → all descendants stay non-effective. |
| PO-18 | Version pinning: a record with a different schema_version, vocabulary_version or objective_version grants no authority, and an absent dimension grants zero. [HR-05, HR-09, HR-10] | v1 record under a v2 evaluator → UNKNOWN_AUTHORITY_DIMENSION; vocabulary bump → VERSION_MISMATCH; objective edit → OBJECTIVE_MISMATCH. |
| PO-19 | System policy only narrows: no lineage ⇒ ⊥ whatever the ceiling; a root above the ceiling is rejected; tightening the ceiling lowers the effective scope. [HR-07] | Empty-store evaluation with a permissive ceiling → ⊥; owner P4 root under a P2 ceiling → rejected; tightening after issuance → effective P2. |
| PO-14 | Security-critical records are deeply immutable through all ordinary mutation APIs (B-11) and admitted only as exact-type, revalidated, store-owned snapshots (v0.2.4 B-01). | Mutation matrix incl. \|= and *=; subclass/model_construct/model_copy smuggling fixtures. |

## 24. Constitutional compatibility

No existing constitutional rule is silently superseded. The one naming
refinement (generalizing `parent_agent_id`/`child_agent_id` to principals with
an explicit root) is recorded here for human review.

**[HR-13]** The "Resolution" column below is superseded for *classification*
purposes by Part II §O. That section labels every rule as compatible
interpretation, strengthening, explicit refinement requiring authorization,
or conflict, and it names two pre-existing conflicts (approval binding to
the requesting agent; denial persistence) that block integration.

| Existing invariant | v0.2.5 interpretation | Mechanism | Potential conflict | Resolution |
|---|---|---|---|---|
| central_authority chain human_owner -> jarvis_control_plane -> agents | Only HUMAN_OWNER roots grants; control plane issues/evaluates | RootAuthorization + trusted store | None | Adopted |
| trust_boundaries: agents = delegated_responsibility_only | Agents hold only lineage-bounded scopes | Evaluator | None | Adopted |
| delegation_rules.fields (parent_agent_id, child_agent_id, ...) | Generalized to delegator/delegate PrincipalRef + explicit root | PrincipalRef, parent union | parent_agent_id cannot express a human root without None | Supersede field NAMES by reviewed design; semantics preserved; recorded as explicit refinement, not silent |
| delegation_rules.fields budget_ceiling, context_scope, memory_scope, allowed_outputs | Deferred dimensions | Schema versioning | v0.2.0 lists them as delegation fields | Deferred to v0.2.6/v0.2.7/v0.2.8; absent dimensions are not 'unlimited' because their owning systems enforce independently |
| delegation_rules.fields status, created_at | `status` becomes computed effectiveness; `created_at` becomes store-set `issued_at` | Append-only records + RevocationRecord | v0.2.0 lists `status` as a record field. A mutable stored status can be replayed or rewritten. | Explicit refinement for human review: status is computed at trusted time, never stored (DI-07). |
| delegation_rules.fields task_scope, allowed_capability_requests | `task_scope` maps to `objective_id` (durable id); `allowed_capability_requests` maps to `action_types` over the Permission Engine vocabulary | AuthorityScope | Free-text task scope can't be machine-verified | Refined into closed, machine-checkable dimensions; free-text task description is not an authority field |
| authority_rules.effective_authority_is_intersection_of: system_policy, owner_policy, objective_authority, requesting_agent_authority, delegation_authority, child_agent_ceiling, tool_policy, permission_tier, applicable_budget | system_policy + owner_policy become the SYSTEM_POLICY ceiling and the owner-issued root scope; objective, requester and delegation map to the lineage meet; child_agent_ceiling has no v0.2.5 per-agent field (a lineage scope is the ceiling); tool_policy, permission_tier and budget stay with ToolRegistry/Permission Engine/Budget as separate sequential gates | Meet over lineage + pipeline ordering | Could be read as one monolithic intersection computed in one place | Resolved: each term is enforced by its owning system; delegation computes only its own terms, and every gate can only narrow (no God engine, §27) |
| delegation_rules.invariant child_authority <= parent_effective_authority | child <= parent redelegable_scope <= parent scope | leq + meet | Stricter than v0.2.0 wording | Compatible (strengthening) |
| authority_rules.effective_authority_is_intersection_of [..., applicable_approval_state] | Approval state is consumed at the final boundary as a separate gate, not folded into delegated scope | Pipeline ordering | Could be read as approval widening scope | Resolved: intersection can only narrow; approval is an additional required condition, never a scope term |
| authority_rules.single_delegation_lineage_per_action | Exactly one leaf delegation per action | Action binding (CR-01) | Action has no field for it today | CR-01 (separately authorized, needs migration) |
| authority_rules.cross_delegation_union_allowed=false | No joins defined anywhere | Meet-only algebra | None | Adopted |
| authority_rules.no_authority_laundering (retry/replan/fallback/recovery) | Authority depends only on lineage + trusted time | Evaluator inputs exclude model/provider/retry state | None | Adopted |
| permission_compatibility P0-P5 + preserved Permission Engine | Ceiling compared with Permission Engine classification | PTier mapping (CR-02) | PermissionLevel cannot distinguish P0/P1 or P3/P4 | CR-02: Permission Engine exposes authoritative tier; interim exhaustive mapping must fail closed |
| approval_binding_rules.bound_to includes requesting_agent, scope | Approval must bind requesting principal + delegation | CR-01 extends action_hash allowlist | v0.1.3 action_hash omits requesting agent | CR-01; existing gap recorded, not silently fixed |
| denial_persistence_rules (keyed by action_identity, semantic_intent) | v0.2.5 supplies root/objective lineage keys | Lineage ids | No durable DenialRecord exists in v0.1.3; semantic intent unimplemented | Recorded as open dependency (future owner: approval/orchestration) |
| self_approval_rules | Delegation carries no approval authority | No approval fields; CR-03 | decide_approval compares strings only | CR-03: decided_by must be HUMAN_OWNER principal |
| coding_agent_rules.protected_targets | Not delegable as ordinary change | Protected-target action class (future) | No action class for repository edits exists yet | Deferred to integration/protected-target policy; DI-13 |
| multi_business_rules.tenant_scope_is_explicit_authorization_dimension | Future scope dimension via schema version | schema_version | Not implemented in v0.2.5 | Deferred; namespace strings grant nothing |
| budget_rules.hierarchical_budget_child_may_exceed_parent_delegation=false | Future budget dimension must attenuate | Deferred | Budget engine treats unconfigured account as unlimited | Recorded: future delegated budgets must not inherit 'unconfigured = unlimited' |
| audit_integrity_rules (immutable, superseding records, dangling lineage fails closed) | Append-only records; computed state | Store + resolver | None | Adopted |
| fail_closed_conditions: missing/expired delegation, invalid chain | Reason codes | Evaluator | None | Adopted |
| SI-25 frozen v0.1.3 guarantees | No v0.1.3 file changes in v0.2.5 core stages | CR-01..CR-05 require separate authorization | Integration needs v0.1.3 changes | Staged: core first, integration separately authorized |
| Legacy app/security/permissions.py + app/agents AgentDescriptor.permissions (agent-TYPE standing permissions, legacy app/orchestration path) | Not an authority root; never consulted by delegation | Evaluator ignores it | Pre-existing 'type grants permission' model | Recorded; if the legacy path is ever joined, its sets may only act as an additional ceiling (intersection) |

## 25. Change requests requiring separate authorization

None of these are made in v0.2.5 design; the core implementation stages
(v0.2.5.1–.4) need none of them.

| ID | Change | Touches | Reason |
|---|---|---|---|
| CR-01 | Bind Action to requesting principal and leaf delegation_id; add both to action_hash allowlist and ActionRecord. The requesting principal is a typed PrincipalRef, bound insert-once at Action creation and read from that binding on every resume, recovery and execution. It is never taken from Action/ActionPlan content or from the resuming caller (T-44, T-46). See Part II §P for the side-table alternative. | v0.1.3 Action/action_hash/ActionRecord (frozen) + Alembic migration | Approval binding to requesting agent (v0.2.0) and single lineage per action |
| CR-02 | Permission Engine exposes the authoritative P-tier on PermissionDecision (additive) | v0.1.3 permission_engine (frozen) | PermissionLevel cannot distinguish P0/P1 and P3/P4; the mapping must be owned by the Permission Engine, not duplicated |
| CR-03 | decide_approval requires a HUMAN_OWNER principal for decided_by | v0.1.3 approval_engine (frozen) | Self-approval through delegated helpers |
| CR-04 | A durable AgentRegistry with an append-only, timestamped history of lifecycle events (DISABLED/RETIRED). The evaluator applies the lifecycle-history rule (§12), so re-enabling never resurrects authority. | v0.2.4 AgentRegistry (in-memory, immutable) | Disabled-after-issuance semantics and durable lineage references |
| CR-05 | The durable executor runs C′ BEFORE gates A/B/C, re-deriving permission and delegation from durable state. The caller-supplied PermissionDecision is used only as a consistency check (T-53). | v0.1.3 durable_action_executor (frozen) | Revocation/expiry freshness at execution |

## 26. Reason codes (minimal set)

| Code | Meaning |
|---|---|
| `NO_EFFECTIVE_DELEGATION` | Requester named no delegation, or holds none |
| `UNKNOWN_DELEGATION` | delegation_id not in trusted store |
| `DELEGATE_MISMATCH` | Leaf delegate is not the requesting principal |
| `UNKNOWN_PRINCIPAL` | Principal does not resolve (unregistered agent / unknown owner id / unknown kind) |
| `DELEGATE_INACTIVE` | Delegate agent disabled |
| `DELEGATOR_INACTIVE` | Delegator agent disabled |
| `DELEGATION_REVOKED` | This edge revoked |
| `DELEGATION_EXPIRED` | Trusted time >= expires_at |
| `UPSTREAM_INEFFECTIVE` | An ancestor edge is not effective |
| `LINEAGE_INVALID` | Discontinuous, cyclic, over-long, rootless or tampered lineage |
| `OBJECTIVE_MISMATCH` | Action objective differs from lineage objective |
| `UNKNOWN_AUTHORITY_DIMENSION` | Unrecognized schema_version/dimension/enum value |
| `CEILING_EXCEEDED` | Required P-tier above effective ceiling |
| `ACTION_TYPE_NOT_DELEGATED` | action_type not in effective action set |
| `REDELEGATION_FORBIDDEN` | Issuance from an edge without redelegation |
| `DEPTH_EXCEEDED` | Issuance beyond remaining depth |
| `SCOPE_NOT_ATTENUATED` | Issuance request exceeds parent redelegable scope in some dimension |
| `SELF_DELEGATION` | delegator == delegate |
| `PRINCIPAL_CYCLE` | Delegate already appears in lineage |
| `NOT_ISSUABLE_TO_AGENT` | P5 or other non-delegable authority requested for an agent |
| `REVOKER_NOT_AUTHORIZED` | Revoker is not owner/delegator/ancestor |
| `CLOCK_UNTRUSTED` | No trusted time snapshot was supplied, or the clock is below the store high-water mark [HR-15] |
| `EMPTY_AUTHORITY` | The effective meet is ⊥ [HR-01] |
| `REQUESTER_UNBOUND` | No durable requester binding exists, or the caller-supplied requester differs from it [HR-03] |
| `PRINCIPAL_LIFECYCLE_EVENT` | The delegator or delegate has had a lifecycle event since issuance [HR-04] |
| `VERSION_MISMATCH` | The scope's vocabulary_version does not match the evaluator's [HR-09] |
| `ROOT_AUTHORIZATION_INVALID` | Owner event id reused, digest mismatch, or a root not issued by the owner [HR-06] |

---

## 27. Future API (not implemented)

| Operation | Trusted caller | Input | Output | Fail-closed behavior | Atomic with | Audit event | Mutates |
|---|---|---|---|---|---|---|---|
| `issue(request, *, now)` | owner layer (roots) / control plane (children) | `DelegationRequest` (exact type) | `DelegationRecord` | Any §7 check fails → typed error, no write | record + audit | `DELEGATION_ISSUED` | yes |
| `revoke(delegation_id, revoked_by, reason, *, now)` | owner / delegator / ancestor / delegate (renounce) | ids + closed reason | `RevocationRecord` | Unauthorized revoker → error, no write; duplicate → no-op | record + audit + watermark | `DELEGATION_REVOKED` | yes |
| `get(delegation_id)` | control plane | id | `DelegationRecord` (historical) | Unknown → `UNKNOWN_DELEGATION` | — | — | no |
| `resolve_lineage(leaf_id, *, now)` | evaluator | id + trusted time | root→leaf records + effectiveness | First failing hop → typed reason | consistent snapshot | — | no |
| `evaluate_effective_authority(requester, leaf_id, required, *, now)` | pipeline gate / executor C′ | principal, id, (tier, action_type, objective) | `AuthorityEvaluation` | Anything unknown → `LINEAGE_INVALID`/`OUTSIDE_SCOPE` | consistent snapshot | `AUTHORITY_EVALUATED` (by caller) | no |
| `list_descendants(delegation_id)` | owner-facing audit | id | ids | Unknown → error | — | — | no |

No "authority manager": identity stays in AgentRegistry, classification in the
Permission Engine, approval in the Approval Engine, budgets in Budget,
execution in the executor. The delegation package only issues, revokes,
resolves and evaluates.

## 28. Future modules and dependency direction

```text
app/agent_identity  ←  app/delegation  ←  (separately authorized) orchestrator / executor glue
                              ↑
              reads PermissionDecision type only (never imports approval/budget/executor)
```

- `contracts.py` — types, enums, reason codes. `scope.py` — pure `validate/leq/meet`.
  `store.py` — trusted append-only issuance/revocation. `evaluator.py` — lineage + evaluation.
- Prohibited imports: providers registry/router, tool adapters, approval
  engine, budget, executors, orchestrator, `app.agents`, `app.security.permissions`.
- `app.agent_identity` and the Permission Engine never import delegation.

## 29. Implementation stages (future; smallest safe sequence)

| Stage | Scope | Touches frozen v0.1.3? |
|---|---|---|
| v0.2.5.1 | contracts + pure scope algebra | no |
| v0.2.5.2 | in-memory trusted store (issue / revoke / get) | no |
| v0.2.5.3 | lineage resolver + evaluator | no |
| v0.2.5.4 | hostile benchmark over the full threat matrix | no |
| v0.2.5.5 | durable store + CR-01…CR-05 integration + migration | **yes — separate authorization** |

## 30. Hostile tests that must precede each stage

- **.1** — PO-01 property test (random scopes: `attenuate` raises or returns `leq` child); partial-order laws (reflexive, antisymmetric, transitive) and meet laws (commutative, associative, idempotent, `meet ≤ both`); incomparable scopes never reported comparable; exhaustive enum/unknown-version/unknown-dimension; None/empty/wildcard table; mutation matrix incl. `|=`/`*=`; subclass/`model_construct`/`model_copy` fixtures; no metadata/approval/credential fields (structural).
- **.2** — T-04, T-06, T-07, T-08, T-10, T-15, T-17, T-19, T-20, T-21, T-27, T-28, T-33, T-41, T-42; R-01…R-08; issuance with P5 to agent; issuance order permutations.
- **.3** — multi-hop A→B→C→D revoke/expire/disable at every edge (PO-04); sibling/cousin/grandparent/unrelated/same-role/same-model/same-namespace fixtures (T-05, T-37); determinism with permuted insertion (PO-12); objective mismatch; tampered-store PO-03; requester passed separately from Action content (T-44); clock boundary tests.
- **.4** — every T-/R-/D- row as an executable scenario; D-rows marked PARTIAL/NO are asserted as documented limitations, not passes.
- **.5** — interleaving tests for revoke/evaluate/execute (R-09/R-10); approval cross-principal consumption after CR-01; `decided_by` AGENT rejection after CR-03; migration tests.

## 31. Explicitly deferred

Tenant/business dimension; resource scoping; data classification, context and
memory scope (v0.2.6); AI inference budgets and durable ModelInvocation
(v0.2.7); multi-agent orchestration, sub-objectives, split detection (v0.2.8);
business-spend/financial delegation; P5 delegation to agents; one-shot
delegations; `not_before`; caching; durable store and all CR-01…CR-05
integration; denial store and semantic intent keys; agent lifecycle (CR-04);
Credential Broker; protected-target action class.

## 32. Limitations and open questions

1. **Denial persistence is only partly achievable** without a trusted intent key; rephrasing and split-recombination remain open (D-01, D-04, T-12).
2. **Integration requires frozen-v0.1.3 changes** (CR-01, CR-02, CR-03, CR-05) and a migration; v0.2.5 core can be built and hostile-tested without them but cannot be *enforced* in the action pipeline until they are authorized.
3. **Root issuance UX:** the owner layer must display prior denials and existing lineages when issuing a root; not designed in detail here.
4. **Should SYSTEM_POLICY ever issue low-tier (P0–P1) standing roots** to reduce owner toil? Current design: no.
5. **Escalation workflow:** out-of-scope requests BLOCK; whether a future "escalation request" should create an owner prompt (without mutating the delegation) is open.
6. **Durable AgentRegistry** is a prerequisite for durable lineage (CR-04).
7. **Residual in-flight window** after execution claim cannot be closed by revocation.
8. **Legacy agent-type permission model** (`app/security/permissions.py`) remains in the legacy orchestration path; reconciling it is out of scope.
9. The action_type vocabulary is owned by the Permission Engine as a private dict; v0.2.5 needs a public, versioned vocabulary (part of CR-02).
10. **OQ-10, P5 authorization protocol — OPEN [HR-12, HR-27, DA-03].** v0.2.5 defines no P5 execution path: an agent P5 proposal stops at the authorization boundary. Any future path requires a separately designed, hostile-reviewed and Human-Owner-approved P5 authorization protocol. That protocol must also settle owner-originated approval semantics against the self-approval rule (`decided_by == requested_by` → error), together with CR-03. It is not designed here. Until it exists, P5 is unreachable through agents (fail closed).
11. **No trusted principal context exists [HR-03].** Until an authenticated invocation identity exists, trusting the requester means trusting the calling code path.
12. **No objective store exists [HR-10].** Objective binding is an integration precondition.
13. **P3/P4 residual [HR-02].** An `external_modify` action on a tool that mis-declares MEDIUM risk is P3 by construction. ToolRegistry declarations are security-relevant configuration.
14. **Integration removes an existing capability [HR-12].** Agent-originated `financial` actions (REQUIRE_APPROVAL in v0.1.3) become impossible once the gate runs before approval.
15. **Accepted availability costs.** Every schema or vocabulary bump forces mass re-issuance (HR-05/09), and any delegator disable permanently removes all descendants (HR-04).

---

## 33. Design review questions — answers

### Q1. What exactly is authority?
The upper bound on what a principal may *request* the control plane to do: a point in the AuthorityScope partial order (P-tier ceiling × action-type set × objective × expiry), justified by one trusted lineage to a human root. It is never a permission result, approval, capability or tool access.

### Q2. Where does root authority originate?
Only from the HUMAN_OWNER through the trusted non-agent layer, as an explicit `RootAuthorization`. System policy is a ceiling, not a source. Titles, agents, providers and models are never roots.

### Q3. What exactly can be delegated?
A subset (in the partial order) of the delegator's `redelegable_scope`: a P-tier ceiling up to P4, a non-empty subset of action types, the same objective, an expiry no later than the parent's, and optionally a smaller redelegation policy with reduced depth.

### Q4. What can never be delegated?
P5 (to agents, in v0.2.5); approval authority; the ability to revoke upstream edges; issuance of roots; protected-target modification; credentials; financial/business-spend authority; context/data access (v0.2.6); inference budgets (v0.2.7); anything via wildcard.

### Q5. How is authority attenuation proven?
Check-not-clip `leq` at issuance per dimension (decidable, closed dimensions), plus recomputation of the meet over the whole lineage at evaluation (PO-01, PO-03), verified by property-based tests over random scopes and chains.

### Q6. How are incomparable authority scopes handled?
The scope order is partial. Incomparable scopes are never ranked or joined. `leq` returns false for them, so issuance fails and evaluation reports `OUTSIDE_SCOPE`, which fails closed. Their meet is total: either a smaller valid scope, or the explicit bottom ⊥ (zero authority, `EMPTY_AUTHORITY`) [HR-01].

### Q7. Can multiple delegations combine?
No. Each action names one leaf delegation; its lineage is the only authority source; no join/union exists.

### Q8. How is redelegation constrained?
Only via an explicit `RedelegationPolicy`; child scope ≤ parent's `redelegable_scope`; child redelegable ≤ child scope; depth strictly decreasing; system max depth; no reset per generation.

### Q9. How are cycles prevented?
Self-delegation rejected; a delegate may not already appear in the lineage; records reference only pre-existing parents with store-generated ids; the evaluator uses a visited set and max length and rejects discontinuity.

### Q10. How does revocation propagate?
Whole-edge, irreversible, immediate; every descendant becomes `NOT_EFFECTIVE (UPSTREAM_INEFFECTIVE)`; records are retained; nothing is re-parented.

### Q11. What happens when a delegator becomes disabled?
Its edges and all their descendants become permanently non-effective under the lifecycle-history rule (§12). Re-enabling the delegator never resurrects them; they must be re-issued [HR-04].

### Q12. What happens when a delegate becomes disabled?
Issuing to it fails. An existing edge to it becomes permanently non-effective, and re-enabling the delegate does not restore it [HR-04].

### Q13. How does expiration work?
Required `expires_at`, bounded by max TTL, never later than the parent's; evaluated only against the injected trusted clock; `t ≥ expires_at` is expired; no renewal in place.

### Q14. How are stale records prevented from restoring authority?
No stored status to replay; ids never reused; revocation permanent; effectiveness recomputed from records + revocations + trusted time on every evaluation and again at the final boundary; no caching.

### Q15. How is objective scope bound?
By durable `objective_id` equality along the whole lineage and against the Action's bound objective (CR-01); never by text.

### Q16. How does a denied action remain denied across agents?
v0.2.5 by itself does not keep it denied. What it provides is the `(root_delegation_id, objective_ref)` key, shared by every descendant lineage. A future DenialRecord keyed on that plus the action_hash would catch **exact-payload** retries, redelegations and new agents. Model and provider switches never change the keys. Rephrasing, any payload change, and split-and-recombine need a future trusted intent identity. v0.2.5 does not solve these, and the v0.2.0 denial rules stay unmet until that identity exists [HR-11].

### Q17. How is approval kept separate?
The delegation gate precedes approval-request creation, so out-of-scope actions are blocked before any approval exists; approvals bind to the exact action hash (and, after CR-01, to principal + leaf delegation); approval never writes to the delegation store; delegation has no approval fields; CR-03 requires a human `decided_by`.

### Q18. How does P0–P5 interact with delegated ceilings?
The Permission Engine determines the required tier; delegation requires `required_tier ≤ ceiling`; if so the Permission Engine's outcome (ALLOW / audit / approval / BLOCK) still applies unchanged. A ceiling never lowers the tier or skips approval.

### Q19. How will the existing Permission Engine consume the result?
It won't. The Permission Engine stays independent; delegation consumes its output. The orchestrator (after separate authorization) calls the delegation evaluator between `evaluate_permission` and `create_approval_request`, and the durable executor re-evaluates at C′.

### Q20. What must be revalidated immediately before future execution?
Agent active; every lineage edge effective (not revoked, not expired at trusted time, delegator/delegate active); lineage continuity and root; objective binding; tier and action type within scope; freshly derived Permission Engine result; approval valid and unconsumed; budget — with the revocation read and the execution claim serialized.

### Q21. Which parts belong in v0.2.5 implementation?
Stages v0.2.5.1–.4: contracts, pure scope algebra, in-memory trusted store, lineage resolver/evaluator, hostile benchmark. Stage .5 (durable store + CR-01…CR-05 integration + migration) only with separate authorization.

### Q22. Which parts explicitly belong to later phases?
Everything in §31: tenancy, resources, data/context/memory (v0.2.6), inference budgets and ModelInvocation (v0.2.7), orchestration, sub-objectives and split detection (v0.2.8), business spend, P5 delegation, the P5 authorization protocol (OQ-10), denial store/intent keys, agent lifecycle, Credential Broker, protected-target action class.

---

---

# Part II — Independent hostile architecture review HR-1

```text
status = DESIGN_ONLY
implementation_authorized = false
review = HR-1 (hostile architecture review of the Part I design)
```

## A. Method

For every security claim in Part I the review:
1. identified the invariant;
2. built a counterexample;
3. checked whether the design rejects it;
4. checked whether that rejection is machine-verifiable;
5. checked whether an implementer could reasonably misread the contract;
6. identified which system actually enforces it.

Ambiguity was treated as a finding.

Claims about the existing code were checked against the source at
`d10fbbb`, not against the Part I prose:
- `permission_engine.py`: `_ACTION_TYPE_FLOOR`, `_evaluate_with_tool`, and
  the `max()` of floor and tool defaults;
- `tool_registry.py` default levels;
- `action_hash.py` `_HASHED_FIELDS`;
- `approval_engine.py`: the string self-approval check and the
  `action_id`+`action_hash` binding;
- `schemas.ApprovalRequest.requested_by="system"`;
- `action_plan_orchestrator.py`: `requested_by = requested_by or owner`, and
  `owner="system"`;
- the `models.ActionRecord` and `ActionPlanRecord` columns (no requester, no
  objective);
- `durable_action_executor.py`: gate A/B/C is conditioned on the
  caller-supplied `decision.outcome`;
- `budget.py`, where "unconfigured" means unlimited;
- the v0.2.0 JSON rules (`approval_binding_rules`, `denial_persistence_rules`,
  `self_approval_rules`, `coding_agent_rules`).

## B. Findings

Status legend:
- **REMEDIATED** means the design artifact was corrected in this review.
- **DOCUMENTED** means an INFO item, or a limitation owned by another phase,
  that is now stated explicitly.

| ID | Sev | Artifact / section | Counterexample | Impact | Root cause | Remediation | Design test | Status |
|---|---|---|---|---|---|---|---|---|
| HR-01 | HIGH | §3.3 algebra | meet({read}@O1, {send}@O1): the intersection ∅ violates the non-empty invariant. meet(·@O1, ·@O2) was "undefined" | The "meet-only algebra" claim was false. An implementer could return `None` for an undefined meet, and `None` might then be read as "no restriction" | No bottom element | Explicit ⊥ (NO_AUTHORITY), an internal sentinel, never issued or stored; meet made total; `EMPTY_AUTHORITY` reason; DI-15, PO-15, T-45 | PO-15 property tests | REMEDIATED |
| HR-02 | HIGH | §3.2, §16 P-tier mapping | `external_modify` on a HIGH-risk tool → EXTERNAL/HIGH. EXTERNAL/LOW is reachable through a tool declaring EXTERNAL/LOW with `read` support, which contradicts the draft's "unreachable" | The P3/P4 distinction was under-specified and depended on the unstated `max()` risk semantics. A careless mapping (risk ≤ MEDIUM → P3) would under-classify | PermissionLevel lacks P3/P4 | §3.7: exact `max(T_floor, T_class)` table; P3 only when positively established; residual tool-misdeclaration risk stated; CR-02 ownership; T-57 | Exhaustive action_type × level × risk table | REMEDIATED |
| HR-03 | HIGH | §7 requester trust | Plan created with `requested_by="agent.a"`, later resumed by a caller passing `requested_by="agent.b"`. Nothing durable records A. The default requester is `"system"` | Sibling or requester substitution once delegation is integrated. Part I's amendment wrongly implied that today's `requested_by` is trustworthy | The requester is a bare, per-call, unpersisted string | Typed PrincipalRef bound insert-once at Action creation; every later check reads the binding; no default requester; trusted principal context declared as a dependency; DI-16, PO-16, T-46, `REQUESTER_UNBOUND` | Resume-substitution fixtures | REMEDIATED |
| HR-04 | HIGH | §12 lifecycle | CEO disabled, then re-enabled. The evaluator reads only current `enabled`, so CTO's delegation silently returns. Without CR-04 there is no atomic revocation | Stale authority resurrection | Dynamic suspension was the de-facto semantics | Lifecycle-history rule: any event since `issued_at` permanently ends the edge; re-issuance required; revocation ≠ disable; integration precondition on append-only lifecycle history; DI-17, PO-17, T-47 | disable→enable at every hop of a 10-hop chain | REMEDIATED |
| HR-05 | HIGH | §3.4 deferred dimensions | v0.2.6 adds tenant scope. The Part I sentence "enforced by their owning systems; delegation does not widen them" lets a v1 record pass the delegation gate for any tenant | Old-schema, new-dimension escalation | Two contradictory statements (fail closed vs silent) | §3.5: absent dimension = zero; exact-version evaluation; no automatic upgrade; no cross-system inference; DI-18, PO-18, T-48 | v1-under-v2 fixtures | REMEDIATED |
| HR-06 | MEDIUM | §4 root | One owner authorization event id reused for N root edges, or a root row inserted with a copied event id | Unbounded root minting from a single human act | No uniqueness or content binding on the root | Unique `owner_authorization_event_id`; `root_request_digest`; `issue_root` only on the owner channel; DB integrity as a stated trust assumption; T-49 | Duplicate-event and digest-mismatch fixtures | REMEDIATED |
| HR-07 | MEDIUM | §3 system policy | No delegation, P3 ceiling: an implementer computes meet(ceiling) = P3. Owner issues P4 while policy allows P2 | System policy acting as a grantor; owner overriding policy | The ceiling was untyped, and the root-vs-ceiling rule was unstated | §3.8: typed SystemPolicyCeiling, not evaluable alone; no lineage ⇒ ⊥; root above ceiling rejected; later tightening applies; override only through a separate policy-management action; `policy_version` recorded; DI-19, PO-19, T-50 | Empty-store and over-ceiling fixtures | REMEDIATED |
| HR-08 | MEDIUM | §16, CR-05 | `execute_action_durably(action, PermissionDecision(ALLOW))` for an external action skips gate C today | Approval bypass today and delegation bypass after integration if C′ runs after A/B | The executor trusts the caller's decision | C′ runs before A/B/C, recomputes permission and delegation, and uses the supplied decision only as a consistency check; T-53 | Supplied-ALLOW fixture | REMEDIATED |
| HR-09 | MEDIUM | §3.2 action_types | Permission Engine re-tiers `external_modify`, or a tool starts using `read` for a sending operation. Old scopes containing the string now cover the new meaning | Silent widening through vocabulary evolution | The vocabulary is unversioned | `vocabulary_version` pinned in the scope and in the ceiling; any change bumps it; `VERSION_MISMATCH`; T-52 | Vocabulary-bump fixture | REMEDIATED |
| HR-10 | MEDIUM | §13 objective | Delegation issued for objective O. O's text is later changed from "research suppliers" to "sign supplier contract" with the same id | Authority silently changes meaning; ids could be model-chosen | The objective was unversioned and its origin unspecified | `ObjectiveRef(id, version)`; immutable per version; control-plane origin; no objective store today, so this is an integration precondition; T-54 | Objective-edit fixture | REMEDIATED |
| HR-11 | MEDIUM | §14 denial matrix, PO-09 | "denied → new agent: YES". A reworded or byte-changed payload evades any hash key, and no DenialRecord exists | Overclaimed security property | An exact-hash key was presented as intent persistence | D-02/D-03/D-05 downgraded to EXACT-PAYLOAD ONLY with a future store; PO-09 downgraded; the v0.2.0 denial rules are stated as unmet | Documented NON-catch assertions | REMEDIATED |
| HR-12 | MEDIUM | §3.2 P5 | In v0.1.3, an agent-originated `financial` action reaches REQUIRE_APPROVAL and a human may approve it. After integration the gate BLOCKs it | An existing workflow is removed without the design saying so, and P5 exclusion was presented as if it were constitutional | The draft did not separate policy from constitution | §3.7: exclusion is a new policy decision (DA-03, Human-Owner approved with rewording); no standing P5; agent P5 proposals stop at the authorization boundary; behavior change recorded; OQ-10 | — (policy) | REMEDIATED |
| HR-13 | MEDIUM | §24 compatibility | The approval-binding (`requesting_agent`) and denial-persistence rows were labeled as resolved or as open dependencies | Conflicts shown as compatible | No classification column | §O classification: every row labeled compatible, strengthening, refinement or conflict; two pre-existing conflicts named | Checker verifies the classification list | REMEDIATED |
| HR-14 | MEDIUM | §9 depth | Is `remaining_depth = 1` "one more edge", or "the child may itself redelegate once"? | Off-by-one allows an extra hop | Informal definition | Definition table plus three machine-checkable issuance rules | Depth fixtures 0/1/2 | REMEDIATED |
| HR-15 | MEDIUM | §10 time | Trusted clock rolled back by one day: an expired edge evaluates as effective. Naive datetimes compared against aware ones | Revived authority | No monotonic guard; representation unspecified | Aware-UTC only; high-water mark ⇒ `CLOCK_UNTRUSTED`; boundary rules; T-55 | Rollback and naive fixtures | REMEDIATED |
| HR-16 | LOW | §7 per-hop | A tampered record with `redelegable_scope > scope` passes the evaluator, because only `leq(child, parent.redelegable)` was re-checked | Evaluator depended on issuance-time validation | Incomplete per-hop list | Both `leq`s re-checked at every hop; reject, not clip; parent ordering checked; T-56 | Tamper fixtures | REMEDIATED |
| HR-17 | LOW | §4 principals | `AGENT:"owner"` vs `HUMAN_OWNER:"owner"` in cycle detection or revoker checks written with bare ids | False equivalence | Pair semantics were not stated for every use | `(kind, id)` required for equality, hash, serialization, cycles, revoker checks and audit | Kind-collision fixtures | REMEDIATED |
| HR-18 | LOW | §11 revocation | Can a revocation be revoked? Does the reason matter? | Implementation drift | Unanswered questions | Explicit answers added | R-07 fixtures | REMEDIATED |
| HR-19 | LOW | CR-03 | Typed principals, while `decide_approval` still compares strings: `"AGENT:x"` vs `"x"` aliasing | False distinction or false equivalence in self-approval | String identity | CR-03 requires `(kind, id)` equality, `HUMAN_OWNER` only, one canonical owner id and no alias table (§P) | CR-03 tests | REMEDIATED |
| HR-20 | LOW | checker | Production code placed at `jarvis/delegation.py` or `app/policy/x.py` with renamed classes passes the checker. Counts were hardcoded | False assurance | Filename and class-name heuristics | Whole-repo `git status` allowlist; HR/DA/classification checks; dimension MD↔JSON consistency; blind spots documented (§Q) | Tamper tests | REMEDIATED |
| HR-21 | LOW | §17 audit | A DB edit changes `scope.permission_ceiling` in place, and nothing notices | Undetected semantic mutation | No record digest | Canonical record digest stored in the `DELEGATION_ISSUED` audit event and re-verified at evaluation (detects corruption and naive tampering, not a DB-admin attacker who updates both); requires B-11 deep immutability | Digest-mismatch fixture | REMEDIATED |
| HR-22 | INFO | §7 | Diamond graph and chain switching | Already safe by "one named leaf", but not stated | — | Explicit statement; T-51, T-56 | Diamond fixtures | DOCUMENTED |
| HR-23 | INFO | §19 | Delegation is read as budget approval | — | — | **Delegation does not make an unconfigured budget safe.** "Unconfigured = unlimited" is a Budget issue, hardened separately if ever; delegation grants no budget | — | DOCUMENTED |
| HR-24 | INFO | §18 | P4 `external_modify` delegation vs protected targets | `coding_agent_rules` exists only as a constitution entry; no code enforces it | — | Integration precondition: no action type that can write to the repository, the delegation store, migrations or security artifacts may be delegable until an independent protected-target gate exists. None exists today; the only adapter is sandboxed | — | DOCUMENTED |
| HR-25 | INFO | §16 order | Options A, B, C | — | — | B now, C after CR-02; comparison table | — | DOCUMENTED |
| HR-26 | INFO | §10 computed status | "What did the system believe at time t?" | — | — | Answered by immutable issuance and revocation events plus append-only `AUTHORITY_EVALUATED` audit events (evaluation result, watermark, policy_version, trusted time). Current effectiveness is always recomputed; no mutable status | — | DOCUMENTED |
| HR-27 | INFO | OQ-10 | Any future owner-originated P5 path meets the self-approval rule (the owner approving an action the owner requested) | — | — | Open question (OQ-10), bound to CR-03 and the future P5 authorization protocol | — | DOCUMENTED |
| HR-28 | INFO | CR-01 | Migration alternatives | — | — | §P comparison; side table recommended | — | DOCUMENTED |

No CRITICAL findings. **All HIGH and MEDIUM findings are remediated in the
design.** Two pre-existing constitutional conflicts remain. Both belong to
v0.1.3/v0.2.0, not to v0.2.5 (§O). They **gate integration (stage .5)**, not
design approval.

## C. Remediation change log (no silent patching)

| Change (Part I location) | Why | Finding |
|---|---|---|
| §3.2 table: added `schema_version`, `vocabulary_version`; `objective_id` → `objective_ref`; naive datetimes rejected; P5 marked as policy | Version pinning; objective versioning; P5 honesty | HR-05, HR-09, HR-10, HR-12, HR-15 |
| §3.3: carrier set with ⊥, total meet, closure answers; reject-not-clip at evaluation | Algebra closure | HR-01, HR-16 |
| §3.4: deferred-dimension row rewritten; ⊥ row added | Contradiction removed | HR-05 |
| New §3.5–§3.8 | Schema evolution, vocabulary, P-tier mapping and P5, system ceiling | HR-05, HR-09, HR-02, HR-12, HR-07 |
| §4: root trust dependency; principal identity | Root replay; kind confusion | HR-06, HR-17 |
| §5 contracts: `ObjectiveRef`, `SystemPolicyCeiling`, root digest and unique event, `policy_version`, ⊥ sentinel note | Contract support for the above | HR-01, HR-06, HR-07, HR-09, HR-10 |
| §7: per-hop list expanded; parent-pointer and diamond rule; requester trust rewritten | Tamper, requester | HR-03, HR-16, HR-17, HR-22 |
| §9 depth table | Off-by-one | HR-14 |
| §10 timestamp and rollback rules | Clock | HR-15 |
| §11 revocation answers | Ambiguity | HR-18 |
| §12 lifecycle rule replaced (options A/B/C) | Resurrection | HR-04 |
| §13 objective trust and mutation | Objective | HR-10 |
| §14 D-02/D-03/D-05 and intro downgraded | Overclaim | HR-11 |
| §16 pipeline comparison and C′ ordering | Order; caller decision | HR-25, HR-08 |
| §20 DI-15..DI-19; §21 T-45..T-57; §23 PO-09 downgraded, PO-15..PO-19; §26 new reason codes | Traceability | all |
| §25 CR-01/CR-04/CR-05 text | Requester binding; lifecycle history; C′ order | HR-03, HR-04, HR-08 |
| §32 items 10–15; §33 Q6/Q11/Q12/Q16 | Limitations and answers aligned | HR-01, HR-04, HR-11, HR-12 |
| JSON: mirrored all of the above plus `hostile_review` block | No MD/JSON drift | HR-20 |
| Checker and design test: allowlist, HR/DA/classification/dimension checks, new counts | False assurance | HR-20 |

## D. Authority algebra verdict

`(AuthorityScope ∪ {⊥}, leq, meet)` is a meet-semilattice with bottom per
`(schema_version, vocabulary_version)`:
- **meet is total**;
- **there is no join**;
- **incomparable scopes stay incomparable**.

⊥ is internal. No `AuthorityScope` instance represents it, so the non-empty
invariants survive. Time is outside the algebra.

## E. P0–P5 verdict

P3 is `PTier.P3`. It is reached only by `EXTERNAL_ACTION ∧ MEDIUM` together
with a floor ≤ P3. P4 is `PTier.P4`.
- **Who maps it:** the delegation evaluator's single exhaustive table until
  CR-02, then the Permission Engine.
- **Can a P4 action compare as P3?** Not for `send`, `publish` or `delete`.
  Only an `external_modify` on a tool that mis-declares MEDIUM (residual,
  ToolRegistry trust).
- **Is a frozen-code change needed?** For correctness, no (the interim table
  is conservative). For single ownership, yes (CR-02).
- **P5:** a new policy decision (DA-03, approved with rewording). Agents
  may propose P5 actions but hold no P5 authority; a proposal stops at the
  authorization boundary. No execution path exists until a future P5
  authorization protocol (OQ-10, open).

## F. Root authority verdict

The owner is the only root. System policy only narrows. The trust dependency
on an authenticated owner channel and store integrity is explicit, and root
replay is closed by unique event ids and content digests. v0.2.5 provides no
authentication and no signing.

## G. Requester, action and approval binding

**Minimum secure approval binding (future, CR-01 + CR-03).** An approval is
valid ⇔ all of the following hold:
- the existing `action_id` + `action_hash`, unconsumed and unexpired;
- **`approval.requester == binding.requester`**;
- **`approval.leaf_delegation_id == binding.leaf_delegation_id`**.

These are deliberately **not** separate binding fields:
- **the objective**, because it is determined by the immutable leaf scope;
- **the full lineage**, because it is determined by the immutable parent
  pointers from the leaf.

"Same payload, same hash, different requester" is **not** replayable across
actions today, because `action_id` binds. It **is** substitutable on the same
Action via resume (HR-03), and the insert-once binding closes that.

**Self-approval with typed principals.** `decided_by` must be a
`HUMAN_OWNER` PrincipalRef whose `(kind, id)` equals the configured owner. The
comparison uses the pair. No alias table exists: one canonical owner id.

## H. Pipeline order

B now, C after CR-02 (§16). The Permission Engine is classification plus an
outcome and never grants authority. It needs no requester or delegation
context. C′ recomputes both at execution.

## I. Multiple lineages

**One lineage per action is constitutional**, not an optimization:
- v0.2.0 `authority_rules.single_delegation_lineage_per_action = true`;
- v0.2.0 `cross_delegation_union_allowed = false`.

v0.2.5 **intentionally sacrifices compositional expressiveness.** An action
that genuinely needs data authority from A and publish authority from B is
**not representable, and fails closed.** The only fix is a single new
delegation from a common ancestor that covers both. **No implementation may
"helpfully" combine lineages. Removing this rule is a constitutional change,
not a refactor.**

## J. Redelegation and depth

The depth table is in §9. The scope and redelegable-scope inequalities hold
at every hop, re-checked at evaluation. No counterexample was found where the
child's operational scope shrinks while its redelegable scope grows, because
`child.redelegable ≤ child.scope ≤ parent.redelegable`.

## K. Lifecycle and revocation

Disabling now permanently ends affected edges (HR-04), so there is no
resurrection. Revocation and disabling are distinct. Descendants are
invalidated at evaluation without rewriting records.

**Can v0.2.5 specify disabled semantics without a durable lifecycle model?**
It can specify them, but only the **history-based** rule is enforceable.
That is a hard dependency on CR-04, marked as an integration precondition.

## L. Objectives

Objectives are identified by versioned references with control-plane origin
and are immutable per version. No objective store exists today, so this is
an integration precondition (v0.2.8).

## M. Schema evolution

An absent dimension grants zero authority. Evaluation is exact-version. There
is no automatic upgrade; old records must be re-issued. The same rule covers
tenant (§37), resource (§38) and data-classification (§36) dimensions.

## N. Denial laundering

v0.2.5 catches none of it by itself. With a future DenialRecord it catches
exact-payload repeats only. Rephrasing, split-and-recombine, and any payload
change remain unsolved. No AI semantic-equivalence check may serve as a
security boundary.

## O. Constitutional classification

| v0.2.0 rule | Classification | Note |
|---|---|---|
| central_authority | compatible interpretation | |
| trust_boundaries (agents = delegated responsibility) | compatible interpretation | |
| delegation_rules.fields parent_agent_id/child_agent_id | **explicit refinement requiring authorization** | principals + explicit root |
| delegation_rules.fields status, created_at | **explicit refinement requiring authorization** | status computed; store-set issued_at |
| delegation_rules.fields task_scope, allowed_capability_requests | **explicit refinement requiring authorization** | objective_ref; action_types |
| delegation_rules.fields budget_ceiling, context_scope, memory_scope, allowed_outputs | **explicit refinement requiring authorization** | deferred; absent = zero |
| delegation_rules.invariant | strengthening | child ≤ redelegable ≤ scope |
| authority_rules.effective_authority_is_intersection_of | compatible interpretation | enforced distributively by owners |
| authority_rules.single_delegation_lineage_per_action / cross_delegation_union_allowed=false | compatible interpretation | adopted as constitutional (§I) |
| authority_rules.no_authority_laundering | compatible interpretation | |
| permission_compatibility tiers | compatible interpretation | PTier = constitutional names; CR-02 |
| (new) P5 not delegable to agents | **explicit refinement requiring authorization** | new policy; removes agent-originated financial approvals (HR-12); design-approved as DA-03 (with rewording), not implementation-authorized |
| approval_binding_rules.bound_to requesting_agent | **conflict (pre-existing, v0.1.3 implementation vs v0.2.0)** | unresolved until CR-01 + CR-03; blocks integration |
| denial_persistence_rules (reframing, splitting) | **conflict (pre-existing, unmet requirement)** | not satisfiable by v0.2.5; blocks any claim of denial persistence |
| self_approval_rules | strengthening | CR-03 typed human decided_by |
| coding_agent_rules.protected_targets | compatible interpretation | unenforced in code; integration precondition (HR-24) |
| multi_business_rules | strengthening | absent tenant dimension = zero |
| budget_rules.hierarchical_budget | compatible interpretation | deferred; unconfigured budget not made safe by delegation |
| audit_integrity_rules | compatible interpretation | + record digests (HR-21) |
| fail_closed_conditions | compatible interpretation | |
| SI-25 frozen v0.1.3 guarantees | **conflict for integration stage only** | resolved only via the frozen-change process (§P) |

## P. Frozen v0.1.3 change requests

**Frozen-baseline policy.** "Frozen v0.1.3" means no change to those
components as an ordinary change. A frozen contract may be superseded
**only** through all of the following:
1. an explicit change request (this table);
2. a separate hostile design review;
3. hostile tests written first;
4. a regression proof (the full suite, plus the v0.1.3 freeze checker updated
   by a reviewed manifest amendment);
5. a versioned migration where persistence changes;
6. a rollback strategy;
7. explicit human authorization.

v0.2.5 core stages .1 to .4 need none of these.

| CR | Frozen component | Why necessary | Security benefit | Regression risk | Migration | Backward compat | Hostile tests first | Rollback |
|---|---|---|---|---|---|---|---|---|
| CR-01 | orchestrator requester handling; approval persistence; approval validity | Requester not persisted; approval not bound to requester or leaf | Closes T-22/T-44/T-46 | MEDIUM (approval validity path) | **Yes**, see the alternatives below | Pre-existing actions have no binding. With enforcement on they fail closed (no delegated execution); the legacy path is unchanged with enforcement off | cross-principal consumption; resume substitution; missing binding row; T-22/T-44/T-46 | Enforcement flag off. Downgrade migration only if no delegated execution has occurred, otherwise forward-fix. Binding rows are retained for audit |
| CR-02 | `permission_engine` | Tier not representable; private vocabulary | Single owner of the P-tier; versioned vocabulary (T-52/T-57) | LOW (additive field) | No | Additive `tier` field | exhaustive tier table equals interim mapping | Revert additive field; interim mapping remains |
| CR-03 | `approval_engine.decide_approval` | String self-approval; AI decided_by accepted | Human-only approval; kind-safe equality (T-43, HR-19); owner-originated semantics (OQ-10) | MEDIUM (existing tests use string ids) | Likely: a typed `decided_by` needs a kind column, or a canonical `kind:id` encoding with a backfill of existing rows as legacy | Legacy rows are read-only history | AGENT decided_by rejected; kind collision; alias; owner-originated flow | Code revert; the additive column is kept |
| CR-04 | v0.2.4 AgentRegistry (not v0.1.3, but a reviewed contract) | In-memory, no lifecycle history | Resurrection impossible (T-47) | MEDIUM | Yes (agents + lifecycle_events tables) | Registration API unchanged; history append-only | T-47 at every hop; history immutability | Drop tables with delegation enforcement off |
| CR-05 | `durable_action_executor` | Trusts the caller's PermissionDecision | Closes T-53; freshness (R-09/R-10) | **HIGH** (core execution, idempotency and recovery) | No | Consistency check rejects previously accepted mismatched callers (intended) | supplied-ALLOW; interleavings; recovery replay; mismatch matrix | Code revert; no data change |

**Migration alternatives for CR-01 [HR-28].**

| Option | Change | Pros | Cons |
|---|---|---|---|
| (a) | Add requester + leaf columns to `ActionRecord` and to the `action_hash` allowlist | One record | Changes the frozen hash semantics: every historical hash changes meaning, and existing approvals fail the hash check (fail-closed but disruptive). Mixes content identity with authorization identity |
| **(b)** | New insert-once table `action_authority_bindings(action_id PK, requester_kind, requester_id, leaf_delegation_id, bound_at)`, plus the same three fields on the approval-request row; approval validity compares them | Frozen `ActionRecord` columns and `action_hash` untouched; content hash stays a content hash; binding is independently auditable | Two records to join; a missing binding row must fail closed |

**Recommended: (b).** Both need a migration. (b) keeps the frozen hash stable
and is equally auditable.

## Q. Checker and test limitations

`scripts/check_v025_design_contract.py` is **supplemental evidence, not a
proof**.

What it now does:
- whole-repo `git status` allowlist (only the four v0.2.5 files may be
  new or modified), which catches production code under any name;
- required-ID lists (DI, PO, T, R, D, CR, HR, DA);
- severity/status gating: every HIGH or MEDIUM finding must be REMEDIATED;
- constitutional classification labels;
- MD↔JSON dimension consistency;
- ID cross-references;
- the Q1–Q22 answers;
- baseline checks: Alembic graph parsed from `migrations/versions`, the
  v0.1.3 tag, ToolAdapters.

Blind spots:
1. It checks presence and structure, not the **correctness** of any prose
   argument.
2. The ID lists are hardcoded. That is intentional (tampering is detected),
   but new threats need manual list updates.
3. It needs Git. Without Git it fails closed rather than passing.
4. The allowlist cannot see code outside the repository or already-committed
   code (HEAD is checked separately in the report).
5. Regex checks on the Markdown are bypassable by determined rewording.
6. Line endings are normalized by reading text, and the checker makes no
   byte-hash claims.

`tests/test_v025_design_contract.py` is labeled **DESIGN CONTRACT TEST**. It
exercises only artifacts and the checker, **never runtime delegation**, which
does not exist.

## R. Full design recheck

| Scenario | Result under the remediated design |
|---|---|
| One hop | Issuance check-not-clip ⇒ child ≤ parent.redelegable ≤ parent.scope |
| 10 hops | Depth budget strictly decreasing; SYSTEM_MAX_DEPTH bounds it; per-hop re-check at evaluation; transitivity gives A10 ≤ … ≤ A1 ≤ root ∩ ceiling |
| Incomparable scopes | leq false ⇒ issuance rejected; meet a smaller scope or ⊥ |
| Disjoint action sets | meet = ⊥ ⇒ EMPTY_AUTHORITY |
| Different objectives | meet = ⊥; lineage requires identical objective_ref ⇒ LINEAGE_INVALID / OBJECTIVE_MISMATCH |
| Revoked parent | UPSTREAM_INEFFECTIVE for every descendant; never re-parented |
| Expired parent | Child expiry ≤ parent expiry, so the child is expired too; clock rollback blocked |
| Disabled parent (delegator) | Lifecycle event since issuance ⇒ permanently non-effective, including after re-enable |
| Disabled child (delegate) | Same; issuance to a disabled agent rejected |
| Changed model / provider | Not an input to any authority function ⇒ identical evaluation |
| Changed role / title | Not an input ⇒ identical (zero if no delegation) |
| New schema dimension | Old records ⇒ UNKNOWN_AUTHORITY_DIMENSION; re-issuance required; absent = zero |
| No lineage + permissive ceiling | ⊥ |

**Central property:** `Authority(child) ≤ DelegableAuthority(parent)` holds on
every path examined. No reset, union, resurrection, cross-objective,
cross-principal or cross-tier path survived.

## S. Remaining limitations (not v0.2.5 defects)

1. **Integration is blocked by pre-existing conflicts.** Approval binding to
   the requester and denial persistence are unresolved (§O).
2. **Trust dependencies:** an authenticated owner channel, a trusted
   principal context, store integrity, and ToolRegistry declarations.
3. **Missing future systems:** there is no objective store, no lifecycle
   history, no DenialRecord store and no protected-target gate. All four are
   integration preconditions.
4. **OQ-10 (open):** the future P5 authorization protocol, including
   owner-originated approval semantics. Not designed in v0.2.5.
5. **Residual windows:** the in-flight window after execution claim E, and
   P3 tool mis-declaration.

## T. Design approval questions for the Human Owner

These are the questions as asked at HR-1. **The Human Owner's decisions
are recorded in Part III**; the design itself approves nothing.

- **DA-01 — Authority algebra.** Meet-semilattice over `AuthorityScope ∪ {⊥}`
  with an explicit internal bottom (zero authority, never issued or stored),
  total meet, no join, partial order with incomparability.
- **DA-02 — One-lineage rule.** Exactly one leaf delegation per action; no
  union or composition. Treated as constitutional (§I), accepting the loss of
  compositional expressiveness.
- **DA-03 — P5.** No standing P5 delegation to AI agents in v0.2.5. Accept
  that integration removes agent-originated `financial` approvals.
  The owner-adoption path originally asked here was REJECTED by the Human Owner; see Part III §V.
- **DA-04 — Root authority.** The Human Owner is the only root, through an
  authenticated owner channel. System policy is a typed ceiling that only
  narrows and is never overridden by a root.
- **DA-05 — Revocation.** Whole-edge, irreversible, idempotent; upstream
  revocation invalidates descendants at evaluation; history never deleted;
  no re-parenting.
- **DA-06 — Disable/re-enable.** Any DISABLED or RETIRED event of the
  delegator or delegate since issuance **permanently** ends the edge and its
  descendants. Re-enabling never restores it; re-issuance is required.
  Requires durable lifecycle history (CR-04).
- **DA-07 — Computed status.** Effectiveness is computed from immutable
  issuance, revocation and lifecycle events at trusted time. Historical
  belief is recorded in `AUTHORITY_EVALUATED` audit events. There is no
  mutable status.
- **DA-08 — Objective binding.** Authority binds to
  `ObjectiveRef(id, version)` from a control-plane objective store, immutable
  per version, never to text.
- **DA-09 — Schema evolution.** New dimensions, schema versions or vocabulary
  versions fail closed for old records; an absent dimension grants zero
  authority; no automatic upgrade.
- **DA-10 — Frozen-code integration.** CR-01 to CR-05 each require separate
  later authorization and hostile review under the frozen-baseline policy
  (§P). Recommended CR-01 option: side table (b).


---

# Part III — Human Owner design decisions (design approval only)

```text
status = DESIGN_ONLY
human_design_approval = APPROVED
design_approved = true
implementation_authorized = false
pipeline_integration_authorized = false
migration_authorized = false
frozen_code_changes_authorized = false
p5_execution_protocol_authorized = false
v0_2_6_authorized = false
```

The Human Owner approved the decisions below. **This is design approval.
It is not implementation authorization.** `DESIGN_ONLY` still means that no
runtime delegation or authority code exists, and none is authorized.

## U. Decisions DA-01..DA-10

| ID | Decision | Approved rule |
|---|---|---|
| DA-01 | APPROVED | Closed attenuation structure with an explicit internal zero-authority bottom ⊥. No union/join is available to agents. Meet only preserves or reduces authority. |
| DA-02 | APPROVED | Exactly one delegation lineage may justify one action. Independent lineages are never unioned, joined or composed. No single complete valid lineage ⇒ FAIL CLOSED. |
| DA-03 | APPROVED_WITH_REWORDING | AI agents may never hold standing delegated P5 authority under v0.2.5. An AI agent may formulate or propose a P5 action, but v0.2.5 grants no authority to execute that action. Any future P5 execution path requires a separately designed, hostile-reviewed and Human-Owner-approved P5 authorization protocol. |
| DA-04 | APPROVED | The Human Owner is the explicit root. System policy is a ceiling only: it may narrow and never creates authority. `effective_root_authority ⊆ owner_authorized_scope` and `effective_root_authority ⊆ system_policy_ceiling`. No trusted owner authorization ⇒ NO AUTHORITY, even where system policy would permit. |
| DA-05 | APPROVED | Revocation is whole-edge, irreversible for that record, append-only and auditable. Upstream revocation makes dependent descendants ineffective. Historical records remain. No re-parenting. |
| DA-06 | APPROVED | A delegation issued before its agent was disabled or retired, and all dependent descendants, never resurrect on re-enable. Fresh authority requires fresh issuance. Requires durable lifecycle history (CR-04). |
| DA-07 | APPROVED | Effectiveness is computed from immutable issuance, revocation, lifecycle and time evidence. No mutable security-authoritative `status = ACTIVE` field. Historical decisions live in append-only audit evidence. |
| DA-08 | APPROVED | Authority binds to durable versioned objective identity (`ObjectiveRef(id, version)`), never to natural-language text alone. Changing objective meaning never silently changes existing authority. |
| DA-09 | APPROVED | Schema evolution fails closed: a missing new dimension on an old record is zero authority for that dimension, never unlimited. No automatic privilege-expanding upgrade. |
| DA-10 | APPROVED | CR-01..CR-05 are not implementation-authorized. Each frozen-code integration change needs explicit future authorization, hostile tests first, regression analysis, migration analysis where applicable, a rollback strategy, compatibility analysis and human review. The CR-01 side-table option (b) stays a recommendation only. |

## V. DA-03 remediation

| | Wording |
|---|---|
| Earlier HR-1 wording (REJECTED) | Agent P5 proposals become reachable when the owner adopts the proposal as an owner-requested action. REJECTED: owner adoption is not an approved security mechanism and is not part of the v0.2.5 architecture. |
| Approved wording | AI agents may never hold standing delegated P5 authority under v0.2.5. An AI agent may formulate or propose a P5 action, but v0.2.5 grants no authority to execute that action. Any future P5 execution path requires a separately designed, hostile-reviewed and Human-Owner-approved P5 authorization protocol. |

```text
Agent P5 proposal   ≠  Agent P5 authority
Human approval      ≠  standing delegated P5 authority
P5 proposal         →  STOP at authorization boundary   (until a future P5 protocol exists; OQ-10 OPEN)
```

**DA-03 hostile checks.** Every interpretation below is rejected; each must
fail closed.

| ID | Attack | Result | Why it fails closed |
|---|---|---|---|
| DA03-A | CFO agent holds P4, proposes a transfer, and automatically gets P5 | FAIL_CLOSED | A proposal carries no authority. P5 is never a valid agent ceiling (`NOT_ISSUABLE_TO_AGENT`); a P5 action against a P4 lineage is `CEILING_EXCEEDED`. |
| DA03-B | Human approves one P5 proposal, so the CFO now has standing P5 | FAIL_CLOSED | Approval writes nothing to the delegation store and issues no delegation. P5 is not issuable to agents. v0.2.5 has no P5 execution path. |
| DA03-C | Human approves one P5 proposal, and another P5 proposal inherits the approval | FAIL_CLOSED | Approvals bind to one exact action hash (and, after CR-01, to requester and leaf delegation). Approval is not authority and is never transferable. The proposal stops at the authorization boundary. |
| DA03-D | Agent labels the action "owner adopted", so P5 is allowed | FAIL_CLOSED | Labels, notes and metadata are not authority inputs (T-26; records have no metadata). Owner adoption is not a v0.2.5 mechanism. |
| DA03-E | Agent changes `requested_by` to HUMAN_OWNER, so P5 is allowed | FAIL_CLOSED | The requester binding is a typed `PrincipalRef`, insert-once at Action creation; a caller-supplied mismatch is `REQUESTER_UNBOUND`. Agents cannot assert owner identity. Trusted principal context is a future dependency; CC-01 blocks integration until then. |
| DA03-F | Provider or model output says the owner approved, so P5 is allowed | FAIL_CLOSED | Model and provider output is never an authority or approval input (no authority laundering). Owner decisions come only through the future trusted owner channel. |
| DA03-G | An approval exists, so the delegation ceiling mutates to P5 | FAIL_CLOSED | Delegation records are immutable and approval never writes the delegation store. A ceiling can only be preserved or reduced; P5 is not an agent ceiling. |

## W. Constitutional blockers (acknowledged, NOT waived)

- **CC-01 — Requester-bound approval.** v0.2.0 requires approval bound to the
  requesting agent/principal. Frozen v0.1.3 does not provide it. Pipeline
  integration stays **blocked** until the relevant CRs (CR-01, CR-03) are
  separately reviewed and authorized.
- **CC-02 — Denial persistence.** The constitution requires denial
  persistence across rewording/reframing and splitting. The current
  architecture does not satisfy it, and v0.2.5 delegation does **not** claim
  to:

```text
delegation lineage  ≠  semantic intent equivalence
delegation lineage  ≠  split/recombine detection
```

Both are future architecture dependencies. The constitutional requirement is
not weakened.

## X. Accepted design limitations

1. The trusted owner channel is a future dependency.
2. Trusted principal context is a future dependency.
3. The objective store and objective versioning are a future dependency.
4. Durable agent lifecycle history is a future dependency (CR-04).
5. The denial store and intent architecture are a future dependency (CC-02).
6. The protected-target gate remains separate.
7. ToolRegistry declarations remain a trust dependency.
8. Revocation cannot retroactively stop an external effect already completed.
9. Tool under-declaration risk remains unresolved.
10. OQ-10 remains OPEN.
11. No P5 execution protocol exists in v0.2.5.

## Y. Authority algebra reconfirmed

The decisions above leave the attenuation invariants unchanged:

```text
child.scope              ≤  parent.redelegable_scope
child.redelegable_scope  ≤  child.scope
Authority(leaf) ≤ … ≤ Authority(root) ≤ Human Owner authorization
effective_scope = meet(lineage) ∧ system_policy_ceiling   (system policy only narrows)
no lineage  ⇒  ⊥ (NO AUTHORITY)
```

## Z. Authorization state

Design approval does not imply that a runtime implementation exists. Still
**false**: `implementation_authorized`, `pipeline_integration_authorized`,
`migration_authorized`, `frozen_code_changes_authorized`,
`p5_execution_protocol_authorized`, `v0_2_6_authorized`.

**NO v0.2.5 PRODUCTION IMPLEMENTATION HAS BEEN AUTHORIZED OR CREATED.**
