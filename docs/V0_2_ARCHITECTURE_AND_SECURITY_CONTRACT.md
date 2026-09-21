# Jarvis OS v0.2 — Architecture & Security Contract

**Phase:** v0.2.0 — CONTRACT/DESIGN ONLY
**Status:** DRAFT — no v0.2 production code exists yet
**Predecessor:** v0.1.3, frozen commit `be667b177f27839f5a370939bca045b7fb06eb4c`, tag `v0.1.3`, Alembic head `7f2c9a1e4b6d`
**Revision note:** this draft has been revised once following a hostile review that produced 12
findings (F-01–F-12, none duplicated or dropped) — §§7, 10, 11, 19, 21, 22, 26, 27 strengthened;
§§33–37 added. See §33–§37 for the sections added in that pass.

This document defines the architectural and security rules that will govern Jarvis OS v0.2 —
**Multi-Provider Agent Orchestration**. It is a contract, not an implementation. Nothing in this
document authorizes writing provider integrations, agents, delegation, new ToolAdapters, or any
other v0.2.x production code. Implementation follows in later, separately reviewed phases
(v0.2.1 onward) as defined in §32.

---

## 1. Release Purpose

v0.2 introduces governed multi-provider, multi-agent orchestration on top of the v0.1.3 control
plane. It allows Jarvis to draw on multiple AI providers (OpenAI, Anthropic/Claude, local models,
research-specialized models) and to delegate work to governed sub-agents, while keeping Jarvis as
the sole control plane for authority, permissions, approvals, and budget. v0.2 expands *who can
propose work and intelligence*; it does not expand *who can authorize consequential action*.

---

## 2. Central Authority Model

**Models possess intelligence, not authority.**
**Agents possess delegated responsibility, not inherent authority.**
**Jarvis remains the authority boundary.**

```
Human Owner
  -> Jarvis (authority boundary)
    -> governed agents / providers (propose work)
      -> proposed work (untrusted until validated)
        -> existing control plane (permission, approval, budget, verification)
          -> authorized execution
```

Every arrow above is a proposal or a decision, never a grant of authority in itself. Only the
control plane step can turn a proposal into an authorized execution.

---

## 3. Trust Boundaries

| Entity | Trust posture |
|---|---|
| Human owner | Root of authority |
| Jarvis control plane | Authority boundary; only trusted decision-maker |
| AI providers (OpenAI, Anthropic, local, research) | Untrusted compute; output is a proposal |
| Models | Untrusted; produce intelligence, not authority |
| Agents / sub-agents | Delegated responsibility only, bounded by §8–§9 |
| External research / documents / web content | Untrusted data, always |
| Memory / context | Trusted storage, but content originating externally stays untrusted |
| ToolAdapters | Trusted execution surface, gated by permission/approval |
| Credentials | Never disclosed to models directly (§13) |
| External systems | Untrusted, reached only through governed ToolAdapters |
| Future business units | Isolated trust domains (§26) |
| Future infrastructure nodes | Untrusted compute targets, scheduled not chosen (§27) |

AI model output is classified **untrusted** until it passes the validation stages in §14, no
matter which provider produced it. External content remains untrusted through every
summarization, translation, or transformation step — transformation never upgrades trust (§15).

---

## 4. Provider Architecture

A common provider abstraction separates orchestration logic from any single vendor. Conceptual
entities (not implemented in v0.2.0):

- **ProviderDefinition** — identity, vendor, supported model families
- **ModelDefinition** — a specific model behind a provider, with capabilities/limits
- **ProviderCapability** — declared capability (reasoning, coding, structured output, tool use, …)
- **ProviderRequest** — normalized request shape sent to any provider
- **ProviderResponse** — normalized response shape returned by any provider
- **ProviderHealth** — liveness/error-rate/latency signal for a provider
- **ProviderSelection** — durable record of why a provider/model was chosen for a request
- **ProviderFailure** — normalized failure classification (see §28)

