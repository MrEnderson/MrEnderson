# Jarvis OS v0.2.3 — Provider Router + Cost / Health / Fallback Policy

**Phase:** v0.2.3 — implementation
**Status: IMPLEMENTATION CANDIDATE, hostile-reviewed, on branch `v0.2.3/provider-router`.**
**This is NOT frozen, NOT promoted to `master`, and NOT remotely preserved.**
`master`/`origin/master` remain at the v0.2.2 candidate commit
(`83678171c9d28981d1c415e566a8ff802a7ad0af`); promotion/preservation of v0.2.3,
if authorized, is a separate later step this document does not perform or
claim.
**Predecessor:** v0.2.2 (`83678171c9d28981d1c415e566a8ff802a7ad0af`, "Jarvis OS v0.2.2 — provider
registry and capability metadata candidate", promoted to `master`)
**Relationship to v0.2.0:** implements the router portion of
`docs/V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md`'s `provider_rules` (which already
named `ProviderHealth`/`ProviderSelection` as future entities and stated
`fallback_may_weaken_privacy_or_permission_or_budget_policy: false`). That
contract is a protected target — this phase changes no line of it.
**Relationship to v0.2.2:** additive only. `ProviderRegistry`/`ProviderDefinition`/
`ModelDefinition`/`catalog.py` are used exactly as they are — **zero changes**
to any file under review in the v0.2.2 candidate preservation. The router is
a new, read-only consumer of that registry.

## Central invariant

> **The Provider Router may select computational capability. It may never
> grant authority.**

A `ProviderSelectionRecord` is a proposed computational destination for an
already-authorized model invocation. It authorizes nothing: not a tool, not
filesystem/browser/network access, not email/publishing, not money movement,
not installs, not privileged OS access, not credentials, not a business
action, not an approval bypass, not a permission tier, not delegation, not
self-modification. `app/decision_intelligence/{tool_adapters,tool_registry}.py`,
the Permission Engine, and the Approval Engine remain the only sources of
execution authority in this codebase, and this phase does not touch any of
them.

## Non-goals (explicitly out of scope for v0.2.3)

- Invoking a provider (`generate()`/`stream()`) — the router never calls one.
- A real OpenAI/Anthropic/Tavily integration, network access, or credentials.
- Live health checks or live pricing lookups — health and cost are
  deterministic, Jarvis-supplied snapshots, not live measurements.
- A durable `ProviderSelectionRecord`/`ModelInvocation` audit trail — that is
  v0.2.7's durable-invocation phase. v0.2.3's result is an in-memory value
  returned to the caller, never persisted by this package.
- An explicit multi-candidate fallback *chain* baked into one routing call
  (see "Fallback semantics" below for why, and what replaces it).
- A `LOCAL_PREFERRED` privacy tier, latency-based routing, or any
  provider/model "quality"/"best" ranking (see "Deliberately deferred").
- Any change to `ProviderRegistry`, `ProviderDefinition`, `ModelDefinition`,
  or `catalog.py` (v0.2.2 stays exactly as promoted).
- v0.2.4+ (Agent Identity/Delegation), Context Broker, Credential Broker.

## Trust classification

**Trusted control data** (Jarvis-controlled, used for routing decisions):
- The v0.2.2 `ProviderRegistry`'s pinned `ProviderDefinition`/`ModelDefinition`
  snapshots (identity, `enabled`, capabilities — read via the existing,
  already-hostile-reviewed registry/catalogue APIs, never re-read from a live
  provider object).
- `ProviderRoutingRequest` — constructed by trusted calling code, not by a
  provider or model.
