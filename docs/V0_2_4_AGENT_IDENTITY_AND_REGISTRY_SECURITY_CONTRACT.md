# Jarvis OS v0.2.4 — Agent Identity + Agent Registry

**Phase:** v0.2.4 — implementation
**Status: IMPLEMENTATION CANDIDATE, on branch `v0.2.4/agent-identity-registry`. NOT frozen, NOT
promoted, NOT preserved.** `master`/`origin/master` remain at the v0.2.3 commit
(`7dbc719ece601513f0eec3f315955ad256a5f638`) until a separately authorized
promotion.
**Predecessor:** v0.2.3 (`7dbc719ece601513f0eec3f315955ad256a5f638`, "Jarvis OS
v0.2.3 — provider router and policy candidate", promoted to `master`).
**Relationship to v0.2.0:** implements a strict subset of the protected
contract's `agent_rules` (`docs/V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md` /
`v0.2_architecture_security_contract.json`, unchanged, no line touched):
`agent_rules.identity_fields` names a much larger future field set
(`permission_ceiling`, `model_budget`, `external_spending_ceiling`,
`delegation_rights`, `reports_to`, `escalation_policy`, `context_scope`,
`memory_scope`, ...) — v0.2.4 implements only the pure-identity subset
(`agent_id`, `name`→`display_name`, `role`, `status`→`enabled`,
`audit_identity`-equivalent via `agent_id` itself) and explicitly defers
every authority/delegation/budget/scope field to v0.2.5+ (see "Deliberately
deferred" below). `agent_rules.role_or_title_grants_authority: false` and
`agent_rules.model_supplied_identity_claims_trusted: false` (already in the
v0.2.0 contract) are the invariants this phase implements and hostile-tests.

## Central invariant

> **Agent identity is not authority.**

```text
AgentDefinition ≠ Permission
AgentDefinition ≠ Approval
AgentDefinition ≠ Delegation
AgentDefinition ≠ Capability (execution sense)
AgentDefinition ≠ Tool Access
AgentDefinition ≠ Execution Authority
```

An agent identity describes WHO is requesting work, never WHETHER that work
is permitted. `"role": "Chief Executive Officer"` carries exactly as much
Jarvis authority as `"role": "Intern"` — none, by construction, until a
future, separately reviewed authority mechanism (v0.2.5+) says otherwise.

## Critical architectural decision: module placement (avoids a real collision)

**v0.2.4's production code lives in a NEW top-level package, `app/agent_identity/`
(`contracts.py`, `registry.py`) — deliberately NOT inside the existing
`app/agents/` package.** This was not an arbitrary naming choice; inspecting
the existing architecture first (mandatory phase order, this task's own
requirement) surfaced a genuine near-collision: `app/agents/` **already
exists** and is an **executable, permission-bearing** v0.1.3 system —
`app/agents/registry.py`'s `AgentRegistry.create()` instantiates real
`JarvisAgent`/`ResearchAgent`/`StrategyAgent`/`ExecutionAgent`/`QAAgent`
Python objects, and `app/schemas/agents.py`'s `AgentDescriptor` already
carries `permissions: list[PermissionLevel]` and `capabilities: list[str]`
directly wired into the P0-P5-style permission check
(`AgentRegistry.has_permission()`). That system answers "what can this
agent-TYPE do and how do I run one" — exactly the executable, authority-
adjacent territory this phase's central invariant forbids a NEW identity
concept from being confused with. Reusing the name `AgentRegistry` or
placing a non-executing `AgentDefinition` inside `app/agents/` would
invite exactly the kind of "Agent → Execution" conflation §79/§100 of the
originating task explicitly forbids, purely through package-proximity and
naming coincidence. `app/agent_identity/` is unambiguous, imports nothing
from and is imported by nothing in `app/agents/`, and mirrors the
`app/providers/` (`contracts.py` + `registry.py`) module shape v0.2.1-2.3
already established for exactly this kind of identity/catalogue package.

## Non-goals (explicitly out of scope for v0.2.4)

- Any authority/permission/approval mechanism — the existing P0-P5
  Permission Engine and Approval Engine are untouched.
- `permission_ceiling` — deferred to v0.2.5 (§39 of the originating task:
  "a ceiling is easy to misread as a grant").
- `reports_to`/`parent_agent_id`/delegation hierarchy — deferred to v0.2.5
  (§40: do not accidentally create delegation through the identity registry).
- `tools`/executable capability grants — no ToolAdapter reference of any
  kind on `AgentDefinition`.
- Multi-business tenancy enforcement — `agent_id` MAY be namespaced
  (`business.alpha.marketing`) as a naming convention, but a string prefix
  is never treated as an access-control boundary; no tenant isolation logic
  exists in this phase.
- Authentication, login, human user accounts, RBAC, OAuth — this is AI-agent
  identity inside Jarvis, not user management.
- Any provider/model invocation, routing, or health/cost snapshot — v0.2.3's
  `route_providers()` is not called, modified, or duplicated.
- Database persistence/migration — in-memory registry only (see
  "Durability" below).
- v0.2.5 (Delegation, Authority Attenuation).

## Trust classification

**Trusted control data**: an `AgentDefinition` constructed and passed to
`AgentRegistry.register()` by trusted Jarvis code (a config file, a
deliberate registration call written by a developer/operator) — never
derived from provider/model output.

**Untrusted, carries zero identity authority** (§5 of the originating task,
verbatim list, all tested): `ProviderResponse` content/structured_output,
system prompt text, user-supplied external documents, website content,
provider metadata, model metadata, an agent's own self-description, JSON
emitted by an LLM claiming `"agent_id": "jarvis.ceo"`, and a plain string
claiming `"I am the CFO"`. No code path in `app/agent_identity/` reads any
of these — `AgentRegistry.register()` takes only a trusted, already-
constructed `AgentDefinition` object; there is no "register from JSON"
convenience path that could be pointed at model output.

## The three identity namespaces remain distinct

```text
provider_id   -- app.providers, v0.2.1-2.2, Jarvis-controlled computational identity
model_id      -- app.providers, v0.2.1-2.2, composite (provider_id, model_id)
agent_id      -- app.agent_identity, v0.2.4, Jarvis-controlled LOGICAL identity
```

A string equal to a registered `provider_id` or `model_id` establishes
**nothing** about `agent_id` and vice versa — these are three separate
`dict`-keyed namespaces in three separate registry objects with no shared
storage, no cross-lookup, and no code path that treats string equality
across namespaces as identity equivalence. `app/agent_identity/registry.py`
does not import `app.providers.registry` at all. `contracts.py` imports
only pure value helpers from `app.providers` — the `ProviderCapability`
enum (for the descriptive `required_capabilities` field), the
`validate_identifier`/`validate_display_name` policies, and the
`FrozenDict`/`FrozenList` base containers — never `ProviderRegistry`,
`route_providers`, or any provider instance.

## Agent contract (`AgentDefinition`)

```text
agent_id: str                                    -- durable machine identity (see "Identifier policy")
display_name: str                                -- human-readable, ZERO authority semantics
role: str                                        -- descriptive organizational label, ZERO authority semantics
description: str | None = None                   -- free-text, descriptive (newline/tab allowed)
enabled: bool = True  (strict)                   -- eligible for future active orchestration; NOT a permission
preferred_provider_ids: frozenset[str] = ∅       -- computational preference only, unenforced here, ≤ 256
required_capabilities: frozenset[ProviderCapability] = ∅  -- descriptive only, unenforced here
metadata: dict[str, Any] = {}                    -- opaque, JSON-shaped, bounded, deep-frozen, reserved-key REJECTING
created_at: datetime                             -- construction time; descriptive only, no security meaning
```

Model config: `frozen=True, extra="forbid", validate_default=True,
hide_input_in_errors=True`. An unrecognized constructor field
(`permission="P5"`, `approved=True`, `execute=True`, `credential=...`,
`tool_access=[...]`, `authority="OWNER"`) raises `ValidationError`
immediately; there is no field on this type any of those could attach to.
`hide_input_in_errors=True` keeps a rejected value (e.g. a secret a trusted
caller mistakenly passed) out of the `ValidationError` string (B-08).

**`display_name`/`role` have zero authority semantics, by design and by
construction** — validated `str` fields with no enum, no mapping to a
permission tier, and no code anywhere that branches on their value.
`role="CEO"` and `role="Intern"` are equally inert strings. No
`CEO => P5`/`CFO => money`/`DEVELOPER => repository write` mapping exists
or is planned by this phase. `role` is deliberately free text, not an enum
(§42). Both reuse `validate_display_name` (blank/length) and additionally
reject control characters and Unicode line/paragraph separators, so a label
cannot forge a new line in an audit log (B-06).

**`enabled` is strict** — only `True`/`False`; `"yes"`, `"on"`, `1`, `None`
are rejected rather than coerced (B-07). Eligibility must be explicit.

## Identifier policy (`agent_id`)

`agent_id` first passes `app.providers.contracts.validate_identifier`
UNCHANGED (blank, > 256 chars, leading/trailing whitespace, ASCII control
characters all rejected — the same policy as `provider_id`/`model_id`), and
then must additionally match the ASCII pattern
`[A-Za-z0-9](?:[A-Za-z0-9._:-]*[A-Za-z0-9])?`.

**Why this is stricter than `provider_id` (deliberate, justified
divergence — B-05):** an `agent_id` is an audit identity that future
delegation (v0.2.5) will reference. Under the shared policy alone,
`jarvis.cеo` (Cyrillic `е`), `jarvis.​ceo` (zero-width space) and
`jarvis ceo` (Unicode line separator) were all accepted — each renders
identically, or nearly so, to a legitimate identity in a log. The shared
function is kept (not re-implemented) so the common baseline cannot drift;
the stricter charset is an additional layer local to this type. Changing
`validate_identifier` itself would alter v0.2.1-2.3 behavior and is out of
scope.

**Case-sensitive, no normalization** (§47) — `jarvis.cto`, `Jarvis.CTO`,
`JARVIS.CTO` are three distinct identities, matching `provider_id`.

`agent_id` MAY be namespaced by convention (`business.alpha.marketing`,
`agent:research.primary`). **A namespace prefix is never an access-control
or tenant boundary** (§41) — there is no parsing, splitting, or
prefix-matching logic anywhere in `app/agent_identity/`.

## Metadata policy: JSON-shaped, bounded, reserved-key REJECTION

**Decision, with reasoning** (§20 asks for an analyzed choice):
v0.2.1-2.3's provider/router metadata is opaque and simply never read.
`AgentDefinition.metadata` is also never read by any code — AND it
actively rejects security-shaped content at construction. Reason: agent
identities are deliberately named after high-authority-sounding roles
(CEO, CFO, security reviewer), exactly the record a future careless
consumer is most likely to misread as carrying authority. Rejection makes
"this metadata cannot carry anything security-relevant" a property of the
type, not a convention every reader must remember.

1. **JSON-shaped values only (B-02).** `str`, `int`, `float` (finite),
   `bool`, `None`, `dict` with `str` keys, `list`/`tuple`. Everything else
   — `bytearray`, `bytes`, sets, arbitrary objects, callables, a live
   ToolAdapter instance — is rejected. Previously such objects passed
   through `deep_freeze` untouched, so a `bytearray` stayed mutable after
   construction (breaking A11) and a callable/ToolAdapter could be embedded
   (A16).
2. **Reserved security-shaped keys rejected at any depth, normalized
   (A-01, B-04).** A key is split into lowercase tokens (camelCase,
   `-`, `_`, spaces and other separators all normalize) and rejected if it
   contains any reserved term as a contiguous token run. Reserved terms:
   `permission(s)`, `approval(s)`, `approve(d)`, `approver`, `authority`,
   `authorities`, `authorize(d)`, `authorization`, `admin`, `superuser`,
   `execute`, `executable`, `can_spend`, `business_spend`, `tool_access`,
   `delegation`, `delegate`, `credential(s)`, `secret(s)`, `token(s)`,
   `api_key`, `apikey`, `access_key`, `private_key`, `password(s)`,
   `passwd`, `bearer`. So `Permission`, `PERMISSIONS`, `apiKey`,
   `OPENAI_API_KEY`, `access_token`, `tool-access`, `permission_ceiling`
   are all rejected. The previous exact-match, case-sensitive check let
   every one of those through. **Deliberate false positives:** benign
   keys such as `max_tokens` are also rejected (fail-closed; an identity
   record has no need for them).
3. **Canonical-field shadow keys rejected (§76/§77).** A key whose
   normalized form equals `agent_id`, `display_name`, `role`,
   `description`, `enabled`, `active`, `disabled`,
   `preferred_provider_ids`, `required_capabilities`, `metadata` or
   `created_at` is rejected, so no consumer can ever read
   `metadata["enabled"]`/`metadata["role"]` in place of the canonical
   value. Exact match only: `claimed_role`/`role_history` remain allowed
   (opaque, never read).
4. **Bounded (B-09).** Depth ≤ 8, total entries ≤ 1024, key length ≤ 256,
   string length ≤ 4096. Previously a 5000-deep structure raised an
   uncontrolled `RecursionError` and 100 000 entries were accepted.
5. **Frozen, including in-place operators (B-03 → B-11).** Values are
   frozen into the shared `app.providers.frozen` `FrozenDict`/`FrozenList`,
   which block `|=` and `*=` since the B-11 fix. B-03 originally added
   agent-local subclasses for this; they were removed once B-11 closed the
   gap at its root, so there is a single freezing implementation. The
   `test_b03_*` tests still assert the behavior on `AgentDefinition`.

## Provider/model policy — preference, not routing

`preferred_provider_ids`/`required_capabilities` are **descriptive
preferences only** (§18). No code in `app/agent_identity/` calls
`route_providers()`, imports `ProviderRegistry`, or enforces these
preferences. `required_capabilities=CODING` grants no repository write,
shell, install, or ToolAdapter access (§78) — it is a statement about the
computational substrate a future layer might select, nothing more.
`required_capabilities` reuses `ProviderCapability` rather than inventing a
duplicate vocabulary. A changed preference cannot rebind an existing
identity (duplicate registration fails closed, §19).

## Registry API (`AgentRegistry`)

```text
register(agent: AgentDefinition) -> None         -- exact type only; stores a re-validated snapshot
get(agent_id: str) -> AgentDefinition            -- any registered identity, regardless of enabled
get_active(agent_id: str) -> AgentDefinition     -- UnknownAgentError / DisabledAgentError
contains(agent_id: str) -> bool                  -- False for any non-str key
list_definitions() -> list[AgentDefinition]      -- ALL registered, agent_id-sorted
list_enabled() -> list[AgentDefinition]          -- only enabled, agent_id-sorted
```

Errors: `AgentRegistrationError` (base), `DuplicateAgentError`,
`UnknownAgentError`, `DisabledAgentError`, `InvalidAgentError`. A non-`str`
lookup key (including an unhashable one) raises `UnknownAgentError`, never
a raw `TypeError` (B-10).

**No `replace` parameter exists, at all** — v0.2.4 starts where v0.2.2's
hardening pass ended. `register()` on an already-registered `agent_id`
**always** raises `DuplicateAgentError`: identical record, higher-status
role, `enabled=True` over `enabled=False`, different metadata, different
provider preferences, anything. There is no `overwrite`/`upsert`/`force`/
`update_identity`/`set_definition` path (tested and checker-enforced). A
future controlled lifecycle mechanism must be separately designed and
reviewed (§23, §74).

**`get()` vs. `get_active()` — two methods, not a boolean flag** (§75/§84):
`get()` is the audit/history question and ignores `enabled`; `get_active()`
is the eligibility question and fails closed for unknown OR disabled
identities with two distinct typed errors. A flag such as
`include_disabled=True` would let a caller pass the wrong literal and
silently receive audit data where an eligibility check was intended.

**Deterministic ordering** — lists are always `agent_id`-sorted, never
insertion order.

## Registration is the trust boundary: exact type + re-validated snapshot (B-01)

`register()` accepts only an object whose type is **exactly**
`AgentDefinition` and stores **its own freshly re-validated copy**, never
the caller's object. Before this fix, the registry accepted any
`isinstance(..., AgentDefinition)` object as-is, so all of the following
registered successfully:

- a subclass declaring `extra="allow"` carrying `permission="P5"` (the
  registered record then really had a `.permission` attribute);
- `AgentDefinition.model_construct(agent_id="bad\x00id", metadata={"permission": "P5"})`;
- `valid.model_copy(update={"enabled": "sure", "metadata": {"approved": True}})`.

All now raise `InvalidAgentError`. The Pydantic bypass paths still exist
on the class itself (in-process Python cannot be prevented from calling
them — see Limitations), but a record produced by them can no longer
**enter the registry**, which is the only place identity becomes
authoritative.

## Enabled semantics

`enabled=True` means **"this identity may participate in future agent
orchestration"** — nothing more. It is NOT a permission, budget grant, or
tool access. `enabled=False` makes an identity unavailable to
`get_active()`/`list_enabled()`; it does **not** erase it (`get()` and
`list_definitions()` still return it for audit).

## Disabled-identity security

There is no way to flip `enabled` on a registered identity in v0.2.4: not
via re-registration (unconditional `DuplicateAgentError`), not via a
`model_copy(update={"enabled": True})` re-submission (duplicate, and would
also be re-validated), not via metadata (`enabled`/`active` shadow keys are
rejected outright; other keys are never read), and not via any other API.

## Immutability

`frozen=True` + `validate_default=True` (the v0.2.2-discovered defect:
without it, default-valued `metadata` would be a mutable `{}`). Metadata is
frozen as described above, including `|=`/`*=`. Input aliasing is
defended: the caller's original dict/list, mutated after construction, does
not affect the record; the registry additionally holds its own snapshot.

## Concurrency and durability

`AgentRegistry` is a plain in-memory `dict` with no lock — **not
thread-safe**, matching `ProviderRegistry`. No database persistence and no
Alembic migration: an in-memory registry is sufficient for this
identity-only phase.

## Hostile review

**Pass 1 — 1 finding (remediated):**

| ID | Severity | Summary | Fix |
|---|---|---|---|
| A-01 | LOW | Reserved-key rejection checked only top-level keys | Recursive check at any depth |

**Pass 2 (independent, adversarial probing of the pass-1 result) — 11
findings.** Each was reproduced with an executable probe before fixing;
each has regression tests `test_b0N_*` / `test_b10_*` in
`tests/test_v024_hostile_agent_registry.py`.

| ID | Severity | Summary | Fix |
|---|---|---|---|
| B-01 | MEDIUM | Registry accepted subclasses (with `permission="P5"`) and `model_construct`/`model_copy(update=)` records carrying invalid ids, reserved metadata and non-bool `enabled` | Exact-type check + full re-validation into a registry-owned snapshot |
| B-02 | MEDIUM | Metadata accepted non-JSON objects: `bytearray` mutable after construction (A11), callables / ToolAdapter instances embeddable (A16) | JSON-shaped values only; `str` keys only |
| B-03 | MEDIUM | `metadata \|= {...}` and `list *= n` mutated "frozen" metadata (inherited `FrozenDict`/`FrozenList` gap) | Initially agent-local subclasses; superseded by the shared B-11 fix (subclasses removed) |
| B-04 | MEDIUM | Reserved-key check was exact/case-sensitive: `Permission`, `apiKey`, `OPENAI_API_KEY`, `access_token`, `tool-access` all accepted — contradicted the doc's "structurally absent" claim | Normalized token-run matching; canonical-field shadow keys rejected |
| B-05 | LOW | `agent_id` accepted homoglyphs, zero-width chars, U+2028, spaces, `../` | Additional ASCII charset on top of `validate_identifier` |
| B-06 | LOW | `role`/`display_name` accepted `\n` etc. (audit-log line forging) | Reject Cc/Zl/Zp; `description` allows only `\n`/`\t` |
| B-07 | LOW | `enabled` coerced `"yes"`/`"on"`/`1` to `True` | `strict=True` |
| B-08 | LOW | `ValidationError` string echoed a rejected secret value (`input_value=...`) | `hide_input_in_errors=True` |
| B-09 | LOW | Unbounded metadata: 5000-deep → uncontrolled `RecursionError`; 100 000 entries accepted; `preferred_provider_ids` unbounded | Depth/entry/key/string bounds; ≤ 256 provider ids |
| B-10 | INFO | `get([])` raised raw `TypeError` instead of the typed fail-closed error | Non-`str` keys → `UnknownAgentError` / `contains` False |
| B-11 | MEDIUM (v0.2.1 scope) | Shared `app/providers/frozen.py`: `FrozenDict \|=` and `FrozenList *=` mutated in place at every nesting level of `ProviderDefinition`, `ModelDefinition`, `ProviderRequest`, `ProviderResponse`, `ProviderFailure`; changed `compute_request_hash`, `compute_response_hash`, equality and serialization | **Remediated (separately authorized):** `__ior__` added to `FrozenDict`'s blocked set, `__imul__` to `FrozenList`'s. Regression tests `test_b11_*` in `tests/test_provider_hardening.py` |

Pass 1 recorded "Pydantic `ValidationError` echoes raw values" and
"no metadata limits" as accepted limitations; pass 2 found both cheap to
fix and fixed them (B-08, B-09). The pass-1 assertion that the registry
"stores the exact frozen value, nothing to defend" was wrong: B-01 shows
the stored object itself was the attack surface.

Also attacked and clean: duplicate/replacement paths, disabled
resurrection, hidden replacement APIs, nondeterministic ordering, read
mutation, provider/model/agent namespace collision, `ProviderResponse`
content/structured_output/metadata claiming an identity, provider/router
invocation (none, AST-checked), imports of permission/approval/budget/
executor/ToolAdapter/`app.agents` modules (none), environment/secret access
(none), subclass/isinstance relationship to `PermissionDecision`,
`Approval`, `Action`, `ExecutionResult`, `ToolDefinition` (none).

## Limitations (honest)

- In-process Python is not a security boundary: code in the same process
  can call `dict.__setitem__(frozen, ...)`, `object.__setattr__(record, ...)`,
  or mutate `registry._entries` directly. v0.2.4 defends against careless
  and data-driven misuse, not against malicious in-process code.
- `AgentDefinition.model_construct(...)` / `model_copy(update=...)` still
  produce unvalidated instances; they are forbidden for untrusted data and
  cannot be registered (B-01), but any other consumer of such an instance
  receives it unvalidated.
- `ValidationError.errors()` still returns the raw input by default;
  callers logging structured errors must pass `include_input=False`.
- Reserved-key matching is lexical. A semantically equivalent key in
  another language or an invented abbreviation (`perm_lvl`) is not
  rejected — it is still never read (the primary invariant), just not
  structurally excluded.
- Values are not inspected: `{"notes": "permission: P5"}` is accepted as
  opaque text with zero effect.
- `created_at` is caller-suppliable and carries no security meaning.
- Not thread-safe; not durable.
- Frozen containers do not stop explicit base-class calls (`dict.__setitem__(frozen, ...)`, `list.append(frozen, ...)`) or an explicit `frozen.__init__(...)` re-call; these are same-process bypasses, outside the contract.

## Deliberately deferred (not in v0.2.4)

- `permission_ceiling`, `model_budget`, `external_spending_ceiling` —
  authority/budget concepts; belong to v0.2.5+ where delegation/authority
  attenuation is designed properly, not encoded prematurely here.
- `reports_to`/`parent_agent_id`/delegation hierarchy.
- `tools`/ToolAdapter references of any kind.
- Multi-business tenant isolation enforcement (namespacing convention only).
- Any lifecycle mechanism to change `enabled` or any other field on an
  already-registered identity.
- Database persistence / migration.
- Authentication, login, RBAC, OAuth, human user accounts.
- Agent Delegation, Authority Attenuation (v0.2.5).
- Context Broker, Credential Broker (v0.2.6).