Business logic (orchestration, agents, budget, permission) must depend on this abstraction, not
on a specific vendor SDK, wherever a provider abstraction is the appropriate layer. Providers such
as OpenAI, Anthropic, local models, and research-specialized models all sit behind this one
boundary.

---

## 5. Provider Registry

A future **Provider Registry** records, per provider/model:

- provider identity; available models
- model capabilities: context limits, modalities, reasoning, coding, structured-output, tool-use
- privacy classification; cost metadata; health; enabled/disabled state
- allowed task classes

**Registration does not grant execution authority.** A provider being registered and enabled only
makes it *eligible* for selection by the router (§6); it does not bypass permission, approval, or
budget evaluation.

---

## 6. Provider Router

The router selects a provider/model per request based on: task class, reasoning requirement,
coding requirement, context requirement, modality, privacy, sensitivity, latency, availability,
health, cost ceiling, and organizational policy.

The router **must produce a durable, explainable selection decision** (a `ProviderSelection`
record — see §17, §25).

**Provider fallback must never weaken** privacy, sensitivity restrictions, permission policy,
budget policy, or (if later introduced) jurisdiction/data-location policy. A provider that cannot
satisfy the sensitivity/privacy requirement is not an eligible fallback, regardless of
availability.

---

## 7. Agent Identity

A durable governed **Agent** identity has conceptual fields:

`agent_id`, `name`, `role`, `status`, `reports_to`, `objective_scope`, `provider/model_policy`,
`allowed_capability_requests`, `permission_ceiling`, `model_budget`, `external_spending_ceiling`,
`context_scope`, `memory_scope`, `delegation_rights`, `escalation_policy`, `lifecycle_state`,
`audit_identity`.

**Agent role/title does not grant authority.** A CFO agent does not automatically receive
financial authority. A CTO agent does not automatically receive privileged infrastructure access.
A CEO agent does not automatically receive publishing, contracting, or spending authority. Every
agent's actual authority is the effective authority computed in §9, never its job title.

**Agent identity itself is a Jarvis-trusted record, never a model-supplied claim.** An `agent_id`,
role, `reports_to` value, or any other identity field is only valid if it comes from Jarvis's own
agent registry. A model or provider response that claims "I am Jarvis," claims a different
`agent_id`, claims a role it was not registered with, or claims that human approval was granted
**must be ignored for authority purposes** — such a claim is model output (§14) and carries zero
evidentiary weight on its own. Authority and identity lookups always go to the durable registry,
never to text inside a provider response. A deleted or disabled agent's `lifecycle_state` is
authoritative and immediately voids any authority it previously held, regardless of in-flight
requests still carrying its `agent_id`.

---

## 8. Delegation Contract

A durable **Delegation** has conceptual fields:

`delegation_id`, `parent_agent_id`, `child_agent_id`, `objective_id`, `task/scope`,
`allowed_outputs`, `allowed_capability_requests`, `permission_ceiling`, `budget_ceiling`,
`context_scope`, `memory_scope`, `created_at`, `expires_at`, `status`.

**Invariant:**

```
child_authority ⊆ parent_effective_authority
```

Delegation may preserve or reduce authority. Delegation **must never increase** authority, in any
dimension (permission tier, budget, context scope, capability requests).

---

## 9. Effective Authority Calculation

Effective authority for any requested action is the **intersection** of all applicable
constraints:

```
effective_authority =
    system_policy
  ∩ owner_policy
  ∩ objective_authority
  ∩ requesting_agent_authority
  ∩ delegation_authority
  ∩ child_agent_ceiling
  ∩ tool_policy
  ∩ permission_tier
  ∩ applicable_budget
  ∩ applicable_approval_state
```

**The most restrictive applicable constraint wins.** If any constraint's status is unknown or
cannot be evaluated, the calculation **fails closed** (denies) rather than defaulting to allow.

---

## 10. No Authority Laundering

Explicitly prohibited pattern: Agent A lacks P4 permission; Agent A asks Agent B (which has a
broader nominal capability) to perform the P4 action on its behalf. This **must not** grant Agent
A's request the effective authority of Agent B.