- `ProviderLocalitySnapshot`, `ProviderHealthSnapshot`, `ProviderCostSnapshot`
  — deterministic, Jarvis-supplied-at-call-time mappings (see "Snapshot
  design" below). For v0.2.3 these are synthetic/test-constructed; a future
  phase may wire them to a real (still Jarvis-controlled, never
  provider-controlled) health/cost source.
- The router's own optimization policy and deterministic tie-break rule.

**Untrusted** (never influences a routing decision):
- `ProviderResponse.content`/`structured_output`/`provider_metadata` — model
  output and anything a provider claims about itself in a response.
- `ProviderDefinition.metadata`/`ModelDefinition.metadata` — opaque,
  Jarvis-controlled but *uninterpreted* descriptive data (unchanged from
  v0.2.2: `CompatibleModel`-style `extra="forbid"` on every routing output
  type means an authority/selection-shaped key cannot be smuggled through
  even if someone tried to copy metadata into a result — and the router
  never reads provider/model `.metadata` at all).
- Any external document/web content.

## Architecture

```text
Jarvis (trusted caller)
  │
  ▼
ProviderRoutingRequest (frozen, validated)
  │
  ▼
route_providers(registry, request, locality, health, cost, *, optimization, ...)
  │  read-only: registry.list_definitions() / registry.list_models()
  │  read-only: locality / health / cost snapshots
  ▼
per-candidate evaluation (EVERY registered (provider_id, model_id) pair)
  │
  ├── enabled?                    -> PROVIDER_DISABLED
  ├── denied/not-allowed?         -> PROVIDER_DENIED / PROVIDER_NOT_ALLOWED
  ├── capability (provider∩model) -> CAPABILITY_MISMATCH
  ├── locality/privacy            -> LOCALITY_MISMATCH
  ├── health                      -> HEALTH_UNAVAILABLE / HEALTH_UNKNOWN /
  │                                   HEALTH_DEGRADED_NOT_ALLOWED
  └── cost                        -> COST_EXCEEDED / COST_UNKNOWN
  │
  ▼
CandidateEvaluation tuple (ALL candidates, eligible + rejected, with reasons)
  │
  ▼
eligible subset
  │
  ▼
explicit optimization policy (DETERMINISTIC | LOWEST_COST)
  │
  ▼
deterministic tie-break: (provider_id, model_id) lexicographic ascending
  │
  ▼
ProviderSelectionResult (frozen)
  status = SELECTED | NO_ELIGIBLE_PROVIDER
  selected: ProviderSelectionRecord | None
  evaluations: tuple[CandidateEvaluation, ...]
  │
  ▼
STOP — no invocation, no persistence, no authority
```

The router never calls `provider.generate()`/`.stream()`, never calls
`registry.register()`, never mutates the request, and never re-reads a
provider's live `.definition` (it consults only the registry's already-pinned
snapshot, exactly as `catalog.py` does).

## Hard constraints vs. optimization (§38-40 of the originating task)

Hard constraints **eliminate** a candidate; they are never weighted, scored,
or summed with anything else. A disabled or privacy-incompatible provider is
removed from consideration, not penalized and then possibly outscored by a
"good enough" total. There is **no security scoring**: nothing here computes
`privacy = +50, disabled = -100` and sums. The six hard constraints (enabled,
allow/deny, capability, locality/privacy, health, cost) run first and produce
the **eligible set**; only then does an explicit, caller-chosen optimization
policy operate — and only over candidates that already passed every hard
constraint.

Two optimization policies exist for v0.2.3, deliberately minimal (§40 of the
originating task explicitly warns against "BEST"/"SMART"/"QUALITY" scoring
without evidence of need):

- `DETERMINISTIC` — no preference among eligible candidates beyond the final
  tie-break.
- `LOWEST_COST` — **only** candidates with a *known* trusted cost may be
  selected. Among those, the minimum-cost subset wins. **If NO eligible
  candidate has a known cost, `LOWEST_COST` selects nothing and the result
  is `NO_ELIGIBLE_PROVIDER`** — it does **not** silently fall back to an
  arbitrary `DETERMINISTIC`-style pick mislabeled as a cost-based decision.

  **This exact semantic was a hostile-review finding (F-01, second pass):**
  the original implementation *did* silently degrade to a deterministic pick when no
  cost was known, and worse, still stamped the winning record's `reason`
  with `"selected via LOWEST_COST policy..."` — a caller who explicitly
  asked for cost-aware routing had no way to tell, from the result alone,
  that no cost comparison had actually happened. An unknown-cost candidate
  can never be proven cheapest, so — matching the same "unknown = ineligible
  where security relevant" discipline applied to health/locality — it never
  wins `LOWEST_COST`, not even by default when nothing else is available.
  Five concrete cases, all regression-tested
  (`tests/test_v023_hostile_router.py`):

  | Case | Result |
  |---|---|
  | All eligible candidates: cost unknown | `NO_ELIGIBLE_PROVIDER` |
  | A unknown, B known (any value) | B wins, however large B's cost |
  | Both known, equal (`Decimal("1")` == `Decimal("1.00")`) | neutral `(provider_id, model_id)` tie-break |
  | `max_estimated_cost` set | unknown-cost candidates already excluded by the HARD cost constraint before optimization ever runs — `LOWEST_COST` then always has only known-cost candidates to compare |
  | Cost `Decimal("0")` | a legitimate, comparable value — zero is never treated as "unknown" |

Final tie-break is **always** `(provider_id, model_id)` ascending
lexicographic order, applied after optimization narrows (or fails to narrow)
the eligible set to more than one candidate. This ordering is a neutral
determinism device, not a quality judgment — the same discipline v0.2.2's
`list_definitions()`/`list_models()` already established. No code path ever
returns `candidates[0]` off an unsorted/insertion-ordered list; the eligible
set is always sorted first.

## Privacy / locality

