# Jarvis OS v0.2.5.1 — Pure Authority Contracts + Algebra

```text
phase                              = v0.2.5.1 (contracts + pure scope algebra)
predecessor                        = 1e242b827f46de42064ea0965f59e8c2bf82591c (v0.2.5 approved design)
status                             = IMPLEMENTED_UNCOMMITTED — final hostile review done; awaiting Human Owner commit authorization
authorized_phase                   = v0.2.5.1 only (pure contracts + algebra)
v0.2.5.2+                          = NOT AUTHORIZED
delegation_runtime                 = absent
pipeline_integration               = absent
persistence / migration            = absent
p5_execution                       = absent
CR-01..CR-05                       = NOT AUTHORIZED
CC-01, CC-02                       = BLOCKING, not waived
OQ-10                              = OPEN
v0.2.6                             = NOT AUTHORIZED
```

> **Representation of authority is not possession of authority.** v0.2.5.1
> may represent and compare authority. It never grants, persists,
> delegates, approves, executes, recovers, combines, infers or manufactures
> authority.

Normative source: `docs/V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md`
(§3.2–3.7, §4, §5, §30 stage .1) and its JSON companion. Those artifacts were
not modified.

## 0. Authorization status (F-04)

The approved design artifacts state `status = DESIGN_ONLY`,
`implementation_authorized = false` and "NO v0.2.5 PRODUCTION IMPLEMENTATION
HAS BEEN AUTHORIZED OR CREATED." Those statements record the authorization
state **at the v0.2.5 design checkpoint** (commit
`1e242b827f46de42064ea0965f59e8c2bf82591c`). They are immutable historical
design-approval evidence. They were true when the design was approved, they
stay unchanged, and they do not dynamically describe later phases that the
Human Owner authorizes separately.

After that checkpoint, the Human Owner explicitly authorized one narrow
phase, **v0.2.5.1: Pure Authority Contracts + Algebra**:

| Authorized (v0.2.5.1) | Not authorized |
|---|---|
| pure authority contracts | delegation issuance / runtime (incl. `attenuate()`) |
| pure authority algebra (`leq`, `meet`, ⊥) | persistence, migration |
| hostile tests | evaluator |
| phase-aware validator evolution | pipeline integration |
| this document | CR-01..CR-05, P5 execution |
| | v0.2.5.2+ and v0.2.6 |

So there is no contradiction. The design flags say what was authorized at
the design checkpoint, and this section says what one later phase adds. The
v0.2.5.1 authorization is phase-specific. It does not set the historical
flags to true, it is not a general implementation or autonomy flag, and
it does not carry over to v0.2.5.2 or any later stage, each of which needs its
own Human Owner authorization.

`scripts/check_v025_design_contract.py` enforces both halves. It still
requires the historical flags to be exactly false, and it requires the design
artifacts' committed content to equal the `1e242b8` blobs (`git diff`). Separately, its
repository checks allow exactly the v0.2.5.1 file set. They reject any other
file (e.g. `app/authority_contracts/store.py`), `app/delegation/`,
`app/authority/` and later-stage classes (`DelegationRecord`,
`RootAuthorization`, `AuthorityEvaluation`, `DelegationStore`, …). They also
require the phase-status lines above.

## 1. What exists

| File | Responsibility |
|---|---|
| `app/authority_contracts/__init__.py` | Public API (11 names, `__all__`) |
| `app/authority_contracts/contracts.py` | `PrincipalKind`, `PrincipalRef`, `ObjectiveRef`, `PTier`, `AuthorityScope`, pinned vocabulary v1 |
| `app/authority_contracts/algebra.py` | `NO_AUTHORITY` (⊥), `leq`, `meet` |
| `tests/test_v0251_hostile_authority_algebra.py` | Hostile tests (written first) |
| `scripts/check_v025_design_contract.py`, `tests/test_v025_design_contract.py` | Phase-aware repository guard (see §7) |