More generally: **delegation chains, replanning, retries, provider fallback, and failure
recovery cannot increase effective authority.** Each of these mechanisms may only operate within
the authority already established by §9; none of them is a path to acquiring authority that
was not already present.

**Authority is never unioned across delegations.** An agent may hold multiple simultaneous
delegations (e.g. one from each of two parent workflows). Each action an agent takes must be
evaluated under **exactly one** delegation lineage — the one under whose objective/task scope the
action was actually requested — never under the combined or highest ceiling of all delegations the
agent happens to hold. An agent cannot borrow a wider `permission_ceiling` or `budget_ceiling`
from delegation X to cover an action that belongs to delegation Y, and cannot act under a
delegation it was not actually given for the task at hand ("wrong delegation" use). If the
correct lineage for a given action cannot be unambiguously determined, the action fails closed
(§29) rather than defaulting to the most permissive available delegation.

---

## 11. Context Broker

A future **Context Broker** sits between Jarvis storage/memory and AI providers, enforcing
**minimum necessary disclosure**:

```
Agent -> Context Request -> authorization -> relevance retrieval
      -> sensitivity filtering -> provenance preservation
      -> minimum context package -> provider
```

Agents and providers must not receive the entire Jarvis memory/database by default. Every context
package is scoped to what the specific request requires and authorized to receive.

**Context authorization and sensitivity classification travel with the content, not with the
request that first retrieved it.** Three cases follow directly from that:

1. **Delegation** — if an agent receives CONFIDENTIAL context and then delegates a sub-task to a
   child agent, the child does not inherit that context merely by virtue of the delegation; the
   Context Broker re-evaluates disclosure for the child independently. A parent cannot use
   delegation as a way to hand a child agent context the child could not have requested itself.
2. **Transformation** — summarizing, translating, or otherwise deriving new content from
   RESTRICTED/CONFIDENTIAL source material does not produce PUBLIC or INTERNAL output. The
   derived content inherits the sensitivity of its source (see provenance, §16) until an explicit,
   auditable declassification decision says otherwise.
3. **Storage** — an agent must not persist provider output or retrieved context into a broader
   memory scope than the classification it was disclosed under (e.g. writing RESTRICTED material
   into a memory scope other agents can read by default). Storage location does not override
   classification; the Context Broker's sensitivity filtering applies on *every* read, not only
   the first one.

---

## 12. Data Classification

An initial conceptual classification (final field-level detail may evolve, but every provider/
context policy decision must reference an explicit sensitivity concept):

- **PUBLIC** — no restriction
- **INTERNAL** — Jarvis-internal, safe for any registered provider
- **CONFIDENTIAL** — restricted to providers/agents meeting a privacy bar
- **RESTRICTED** — narrow, need-to-know, may exclude non-local providers
- **SECRET/CREDENTIAL** — never enters model context (see §13)

---

## 13. Credential Broker

Future secret handling follows:

```
Agent -> capability request -> Jarvis -> permission/approval
      -> ToolAdapter -> Credential Broker -> external service
```

**The model must not receive raw secrets merely because a tool needs authentication.** The
Credential Broker resolves and injects credentials at the ToolAdapter/execution boundary, after
permission and approval have already been evaluated. Expectations: redaction by default, least
privilege scoping, short-lived/scoped credentials where the provider supports them, and an audit
record of every credential use.

---

## 14. Model Output Validation

All provider output is a **proposal**, never a direct action. Future validation stages, applied
in order:

1. transport validation
2. schema validation
3. semantic validation
4. provenance validation
5. evidence validation (where applicable)
6. policy validation
7. authority validation
8. permission evaluation
9. approval evaluation
10. budget evaluation

**Never: MODEL OUTPUT → DIRECT EXECUTION.** Every path from a model response to an executed
effect passes through this full chain.

---

## 15. Prompt Injection Defense