`PrivacyRequirement` has exactly two values: `CLOUD_ALLOWED` (no locality
constraint — the default) and `LOCAL_ONLY` (hard constraint: only providers
whose trusted locality is `LOCAL` are eligible). **`ANY` was considered and
rejected as a third value** (per the originating task's explicit request to
analyze this): it would mean exactly the same thing as `CLOUD_ALLOWED`
("no locality constraint"), and carrying two names for one semantic invites
an eventual accidental divergence. A separate `locality_requirement` request
field was likewise rejected as redundant with `privacy_requirement` — one
field, two values, is the whole of what v0.2.3 needs, and having two fields
that could theoretically disagree (`privacy_requirement=CLOUD_ALLOWED` but
`locality_requirement=LOCAL_ONLY`?) is exactly the "ambiguous semantics" the
originating task warned against.

`ProviderLocality` has two values: `LOCAL`, `CLOUD`. A provider's locality
comes from a Jarvis-supplied `ProviderLocalitySnapshot` passed into
`route_providers()` at call time — **not** a new field on `ProviderDefinition`
(a deliberate choice: it keeps v0.2.2's already-hostile-reviewed,
now-promoted `contracts.py`/`registry.py` completely untouched, and treats
locality the same way as health/cost — Jarvis-controlled routing-time trust
data, not identity). A provider absent from the snapshot has **unknown**
locality, which never satisfies `LOCAL_ONLY` (fails closed) and never matters
for `CLOUD_ALLOWED` (no locality constraint to fail).

```text
LOCAL_ONLY, no eligible local provider  -> NO_ELIGIBLE_PROVIDER (never cloud fallback)
```

This is enforced structurally, not by a special "don't fall back" check:
there is no separate fallback code path at all (see below), so there is
nothing for a cloud provider to fall back *into*.

## Health

`HealthState`: `HEALTHY`, `DEGRADED`, `UNAVAILABLE`. A fourth state,
"unknown," is represented by **absence** from the `ProviderHealthSnapshot`
rather than an explicit enum member — this makes "no trusted health
information was supplied for this provider" structurally distinct from "a
trusted source explicitly reported some value," and routes both to the same
fail-closed `HEALTH_UNKNOWN` reason code without needing a sentinel enum
member that a construction-time validator would otherwise have to police.

Semantics: `HEALTHY` → eligible. `UNAVAILABLE` → always ineligible.
`DEGRADED` → ineligible **unless** the caller explicitly passes
`allow_degraded_health=True` to `route_providers()` (default `False`); when
allowed, `DEGRADED` and `HEALTHY` are equally eligible — there is no
`HEALTHY` > `DEGRADED` *ranking*, only an eligibility gate (§21 of the
originating task: prefer filtering over ranking). Health is never
self-declared: `route_providers()` takes a `ProviderHealthSnapshot` argument
and never reads `ProviderResponse`/model output/opaque metadata for health
information — there is no code path that could.

