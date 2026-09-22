# Jarvis OS v0.2.1 — Provider Abstraction

**Phase:** v0.2.1 — implementation
**Status:** IMPLEMENTED (candidate, on branch `v0.2.1/provider-abstraction`, not merged)
**Relationship to v0.2.0:** implements the provider-abstraction portion of
`docs/V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md` §4-§14, §19-§21. That
contract is a protected target (contract §21, ISR-02) — this phase changes
no line of it.
**Relationship to v0.1.3:** additive only. `app/agents/providers.py`
(the existing `ModelProvider` Protocol/`MockProvider`/`OpenAIProvider`/
`AnthropicProvider` used by v0.1.3's agents) is untouched.

## Architecture implemented

A new top-level package, `app/providers/` (see "Why not `app/orchestration/`"
below):

| Module | Implements |
|---|---|
| `contracts.py` | `ProviderCapability`, `ProviderDefinition`, `ModelDefinition`, `ProviderRequest`, `ProviderResponse`, `UsageInfo` |
| `failures.py` | `ProviderFailureCategory`, `ProviderFailure`, `ProviderFailureError`, `redact_secrets` |
| `protocol.py` | `AIProvider` (the provider interface) |
| `registry.py` | `ProviderRegistry` + typed registration errors |
| `correlation.py` | `validate_response_correlation` |
| `request_hash.py` | `compute_request_hash` / `compute_response_hash` |
| `fake_provider.py` | `FakeProvider`, `FakeProviderMode` |

## Why `app/providers/`, not `app/orchestration/`

The contract's own sketch (§8) suggested a location under `app/orchestration/`.
On inspection, `app/orchestration/` (`budget.py`, `dispatcher.py`,
`evaluator.py`, `executor.py`, `planner.py`, `state_machine.py`, ~9,000
lines) is entirely the v0.1.3 **mission/task control loop** — planning an
objective into tasks, dispatching agents, evaluating results, executing
actions. That is a different "orchestration" from this phase's concern
(a vendor-neutral AI provider layer). Placing provider contracts there
would overload an already-large package with an unrelated meaning of the
word and misleadingly suggest this phase's contracts depend on or extend
the mission control loop, which they do not. A new top-level package
matches the repository's existing one-package-per-concern convention
(`agents/`, `decision_intelligence/`, `research_intelligence/`, `security/`,
`tools/`, …) and keeps the provider abstraction's own boundary as clean in
the module graph as it is in the contract.

## Trust boundary

- `ProviderDefinition`/`ModelDefinition`: Jarvis-controlled identity, never
  inferred from provider content; frozen + `extra="forbid"`, so neither the
  identity fields nor an unexpected field can be set after/at construction.
- `ProviderRequest`: represents an inference request, not an action. It
  structurally cannot carry an approval object, a ToolAdapter, a raw
  credential, or a DB session — `extra="forbid"` makes attempting to smuggle
  one in a `ValidationError`, not silent acceptance.
- `ProviderResponse`: `trusted` is a **read-only property** that always
  returns `False` — it is not a constructor field, so no caller and no
  provider-supplied payload can ever produce a `ProviderResponse` instance
  whose `trusted` reads `True`. Attempting to pass `approved=True`,
  `authorized=True`, or `permission_granted=True` at construction raises
  `ValidationError` (same `extra="forbid"` mechanism) rather than being
  silently ignored.
- `ProviderRegistry`: identity/discovery only — `register`/`get`/`contains`/
  `list_definitions`, plus `get_enabled` (fails closed with
  `DisabledProviderError` for a registered-but-disabled provider,
  distinct from `UnknownProviderError` for a provider that was never
  registered). No `select_best_provider`/`fallback_to_another_provider`
  method exists anywhere in this package. A provider's `ProviderDefinition`
  is read from its live `.definition` property **exactly once, at
  registration**, and that snapshot — never a later live re-read — is what
  `get_enabled`/`list_definitions` consult; a provider object whose
  `.definition` changes after registration cannot retroactively change its
  registered identity, enabled state, or listed capabilities.
- `validate_response_correlation` / `validate_failure_correlation`
  (`correlation.py`): a mismatched `request_id`/`provider_id`/`model_id`
  between what was asked and what came back — on either the success path
  (`ProviderResponse`) or the failure path (`ProviderFailureError`) —
  raises `ProviderFailureError` (category `INVALID_RESPONSE`). A spoofed
  response, or a failure that claims to belong to a different request,
  cannot silently masquerade as the one that was actually requested.
- `FakeProvider` construction fails (`ModelOwnershipError`) if given a
  `ModelDefinition` whose `provider_id` doesn't match its own
  `ProviderDefinition.provider_id` — a provider cannot invoke/claim a model
  belonging to another provider. Separately, per-request model mismatch
  (a request asking for a model this provider instance doesn't serve)
  fails at `generate()` time with `UNSUPPORTED_MODEL` — two different
  checks, two different, explicit owners (construction-time static
  ownership vs. per-request routing correctness).
- Every dict/list/set-valued field is deep-frozen on construction
  (`frozen.py`) — see "Deep immutability" below.
- `provider_id`/`model_id`/`request_id`/`provider_type`/`task_class`/
  `structured_output_schema_name` reject blank, >256 chars, leading/
  trailing whitespace, and ASCII control characters (`contracts.
  validate_identifier`) — these are dict-keyed, exact-matched identifiers;
  a stray control character or whitespace difference must never silently
  create two IDs Jarvis treats as different, or corrupt a log line.

## Trust model: two different kinds of trust

This is worth stating explicitly, because it is easy to conflate:

**`ProviderResponse` is untrusted data.** Everything in this document about
"the provider's claim cannot become authority" is about the *content* a
provider returns — a `ProviderResponse` is validated, structurally
incapable of smuggling authority fields, and never inspected for
"magic" keys. That is the entirety of what "untrusted" means here.

**An installed `AIProvider` implementation is trusted, in-process
application code.** `FakeProvider`, and any future `AnthropicProvider`/
`OpenAIProvider`/`LocalProvider` built behind this abstraction, is a
Python object that runs inside Jarvis's own process with Jarvis's own
privileges. The v0.2.0 contract's "provider output is untrusted" (§14,
§23) does **not** mean — and this abstraction does **not** provide — any sandboxing of a
malicious or compromised provider *adapter implementation*. A hostile
`AIProvider.generate()` implementation could, in principle, do anything
any other trusted Python code running in-process can do; the only
defenses against that are the same ones that apply to all of Jarvis's own
code: code review before an adapter is added, and supply-chain controls
on any dependency it imports. **v0.2.1 implements zero code-level
sandboxing of provider adapter implementations, and does not claim to.**

## Failure taxonomy

`ProviderFailureCategory`: `PROVIDER_UNAVAILABLE`, `RATE_LIMITED`,
`TIMEOUT`, `AUTHENTICATION_FAILED`, `AUTHORIZATION_FAILED`,
`INVALID_REQUEST`, `UNSUPPORTED_MODEL`, `UNSUPPORTED_CAPABILITY`,
`INVALID_RESPONSE`, `MALFORMED_STRUCTURED_OUTPUT`, `CONTEXT_LIMIT_EXCEEDED`,
`CONTENT_REJECTED`, `SAFETY_REJECTED`, `TRANSIENT_PROVIDER_ERROR`,
`PERMANENT_PROVIDER_ERROR`, `UNKNOWN_PROVIDER_ERROR`.

`ProviderFailure.retryable` is a **read-only property**, not a constructor
field, derived deterministically as `category in RETRYABLE_CATEGORIES` —
the same pattern as `ProviderResponse.trusted`. It cannot be set
independently of `category`, so a contradictory state (e.g. `category=
PERMANENT_PROVIDER_ERROR` with a caller-asserted `retryable=True`) is not
constructible. Nothing in this package reads `retryable` to actually
retry. **There is no automatic retry loop anywhere in v0.2.1.**

`ProviderFailure.message` is redaction- and length-bounded on construction
via a `field_validator` — there is no way to build a `ProviderFailure`
whose message still contains a secret-shaped substring the redactor
recognizes (`sk-...`, `sk-ant-...`, `ghp_...`, `tvly-...`, `AKIA...`,
`Bearer <token>`, `key=value`-shaped assignments, including JSON-quoted
`"key": "value"` shapes).

This is the *target* shape a future real-provider adapter would normalize
into from vendor-specific exceptions (contract §51: `Anthropic exception /
OpenAI exception -> ProviderFailure`). **No such mapping is implemented
here** — `app/agents/providers.py`'s own `ModelProviderError` hierarchy is
untouched and unrelated at the code level (only conceptually analogous).

## Deep immutability

**v0.2.2 correction:** the `deep_freeze` mechanism below originally only
ran when a caller explicitly passed a value for a dict/list-valued field —
Pydantic does not run `field_validator` on a field's `default_factory`
value unless the model sets `validate_default=True`. The far more common
case (leaving `metadata`/`generation_parameters`/`details` at their
empty-dict default) was therefore silently still mutable. Fixed by adding
`validate_default=True` to the shared `_FROZEN` `ConfigDict` in both
`contracts.py` and `failures.py` — see
`tests/test_provider_hardening.py::test_default_valued_dict_fields_are_also_frozen_not_only_explicit_ones`.
The description below is accurate as of that fix.

`ConfigDict(frozen=True)` only blocks *reassigning* a Pydantic field —
it does nothing to a mutable object already sitting in that field. A
hostile review confirmed this was exploitable: `ProviderRequest.
generation_parameters` and `ProviderResponse.structured_output` are both
part of the canonical hash (`request_hash.py`), so an in-place mutation of
either after construction silently changed what an already-"validated"
object hashed to. Every dict/list/set-valued field on every contract in
this package (`metadata`, `provider_metadata`, `generation_parameters`,
`structured_output`, `details`) is now recursively deep-frozen on
construction (`frozen.py`'s `deep_freeze`, `FrozenDict`/`FrozenList`):
mutating any of them — at any nesting depth — now raises `TypeError`,
and the object's hash is stable for its entire lifetime.

Two *other*, standard Pydantic APIs remain able to bypass validation —
this is a property of Pydantic itself, not something specific to this
package's models, and neither is called anywhere in `app/providers/` or
its tests today:

- `.model_copy(update={...})` produces a **new** object without
  re-running field validators (it can produce an otherwise-invalid
  instance, e.g. a blank `provider_id`), though the copy remains frozen.
- `.model_construct(...)` skips validation for fields it recognizes (it
  can produce an instance with a blank/control-character `request_id`/
  `provider_id` the normal constructor would reject). Empirically verified
  (`tests/test_provider_hardening.py`) that on the Pydantic version this
  repository pins, `extra="forbid"` causes an unrecognized kwarg passed to
  `model_construct` to be silently discarded rather than exposed as a
  retrievable attribute — so this specific API does **not** let an
  `approved=True`-style extra field through on this version. That is a
  property of the current Pydantic version, not a guarantee this package
  makes; do not rely on it without re-verifying against whatever Pydantic
  version is in use.
- Both are documented, public Pydantic APIs, not private/internal attack
  surface. Future code that builds a request/response by copying or
  constructing one of these types **must** use the normal constructor
  (`ProviderRequest(...)`), never `.model_copy()`/`.model_construct()` —
  see `tests/test_provider_hardening.py`'s `test_model_copy_*`/
  `test_model_construct_*` tests, which exist to keep this risk visible
  rather than silently assumed away.

## Resource governance (deferred)

`provider_id`/`model_id`/`request_id`/etc. are bounded to 256 characters
(`display_name` to 512) — see "Trust boundary" above. **Arbitrary-size
payload content is not bounded here**: `ProviderRequest.input`/
`system_instructions`, `ProviderResponse.content`/`structured_output`, and
every `metadata` dict can hold an unbounded amount of data. This is a
deliberate v0.2.1 scope decision, not an oversight — "how large is too
large" depends on task/model/context in a way a generic contract
shouldn't hardcode, and the existing v0.1.3 code already has its own
per-purpose bounding conventions (e.g. `research_max_evidence_excerpt_chars`
in `app.config.settings`) applied at prompt-construction time. Payload-size
resource governance for this abstraction is left to a later phase.

## FakeProvider

The only new provider implementation this phase authorizes. Zero network
calls, zero credentials, fully deterministic: every `generate()` outcome is
determined entirely by its configured/overridden `FakeProviderMode` plus
the request it receives.

Modes: `SUCCESS`, `TRANSIENT_FAILURE`, `PERMANENT_FAILURE`, `TIMEOUT`,
`MALFORMED_STRUCTURED_OUTPUT`, `WRONG_REQUEST_ID`, `WRONG_PROVIDER_ID`,
`WRONG_MODEL_ID`, `AUTHORITY_CLAIM`, `TOOL_EXECUTION_CLAIM`,
`FAKE_APPROVAL_CLAIM`, `SECRET_ECHO_ATTEMPT`.

`invocations: list[ProviderRequest]` is test-visible call history only; no
production code reads it.

## Test coverage

- `tests/test_provider_contracts.py` — positive contract + hashing tests.
- `tests/test_provider_registry.py` — registration/lookup/duplicate/
  unknown/disabled tests.
- `tests/test_fake_provider.py` — deterministic success/failure/protocol-
  conformance tests.
- `tests/test_provider_security.py` — one test per hostile scenario in
  contract §23-§37 / this checkpoint's §23-§37 (authority claim, fake
  approval, fake tool call, identity spoofing, correlation mismatch,
  malformed structured output, secret redaction, capability mismatch, tool-
  capability-≠-permission, dangerous metadata, mutability).
- `tests/test_v021_hostile_provider_benchmark.py` — one consolidated,
  end-to-end scenario driving a single registered `FakeProvider` through
  every hostile mode in sequence, mirroring how
  `tests/test_v0138_hostile_benchmark.py` composes the v0.1.3 control plane
  end-to-end rather than only testing its parts.
- `tests/test_provider_hardening.py` — regression tests from a SECOND
  hostile pass that attacked the production implementation itself (not
  just its contract): deep immutability under nested mutation, hash
  stability, registry identity pinning against a shape-shifting provider,
  model-ownership enforcement, capability intersection (not union),
  `retryable` deriving from `category` with no contradictory state
  possible, failure-path correlation, the hostile identifier policy,
  `FakeProviderMode` exhaustiveness, JSON-shaped secret redaction, and
  serialization round-trip identity — plus two tests that pin the exact,
  verified behavior of `.model_copy()`/`.model_construct()` on frozen
  `extra="forbid"` models, since that behavior is a documented but
  easy-to-get-wrong property of Pydantic itself.

## Migration decision

**No database migration.** Every contract here is an in-memory Pydantic
domain object; `ProviderRegistry` is an in-memory dict-backed catalog, the
same shape as `app.decision_intelligence.tool_adapters.ToolAdapterRegistry`.
Durable persistence (`ModelInvocation`) is v0.2.7, not this phase — see
contract §57, ISR tracking in the v0.2.0 contract §37.

## Intentionally deferred (not in v0.2.1)

Real OpenAI/Anthropic/local provider adapters; provider routing or
fallback (v0.2.3); provider health orchestration; Agent Identity/Registry,
Delegation, authority attenuation (v0.2.4-v0.2.5); Context Broker,
Credential Broker (v0.2.6); durable `ModelInvocation` / AI budget
accounting (v0.2.7); multi-agent orchestration (v0.2.8); any new
ToolAdapter, external side effect, or v0.2.2+ work.