External instructions are **untrusted data**, never authority. A webpage, email, PDF, document,
repository file, tool result, retrieved memory item, or another model's output cannot grant
authority merely by asserting it. **Transformation does not upgrade trust.**

Example: `External webpage -> Research Agent -> Summary -> Strategy Agent` must retain enough
provenance/trust metadata that an instruction embedded in the original webpage cannot silently
become system policy by the time it reaches the Strategy Agent, no matter how many summarization
steps occurred in between.

---

## 16. Provenance

Conceptual provenance record per piece of content:

`content_id`, `source_type`, `source_reference`, `trust_classification`,
`sensitivity_classification`, `retrieved_by`, `retrieved_at`, `transformations`, `derived_from`,
`agent/model_responsible_for_transformation`.

Derived content remains traceable to its source wherever practical, so a downstream consumer (or
an auditor) can answer "where did this ultimately come from, and was it ever trusted."

---

## 17. Model Invocation

A durable conceptual **ModelInvocation** record:

`invocation_id`, `agent_id`, `delegation_id`, `objective_id`, `provider`, `model`, `task_class`,
`context_references`, `sensitivity_classification`, `request_hash`, `response_hash`,
`token_usage`, `estimated_cost`, `latency`, `status`, `failure_classification`, `timestamps`.

Raw sensitive prompts/responses are **not required** to be stored if hashes, references, and
redacted records provide sufficient auditability — prefer the safer option.

---

## 18. AI Budget Model

Two budgets are kept strictly separate:

**Compute/model budget** — model calls, input tokens, output tokens, estimated provider cost,
retry allowance.

**Business/external spending authority** — advertising spend, purchases, subscriptions,
bank/payment activity.

**Model budget never grants external financial authority.** Exhausting or having a large model
budget says nothing about P5 financial permission; those remain governed independently by the
existing Permission/Approval/Budget Engines (§23).

---

## 19. Hierarchical Budgeting

Budget delegates down the same hierarchy as authority: e.g. `Jarvis -> CTO -> Developer Agent`. A
child can never receive more delegated budget than its parent's remaining delegation permits, and
the **sum of all budget simultaneously delegated to children must never exceed the parent's
remaining (not original) capacity** — a parent with £100 that has already delegated £70 to one
child has at most £30 left to delegate to a second, not another £100.

**Budget accounting must be atomic/reserved, not check-then-spend.** A request that will consume
model budget must reserve that amount before the call is made and release/settle it afterward;
checking "is there budget left" and spending it as two separate steps allows concurrent requests
(retries, fallback attempts, parallel child agents) to each pass the check before either commits,
overspending the ceiling. Retries and provider-fallback attempts each consume their own reserved
budget — they do not get a second, unbudgeted attempt merely because the first one failed (§10).
Budget delegation is durable and auditable, following the same non-increase invariant as §8.

---

## 20. Multi-Agent Orchestration

Agents exchange structured tasks/results **through the orchestration layer**, not directly with
each other:

```
Agent A -> Jarvis orchestration -> Delegation -> Agent B
        -> result -> Jarvis -> Agent A / parent workflow
```

Uncontrolled peer-to-peer autonomous authority between agents is out of scope and disallowed;
every hand-off is mediated by Jarvis so it can be governed and audited.

---

## 21. Coding Agent Contract

Future coding-agent workflow:

```
Change Request -> isolated branch/worktree/sandbox -> implementation -> tests
               -> static/security analysis -> QA -> review -> authorization
               -> merge -> deployment (separately governed)
```

**Development authority ≠ merge authority ≠ deployment authority.** A coding agent that can
propose and implement a change does not thereby gain the right to merge or deploy it. Coding
agents must not silently modify the protected frozen release (v0.1.3, or any future frozen tag).