The package is named `authority_contracts`, not `app/delegation/` or
`app/authority/` (the design's future module paths), because neither
delegation nor an authority runtime exists. Nothing in the repository imports
it; it is not in the action path.

## 2. Contracts (design mapping)

| Type | Definition | Design source |
|---|---|---|
| `PrincipalKind` | plain `Enum` {`HUMAN_OWNER`, `AGENT`} | §4; SYSTEM_POLICY is not a principal |
| `PrincipalRef` | `(kind, id)`; equality/hash include `kind`; id = v0.2.4 agent_id rules (≤256, ASCII `[A-Za-z0-9._:-]`, no control/line-separator/homoglyph/padding) | §4, HR-17, T-41 |
| `ObjectiveRef` | `(objective_id, objective_version)`; id = same identifier rules; version exact `int` in 1..2⁶³−1, no default | §3.2, HR-10 |
| `PTier` | plain `Enum` P0..P5 (constitutional names); no ordering operators; rank table internal | §3.7 |
| `AuthorityScope` | exactly `schema_version`, `vocabulary_version`, `permission_ceiling`, `action_types`, `objective_ref`, `expires_at`; all required | §3.2, §5 |
| `NO_AUTHORITY` | singleton sentinel ⊥; not an `AuthorityScope`, not `None`, no fields | §3.3, HR-01 |
| `ACTION_TYPE_VOCABULARY` | vocabulary v1 = the 14 design action types | §3.2, §3.6 |

`AuthorityScope` invariants (all enforced at construction, fail closed):

- `schema_version == 1`, `vocabulary_version == 1`, exact `int` (no `True`,
  `"1"`, `1.0`). No upgrade, downgrade or best-effort compatibility.
- `permission_ceiling` ∈ P0..P4 as an exact `PTier`. **P5 is rejected**
  (DA-03); it is never mapped to P4.
- `action_types`: exact non-empty `frozenset` of exact `str` in vocabulary
  v1. No wildcard (`*`, `ALL`, `ANY`, `UNLIMITED`), no case variants.
- **Tier consistency** (§3.2): every action type's T_floor (§3.7) ≤ ceiling.
  Hence `financial`, `install`, `privileged` (floor P5) are unrepresentable
  in any scope.
- `objective_ref`: exact `ObjectiveRef` instance (no free text, no dict).
- `expires_at`: exact `datetime` with `tzinfo is datetime.timezone.utc`.
  Naive and non-UTC offsets are rejected, not converted.

No other dimension exists: no tenant, resource, data class, budget, tool,
provider, model, role, title, approval, delegation id, execution, financial
or metadata field. An absent future dimension grants zero authority (§3.5).

## 3. Algebra

Carrier `Auth = AuthorityScope ∪ {⊥}`; a meet-semilattice with bottom.

`leq(a, b, /)` — "a grants no more than b":
- `leq(⊥, X)` = True; `leq(X, ⊥)` = False unless `X is ⊥`.
- scopes: equal versions ∧ equal `objective_ref` ∧ `ceiling(a) ≤ ceiling(b)`
  ∧ `action_types(a) ⊆ action_types(b)` ∧ `expires_at(a) ≤ expires_at(b)`.
- version mismatch ⇒ False (not comparable, fail closed).

`meet(a, b, /)` — total greatest lower bound:
- ⊥ if either is ⊥, versions differ, objectives differ, or action types are
  disjoint.
- else `(min ceiling, a ∩ b action types, same objective_ref, earlier
  expires_at, same versions)`, rebuilt through the validated constructor.

Properties: no join/union, no total order (`<`/`sorted` raise), no clock
(`expires_at` is compared as a stored value; "expired now?" is future
effectiveness at trusted time), no I/O, deterministic.

**Check-not-clip boundary.** `meet` may compute an intersection; nothing in
this phase uses it to narrow a request. There is no `attenuate()`/issuance
function: issuance (reject a request unless `leq(request,
parent.redelegable_scope)`, `SCOPE_NOT_ATTENUATED`) belongs to v0.2.5.2
(Human Owner decision for this phase).

**Untrusted operands.** Anything other than an exact `AuthorityScope` or
`NO_AUTHORITY` raises `TypeError`. A version mismatch yields False/⊥ without
trusting either operand. Before a scope can make `leq` true or contribute to
a non-bottom meet it is rebuilt through the validated constructor, so a
tampered record (e.g. ceiling forced to P5 via `object.__setattr__`) raises
instead of propagating.

Reason codes / outcomes: none are implemented. The algebra returns `bool` or
`AuthorityScope | NO_AUTHORITY`. `OUTSIDE_CEILING` and
`LINEAGE_DISCONTINUOUS` do not appear (tested).

## 4. Immutability and bypass hardening

`frozen=True, extra="forbid", strict=True, hide_input_in_errors=True,
revalidate_instances="always"`. Every field value is an immutable hashable
object, so there is no nested container to mutate and mutable inputs are
rejected rather than copied (no caller alias survives). Subclassing,
`model_construct()`, `model_copy()` and therefore `copy.replace()` raise
`TypeError`. `model_validate(instance)` revalidates (finding F-01).
Assigning or deleting any attribute, including pydantic internals
(`__pydantic_extra__`, `__pydantic_fields_set__`, `__pydantic_private__`,
`__dict__`), raises `TypeError` (final hostile review F-05: `frozen` guards
declared fields only).
`copy`/`deepcopy`/`pickle` of valid values give equal valid values.

**Out of contract:** explicit base-class writes (`object.__setattr__`,
`__dict__`), crafted pickles and module monkeypatching. Same-process Python
code is not sandboxed; the algebra's revalidation limits what such a value
can do, but no constructor-level guarantee covers it.

## 5. Deliberate interpretations (for review)

1. `PTier`/`PrincipalKind` are plain `Enum`, not the design sketch's
   `(str, Enum)`, so a tier or kind never equals a bare string. Values and
   names are unchanged.
2. Only schema v1 and vocabulary v1 are constructible, because action types
   can only be validated against a known vocabulary. The mismatch branches of
   `leq`/`meet` are therefore reachable only by out-of-contract values; they
   still return not-leq/⊥ as the design specifies.
3. Tier consistency is a constructor invariant (Human Owner decision for
   this phase). The meet stays closed: types in the intersection have
   floor ≤ both ceilings, so ≤ the minimum.
4. Vocabulary v1 and its T_floor are pinned in this package, mirroring the
   Permission Engine without importing or changing it; a read-only test
   guards drift. Publishing a versioned vocabulary is CR-02.
5. Objective ids reuse the agent_id identifier rules (the design does not
   specify a charset; this is the strict choice).
6. `expires_at` must carry `timezone.utc` itself; an equal instant in
   another offset is rejected, not normalized.
7. JSON serialization is deterministic (`action_types` sorted, `Z` times).
   Deserialization is not supported: dicts/strings are rejected for typed
   fields, so `model_validate_json` fails closed.

## 6. Threat model and coverage

Hostile matrix A-01..A-54 plus X-02..X-15, F-01 and F-05 are in
`tests/test_v0251_hostile_authority_algebra.py`. Algebraic laws (reflexive,
antisymmetric, transitive, meet commutative/associative/idempotent, lower
bound, greatest lower bound, partial-not-total, PO-01 as a `leq` property)
run over a deterministic universe of 513 scopes + ⊥ (5 tiers × 57
tier-consistent action subsets × 3 objectives × 3 expiries) and 6000
seeded-random triples (`random.Random(20260924)`). No new dependency.

## 7. Repository guard change

`scripts/check_v025_design_contract.py` repository checks were made
phase-aware (Human Owner decision): the allowlist is now the exact v0.2.5.1
file set (the committed design artifacts are no longer changeable); `app/`
changes are allowed only under `app/authority_contracts/`; the v0.2.5.1
contract classes may exist only in that package; later-stage classes
(`DelegationRecord`, `RootAuthorization`, `RedelegationPolicy`,
`DelegationRequest`, `DelegationParentRef`, `RevocationRecord`,
`AuthorityEvaluation`, `SystemPolicyCeiling`, stores/engines) remain banned
everywhere; `app/delegation` and `app/authority` remain forbidden. Design
artifact checks are unchanged. They are now labelled as historical
design-checkpoint assertions and backed by a content comparison with
`1e242b8`. The checker also requires this document's phase-status lines (§0).

## 8. Absent by design (deferred)

- v0.2.5.2 — DelegationRequest/Record, RootAuthorization, RevocationRecord,
  RedelegationPolicy, in-memory trusted store, check-not-clip issuance.
- v0.2.5.3 — SystemPolicyCeiling, lineage resolver, evaluator,
  `AuthorityEvaluation`, reason codes/outcomes, trusted-clock effectiveness,
  lifecycle history, required-tier (T_class) mapping.
- v0.2.5.4 — hostile delegation benchmark over the full threat matrix.
- v0.2.5.5 — durable store, migration, CR-01..CR-05 integration.
- v0.2.6 — Context Broker and future dimensions.

Also absent: database models, Alembic revisions, Action/ActionPlan/
orchestrator/Permission/Approval/Budget/Executor changes, principal
authentication, provider/model calls, network access, ToolAdapters, P5
execution, owner adoption. CC-01 (requester-bound approval) and CC-02
(semantic denial persistence) are not addressed and remain BLOCKING.
