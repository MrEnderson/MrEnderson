# Jarvis OS v0.2.2 — Provider Registry + Capability Metadata

**Phase:** v0.2.2 — implementation
**Status:** IMPLEMENTED (candidate, on branch `v0.2.2/provider-registry-capabilities`, not merged)
**Relationship to v0.2.0:** implements the registry/capability portion of
`docs/V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md` §5, §11 (§5 "Provider
Registry"; §11 "Provider Capabilities"). That contract is a protected
target — this phase changes no line of it.
**Relationship to v0.2.1:** additive/evolutionary. Extends
`app/providers/registry.py`'s existing `ProviderRegistry` (does not
replace it) and adds one new module, `catalog.py`. No v0.2.1 hostile-
reviewed invariant is weakened — see "v0.2.1 regression" below, and the
one genuine gap this phase found in v0.2.1 itself (documented in
`docs/V0_2_1_PROVIDER_ABSTRACTION.md`'s "Deep immutability" section) is
fixed, not merely worked around.

## Purpose

A deterministic, vendor-neutral, Jarvis-controlled catalogue of AI
providers, models, and the computational capabilities they declare. It
answers descriptive questions ("which providers are registered", "which
models does provider X have", "which enabled provider/model combinations
declare capability set C") and returns **candidates**, never a selection.
Provider routing/fallback is v0.2.3, not this phase.

```text
Requirement
    |
    v
Capability Catalogue
    |
    +-- candidate A
    +-- candidate B
    +-- candidate C
             |
             X
       NO RANKING
       NO SELECTION
       NO ROUTING
       NO FALLBACK
```

## Security boundary

**Capability metadata describes what computation is available. It never
grants permission to use Jarvis capabilities, tools, credentials, or
external systems.** Concretely and by construction:

- `ProviderCapability` values are all computational description
  (`CODING`, `VISION`, `TOOL_USE`, ...) — none of the vocabulary is or
  ever will be an authority concept (`CAN_SPEND_MONEY`, `APPROVED`,
  `P5_ACCESS` do not exist and cannot be added without a reviewed change
  to this enum).
- Registry membership ≠ authorization; enabled status ≠ permission;
  compatibility ≠ permission; compatibility ≠ selection (§7 Rules 1-6 of
  the originating task's Security Constitution, all still true here).
- `CompatibleModel` (a query result) cannot structurally carry
  `selected`/`recommended`/`preferred`/`routing_score`/`rank`/`priority`/
  `permission`/`approval`/`authority` — `frozen=True, extra="forbid"`
  makes attaching one of these a `ValidationError`, not a silent
  possibility for a future change to introduce accidentally.
- No catalogue/registry operation ever calls `.generate()` on any
  provider — proven, not merely asserted, by hostile tests using a
  provider whose `generate()` raises `AssertionError` on any call and
  whose registration/every catalogue operation still succeeds.
- No catalogue/registry operation imports or touches a ToolAdapter,
  Permission/Approval Engine, credential, network client, or SDK.

## Provider/model identity

Reuses `ProviderDefinition`/`ModelDefinition` from v0.2.1's `contracts.py`
unchanged — no duplicate competing representation was created.

**Model ownership**: every `ModelDefinition.provider_id` must equal the
`provider_id` of the `ProviderDefinition` it's registered under
(`ModelOwnershipError` otherwise) — the same invariant v0.2.1's
`FakeProvider` already enforced at construction, now also enforced at
registry registration. `ModelOwnershipError` was relocated from
`fake_provider.py` to `contracts.py` (re-exported from
`fake_provider.py` unchanged, so existing imports keep working) so
`registry.py` doesn't have to depend on a test-utility module to raise it.

**Model identity namespace**: composite `(provider_id, model_id)` — a
model's simple `model_id` need only be unique *within its own provider*.
Two different providers may each register a model_id `"basic"` without
conflict; chosen because real model ids in this codebase already look
vendor-prefixed (`FAKE_MODEL_ID = "fake/basic"`), and a global namespace
would be needlessly restrictive for a multi-vendor catalogue.

## Registration lifecycle

`UNREGISTERED -> REGISTERED (enabled | disabled)`. Deliberately no
`REMOVED`/unregister state: this phase found no genuine need for runtime
removal, and a mutable unregister operation would create identity/audit
ambiguity this phase doesn't need to solve yet — registration is
process-lifetime additive. Future lifecycle management (health-driven
disable, administrative removal) is deferred, not designed here.

**Atomic registration**: `ProviderRegistry.register(provider, *, models=())`
registers a provider and its models together. Every validation check
(protocol conformance, provider duplicate, model ownership, model
duplicate-within-batch) runs and can raise **before any state is
mutated** — a failed call leaves the registry in exactly the state it was
in before the call, proven by a hostile test registering 20 valid models
plus one ownership-invalid model and asserting the registry contains
nothing afterward. "Atomic" here means exactly that and nothing more:
validation-before-mutation within one synchronous Python call on a plain
`dict`-backed registry — **not** database-transaction atomicity, **not**
multi-thread atomicity, and **not** multi-process/distributed atomicity.
`ProviderRegistry` is **not thread-safe**: it holds no lock, and a real
concurrent `register()`/read from a second thread is unguarded
interleaving on a plain `dict`, exactly like `ToolAdapterRegistry` and
`ToolRegistry` before it. A caller that needs concurrent registration
must serialize access itself (e.g. one registry per process, or an
external lock) — adding a lock here is a future-phase decision, not one
this phase's scope requires.

**Duplicate provider**: unconditionally rejected (`DuplicateProviderError`)
— including an identical redefinition, a different enabled status,
expanded or reduced capabilities, different metadata, a different
`provider_type`, a different provider object, or a different model set.
**Duplicate model** (same `model_id` twice within one registration call):
rejected (`DuplicateModelError`). No silent merge, no "newer wins," ever.

**Identity hardening (final v0.2.2 pass): `ProviderRegistry.register()`'s
v0.2.1 `replace=True` administrative-replacement escape hatch has been
intentionally REMOVED for `ProviderRegistry`** — not defaulted off, not
deprecated, removed as a parameter. `replace=True` was, in this exact
shape, an established codebase pattern already present on
`ToolAdapterRegistry` (since the v0.1.3 FROZEN baseline) and `ToolRegistry`
(v0.2.0), and a hostile review confirmed it was never reachable from
provider-supplied data, was atomic, and had no production caller of its
own. But that same review also found v0.2.2 has **no demonstrated
operational requirement** for runtime provider replacement, and
`ProviderRegistry`'s stated purpose is to establish **stable**
Jarvis-controlled computational identities — not to be a mutable
configuration store. **Provider identity is therefore process-lifetime
stable after registration**: once a `provider_id` is registered in a
given `ProviderRegistry` instance, no ordinary call can redefine its
provider object, enabled status, capabilities, metadata, `provider_type`,
or model catalogue. There is deliberately no alternate path
(`update_provider`/`replace_provider`/`upsert_provider`/`force_register`)
— a future controlled configuration lifecycle, if one is ever needed,
must be designed explicitly rather than implemented as ordinary
re-registration. **This change is scoped to `ProviderRegistry` only**;
`ToolAdapterRegistry` and `ToolRegistry` are untouched and keep their own
`replace=True`, which real production/test call sites do exercise (e.g.
disabling a registered tool adapter).

**Models are not read from a live provider property** — unlike
`ProviderDefinition` (read from `.definition` once and pinned), models are
explicit `ModelDefinition` arguments passed directly to `register()`.
There is no live-re-read risk for them to begin with, since the
`AIProvider` protocol has no `.models` property to misread.

## Capability semantics

Vocabulary unchanged from v0.2.1 (`TEXT_GENERATION`, `STRUCTURED_OUTPUT`,
`REASONING`, `CODING`, `VISION`, `EMBEDDING`, `RERANKING`, `STREAMING`,
`TOOL_USE`) — no new value was genuinely needed for this phase.

**Effective capability = intersection, never union**:
`provider.capabilities & model.capabilities` (`catalog.effective_capabilities`,
matching `FakeProvider.generate()`'s identical rule from the v0.2.1
hostile review). A model cannot gain a capability its provider doesn't
declare; a provider's capability does not propagate to every model it
hosts.

**Query matching**: `find_compatible_models(registry, required_capabilities, *, enabled_only=True)`
returns every catalogue entry where `required_capabilities ⊆ effective_capabilities`
— exact containment, not partial match. An empty `required_capabilities`
(the default) returns every administratively eligible entry — "all
eligible catalogue entries," never "recommended models."

**Unknown capability**: `ProviderCapability` is a plain `str` Enum;
constructing it from an arbitrary string (`ProviderCapability("finance.spend_money")`)
raises `ValueError` — there is no fuzzy matching and no path for a
provider-generated string to become a capability value.

## Query behavior

**Deterministic ordering**: `list_definitions()` sorts by `provider_id`;
`list_models(provider_id)` sorts by `model_id`; `find_compatible_models`
sorts by `(provider_id, model_id)`. None of these rely on dict/set
iteration order. A hostile test registers the same definitions in two
different orders across two separate registries and asserts identical
query output order. **This ordering is deterministic presentation order,
not ranking** — nothing in this package ever returns `candidates[0]` as
"the" answer.

**Enabled/disabled**: administrative catalogue state only — never health,
never a security ban, never budget status. `get()`/`list_models()`/
`get_model()` (discovery) can still see a disabled provider's models;
`find_compatible_models(..., enabled_only=True)` (the default) excludes
them. No model-level `enabled` field was added — provider-level `enabled`
is sufficient for this phase (v0.2.1 already distinguishes `get()` from
`get_enabled()` the same way).

**No fallback**: a capability satisfied only by a disabled provider
returns an **empty** result with `enabled_only=True` — never a silent
substitution of an unrelated enabled provider/model.

## Metadata trust

Provider/model `metadata` is Jarvis-controlled descriptive configuration,
deep-frozen (see below), returned as opaque data. A hostile test registers
a provider with `metadata={"approved": True, "permission": "P5", "execute": True, "tool": "finance.spend_money", ...}`
and confirms: the catalogue query result (`CompatibleModel`) has none of
those as real attributes, and the metadata dict itself is retrieved
unchanged as inert data — never interpreted, never promoted to an
authority object.

## Deep immutability (and a v0.2.1 fix)

Building this phase's tests surfaced a real gap in v0.2.1's `deep_freeze`
mechanism: it only ran when a caller **explicitly** passed a dict/list
value — Pydantic doesn't validate `default_factory` values unless
`validate_default=True` is set. The common case (leaving `metadata` at
its empty-dict default) was silently still mutable. **Fixed**: added
`validate_default=True` to the shared `_FROZEN` config in both
`contracts.py` and `failures.py`. See
`tests/test_provider_hardening.py::test_default_valued_dict_fields_are_also_frozen_not_only_explicit_ones`
and the corrected note in `docs/V0_2_1_PROVIDER_ABSTRACTION.md`.

Aliasing is also defended: mutating a `metadata` dict the caller still
holds a reference to, *after* registration, does not affect the
registered snapshot (the dict was deep-frozen into a new, independent
structure at validation time, not merely referenced). `list_definitions()`
returns a fresh `list` each call — mutating the returned list (e.g.
`.clear()`) does not affect the registry. `list_models()` returns a
`tuple`, not a mutable `list`.

## No routing (v0.2.3 boundary)

Searched `registry.py` and `catalog.py` for `select_provider`,
`select_model`, `choose_best`, `route`, `recommend`, `fallback`,
`pick_cheapest`, `pick_fastest`, `rank`, `score` — none exist, and a test
asserts none of these names are attributes of `ProviderRegistry` or
either module. `find_compatible_models` returns the full candidate tuple;
nothing in this package ever narrows it to one "the" answer.

## Test coverage

`tests/test_provider_catalog.py` covers: registration/lookup/listing/
ordering, model ownership/namespace/duplicates/conflicts, atomicity
(partial-registration hostile tests), capability intersection, capability
query semantics (multi-capability, empty query, disabled exclusion),
deterministic-ordering-is-not-ranking, authority isolation (hostile
metadata), provider-output-cannot-self-register, dynamic/shape-shifting
provider, input/output aliasing, invocation isolation (zero `generate()`
calls across every operation), no-routing-API, unknown-capability
rejection. `tests/test_provider_hardening.py` gained one new regression
test for the default-value freeze fix above.

`tests/test_v022_hostile_registry_review.py` (added by a second, hostile
review pass) covers the identity-hardening blast radius, atomicity at
every validation position, static import/secret isolation of `registry.py`/
`catalog.py`, and JSON-shaped/natural-language self-registration attempts.

**Identity hardening superseded one v0.2.1 test.** `tests/test_provider_registry.py::test_duplicate_with_replace_true_succeeds`
protected `replace=True` behavior that directly conflicts with v0.2.2's
strengthened identity invariant (see "Registration lifecycle" above) and
has been replaced by `test_duplicate_provider_id_rejected_even_with_identical_redefinition`
and `test_register_no_longer_accepts_a_replace_keyword` — a deliberate,
versioned security-hardening decision, not accidental breakage. Likewise
`tests/test_provider_catalog.py::test_replace_true_wholesale_replaces_prior_model_set`
was replaced by `test_duplicate_provider_registration_cannot_replace_the_model_catalogue`,
and several `tests/test_v022_hostile_registry_review.py` tests that
exercised `replace=True`'s (then-intentional) blast radius were rewritten
into regression tests proving that blast radius no longer exists.

## Migration decision

**No database migration.** `ProviderRegistry` remains in-memory,
extended (not replaced) with a `dict[tuple[str, str], ModelDefinition]`
for model storage alongside its existing provider-entry dict. Durable
provider/model configuration can be considered when an actual
persistence/audit requirement exists (later phase), not speculatively now.

## Intentionally deferred (not in v0.2.2)

Real OpenAI/Anthropic/local provider adapters; provider routing/selection/
ranking/fallback/health orchestration/cost-based filtering (v0.2.3); model
unregistration/removal lifecycle; model-level `enabled` state; Agent
Identity/Delegation (v0.2.4-v0.2.5); Context Broker, Credential Broker
(v0.2.6); durable `ModelInvocation`/AI budget accounting (v0.2.7);
multi-agent orchestration (v0.2.8); adapter sandboxing (still none, per
v0.2.1's trust-model documentation, unchanged); resource governance for
payload/metadata size (still deferred, per v0.2.1); any new ToolAdapter or
external side effect; v0.2.3 work of any kind.