**A coding or self-improvement agent must not modify, as an ordinary code change, any of the
following "protected targets":** the permission engine, the approval engine, the budget engine,
this architecture/security contract or its machine-readable counterpart, the validator script(s)
that check compliance with this contract, tests that assert a security invariant, migration
history, or any frozen release's artifacts. A change touching a protected target is not a bug fix
or feature — it is a **policy change**, and must go through a distinct, human-gated policy-change
workflow, separate from and with a higher bar than ordinary code review. In particular, a coding
agent must never modify a test merely to make its own otherwise-failing change pass, and must
never modify the contract or validator it is itself being judged against.

---

## 22. Self-Improvement Contract

Future controlled self-improvement:

```
Observation -> Improvement Proposal -> isolated development environment
            -> candidate implementation -> tests -> security regression -> benchmark
            -> comparison -> approval -> versioned release -> deployment -> monitoring
            -> rollback
```

Jarvis may eventually propose and develop improvements to itself. **It may not automatically
infer permission to deploy them.** Self-modification must never disable or bypass the mechanism
that governs self-modification — the gate cannot approve removing itself.

**The evaluator/benchmark suite that judges a self-improvement candidate must be independent of
that candidate.** A candidate change must never be able to modify, weaken, skip, or replace the
tests, hostile benchmark, or comparison logic that will judge it — that includes weakening
permission checks and calling it an "improvement," and it includes deleting or softening hostile
tests to make a candidate pass. **"Deployment" and "testing" are not interchangeable labels**: a
candidate running against real external systems, real credentials, or real user-facing state is a
deployment and requires deployment authorization (§21) no matter what an agent's own proposal
calls it. Jarvis proposing a self-improvement, then creating a *different* agent to carry out the
deployment, does not confer deployment authority — the authorization requirement in §21 attaches
to the action, not to which agent nominally performs it.

---

## 23. Existing P0–P5 Permission Compatibility

The existing conceptual permission hierarchy is preserved unchanged:

- **P0** — internal reasoning/analysis
- **P1** — read-only/search
- **P2** — internal creation/draft/local artifact
- **P3** — reversible external change
- **P4** — consequential external send/publish/delete/submit
- **P5** — money/security/install/privileged OS

Agents and providers remain subordinate to these tiers regardless of role. **Agent titles do not
override permission levels** — see §7.

---

## 24. Existing v0.1.3 Control Plane Compatibility

The following v0.1.3 components are explicitly preserved and remain authoritative:

Research/Evidence Readiness, Decision Gate, Permission Engine, Approval Engine, Budget Engine,
Durable Executor, Tool Registry, Verification, Failure Intelligence, Retry, Replanning,
Reconciliation, Crash/Restart Recovery, QA, Executive Reporting.

**v0.2 orchestration must feed into these controls, not route around them.** No v0.2 mechanism
(provider routing, agent delegation, multi-agent orchestration) is a substitute for, or bypass of,
any of the above.

---

## 25. Audit Chain

Target reconstruction chain for any executed effect:

```
Objective -> Delegation -> Agent -> Provider Selection -> Model Invocation
          -> Context References -> Model Result -> Decision -> Action Proposal
          -> Permission -> Approval -> Budget -> Execution -> Verification
          -> Final Report
```

Jarvis must eventually be able to answer: Who requested this? Which agent performed reasoning?
Which provider/model was used? What authority applied? What context was disclosed? Why was the
provider selected? What did it cost? What action was proposed? Who/what authorized it? What
actually happened? How was success verified?

---

## 26. Multi-Business Isolation

Future business/tenant boundaries. Each business may eventually have isolated: objectives,
agents, budgets, memory, documents, credentials, policies, audit records, external integrations.
**Cross-business access requires explicit policy.** A business agent must not gain another
business's data merely because both report to Jarvis.

**Tenant/business scope is an explicit authorization dimension, evaluated before relevance, not a
side effect of it.** A retrieval step (including shared vector/semantic search infrastructure)
must filter by tenant authorization *before* ranking by relevance — relevance scoring must never
be the mechanism that determines whether cross-business data is visible, because "this record is
useful to the objective" is not an authorization decision. An agent that is simultaneously
assigned work for Business A and Business B does not thereby gain a combined authorization scope;
each active task carries its own tenant scope, evaluated independently, the same way §10 requires
one delegation lineage per action.