No live network health checks exist or are planned for v0.2.3; snapshots are
deterministic, caller-constructed data (tests build them directly; a future
phase may wire a real, still-Jarvis-controlled health source without
changing this module's public shape).

**Known limitation — health granularity (finding F-02, retained
deliberately, documented prominently per the second hostile-review pass):
`ProviderHealthSnapshot` is keyed by `provider_id` only, not
`(provider_id, model_id)`.** A provider with multiple models where only
ONE model is actually broken cannot express that — the provider-level
`HEALTHY` entry makes every one of its models pass the health hard
constraint, including the broken one, and the deterministic
`(provider_id, model_id)` tie-break may then select it purely because its
`model_id` sorts first (demonstrated: a provider with models `model-broken`
and `model-good`, both otherwise identical, provider-level `HEALTHY` —
`model-broken` is selected, because `"model-broken" < "model-good"`
lexicographically, and nothing in the health model contradicts that
choice). **v0.2.3 does not claim per-model health has been established for
a selected model — only that its PROVIDER'S health, as reported, permits
routing to it.** This was a deliberate scope decision (do not expand to
`(provider_id, model_id)`-granular health without a demonstrated need,
matching the same "avoid unnecessary complexity" discipline applied
throughout this phase), not an oversight — but it is a real limitation a
future phase should close if per-model outages become a genuine operational
concern. `ProviderLocalitySnapshot` has the exact same provider-level-only
granularity and the exact same limitation (a provider that could
theoretically run some models locally and others in the cloud cannot
express that split in v0.2.3). `ProviderCostSnapshot`, by contrast, is
already `(provider_id, model_id)`-granular and does not share this
limitation.

## Cost

Cost is **inference cost estimation only** — never business-spending
authority (R20). `ProviderCostSnapshot` maps `(provider_id, model_id)` to a
`decimal.Decimal` (not `float`, to sidestep binary floating-point comparison
surprises for a security-relevant ceiling check) representing an estimated
total cost in USD for one inference call. This is deliberately **not** the
existing `app/config/pricing.py` (`estimate_cost_usd`) machinery: that
function needs actual `input_tokens`/`output_tokens`, which do not exist
before a call is made, and it reads `Settings`/environment configuration —
neither fits a pre-invocation, offline, deterministic router. v0.2.3's cost
model is an independent, router-owned, Jarvis-supplied snapshot; no
`os.environ`/`getenv` access exists anywhere in the router.

A cost value is validated at snapshot construction: it must be finite (no
`NaN`, no `+Infinity`/`-Infinity` — `Decimal` supports constructing both if
asked, so this is checked explicitly, not assumed) and non-negative. **Zero
is a legitimate cost** (§36 of the originating task) and is distinguished
from "unknown" by simple presence: a `(provider_id, model_id)` key absent
from the snapshot has unknown cost; a key present with value `Decimal("0")`
has a known cost of zero.

`ProviderRoutingRequest.max_estimated_cost: Decimal | None` is the only cost
*constraint*. When `None` (the default), cost never affects eligibility —
known or unknown, any cost passes. When set, a candidate whose cost is
**unknown** is ineligible (`COST_UNKNOWN` — an unproven cost cannot be
proven within a stated ceiling, so it fails closed) and a candidate whose
known cost exceeds the ceiling is ineligible (`COST_EXCEEDED`).

Provider-supplied cost claims (`{"cost": 0, "free": true, "ignore_budget":
true}` in opaque metadata, or anything in `ProviderResponse`) have **zero**
effect — the router never reads `ProviderDefinition.metadata`,
`ModelDefinition.metadata`, or any `ProviderResponse` field for cost, only
the caller-supplied `ProviderCostSnapshot`.

## Allow / deny

`ProviderRoutingRequest.allowed_provider_ids: frozenset[str] | None` (`None`
= no allowlist restriction) and `denied_provider_ids: frozenset[str]` (default
empty). **Deny dominates allow**: a provider in `denied_provider_ids` is
always ineligible (`PROVIDER_DENIED`), even if also present in
`allowed_provider_ids`. If `allowed_provider_ids` is not `None`, a provider
absent from it is ineligible (`PROVIDER_NOT_ALLOWED`). An ID naming a
provider that isn't actually registered has no special handling needed and
no ambiguity: it simply never matches any real candidate's `provider_id`
during the per-candidate evaluation, so it can never *broaden* eligibility —
only an ID that matches a real, otherwise-eligible candidate has any effect,
and only in the fail-closed direction (adding to `denied_provider_ids` can
only remove candidates; a nonexistent ID in `allowed_provider_ids` removes
nothing it wasn't already going to remove). Every ID in both sets is
validated with the same `validate_identifier` policy v0.2.1/v0.2.2 already
use for `provider_id` (reject blank, control characters, hostile whitespace,
length > 256), and each set is capped at 256 entries (§59, a simple bound
against an unbounded attacker/caller-controlled routing request — see
"Resource governance" below for what remains unbounded). Membership is
plain, case-sensitive string equality — `"OpenAI"` and `"openai"` are
different provider IDs, exactly matching the registry's own case-sensitive
identity (no normalization is applied anywhere in this codebase's provider
identity handling, so the router introduces none either). An
`allowed_provider_ids` set that is present but empty (`frozenset()`, as
distinct from `None`) means exactly what it says — no provider is allowed —
and every candidate is `PROVIDER_NOT_ALLOWED`; this is ordinary, correct
fail-closed set-membership behavior, not a special case the router needs to
detect.

## Capability

Unchanged from v0.2.2: effective capability is `provider.capabilities &
model.capabilities` — **never a union** — reusing
`app.providers.catalog.effective_capabilities` directly rather than
reimplementing it. `ProviderRoutingRequest.required_capabilities` must be a
subset of a candidate's effective capabilities (`required ⊆ effective`,
exact containment) or the candidate is `CAPABILITY_MISMATCH`. A model
advertising a capability its provider doesn't, or vice versa, still yields
only the intersection — this is v0.2.2's already-hostile-reviewed guarantee,
inherited unchanged.

## Fallback semantics

**v0.2.3 does not implement a fallback chain.** No `FallbackPolicy` enum, no
ordered list of "next best" candidates baked into one `ProviderSelectionResult`.
This was a deliberate design decision, not an oversight — reasoning:

1. An ordered fallback chain returned from one routing call is itself a form
   of ranking (§41 of the originating task makes exactly this observation),
   and this phase's whole design discipline is "hard constraints eliminate,
   they never rank/score."
2. `route_providers()` is cheap, pure, and deterministic. If a selected
   provider later turns out to be unusable (the future invocation layer
   discovers a failure), the correct action is to call `route_providers()`
   **again** with an updated `ProviderHealthSnapshot` (marking the failed
   provider `UNAVAILABLE`), not to have pre-authorized a fallback chain that
   might apply stale health/cost information by the time it's used.
3. This closes the "fallback privilege escalation" attack class
   *structurally*, not by carefully constraining a fallback code path: there
   is no fallback code path, so there is nothing for a more-capable/wrong-
   locality candidate to be promoted into. Every routing call — first
   attempt or "fallback" retry — runs through the exact same hard-constraint
   pipeline with no special case.
4. Retrying invocation itself (calling a newly-selected provider after a
   prior one failed) is out of scope for v0.2.3 entirely (routing produces a
   proposed destination; it never invokes). That retry-execution loop
   belongs to a future durable-invocation phase (v0.2.7), which does not
   exist yet and is not implemented here.

`fallback_may_weaken_privacy_or_permission_or_budget_policy` (already `false`
in the v0.2.0 protected contract's `provider_rules`) holds trivially and
structurally: there is no fallback mechanism to weaken anything with.

**Precise statement of what "Cost / Health / Fallback Policy" (this phase's
own name) means, since the name could otherwise be misread**: fallback
policy in v0.2.3 means **fallback is performed by a fresh routing decision
under unchanged hard constraints and updated trusted state** — a new call to
`route_providers()` with the same `ProviderRoutingRequest`'s hard
requirements (capabilities, privacy, allow/deny, cost ceiling) and only the
trusted health/cost snapshot updated to reflect what's now known. It does
**not** mean "this module executes automatic fallback" — nothing in
`router.py` retries, chains, or reroutes on its own initiative; every call
is a single, independent, complete evaluation.

**Whose responsibility it is that a re-route preserves the original hard
requirements**: v0.2.3 cannot enforce this across calls it doesn't see (it
has no memory of a "previous" routing request — each call is independent
and stateless) — but the caller-side discipline this contract expects is
explicit: a re-routing request issued after a provider failure must reuse
the SAME hard requirements (`required_capabilities`, `privacy_requirement`,
`allowed_provider_ids`/`denied_provider_ids`, `max_estimated_cost`) as the
original request, changing only the trusted health/cost snapshot to reflect
the new information. An updated health snapshot alone is never, by itself,
authorization to relax `privacy_requirement` to `CLOUD_ALLOWED`, drop a
capability requirement, or raise `max_estimated_cost` — any such change is a
DIFFERENT routing decision made by whatever higher-level policy decided to
make it, not something health information implies or grants.

## Trust boundaries for snapshot producers

`ProviderHealthSnapshot`/`ProviderCostSnapshot`/`ProviderLocalitySnapshot`
are trusted INPUTS to `route_providers()` — this module consumes them, it
does not establish who is authorized to construct them with what values.
Stated explicitly, since the boundary matters and this phase does not
implement it:

- **Health**: v0.2.3 does not define who may produce a
  `ProviderHealthSnapshot` or from what evidence. A provider's own output
  (`ProviderResponse`, or anything in its `metadata`) is categorically NOT
  a trusted health source — see "Health" above; there is no code path that
  could even read it for this purpose. A future health-monitoring
  subsystem, whatever form it takes, must establish its OWN trust boundary
  (what evidence it accepts, who/what may run it, how it's protected from
  a hostile/buggy provider's influence) before its output can safely
  become a `ProviderHealthSnapshot` — that governance question is
  unanswered by this phase and deliberately deferred, not silently assumed
  solved.
- **Cost**: v0.2.3 does not prove vendor pricing is accurate — a
  `ProviderCostSnapshot` is only as trustworthy as whatever constructed it.
  A provider cannot self-price (see "Cost" above); a future pricing
  ingestion pipeline needs its own separate trusted path (analogous to, but
  NOT the same mechanism as, `app.config.pricing`'s post-invocation,
  environment-configured pricing table — see "Cost" above for why that
  specific mechanism doesn't fit here).
- **Locality**: a cloud provider cannot make itself `LOCAL` through
  metadata, a response claim, or any other self-reported channel — the
  `ProviderLocalitySnapshot` is Jarvis-controlled input, full stop.
  Whoever/whatever constructs it in a future wiring phase is the trust
  boundary; v0.2.3 defines the type and its semantics, not its governance.

## Selection record contents (no authority)

`ProviderSelectionRecord` fields: `selection_id`, `routing_request_id`,
`provider_id`, `model_id`, `effective_capabilities`, `trusted_health`,
`trusted_cost` (the winning candidate's resolved cost, or `None` if
unknown), `reason` (a short string built only from Jarvis-controlled routing
facts — optimization policy name, candidate counts — never from opaque
metadata or model output), `policy_version`, `created_at`. `frozen=True,
extra="forbid"` (the same `CompatibleModel` pattern from v0.2.2) means
`permission`/`approval`/`authorization`/`tool_access`/`execute`/`credential`/
`api_key`/`selected`/`recommended`/`priority`/`rank`/`routing_score` cannot
be attached to this type without an explicit, reviewed field addition.
There is no `.authorize()`/`.execute()`/`.approve()` method on it or on
`ProviderSelectionResult` — nothing converts a selection into an action.

"Snapshot provenance" for v0.2.3 means embedding the exact resolved
`trusted_health`/`trusted_cost` values that were actually used for the
winning candidate directly in the record — **not** a persistent
snapshot-id/reference system, because no durable storage layer exists yet
(that's v0.2.7's durable `ModelInvocation` phase). A future phase that adds
durable persistence can add a real snapshot-id reference without breaking
this shape.

`ProviderSelectionResult` (not just the record) additionally carries
`optimization: OptimizationPolicy` and `allow_degraded_health: bool` —
**the actual policy inputs `route_providers()` applied for that call**
(finding F-05, second hostile-review pass). Before this fix, these two
values — passed as ordinary function keyword arguments outside
`ProviderRoutingRequest` — were recorded nowhere on a `NO_ELIGIBLE_PROVIDER`
result (which has no `selected` record to embed them in), so two calls with
an identical `routing_request_id` and request that differed only in these
call-site arguments were indistinguishable after the fact. They are now
present on every result regardless of status, closing that gap. This was
considered as a possible argument for moving `optimization`/
`allow_degraded_health` INTO `ProviderRoutingRequest` itself (so all policy
lives in one immutable, request-scoped place) — deliberately not done:
`ProviderRoutingRequest` represents WHAT is required (capabilities, privacy,
cost ceiling, allow/deny), a property of the task being routed; `optimization`/
`allow_degraded_health` are HOW the router should choose among candidates
that already satisfy what's required — a distinct concern, and folding them
together would make a single request type carry two different kinds of
information. Recording the actual values used on the *result* (this fix)
achieves the auditability goal without conflating the two.

**Structural self-consistency of the routing output types** (finding F-03,
second hostile-review pass) — previously, none of `route_providers()`'s own
correctness was reflected as a constraint on the TYPES themselves;
`ProviderSelectionResult`/`CandidateEvaluation` could be directly
constructed (bypassing the router entirely) into internally contradictory
states: `status=SELECTED` with `selected=None`, `status=NO_ELIGIBLE_PROVIDER`
with a populated `selected`, a `selected` record that matches no entry in
`evaluations` (or matches one marked ineligible), duplicate `evaluations`
entries for the same `(provider_id, model_id)`, or a `CandidateEvaluation`
claiming `eligible=True` while still carrying rejection `reason_codes`. Now
enforced by `model_validator`s on both types — construction itself raises
`ValidationError` for any of these, regardless of what code path built the
instance. This matters because `route_providers()` constructing these
values correctly was never itself proof that the TYPE couldn't be misused
elsewhere — e.g. by a future durable-persistence layer deserializing a
stored result, which is exactly the kind of "another caller reconstructs
this type" scenario the hostile review asked about.

## Determinism

`route_providers()` is a pure function of its arguments: the same registry
state, request, and snapshots always produce the same
`ProviderSelectionResult` (except `selection_id`, which is a fresh UUID per
call by design — every other field, including candidate order and the
winning `provider_id`/`model_id`, is fully determined by the inputs).
Registering the same providers/models in a different order produces the same
selection (inherits v0.2.2's `list_definitions()`/`list_models()` sorted
order, then applies the same explicit tie-break on top). No dict insertion
order, set iteration order, or object identity ever influences the result.
`routing_request_id` carries no caching/identity semantics — v0.2.3 has no
persistence layer, so two calls sharing the same `routing_request_id`
(intentionally or by caller error) are evaluated completely independently;
the router never merges, caches, or conflates decisions by that ID.
Uniqueness of `routing_request_id`, if it matters to a caller, is that
caller's responsibility to maintain — `route_providers()` does not enforce
or rely on it being unique.

`optimization` is validated to be a genuine `OptimizationPolicy` member
BEFORE any branch that depends on it (finding F-04, second hostile-review
pass): the original implementation branched with
`if optimization is OptimizationPolicy.DETERMINISTIC: ... else: <LOWEST_COST
behavior>`, so any non-member value — a typo string like `"BEST"`, an
integer, `None` — silently fell through to the `LOWEST_COST` branch instead
of being rejected, exactly the "unrecognized mode falls through toward
success" defect `app/providers/fake_provider.py`'s `_require_valid_mode`
exists to prevent for `FakeProviderMode`. `route_providers()` now raises
`TypeError` immediately for a non-`OptimizationPolicy` `optimization`
argument, the same fail-loudly discipline.

**Empty `required_capabilities` (§15 of the originating task)**: means
"any registered, otherwise-eligible model" — the same interpretation
v0.2.2's `find_compatible_models` already uses for an empty capability
query ("all eligible catalogue entries," never "recommended models"). This
is a deliberate choice, not an accidental default: `frozenset() ⊆
effective_capabilities` is true for every candidate, so the capability hard
constraint simply never excludes anything when no capability was actually
required — every OTHER hard constraint (enabled, allow/deny, locality,
health, cost) still applies in full. A caller that wants to route to a
model regardless of what it can do (e.g. purely by cost, or purely by
locality) is legitimately expressing that by leaving
`required_capabilities` at its default; a caller that wants any given
routing call to require at least one real capability must say so
explicitly.

## Mutation isolation

- **Registry**: `route_providers()` calls only `registry.list_definitions()`
  and `registry.list_models()` — the same read-only catalogue APIs v0.2.2's
  own `catalog.py` uses. It never calls `.register()`. v0.2.2's identity
  hardening (no `replace=True`, no hidden update/upsert/overwrite path) is
  not reintroduced or weakened by this phase; the router adds no new way to
  mutate a `ProviderRegistry`.
- **Provider**: no provider method is ever called — not `.generate()`, not
  `.stream()`, not any hypothetical `.health_check()` the `AIProvider`
  protocol doesn't even define. A hostile provider whose `generate()` raises
  `AssertionError` on any call is used in regression tests; the router never
  triggers it (invocation count 0 across every routing operation).
- **Request**: `ProviderRoutingRequest` is `frozen=True`; a routing call
  never reassigns any of its fields and never mutates a caller-supplied
  mutable object (allow/deny sets and required-capabilities are frozensets;
  the router builds its own internal working copies rather than aliasing
  caller-held collections).

## Concurrency and consistency

`route_providers()` reads a `ProviderRegistry`'s in-memory state, which
v0.2.2 already documents as **not thread-safe** (no lock). This phase makes
no new concurrency claim: "deterministic" here means "the same snapshot of
inputs always yields the same output within one synchronous call," never
multi-thread, multi-process, or distributed consistency. A caller needing a
coherent registry+health+cost view across concurrent access must serialize
that access itself, exactly as v0.2.2 already requires for the registry
alone. Health/cost snapshots are ordinary Python objects with the same
caveat — nothing here adds a lock.

## Resource governance

Bounded in this phase: `allowed_provider_ids`/`denied_provider_ids` (256
entries each, validated identifiers). **Still unbounded, honestly
documented** (matching v0.2.1/v0.2.2's existing stance, not a new gap this
phase introduces): the number of models a provider registers (a v0.2.2
concern, unchanged), the size of a `ProviderHealthSnapshot`/
`ProviderCostSnapshot`/`ProviderLocalitySnapshot` a caller constructs, and
`required_capabilities` (already implicitly bounded by `ProviderCapability`
having a fixed 9-member vocabulary). No DoS-resistance is claimed for any of
these.

## Snapshot key validation (considered, not implemented)

The second hostile-review pass explicitly attacked
`ProviderHealthSnapshot`/`ProviderLocalitySnapshot`/`ProviderCostSnapshot`
keys with hostile strings (empty, whitespace, control characters, overlong,
wrong types) and unregistered ("ghost") provider/model identities. **No
code change resulted, deliberately**: every registered `provider_id`/
`model_id` the router ever looks up is already guaranteed clean by v0.2.1's
`validate_identifier` (enforced at `ProviderDefinition`/`ModelDefinition`
construction, before registration is even possible) — Python dict lookup is
exact string equality with no normalization, so a snapshot key that doesn't
byte-for-byte match a real, already-clean `provider_id`/`model_id` simply
never matches anything. A ghost/malformed snapshot entry is inert: it can
never broaden eligibility (there is no candidate for it to apply to) and
can at most fail to narrow something that was never going to be narrowed
anyway. Adding identifier-syntax validation to snapshot keys would be
validating data that is already provably harmless if malformed — real
defense-in-depth would cost real complexity for a threat this design
already structurally closes. (Confirmed by direct testing, not merely
asserted: a `ProviderHealthSnapshot` containing a `"ghost-provider"` entry
for an unregistered provider produces zero extra candidates and zero effect
on the real candidate's evaluation.)

## Pydantic bypass paths (carried forward from v0.2.1/v0.2.2, unchanged)

`.model_copy(update=...)` and `.model_construct(...)` bypass both field
validators AND the new `model_validator`s (F-03) on every v0.2.3 routing
contract type, exactly as already documented for v0.2.1's `ProviderRequest`/
`ProviderResponse` (`docs/V0_2_1_PROVIDER_ABSTRACTION.md`, "Deep
immutability"; `tests/test_provider_hardening.py`). This is a real,
unsolved Pydantic-level limitation, not something v0.2.3 claims to have
fixed — confirmed still true here too
(`tests/test_v023_hostile_router.py` does not currently assert this
directly since it's identical to the already-documented v0.2.1 behavior,
not a new finding). `app/providers/router.py` and `routing_contracts.py`
never use either bypass API internally (verified by direct source search)
— only the normal constructors, so this limitation is a caller-facing
caveat (future code building these types MUST use the normal constructor),
not a production defect.

## Static checker blind spots (honest disclosure, §41 of the originating task)

`scripts/check_v023_router_contract.py` is defense-in-depth, not proof, and
was itself hostile-reviewed for blind spots rather than trusted because it
returns `OK`:

- Its forbidden-call/forbidden-import AST checks match specific literal
  names (`.generate(`, `.stream(`, `.register(`, `.health_check(`;
  `tool_adapters`/`permission`/`approval`/etc. substrings). A rename —
  e.g. a hypothetical `.invoke_provider(` instead of `.generate(`, or a
  reintroduced registry-mutation parameter named `force` instead of
  `replace` — would NOT be caught by the checker. This is compensated by
  the hostile TEST suite (`tests/test_v023_hostile_router.py`), which
  verifies actual runtime behavior (invocation count, registry state
  equality) rather than source-text shape, but the checker itself does not
  independently prove the absence of a differently-named equivalent.
- The checker's `no_authority_fields` JSON entry is documentation only —
  it is never cross-checked against the actual field lists of
  `ProviderSelectionRecord`/`CandidateEvaluation`. If a future contributor
  added a `permission` field to one of these types, the checker would not
  detect it; only the hostile test suite's explicit
  `pytest.raises(ValidationError)` constructions for that exact field name
  would (and would then start failing to raise, which is a visible test
  failure, not a silent gap).
- The live behavioral smoke-check added in this pass (LOWEST_COST-with-
  no-known-cost, malformed-optimization-rejected, policy-input-recorded)
  closes the specific F-01/F-04/F-05 regression classes with a real call to
  `route_providers()`, not just a JSON assertion — but it exercises one
  narrow scenario per finding, not the full hostile test matrix. The
  checker is not, and is not intended to be, a substitute for running
  `tests/test_v023_hostile_router.py`.

## Deliberately deferred (not in v0.2.3)

- `LOCAL_PREFERRED` privacy tier — would require a locality-based
  *optimization* dimension (not a hard constraint, since cloud would remain
  eligible), which is exactly the kind of "quality"/preference scoring axis
  §39-40 of the originating task asks this phase to avoid building without
  a demonstrated need. `CLOUD_ALLOWED`/`LOCAL_ONLY` cover every hard
  constraint this phase actually needs.
- Latency-based routing (`max_latency_class` or similar) — no field, no
  filtering, no optimization based on latency. Documented deferral rather
  than fake precision (§37 of the originating task).
- Multi-candidate fallback chains — see "Fallback semantics" above.
- Live health checks, live pricing/billing lookups, any network call.
- Durable `ProviderSelectionRecord` persistence / audit chain (v0.2.7).
- Agent Identity, Delegation, Context Broker, Credential Broker (v0.2.4-6).
- Any change to registry/catalogue concurrency (still not thread-safe).
- Any resource limit on health/cost/locality snapshot size, or on the
  number of models per provider.
- `(provider_id, model_id)`-granular health/locality — see "Known
  limitation — health granularity" (F-02) above.
- Snapshot key identifier-syntax validation — see "Snapshot key
  validation" above (considered, concluded unnecessary, not a gap).

## Hostile review

**Second (independent) hostile-review pass — 5 findings, all remediated in
this branch, zero remaining unaddressed:**

| ID | Severity | Summary | Fix |
|---|---|---|---|
| F-01 | MEDIUM | `LOWEST_COST` with no known-cost candidate silently degraded to an arbitrary pick mislabeled as cost-based in `reason` | `app/providers/router.py`: `LOWEST_COST` now returns no candidate (→ `NO_ELIGIBLE_PROVIDER`) when nothing has a known cost |
| F-02 | LOW (documentation) | Health/locality granularity (provider-level only) not prominently disclosed; a healthy provider's specific broken model could still be selected | Documented prominently in "Health" above; deliberately not expanded to model-level (no demonstrated need) |
| F-03 | MEDIUM | `ProviderSelectionResult`/`CandidateEvaluation` had no structural self-consistency validation (contradictory status/selected, mismatched/duplicate evaluations, eligible-with-reasons all directly constructible) | `app/providers/routing_contracts.py`: `model_validator`s added to both types |
| F-04 | HIGH | An unrecognized `optimization` value (typo, wrong type) silently fell through to the `LOWEST_COST` branch instead of being rejected | `app/providers/router.py`: `route_providers()` now raises `TypeError` for a non-`OptimizationPolicy` `optimization` argument, before any branch |
| F-05 | LOW-MEDIUM | `ProviderSelectionResult` never recorded the actual `optimization`/`allow_degraded_health` policy inputs used, especially absent on `NO_ELIGIBLE_PROVIDER` results | `app/providers/routing_contracts.py`/`router.py`: both fields added to `ProviderSelectionResult`, always populated |

See `tests/test_v023_hostile_router.py` for the executed hostile scenarios
(cost manipulation, health spoofing, fallback privilege escalation,
`LOCAL_ONLY` leakage, disabled-provider revival, unsupported capability,
capability union attack, opaque metadata ranking attack, deterministic tie,
insertion-order attack, router-output-as-permission, provider invocation,
registry mutation, request mutation, unknown privacy/health/cost, invalid
cost, denied-provider override, provider shape-shifting, no-eligible-
provider, deterministic repeated routing, plus the five findings above'
regression coverage) and the machine-readable
`docs/v0.2.3_provider_router_security_contract.json` /
`scripts/check_v023_router_contract.py` for the structural invariants this
document describes in prose.