---

## 27. Infrastructure/Node Abstraction

Future support for: laptop command center, primary desktop compute node, storage/RAG node, future
compute nodes, cloud resources. **Distributed computing is not implemented in v0.2.** The only
principle established now: agents request resource *requirements*, and Jarvis schedules
resources — agents do not pick machines directly.

Conceptual future resource requirement tags: `GPU_HIGH`, `CPU_HIGH`, `RAG_HEAVY`,
`STORAGE_LOCAL`, `BACKGROUND`, `MOBILE`, `PRIVACY_LOCAL_ONLY`.

**An agent must not choose a privileged machine simply to escape policy** — resource selection
never substitutes for authority evaluation. This is the same invariant as provider fallback (§6,
§11): node/resource scheduling may fail over for load or availability, but **must never** alter
permission, data-residency, or privacy policy as a side effect — a `PRIVACY_LOCAL_ONLY` task does
not become cloud-eligible because the local node is busy or has failed; it fails closed (§29)
instead. Node failure is a failure category (§28), not a policy override.

---

## 28. Failure Semantics

Conceptual provider/agent failure categories: provider unavailable, rate limited, timeout,
invalid response, schema failure, policy violation, context denied, budget denied, authority
denied, privacy constraint, unsupported capability, provider mismatch.

Fallback, retry, and replan behavior for each category must remain bounded and policy-aware (see
§10 — none of them may increase authority as a side effect of recovering from failure).

---

## 29. Fail-Closed Rules

The system fails closed (denies, does not proceed) for at least:

unknown provider; unknown model; unknown agent; unknown capability; missing delegation; expired
delegation; invalid authority chain; missing context authorization; privacy incompatibility;
budget exhaustion; malformed structured output; unknown ToolAdapter; missing approval; stale
approval; approval hash mismatch; tampered invocation/result records.

---

## 30. Security Invariants

Normative invariants for all of v0.2 and beyond, using MUST/MUST NOT/SHOULD:

1. **MUST NOT** — Models possess intelligence, not authority.
2. **MUST NOT** — Agents possess delegated responsibility, not inherent authority.
3. **MUST** — Jarvis remains the authority boundary.
4. **MUST** — Agent authority may only remain equal or decrease through delegation.
5. **MUST NOT** — No provider/model/agent may bypass the Jarvis control plane.
6. **MUST NOT** — Tool availability does not imply permission.
7. **MUST** — Model output is untrusted until validated.
8. **MUST** — External content remains untrusted through transformations.
9. **SHOULD** — Secrets are consumed by controlled adapters rather than exposed to models.
10. **MUST** — Context disclosure follows minimum necessary access.
11. **MUST NOT** — Provider fallback may not weaken security/privacy policy.
12. **MUST NOT** — AI/model budgets do not grant business spending authority.
13. **MUST NOT** — Agents cannot approve their own privileged actions.
14. **MUST NOT** — Development authority does not imply merge/deployment authority.
15. **MUST** — Self-improvement must be isolated, tested, versioned, and rollback-capable.
16. **MUST NOT** — Ordinary agents cannot weaken security policy.
17. **MUST** — Consequential actions require durable provenance.
18. **MUST NOT** — Failure recovery cannot increase authority.
19. **MUST NOT** — Retry/replan cannot increase authority.
20. **MUST NOT** — Delegation cannot be used for authority laundering.
21. **MUST NOT** — Human-denied actions cannot be reframed/delegated to evade denial.
22. **MUST** — Unknown capabilities fail closed.
23. **MUST** — Provider selection must be explainable/auditable.
24. **MUST NOT** — Sensitive context may not silently migrate to a less-trusted provider.
25. **MUST** — Frozen v0.1.3 security guarantees remain invariants unless explicitly superseded
    through reviewed/versioned change.

---

## 31. Explicit Non-Goals for v0.2.0

This phase does **not** add: unrestricted shell; unrestricted browser; email sending; publishing;
financial execution; autonomous purchasing; software installation; admin/root access; NAS
administration; autonomous deployment; autonomous self-modification; distributed worker
infrastructure; uncontrolled agent-to-agent execution; new external side-effect ToolAdapters.

This phase produces contract and design documentation only.

---

## 32. Planned v0.2 Delivery Sequence

| Phase | Scope |
|---|---|
| v0.2.0 | Architecture + Security Contracts (this document) |
| v0.2.1 | Provider Abstraction |
| v0.2.2 | Provider Registry + Capability Metadata |
| v0.2.3 | Provider Router + Health/Cost/Fallback Policy |
| v0.2.4 | Agent Identity + Agent Registry |
| v0.2.5 | Delegation + Authority Attenuation |
| v0.2.6 | Context Broker + Provenance + Data Boundaries |
| v0.2.7 | Durable Model Invocation + AI Budget Accounting |
| v0.2.8 | Multi-Agent Orchestration |
| v0.2.9 | Hostile Security / Prompt-Injection Benchmark |
| v0.2.10 | End-to-End Multi-Provider Benchmark |
| — | **v0.2 FREEZE** |

This roadmap may be refined later only through explicit, reviewed architecture change — not
implicitly during implementation of any single phase.

---

## 33. Approval Binding

An approval authorizes **one specific, immutable action identity** — not a category of action, not
an agent, and not a policy. The action identity is computed from every material field of the
proposed action, at minimum: recipient/destination, external system/endpoint, quantity, financial
amount, content (or a hash of it), the requesting agent, and scope.

**Any material mutation of a materially-bound field invalidates the approval.** Concretely, an
existing approval must not silently authorize execution when any of the following differ from what
was approved: modified action parameters, a different recipient, a different destination, an
increased quantity, an increased financial amount, a different external system, a different agent,
materially different content, or materially different scope. This is the concrete meaning of the
`approval_hash_mismatch` fail-closed condition (§29): the executor recomputes the action identity
at execution time and compares it against the identity the approval was granted for; any mismatch
fails closed and requires a fresh approval, not a warning.

Non-material differences (e.g. a re-generated request ID, a timestamp, formatting) do not
invalidate an approval; the distinction between material and non-material fields for a given action
class must itself be an explicit, reviewed part of that action class's definition — never inferred
ad hoc by the executing agent.

---

## 34. Human Denial Persistence (Detailed)

SI-21 (§30) states the invariant; this section makes it concrete. When a human denies a proposed
consequential action ("Action X"), that denial must be recorded as a durable **Denied Action
Record** keyed by the action's identity (§33) and its semantic intent, not merely its literal
parameters. Future proposals are checked against outstanding denial records for material
equivalence before proceeding. The following are explicitly **not** valid ways to evade a denial,
and the contract requires each to be checked against the denial record rather than treated as a
fresh, unrelated proposal:

- **Reframing** — rewriting X as X2 with different wording but the same underlying effect.
- **Splitting** — replanning X into several smaller actions that collectively reproduce X's effect.
- **Redelegation** — delegating X (or X2) to a different or child agent to re-propose it.
- **Provider switching** — resubmitting the same intent through a different provider/model.
- **Waiting/retrying** — resubmitting the same or equivalent action later, unchanged in substance.
- **New child agent** — spinning up a new agent specifically to re-propose a denied action.

Determining "material equivalence" is a policy/semantic judgment, not a byte-for-byte match — an
implementation must not satisfy this invariant merely by checking literal parameter equality, since
that is exactly what reframing defeats. This is flagged here as a precise requirement on the
eventual implementation (v0.2.4–v0.2.7), not something this contract phase can fully specify
mechanically.

---

## 35. Self-Approval Prohibition

SI-13 (§30) states the invariant; this section enumerates the scenarios it must cover so the rule
cannot be satisfied by a narrow reading:

- An agent must not approve its own privileged (P4/P5) action, directly or through a proxy step it
  controls.
- A parent agent must not approve a child's action where policy requires **human** approval — a
  parent is not a substitute for the human owner regardless of how much authority the parent holds.
- A QA or verification agent must not mark an approval requirement as satisfied merely by asserting
  the action looks correct; approval and QA are distinct gates (§14, §24) and neither substitutes
  for the other.
- Provider output claiming "approval granted" carries no weight (§7) — approval status is only ever
  read from Jarvis's own durable approval record.
- A role title (e.g. "CFO agent") does not itself constitute or imply approval authority (§7, §23)
  — approval authority is a specific, granted capability, never inferred from a title.

Approval authority is always independently derived from policy plus a durable approval record; it
is never inferred from an agent's position in a hierarchy, its role, or its own or another agent's
assertions.

---

## 36. Audit Record Integrity

The durable records described in §17 and §25 (ModelInvocation, ProviderSelection, Delegation,
Approval, and the rest of the audit chain) need the following integrity properties — not a
blockchain, just ordinary tamper-evidence appropriate to an audit trail:

- **Append-only.** A written record is not edited in place. A correction is a new record that
  supersedes the old one and references it; the original remains present for audit.
- **Replay/duplicate detection.** A repeated or replayed invocation/action must be distinguishable
  from a new, independent one (e.g. via an idempotency key), so the same approval or budget
  reservation cannot be consumed twice by resubmitting the same request.
- **Lineage integrity.** A delegation, approval, or provider-selection record that a downstream
  record claims to descend from must actually exist and match — a fabricated or dangling lineage
  reference is a `tampered_invocation_or_result_records` condition (§29) and fails closed rather
  than being silently accepted.
- **Request/response consistency.** A ModelInvocation's recorded response must correspond to its
  recorded request (via the request/response hashes in §17); a mismatch is the same fail-closed
  condition.

These are integrity *properties* the eventual storage design must satisfy; this contract does not
prescribe a specific storage mechanism (e.g. it does not require a blockchain or other distributed
ledger) to satisfy them.

---

## 37. Implementation-Sensitive Requirements Register

Two invariants in this contract are fully specified at the *policy* level (the rule is not
ambiguous or optional) but cannot be fully mechanized at the contract-design phase — their
correct enforcement depends on judgment calls that only the implementation can make concrete.
Recording them here is **not permission to defer or weaken the underlying invariant**; the
invariant applies from v0.2.0 onward regardless of implementation status. It is a requirement that
the corresponding functionality is **not considered complete** until each item below is
demonstrably satisfied, and each must be explicitly addressed (not silently skipped) in the phase
that implements it.

| ID | Requirement | Invariant it implements | Owning phase | Completion bar |
|---|---|---|---|---|
| ISR-01 | Denial persistence must detect **semantic/material equivalence** between a newly-proposed action and a previously-denied one (§34) — not merely literal parameter equality, since reframing/splitting/redelegation/provider-switching/waiting/new-child-agent evasions are specifically the cases literal equality misses. | SI-21, §34 | v0.2.4–v0.2.7 (Agent Identity / Delegation / Multi-Agent Orchestration) | A hostile test suite exercising each of the six evasion patterns in §34 must fail to bypass an existing denial. |
| ISR-02 | Protected-target changes (§21: permission/approval/budget engines, this contract and its validator, security-invariant tests, migration history, frozen release artifacts) must route through a **distinct, human-gated policy-change workflow**, separate from and with a higher bar than ordinary code review — not merely documented as a rule agents are expected to follow. | SI-16, §21 | v0.2.8–v0.2.9 (Multi-Agent Orchestration / Hostile Security Benchmark) | The hostile/prompt-injection benchmark (v0.2.9) must include an attempted protected-target modification by a coding/self-improvement agent and confirm it is mechanically blocked, not merely policy-discouraged. |

This register must be kept up to date: an implementation phase that satisfies an entry should mark
it resolved (with a reference to the tests/mechanism that satisfy it) rather than deleting the row,
so the frozen contract history stays legible.
