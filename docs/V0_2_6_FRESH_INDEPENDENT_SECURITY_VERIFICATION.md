# Jarvis OS v0.2.6 — Fresh Independent Security Verification (HR3)

```text
subject                     = docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md
prior review verified       = docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md (HR2)
review type                 = security analysis only (no code, test, validator, design or HR2 change)
design_modified             = false
hr2_modified                = false
code_modified               = false
opendex_modified            = false
final_status                = DESIGN CORRECTIONS REQUIRED BEFORE FREEZE
```

---

## 1. Review independence statement

- This review was performed in a **fresh session** that did **not** author the
  v0.2.6 design or the HR2 review. It had no access to the drafting or HR2
  conversations. It saw only the repository contents.
- Every HR2 factual claim used here was **re-derived from the repository**.
  Where the repository contradicted HR2, this review says so (HR2-01, HR2-12,
  HR2-15, HR2-19).
- **Remaining limitation (HR3-16).** This reviewer is an AI model, very likely
  from the same model family as the author of both documents. Session
  independence is satisfied. Organizational and model-diversity independence
  are **not**. Shared systematic blind spots remain possible. A human security
  review of at least the root-of-trust (§6), isolation (§13) and owner-channel
  (§14) conclusions is recommended before freeze.

This review therefore satisfies the "separate session with no access to the
drafting conversation" gate that HR2-25 asked for. It does not satisfy a
"different person" gate.

## 2. Repository state

Verified at the start of this review:

| Item | Value |
|---|---|
| Branch | `master` |
| HEAD | `13796dcd61015098429f343e2fb982a9c75698bb` |
| `origin/master` | `13796dcd61015098429f343e2fb982a9c75698bb` (equal to HEAD) |
| Tags at HEAD | `v0.2.5.1` |
| `git status --short -uall` | `?? docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md`<br>`?? docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md` |
| Modified tracked files | none |
| Untracked files | exactly the two v0.2.6 documents above (both exist; neither modified by this review) |
| Ignored local files observed | `jarvis.db` (SQLite, ~8 MB), `.env` (holds 2 non-empty `*KEY`/`*TOKEN` entries; values were **not** read), `.venv/` |

After this review, the only change is the new file
`docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md`.

**Validators and tests (run read-only, with `.venv/Scripts/python.exe`):**

| Command | Result |
|---|---|
| `scripts/check_v013_freeze_baseline.py` | OK (Alembic head `7f2c9a1e4b6d`; ToolAdapters `['file.create_sandboxed']`) |
| `scripts/check_v020_contract.py` | OK |
| `scripts/check_v023_router_contract.py` | OK |
| `scripts/check_v024_agent_contract.py` | OK |
| `scripts/check_v025_design_contract.py` | **exit 1: DISCREPANCY FOUND.** The two untracked v0.2.6 documents are outside the v0.2.5.1 allowlist. |
| `python -m pytest -q -p no:cacheprovider` | **1 failed, 2234 passed, 1 warning** (518.59 s). The only failure is `tests/test_v025_design_contract.py::test_design_checker_passes_on_repository`, for the same allowlist reason. |

The frozen v0.2.5 checker is doing its job: it flags uncommitted files it
does not know about. Neither the validator nor the test was modified.

## 3. Materials reviewed

**Contracts:**

- `V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md` (§2–§3, §7–§12, §26–§27 and
  §33 read in full; other sections by outline);
- `V0_2_3_PROVIDER_ROUTER_SECURITY_CONTRACT.md` (privacy and fallback sections);
- `V0_2_4_AGENT_IDENTITY_AND_REGISTRY_SECURITY_CONTRACT.md` (deferred scopes);
- `V0_2_5_DELEGATION_AND_AUTHORITY_SECURITY_DESIGN.md` (inventory, root trust
  HR-06, CR-01…CR-05, threat rows T-11/13/22/43/44/46/47/53, R-10);
- `V0_2_5_1_AUTHORITY_CONTRACTS_AND_ALGEBRA.md` and `app/authority_contracts/`;
- the v0.2.6 design (all 1,658 lines);
- HR2 (all 1,357 lines).

**Code (inspected independently):**

| Area | Files |
|---|---|
| API and app | `app/main.py`, `app/api/routes.py`, `app/schemas/approvals.py`, `app/schemas/projects.py` |
| Approvals | `app/services/approval_service.py`, `app/decision_intelligence/approval_engine.py` |
| Orchestration | `app/orchestration/{executor,planner,dispatcher,evaluator}.py`, `app/schemas/tasks.py`, `app/security/approvals.py` |
| Memory | `app/tools/memory_tools.py`, `app/memory/{manager,retrieval}.py`, `app/services/memory_service.py` |
| Data model | `app/database/models.py` (User, Workspace, Project, Task, AgentRun, Memory, AuditEvent) |
| Providers | `app/agents/providers.py` (live path), `app/providers/{router,routing_contracts}.py` (v0.2.3) |
| Identity and authority | `app/agent_identity/registry.py`, `app/authority_contracts/contracts.py` |
| Config and logging | `app/config/settings.py`, `app/utils/logging.py`, `.env` (key **names** only) |
| Decision intelligence | `app/decision_intelligence/{tool_adapters,sandbox_fs,action_plan_orchestrator}.py` |

OpenDex was not opened, read or modified in this review. The design's and
HR2's OpenDex observations are not re-verified here.

## 4. Verified implementation facts

Facts marked **NEW** are not recorded in the design or in HR2.

| # | Fact | Evidence | Relevance |
|---|---|---|---|
| F-1 | No FastAPI route has authentication or an authorization dependency. The only dependency is `get_db`. | `app/api/routes.py` (all routes); `app/main.py` (no middleware) | HR2-07 confirmed |
| F-2 | `POST /tasks/{id}/approve` and `/reject` take a caller-supplied `resolved_by: str` and record it as the human actor. Approval moves the task to `READY`. | `routes.py:115–133`; `schemas/approvals.py:18–20`; `approval_service.py:47–70` | Owner identity is self-asserted |
| F-3 | `decide_approval` checks only `decided_by` is non-empty and differs from `requested_by`. | `approval_engine.py:320–351` | CR-03 still open |
| F-4 | **NEW.** `POST /chat` accepts any `user_email` (auto-creates a `User`), any `workspace_id` and any `project_id`. It never checks that the project belongs to the workspace or that the workspace belongs to the user. It then overwrites that project's objective and runs `run_objective(workspace_id=W, project_id=P)`, which executes **every READY task in P**, including tasks created under another workspace. | `routes.py:152–200`; `project_service.py:32–45`; `executor.py:368–430`; `dispatcher.py:77–80` | Live cross-workspace confused deputy (HR3-12) |
| F-5 | **NEW.** `GET /projects/{id}/tasks` and `GET /tasks/{id}` return `description`, `output_data` and `error` to any caller. | `routes.py:97–112, 202–220` | Live unauthenticated disclosure |
| F-6 | `GET /projects/{id}/audit` returns `actor_type, actor_id, event_type, entity_type, entity_id, created_at`. It does **not** return `metadata`. | `routes.py:135–150` | Corrects HR2-12 (titles and exception text are not exposed through this route) |
| F-7 | Audit metadata contains content: memory title (`memory_service.py:43`), raw exception text (`action_plan_orchestrator.py:317`), **the full objective text** (`project_service.py:43`, **NEW**), and approval `decision_reason` (`approval_service.py:67`). | as cited | Audit is not metadata-only today |
| F-8 | **NEW.** Full agent input payloads are persisted to `agent_runs` (`run_repo.create(input_payload=input_data)`). Task outputs are persisted in `tasks.output_data` and passed to dependent agents by `_build_input`. Errors are persisted as `str(exc)`. | `executor.py:152–157, 273–278, 289–301`; `models.py:337–352` | Unlabeled content stores outside any future broker |
| F-9 | The planner is a model. `TaskPlan.agent_type`, `requires_approval`, `title`, `description` and `priority` are all model output. `persist_plan` stores them after structural validation only. | `planner.py:14–19`; `schemas/tasks.py:12–34`; `dispatcher.py:15–43` | Model output selects agent identity and approval flag (HR3-05) |
| F-10 | The approval gate is `task.requires_approval OR classify_risk(title+description)`. The regex matches English keywords. | `executor.py:95–109`; `security/approvals.py:10–25` | Model-controlled bypass of approval heuristics |
| F-11 | **NEW.** The live runtime **never uses the v0.2.x modules**. No file outside `app/decision_intelligence`, `app/authority_contracts`, `app/agent_identity` and `app/providers` imports them. The live model path is `app/agents/providers.py::get_default_provider()`, which directly constructs `OpenAIProvider` or `AnthropicProvider`. | grep over `app/`; `agents/providers.py:727–755` | The v0.2.3 router, v0.2.4 registry and v0.2.5.1 contracts are disconnected |
| F-12 | Settings default `model_provider="openai"`. The local `.env` selects `MODEL_PROVIDER=anthropic` and `RESEARCH_PROVIDER=tavily`. Every prompt, and every research query derived from the objective, goes to an external cloud service. There is no locality check anywhere on this path. | `settings.py:18`; `.env` (names/values of non-secret keys only) | Cloud is **unconditionally** allowed on the live path (HR3-09) |
| F-13 | `ProviderRoutingRequest.privacy_requirement` defaults to `CLOUD_ALLOWED`. The v0.2.3 contract documents this as "the default". | `routing_contracts.py:219`; v0.2.3 doc line 185 | HR2's N-5 confirmed, but on a disconnected path |
| F-14 | `retrieve_memory`, `store_memory`, `retrieve_relevant` (outside tests) and `promote_lesson` have no callers. `MemoryType.INSTRUCTION` is defined but never written. Only `promote_research` and `promote_decision` run. | grep; `executor.py:350–365` | HR2-23 confirmed |
| F-15 | Agents, tools, the DB session factory and settings (with raw API keys) all live in **one Python process**. `jarvis.db` is a plain SQLite file. `.env` is a plain file. | `database/connection.py`; `settings.py:16–21, 77`; `main.py` | No process or OS isolation exists (HR3-07) |
| F-16 | Log redaction is by key name only. | `utils/logging.py:11–26` | Values are not scrubbed |
| F-17 | **NEW.** Multiple human `User` rows exist (email-keyed, auto-created by `/chat`). Workspaces belong to users. `PrincipalKind` has only `HUMAN_OWNER` and `AGENT`. | `models.py:201–230`; `authority_contracts/contracts.py:56–63` | No mapping from `User` to principal, and no definition of *which* human is the owner (HR3-13) |
| F-18 | QA retry loop: QA-agent feedback (derived from the worker's output) is fed back into the next worker attempt as `qa_feedback`, through Python variables. | `orchestration/evaluator.py:97–150, 350` | Inter-execution flow that is not an item (HR3-02, HR2-09) |
| F-19 | The v0.2.5 "requester binding" (CR-01) binds **Actions** (`ActionRecord`). There is no durable entity called an "execution" (a model-call loop). The nearest existing entities are `Task`, `AgentRun` (with `attempt`) and v0.2.7's deferred ModelInvocation. | v0.2.5 lines 1109, 1187; `models.py:279–352` | `execution_id` in v0.2.6 has no creator (HR3-01) |

## 5. Threat model

Adopted from the design (A1–A6) and HR2 §4, with one refinement that decides
most of the verdicts:

| Attacker class | Controls | Can v0.2.6 as designed defend? |
|---|---|---|
| **M: model-driven** (injected content, hostile provider output, misaligned model) | Only the text and structured output that trusted Jarvis code consumes | Yes, **if** no model output becomes a control-plane value (§7) |
| **C-in: in-process code** (malicious dependency, malicious connector, merged hostile patch) | Arbitrary Python in the Jarvis process | **No.** Python module boundaries are not a security boundary (§13) |
| **C-os: same-OS-user code** (desktop malware, a dev-agent sandbox running as the same user) | Files, `jarvis.db`, `.env`, process memory | **No.** Needs OS isolation |
| **N: network caller** of the FastAPI app | Every route | **No.** No authentication exists (F-1) |
| **H: non-owner human** with a `User` row | Everything N has | Undefined. There is no principal model for non-owner humans (F-17) |
| **R: restore or rollback** (backup restore, snapshot) | Store contents | Not defended today (HR2-10) |

The design says A1–A4 and A6 are "defended in contract". That holds only
against class M. The design must state this explicitly (HR3-07).

## 6. Root-of-trust analysis

| Component | Classification | Reasoning |
|---|---|---|
| Human owner | **Trusted** (root) | Constitutional root of authority (v0.2 §3). |
| Owner-authentication mechanism | **Future / deferred, but REQUIRED** | Does not exist (F-1, F-2). Until it exists, the trusted root is unreachable: every "owner act" is forgeable by class N. |
| Principal registry (which human is the owner) | **Future / deferred** | Not defined (F-17). It is a TCB component, because it decides who the owner is. |
| Agent registry (v0.2.4) | **Trusted, disconnected** | Sealed and correct, but in-memory and unused by the runtime (F-11). CR-04 lifecycle history is still open. |
| Authority engine (v0.2.5) | **Future** (contracts only) | v0.2.5.1 is pure and disconnected. CR-01/03/05 are open. |
| Context Broker (reference monitor) | **Future, trusted** | TCB by definition. Can modify flows, so it must be a protected target. |
| Provenance, clearance and grant stores | **Future, trusted** | TCB. Their integrity depends on DB-level isolation (C-os can write them). |
| Label-policy evaluator and source policies | **Future, trusted** | TCB. A policy edit is a security change (design §19.3). |
| Node identity system | **Future / deferred** | Self-asserted today (HR2-16). Must stay out of every trust decision until key-bound. |
| Secret broker (Credential Broker) | **Future / deferred** | Today secrets are plain settings fields in process memory (F-15). |
| Audit subsystem | **Partially trusted** | Append-only intent, but it holds content (F-7), has no hash chain in code, and is readable through an unauthenticated route (F-6). |
| Operating system and OS user account | **Trusted** (implicit) | **The real TCB boundary today.** Anyone running as the Jarvis OS user controls everything. The design never names it. |
| Process sandbox | **Future / deferred** | Does not exist. `sandbox_fs` is path validation, not isolation. |
| Repository / bootstrap verifier | **Partially trusted** | The `scripts/check_v0*` validators detect drift but are themselves repository files; a code-level attacker can edit them. Bootstrap trust is an explicit assumption (design §19.4). |
| Dependency set (`requirements.txt`, `.venv`) | **Trusted** (implicit), **missing from protected targets** | Any dependency runs in-process (class C-in). |
| Models, providers, agents' outputs, external content, OpenDex | **Untrusted** | As the design says. |

**Components that can modify the security system** are in the TCB whether or
not the design lists them:

- the broker and policy code;
- the stores;
- the migration scripts;
- the dependency manifest and `.venv`;
- the validators;
- the settings and `.env`;
- the OS account.

HR2 correctly added build, deploy, dependencies, migrations and generated
code. This review adds `.env`/settings and the `.venv` installation.

**Conclusion.** Today the effective root of trust is "whoever can run code as
the Jarvis OS user, or reach the HTTP port". The owner-rooted model in the
design becomes meaningful only after:

1. owner authentication exists (HR3-08);
2. the principal model defines the owner (HR3-13);
3. the TCB/OS boundary is stated and enforced for code-level threats (HR3-07).

## 7. Control-plane / data-plane separation

Every place where a data-plane value can become a control-plane value,
either today or under the design as written:

| # | Data-plane source | Becomes control-plane value | Today | Under v0.2.6 text | Finding |
|---|---|---|---|---|---|
| CP-1 | Planner model output | `agent_type`, i.e. which identity (and so which permissions and clearance) runs | **Yes** (F-9) | Unaddressed. `requesting_agent` comes from "AgentRegistry resolution" of a binding whose origin is the task | HR3-05 |
| CP-2 | Planner model output | `requires_approval` flag | **Yes** (F-9, F-10) | Unaddressed (v0.1.3 behaviour) | HR3-05 |
| CP-3 | Planner model output | Purpose class | n/a | "trusted orchestration" whose input is model output | HR3-05 (HR2-04) |
| CP-4 | Planner model output | TASK_INSTRUCTION integrity and the initial `H_exec` | n/a | Labeled ≥ INTERNAL_RECORD | HR3-06 (HR2-05) |
| CP-5 | Planner model output | Task dependency graph, i.e. which outputs flow to which agents | **Yes** | A flow check exists, but the graph is model-chosen | HR3-05 |
| CP-6 | HTTP body | Owner identity (`resolved_by`) | **Yes** (F-2) | "owner channel", undefined | HR3-08 |
| CP-7 | HTTP body | Workspace/project association, i.e. the future compartment | **Yes** (F-4) | Compartments bind to "clearance, not request fields", but the item's compartment at ingestion comes from task context | HR3-12 |
| CP-8 | HTTP body | Objective text, i.e. the future `ObjectiveRef` and root scope | **Yes** (unauthenticated overwrite) | `ObjectiveRef` is "durable, versioned", but its creation channel is unspecified | HR3-08, HR3-01 |
| CP-9 | Agent request | `provider_id` sink target | n/a | Agent-supplied (§11) | HR3-11 |
| CP-10 | Agent request | Requested label floor (can exclude the owner or shorten retention) | n/a | Allowed | HR2-08 |
| CP-11 | Tool behaviour | The tool's declared audience for a secret | n/a | Declared by the adapter | HR2-06 / HR3-07 |
| CP-12 | Tool output | Label of data the tool read | n/a | `H_exec` only | HR3-04 |
| CP-13 | Owner message that quotes untrusted text | OWNER_ASSERTED integrity, i.e. INSTRUCTION-memory eligibility | n/a | Allowed | HR2-26 |
| CP-14 | Node configuration file | Node identity (a residency decision) | n/a | Self-asserted | HR2-16 |

**Verdict.** v0.2.6 correctly states the principle (INV-CB-026, INV-CB-039).
It does not yet enforce the principle at its own inputs. Rows CP-1 to CP-5 and
CP-9 to CP-12 are design-level gaps. Rows CP-6 to CP-8 are live defects that
the design depends on being fixed.

## 8. Verification of HR2 HIGH findings

### HR2-01: agent-selectable data-access lineage — **PARTIALLY CONFIRMED** (superseded by HR3-01)

| Question | Answer from the design text |
|---|---|
| Does the requestor choose the lineage? | **Contradictory.** The §11 table lists `clearance_leaf_id` with source "durable binding". The §22 step 5 pseudocode uses `binding.clearance_leaf_id` from `durable_requester_binding(req.execution_id)`. So **per the decision procedure, the agent does not choose.** However, `clearance_leaf_id` appears as a *field of `ContextRequest`*, INV-CB-005 is worded "per request", and TST-CB-005 tests a single request. |
| Can one execution change lineage? | Not under §22 as written, since there is one binding per `execution_id`. But nothing states the binding is **immutable** or **created once**, and no trusted component is named as its creator. |
| Can multiple clearances be composed? | Not within one execution under §22. Across executions, a parent receiving children's items needs a single lineage covering all their compartments, which requires an owner decision. That is authorized, not an attack. |
| Does execution identity bind exactly one effective context authority? | **Not stated.** It is only implied by the pseudocode. |
| Is mixed-lineage derivation possible? | Only through the ambiguity: an implementer following §11/INV-CB-005 literally would accept a per-request leaf. |

HR2's exploit path (request 1 names K1, request 2 names K2) **does not work
against §22**. It **does** work against §11 and INV-CB-005 as worded. The real
defect is the missing, immutable, trusted-created execution binding
(HR3-01). Severity as an independent issue: **MEDIUM**. It is absorbed by
HR3-01 (HIGH). Freeze blocker: YES (through HR3-01).

### HR2-02: execution taint has no durable home — **CONFIRMED**

- **Where `H_exec` lives:** unspecified. §9.5 says "the broker keeps, per
  execution". §22 manipulates `H_exec[...]` as a map. There is no transaction
  or store.
- **Restart semantics:** after a restart, `emit()` denies because
  `execution_id not in H_exec`. But the next `deliver()` recreates
  `H_exec[execution_id]` as `⊥ ⊔ delivery_label`, i.e. only the newly
  delivered label.
- **Process crash, in the single-process architecture:** a crash also wipes
  the agent's RAM. Laundering therefore needs a **persistence carrier**, and
  carriers exist today:
  - `agent_runs.input` (F-8);
  - `tasks.output_data`, read by `_build_input` (F-8);
  - provider-side conversation state;
  - `qa_feedback` on retry (F-18).
- **Constructed chain:**
  1. Execution E reads a RESTRICTED item.
  2. Partial output is persisted in `tasks.output_data`/`agent_runs`. After
     CR-CB-04 this would be as an item; today it is raw.
  3. A crash occurs.
  4. The retry creates E′ (new `execution_id`, new `H_exec` = task
     instruction label).
  5. The retry logic re-supplies the prior partial output or the QA feedback
     through non-item plumbing.
  6. E′ emits at INTERNAL.
- **Broker failover and recovery:** unspecified.

Severity **HIGH**. Freeze: YES (durability, serialization and restart
semantics must be in the contract). Implementation: YES.

### HR2-03: labels escape through files and external stores — **CONFIRMED**

Walkthrough of `context A → sandbox file → new retrieval → new context item`:

| Carrier | Is the label preserved under the design? | Evidence |
|---|---|---|
| Local or sandbox files | No. `TOOL_ARG_INTERNAL` write is permitted; re-ingestion uses a source policy | §10.4, §10.5; `file.create_sandboxed` exists |
| Database rows outside the item store | No. `tasks.output_data`, `agent_runs.input`, audit metadata and evidence are not items | F-7, F-8 |
| Caches | Yes, inside the broker (§17.5); not for provider-side caches | — |
| External SaaS/API | No. Only `export_allowed` gates the write; read-back is fresh ingestion | §10.4 |
| Browser state, downloads | Not modelled | — |
| Subprocess outputs | Not modelled (no subprocess tool today) | — |
| Exported artifacts, Git commits | No. EXPORT is terminal; re-import is fresh ingestion | §17.4 |

Persistent information **does** need provenance and a label binding outside
the broker's object store, **or** Jarvis-origin artifacts must be
non-ingestible. See §12. Severity **HIGH**. Freeze: YES. Implementation: YES.

### HR2-04: purpose authority is model-controlled — **CONFIRMED** (extended by HR3-05)

Trace from repository and design:

```text
user objective (unauthenticated HTTP text)
  → JarvisAgent.plan (model)
  → TaskPlan{agent_type, title, description, requires_approval}   (model output)
  → persist_plan (structural validation only)
  → Task row
  → [design] "trusted orchestration fixes PurposeBinding"          (input = model output)
  → ContextRequest.purpose_class must equal the binding
```

No trusted component assigns the security purpose from a trusted source. The
design names "trusted orchestration", whose inputs are model output.
Extension: the same trace also makes `agent_type` (identity, and so
clearance) and `requires_approval` model-chosen (F-9). Severity **HIGH**.
Freeze: YES. Implementation: YES.

### HR2-05: task instructions treated as trusted — **CONFIRMED**

- `TASK_INSTRUCTION` requires integrity ≥ INTERNAL_RECORD (§15.2) and is
  described as "Jarvis-generated task statement from the durable
  objective/task records".
- The records' text is model output (F-9), so it is UNTRUSTED under §10.3.
- Placing it in TASK_INSTRUCTION is an integrity upgrade, which violates
  INV-CB-011.
- `H_exec` is initialized from it (§9.5.1), so the first-delivery rule seeds
  every execution with an up-labeled item.
- The integrity lattice has no value distinguishing an *owner instruction*
  (OWNER_ASSERTED) from a *generated plan* (UNTRUSTED model output that trusted
  code has validated structurally).

Severity **HIGH**. Freeze: YES. Implementation: YES.

### HR2-06: logical broker rules cannot stop in-process code — **CONFIRMED**

| Question | Answer |
|---|---|
| Do agents share a Python process? | Yes. `registry.create()` instantiates agent classes in-process (F-15). |
| Do tools and adapters share it? | Yes. `ToolAdapterRegistry` holds Python objects. |
| Is SQLite directly readable? | Yes. `jarvis.db` is a file; `get_session_factory()` is importable everywhere. |
| Are secrets in environment or config? | Yes. `.env` → `Settings.openai_api_key` / `anthropic_api_key` / `tavily_api_key`; `get_settings()` is callable anywhere. |
| Can broker restrictions be bypassed by ordinary Python or file access? | Yes, for any code-level attacker. |

**Which isolation v0.2.6 promises.** Read strictly, INV-CB-002 ("no read path
… except through the broker") promises complete mediation. That is
**process isolation or stronger**. The architecture can deliver only **policy
isolation** (Level 0–1), and only against the model-driven attacker M. The
design must say so (HR3-07). Severity **HIGH**. Freeze: YES (scope
statement). Implementation: YES for secret-bearing adapters and the
self-improvement sandbox.

### HR2-07: no authenticated owner channel — **CONFIRMED**

Attempted path, by reading code only (nothing was executed against a server):

```text
unauthenticated caller
  → POST /tasks/{id}/approve {"resolved_by": "owner"}
  → ApprovalService.approve: status PENDING → APPROVED; task → READY; audit actor_type="human", actor_id="owner"
  → next run_objective / CLI loop executes the task
```

Combined with F-4, the same caller can also trigger that execution via
`POST /chat` naming the victim's `project_id`. The privileged effect today is
bounded, because agents have no external tools and the Execution agent only
drafts. The pattern, however, is exactly the one the design uses for every
owner act.

Owner authentication is a **prerequisite** for:

| Owner-dependent mechanism | Prerequisite? |
|---|---|
| declassification and endorsement | yes |
| durable memory approval (`OWNER_PERSIST`) | yes |
| security-policy approval (`PolicyVersion.owner_event_id`) | yes |
| self-improvement / deployment approval | yes |
| clearance root issuance (capability issuance) | yes |
| node enrollment | yes |
| owner display (`USER_DISPLAY` vs EXPORT) | yes |

Severity **HIGH**. Freeze: YES (the contract must disable owner-dependent
operations until authentication exists). Implementation: YES. Deployment:
YES.

## 9. Verification of HR2 remaining findings

| HR2 | Verdict | Repository / text evidence (re-derived) | Reasoning | HR3 severity | Freeze | Impl |
|---|---|---|---|---|---|---|
| 08 floor abuse | CONFIRMED | §9.5 `L = H_exec ⊔ requested_floor`; ⊔ is ∪ on `excluded_principals` and min on `expires_at`; `flow()` checks `π ∉ excluded` | An agent can add `HUMAN_OWNER` to `excluded_principals`, shorten `expires_at` so the sweep purges, or request NO_FLOW. "Tighten-only" is not always safe. | MEDIUM | YES | YES |
| 09 control-plane implicit flows | CONFIRMED | Task `status`, `error`, `retry_count`, `output_data` are exposed via `_build_input` and the API (F-5, F-8) | Covert and implicit channels exist. INV-CB-008 over-claims unless observables are bounded or labeled. | MEDIUM | YES (statement of scope) | YES |
| 10 rollback | CONFIRMED | §13.3/§22 watermark lives in the grant store; §19.4 has no high-water mark | A backup restore resurrects revoked state. An older approved policy digest stays loadable. | MEDIUM | YES | YES (before durable stores) |
| 11 TOCTOU boundary | CONFIRMED | §22 `deliver()` has no transaction; v0.2.5 R-10 already accepts a residual window and serializes claim with the revocation read | The design should mirror v0.2.5 R-10: a delivery commit plus a declared point of no return. | MEDIUM | YES | YES |
| 12 audit | **PARTIALLY CONFIRMED** | Audit-before-release is only specified for issuance (§22 step 9). N-3 is confirmed (`action_plan_orchestrator.py:317`). **But the `/projects/{id}/audit` route does not return metadata (F-6)**, so titles and exception text are not exposed there. The route does expose actor ids, event types and entity ids to anyone. Objective text in `OBJECTIVE_CREATED` metadata (F-7) is also missed by HR2. | Gap is real; one HR2 exploit step is wrong. | MEDIUM | YES | YES |
| 13 resource bounds | CONFIRMED | No limits in §8–§22; provenance `inputs = all of H_exec` | Quadratic growth and unbounded walks. | MEDIUM | NO (principle should still be stated) | YES |
| 14 declassification canonicalization | CONFIRMED | §9.7 binds "exact `content_digest`" with no canonical form | The owner approves what they perceive; the digest binds bytes. | MEDIUM | YES | YES |
| 15 provider state / router default | **SUPERSEDED BY HR3-09** (router default CONFIRMED; provider-side state CONFIRMED) | F-13 confirms the default. F-11/F-12 show the live path does not use the router at all: every call goes to the cloud unconditionally. | The real exposure is larger than HR2 states. The design semantic "cloud unless the label forbids" (§15.6) is itself default-allow. | HIGH (as HR3-09) | YES | YES |
| 16 node identity self-asserted | CONFIRMED | §22 `self_node_identity()` has no key binding; §18.5 "rooted locally" exception has no TTL | Residency claims are unenforceable against copying. | MEDIUM | YES (single-node constraints) | NO |
| 17 deletion overstated | CONFIRMED | §17.4 lists only providers and exports as exceptions | Backups, files, Git, `agent_runs`, `tasks.output_data` and audit metadata survive. | MEDIUM | YES (wording) | NO |
| 18 persistence order / rule scope | CONFIRMED | §17.1 places AUDIT and CACHE outside the order; §17.2 rule scope is unconstrained | Ambiguity. | MEDIUM | YES | YES |
| 19 CD-01 vs v0.2 §8 | **PARTIALLY CONFIRMED** | v0.2 §7/§8 list `context_scope`/`memory_scope` as **conceptual** Delegation fields ("must never increase … context scope"). v0.2.5 line 1081 already records them as deferred to "owning systems [that] enforce independently". | A separate type is not forbidden. The design's §27 compatibility table omits v0.2 §8, and `memory_scope` is not mapped. The coupling problem is real (HR3-10). | MEDIUM | YES | YES |
| 20 steering residual | CONFIRMED | §15.3 does not state the residual | Communication gap only. | LOW | NO | NO |
| 21 exclusion churn | CONFIRMED | exclusion is keyed on `PrincipalRef` | Low impact, since registration is owner-only. | LOW | NO | NO |
| 22 SecretRef metadata | CONFIRMED | §16.2 model-visible description | Reconnaissance value. | LOW | NO | YES |
| 23 inaccurate observations | CONFIRMED | F-14; and the design also misses F-4, F-5, F-7 (objective), F-8, F-11, F-12, F-17 | The record is incomplete in more places than HR2 found. | LOW | YES | NO |
| 24 over-tainting | CONFIRMED | §9.5 rationale | Conservative by design. | INFO | NO | NO |
| 25 independence | CONFIRMED | HR2 header | Partly discharged by this session (see HR3-16). | INFO | NO (now partly discharged) | NO |
| 26 INSTRUCTION memory / quoted owner text | CONFIRMED; **re-rated MEDIUM** | §17.2 and INV-CB-042 permit INSTRUCTION memory at ≥ OWNER_ASSERTED; integrity is per item; `MemoryType.INSTRUCTION` exists (unused) | A design-level rule that integration would inherit. It is not merely informational. | MEDIUM | YES | YES |

**HR2 tally (HR2-01 to HR2-26):**

| Verdict | Count | Findings |
|---|---|---|
| CONFIRMED | 22 | 02–11, 13, 14, 16–18, 20–26 |
| PARTIALLY CONFIRMED | 3 | 01, 12, 19 |
| NOT CONFIRMED | 0 | — |
| SUPERSEDED | 1 | 15 |

## 10. New findings

Each finding uses the required format. "NEW" means that neither the design
nor HR2 stated it as a finding.

### HR3-01: No immutable ExecutionSecurityContext; execution bindings have no trusted creator

- **Severity:** HIGH
- **New or confirms:** NEW; SUPERSEDES HR2-01; absorbs the binding half of HR2-04.
- **Security property:** single-lineage evaluation (v0.2 §10, §26); complete, unforgeable execution binding.
- **Repository evidence:** F-19. v0.2.5 CR-01 binds Actions, not model executions. Design §11/§22 rely on `durable_requester_binding(execution_id)` and `durable_purpose_binding(execution_id)`, but no CR, stage or component creates them. §11 also lists `clearance_leaf_id` and `execution_id` as `ContextRequest` fields, which invites request-level supply.
- **Attack prerequisites:** an implementation that fills any binding field from request, task or orchestrator-mutable state; or a retry path that mints a new `execution_id` with a different binding.
- **Exploit path:**
  1. Orchestration creates execution E from a task row whose `agent_type`, purpose hints and objective are model- or HTTP-derived (F-4, F-9).
  2. The binding is written by the same mutable code path.
  3. On a retry, E′ is created with a different clearance leaf or purpose.
  4. Or a request-level `clearance_leaf_id` is honoured because §11 lists it.
- **Impact:** lineage mixing (the HR2-01 effect), purpose substitution, and agent substitution. Every gate that reads "the binding" inherits whatever created it.
- **Existing control analysis:** §22 reads bindings from a store (good). Nothing specifies who writes them, when, from which trusted inputs, or that they are immutable.
- **Required design correction:** define `ExecutionSecurityContext` (ESC) as a sealed, insert-once, store-built record created only by a trusted orchestration component from trusted inputs (§11 of this review). Remove `clearance_leaf_id` and `execution_id` from the agent-supplied part of `ContextRequest`. The request carries only an opaque handle that the broker resolves. Restate INV-CB-005 per execution.
- **Freeze blocker:** YES
- **Implementation blocker:** YES (needs an ESC store and a creation CR, which is a v0.2.5 CR-01 sibling)
- **Deployment blocker:** YES

### HR3-02: Execution taint has no durable, serialized home; restart and retry re-seed taint

- **Severity:** HIGH
- **New or confirms:** CONFIRMS HR2-02 (with the persistence-carrier refinement in §8).
- **Security property:** derivation confinement (INV-CB-008).
- **Repository evidence:** design §9.5 and §22 (no store or transaction); F-8 and F-18 (carriers that survive restart).
- **Attack prerequisites:** the ability to cause a crash or retry (malformed provider output, budget stop, exception); a non-item carrier from the prior attempt.
- **Exploit path:** see §8 (HR2-02), steps 1–6.
- **Impact:** laundering of any content an execution has seen.
- **Existing control analysis:** `emit` denies if `H_exec` is missing (good). `deliver` re-creates it from the new delivery alone (bad). The retry and attempt semantics of executions are undefined.
- **Required design correction:**
  - `H_exec` is durable, part of the ESC record's append-only taint log, and updated inside the delivery commit before release.
  - Emissions are serialized against deliveries.
  - A retry is either the **same** execution (inherits `H_exec`), or a new execution whose initial taint is ⊒ the prior attempt's `H_exec` whenever any artifact of the prior attempt (output, error, feedback) is passed on.
  - Loss or inconsistency of taint state terminates the execution (DENY).
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-03: Labels do not follow information outside broker stores

- **Severity:** HIGH
- **New or confirms:** CONFIRMS HR2-03.
- **Security property:** classification persistence through storage (v0.2 §11 case 3).
- **Repository evidence:** `file.create_sandboxed`; F-7 and F-8 (unlabeled stores); design §10.4–§10.5, §17.
- **Attack prerequisites:** an item whose sinks include `TOOL_ARG_INTERNAL` or `TOOL_ARG_EXTERNAL`; a later ingestion path for that artifact.
- **Exploit path:** item → internal/external write → fresh ingestion under a lower source policy → lower-labeled item → flow or export.
- **Impact:** cross-compartment disclosure and downgrade without any owner act.
- **Existing control analysis:** a label exists only on items. Source policies label by source *class*, not by artifact lineage.
- **Required design correction:** see §12. At minimum:
  - every Jarvis-written artifact is registered with a label binding (artifact id or digest → label and provenance);
  - re-ingestion of a Jarvis-origin artifact joins the bound label;
  - unregistered Jarvis-origin artifacts in Jarvis-controlled locations are non-ingestible;
  - external read-back of Jarvis-written content cannot be detected, so such writes are EXPORT (terminal, and require `export_allowed`).
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-04: Tool results and source reads are labeled from H_exec, not from the data they read

- **Severity:** HIGH
- **New or confirms:** NEW. HR2 mentions it inside its §10 table and HR2-03's correction, but not as a finding. It is a direct in-broker downgrade that needs no round trip.
- **Security property:** label correctness at ingestion (INV-CB-006, INV-CB-007).
- **Repository evidence:** design §22 `emit(...)`: for `kind == TOOL_RESULT`, `L = H_exec ⊔ requested_floor` with integrity forced UNTRUSTED. No source-policy label is joined. §6.3 says content returns "as a new item … labeled by the broker"; §10.5 says ingestion uses source policies. The two are never reconciled for tools that *read*.
- **Attack prerequisites:** any tool that reads data (file read, DB query, connector fetch, web fetch) invoked by an execution whose `H_exec` is lower than the data's true classification.
- **Exploit path:**
  1. Execution E has `H_exec` = INTERNAL (task instruction only).
  2. E invokes a read-capable tool on a RESTRICTED `FINANCIAL` record. The tool's argument is INTERNAL, so it is permitted.
  3. The result is emitted as `TOOL_RESULT` with label `H_exec` = INTERNAL.
  4. It flows to `MODEL_CLOUD` or is persisted at INTERNAL.
- **Impact:** a complete classification bypass for every tool-mediated read.
- **Existing control analysis:** none in the text. The only read-capable adapter today (none besides `file.create_sandboxed`, which writes) limits present exposure.
- **Required design correction:**
  - A read-capable tool is a **source**. Its results are ingested under the owner-approved source policy of the **resource read**, joined with `H_exec`: `L = source_label(resource) ⊔ H_exec`.
  - A tool whose source cannot be classified produces NO_FLOW (fail closed).
  - Tool reads of broker-managed data are forbidden; they must go through `request_context`.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-05: Model output selects purpose, agent identity, approval requirement and the flow graph

- **Severity:** HIGH
- **New or confirms:** CONFIRMS HR2-04, extended (NEW for CP-1, CP-2, CP-5).
- **Security property:** no data-plane value becomes control-plane (INV-CB-026, INV-CB-039; v0.2 §2).
- **Repository evidence:** F-9, F-10; §7 rows CP-1 to CP-5.
- **Attack prerequisites:** injected content that reaches the planner (the objective, or future memory or research in planner context).
- **Exploit path:**
  1. Injection steers the planner to assign a task to the agent identity with the broadest clearance (for example a future "auditor" or "dev" agent).
  2. Or it picks a purpose class that unlocks items, or sets `requires_approval=false` with wording that avoids the regex.
  3. Or it wires a dependency edge that routes one agent's output to another.
- **Impact:** clearance and purpose selection by the attacker within everything the owner has issued. That is the confused-deputy root for the whole broker.
- **Existing control analysis:**
  - Structural plan validation only.
  - The approval regex is a heuristic.
  - The design's "trusted orchestration" is unspecified.
- **Required design correction:**
  - agent identity, purpose class, and approval requirement are derived by trusted code from an **owner-approved mapping** of (objective type, task type) to (agent, purpose, clearance lineage, approval class);
  - the planner may only choose among task types the mapping allows for that objective;
  - the planner's free-text choices never select identity, purpose, clearance or approval;
  - dependency edges are flows checked against the recipient's ESC (already INV-CB-041).
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-06: TASK_INSTRUCTION integrity upgrade and taint seeding from model-authored text

- **Severity:** HIGH
- **New or confirms:** CONFIRMS HR2-05.
- **Security property:** integrity non-upgrade (INV-CB-011); firewall (INV-CB-025).
- **Repository evidence:** F-9; design §15.2, §9.5.1.
- **Attack prerequisites:** normal planning.
- **Exploit path:** see §8 (HR2-05).
- **Impact:** injected planner text is presented in a higher-integrity channel and seeds every execution.
- **Existing control analysis:** none.
- **Required design correction:**
  - TASK_INSTRUCTION accepts only structured fields from trusted records: the task type from a closed vocabulary, the objective id, and owner-authored objective text marked OWNER_ASSERTED (after HR3-08).
  - Model-authored task prose is an UNTRUSTED item in `DATA_UNTRUSTED`.
  - `H_exec` is initialized from the ESC's initial label (§11), not from a text item.
  - Add a distinct integrity notion for "trusted-code-validated structure" only if needed. Never raise integrity for model text.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** NO (design-internal; nothing is deployed)

### HR3-07: Isolation promise exceeds the single-process architecture

- **Severity:** HIGH
- **New or confirms:** CONFIRMS HR2-06.
- **Security property:** complete mediation (INV-CB-002); secrets boundary (INV-CB-023/024/030); sandbox (INV-CB-033).
- **Repository evidence:** F-15, F-16; §5 attacker classes C-in and C-os.
- **Attack prerequisites:** code-level presence in the Jarvis process or OS account (a malicious dependency, connector or patch; the dev sandbox running as the same user).
- **Exploit path:** `import sqlite3; open jarvis.db`; `get_settings().anthropic_api_key`; an adapter sends the credential to its own host.
- **Impact:** all data and secrets.
- **Existing control analysis:** import-analysis tests (TST-CB-002) cannot detect this.
- **Required design correction:**
  - State that v0.2.6 provides **policy isolation against model-driven attackers only**.
  - Name the OS account as the TCB boundary.
  - Require the minimum isolation levels in §13 for secret-bearing adapters, untrusted connectors, self-improvement and code execution before those capabilities are enabled.
  - Scope INV-CB-002, 023, 024 and 033 accordingly.
- **Freeze blocker:** YES (scope statement)
- **Implementation blocker:** YES (for secret-bearing, connector and dev-sandbox capabilities)
- **Deployment blocker:** YES

### HR3-08: Every owner-only mechanism rests on a channel that does not exist

- **Severity:** HIGH
- **New or confirms:** CONFIRMS HR2-07.
- **Security property:** root of authority.
- **Repository evidence:** F-1, F-2, F-3, F-6; §8 (HR2-07).
- **Attack prerequisites:** reachability of the HTTP port.
- **Exploit path:** see §8.
- **Impact:** forged owner acts across every release valve once integrated.
- **Existing control analysis:** none. The design lists owner authentication as a deferred dependency but does not disable its dependents.
- **Required design correction:**
  - Adopt PROPOSED-INV-CB-057: every owner-dependent operation is **disabled** until an authenticated owner channel with the §14 properties exists.
  - Until then, all display is EXPORT.
  - Add an owner-channel CR ordered before any broker integration.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-09: Cloud and external egress is default-allow, on the live path and in the design semantic

- **Severity:** HIGH
- **New or confirms:** SUPERSEDES HR2-15.
- **Security property:** minimum disclosure; locality (v0.2 §6, §11, §27).
- **Repository evidence:** F-11, F-12, F-13; design §15.6 ("otherwise `CLOUD_ALLOWED` is permitted"); §10.5 defaults put `MODEL_CLOUD` on agent-internal state, project data and untrusted web content.
- **Attack prerequisites:** none today. Under the design: any label whose sinks include `MODEL_CLOUD` by default policy.
- **Exploit path:**
  - **Today:** every objective, task, dependency output and research query goes to Anthropic/OpenAI and Tavily without any check.
  - **Under the design:** a label permitting `MODEL_CLOUD` routes to any cloud provider in the per-level list. A provider-less call path, or the router default, adds CLOUD_ALLOWED. A research/search query is an unmodelled egress of context (a query string derived from items).
- **Impact:** sensitive context crosses the provider boundary without an explicit destination decision.
- **Existing control analysis:** v0.2.3 forbids fallback weakening *within* the router, but the router is not on the live path. The design gates cloud by label only.
- **Required design correction:** freeze the following semantic.
  > Transmission of any item, or anything derived from an item, to any destination outside the local node is permitted only under an explicit, owner-rooted destination authorization. That covers cloud model providers, search and research APIs, and any external tool. The authorization names the destination identity (provider id, or tool plus endpoint class), the maximum level and the compartments. It is the meet of the item label, the ESC clearance, and an owner-approved provider/destination allow-list that records retention and training terms. **Absence of authorization is DENY.** The router default is never an input. Search queries are `TOOL_ARG_EXTERNAL` flows. Fallback, retry and re-selection may only choose destinations inside the same authorization and need a new grant (HR3-11).
- **Freeze blocker:** YES
- **Implementation blocker:** YES (containment of `get_default_provider` and research providers is a CR)
- **Deployment blocker:** YES (already live)

### HR3-10: Context reads use an existential authority check decoupled from the execution's lineage

- **Severity:** MEDIUM
- **New or confirms:** NEW. HR2 describes it narratively in its §8 probe 2 but not as a finding. It relates to HR2-19.
- **Security property:** exactly one lineage per action (v0.2 §10); revocation effectiveness.
- **Repository evidence:** design §22 step 4 `has_any_effective_lineage(binding.principal, purpose.objective_ref, now)`; §13.2 clearance edges end on expiry, revocation or *lifecycle* events only.
- **Attack prerequisites:** the agent holds more than one authority lineage for an objective, or the owner revokes the authority edge but not the clearance edge.
- **Exploit path:**
  1. The owner revokes delegation D that justified X's task.
  2. X also holds sibling delegation D′ for the same objective.
  3. Step 4 passes on D′.
  4. X's clearance is unaffected by revoking D.
  5. X keeps reading.
- **Impact:** revocation of the action lineage does not stop data access.
- **Existing control analysis:** none. The two lineages have no consistency rule.
- **Required design correction:**
  - The ESC names exactly one authority leaf and one clearance leaf.
  - Step 4 checks **that** authority leaf, not "any".
  - Revoking either leaf ends the execution's context access.
  - Clearance issuance for an execution requires that its authority leaf is effective.
  - Map `memory_scope` explicitly (PERSIST sinks and persistence classes in the clearance).
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-11: Grant ↔ provider-router binding is unspecified

- **Severity:** MEDIUM
- **New or confirms:** NEW.
- **Security property:** destination binding; no fallback widening (v0.2 §6, §27; v0.2.3).
- **Repository evidence:**
  - design §11: `provider_id` is agent-supplied;
  - §22 step 8: `provider_eligible(req.provider_id, L)`;
  - §13.3: the grant's "sink target" is a parenthetical;
  - v0.2.3 routes by requirements and may re-select on retry;
  - v0.2 §27: agents request requirements and Jarvis schedules.
- **Attack prerequisites:** a router retry or re-selection after grant issuance, or agent choice of provider.
- **Exploit path:**
  1. A grant is issued for provider A (allowed for CONFIDENTIAL).
  2. A fails.
  3. The router re-selects provider B, which is eligible for the ProviderRoutingRequest privacy but not in the CONFIDENTIAL allow-list.
  4. Delivery uses the existing grant, because the sink kind `MODEL_CLOUD` still matches.
- **Impact:** a less-trusted provider receives content.
- **Existing control analysis:** the provider is checked at issue. Delivery revalidation re-runs step 8 with `req.provider_id`, which is not the router's actual choice.
- **Required design correction:**
  - The grant binds the exact destination identity: provider id, model id and locality.
  - The PromptAssembler obtains the router's selection **before** requesting the grant, from requirements derived by the broker; agents never pick providers.
  - Any re-selection needs a new grant, and delivery verifies that the actually-dispatched provider equals the bound one.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** NO

### HR3-12: Workspace/project association is caller-controlled; compartment derivation is unspecified

- **Severity:** MEDIUM (design) / HIGH as a live defect
- **New or confirms:** NEW. The design's O-2 covers only `memory_tools`.
- **Security property:** compartment integrity (TC-12; v0.2 §26).
- **Repository evidence:** F-4, F-5.
- **Attack prerequisites:** HTTP access and knowledge of a project id (ids leak via the audit route and task listings).
- **Exploit path:**
  1. `POST /chat {workspace_id: W_attacker, project_id: P_victim}`.
  2. The victim project's objective is overwritten.
  3. The victim's READY tasks run under `workspace_id=W_attacker`.
  4. Research and decision outputs are promoted into W_attacker's memory.
  5. `GET /projects/P_victim/tasks` returns the outputs.
- **Impact:** live cross-workspace disclosure and integrity violation. Under the design, items ingested from such a task would receive compartments derived from an inconsistent (W, P) pair.
- **Existing control analysis:** none.
- **Required design correction:**
  - Compartments are derived only from the canonical durable parent chain (project → workspace → owner principal) held by the ESC.
  - They are never derived from request-supplied pairs.
  - An inconsistent chain is DENY.
  - Add a CR for API ownership checks (a deployment blocker independent of v0.2.6).
- **Freeze blocker:** YES (derivation rule)
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-13: The principal model cannot represent the humans that exist, and never says which human is the owner

- **Severity:** MEDIUM
- **New or confirms:** NEW.
- **Security property:** root-of-trust definition; cross-user isolation (TC-13).
- **Repository evidence:** F-17. Design §10.2 `USER_PRIVATE(PrincipalRef)`; TC-13 "another principal's private data".
- **Attack prerequisites:** any second `User` row, which `/chat` creates on demand.
- **Exploit path:** an implementation maps every `User` to `HUMAN_OWNER`, since that is the only human kind. Any registered email then acts as owner. Alternatively, non-owner users have no representable private compartment, so their data defaults to the owner's.
- **Impact:** owner impersonation by registration; undefined cross-user boundaries.
- **Existing control analysis:** v0.2.5 HR-19 requires "one canonical owner id and no alias table", but nothing binds that id to an authenticated human or to `User` rows.
- **Required design correction:**
  - State a single-owner assumption for v0.2.6.
  - Define the canonical owner principal and how it is bound to the owner channel.
  - Declare every other `User` a non-principal: no clearance roots, no owner acts, and data compartmented `USER_PRIVATE(user)`, readable only under owner-issued clearance.
  - Defer multi-human principals to a separate design.
- **Freeze blocker:** YES
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-14: Content-bearing orchestration stores and audit metadata are missing from the change-request catalogue

- **Severity:** MEDIUM
- **New or confirms:** NEW; extends HR2-12 and HR2-23.
- **Security property:** complete mediation of persistence (INV-CB-019/020); metadata-only audit (INV-CB-035).
- **Repository evidence:** F-5, F-7 (objective text in `OBJECTIVE_CREATED`; `decision_reason`), F-8 (`agent_runs.input`/`output`, `tasks.output_data`, `tasks.error`, `tasks.description`).
- **Attack prerequisites:** none. These are existing stores.
- **Exploit path:** after integration, content bypasses the broker by living in orchestration tables that dependent agents and the API read directly.
- **Impact:** broker bypass for every inter-agent flow; audit containing payload.
- **Existing control analysis:** CR-CB-03 covers only memory titles. CR-CB-04 covers the plumbing, not the storage. CR-CB-06 covers only the executor and orchestration error fields.
- **Required design correction:** add CRs so that these fields either become item references (content in the item store, labeled) or are removed. Extend CD-05's non-disclosability to all legacy content stores. Add the audit route and the task routes to the owner-channel CR.
- **Freeze blocker:** NO (catalogue correction; the principle is covered by HR3-03)
- **Implementation blocker:** YES
- **Deployment blocker:** YES

### HR3-15: Contract inconsistencies in the grant and request schemas

- **Severity:** LOW
- **New or confirms:** NEW.
- **Security property:** implementability without implementer choice.
- **Repository evidence (design text):**
  - INV-CB-001 requires the grant to bind *environment*, but the `ContextGrant` (§13.3) has no environment field.
  - §22 uses `req.uses`, but `ContextRequest` (§11) has no `uses` field.
  - `operation = DERIVE` has no matching sink.
  - `ContextGrant.sink` "(+ sink target)" is not a typed field.
- **Attack prerequisites:** implementer ambiguity.
- **Exploit path:** an implementation omits the environment binding, so a grant issued in one environment class is presented in another on the same node.
- **Impact:** minor, but it violates exact-contract discipline.
- **Required design correction:** add `environment` and a typed `sink_target` to the grant; add `uses` to the request (agent may only request ONE_SHOT, and EXECUTION is policy-granted); define DERIVE or remove it.
- **Freeze blocker:** YES (text-only)
- **Implementation blocker:** NO
- **Deployment blocker:** NO

### HR3-16: Residual independence limitation of this verification

- **Severity:** INFO
- **New or confirms:** NEW (successor to HR2-25).
- **Security property:** assurance.
- **Repository evidence:** §1.
- **Attack prerequisites:** —
- **Exploit path:** shared model-family blind spots.
- **Impact:** undiscovered defects.
- **Required design correction:** a human review of §6, §13 and §14 before freeze.
- **Freeze blocker:** NO (recommended, not blocking)
- **Implementation blocker:** NO
- **Deployment blocker:** NO

## 11. Execution security context analysis

**Required: yes.** Define a first-class, sealed, insert-once
`ExecutionSecurityContext` (ESC), created only by trusted orchestration and
never by an agent or model.

| Field | Required? | Source (must be trusted) | Agent may change? |
|---|---|---|---|
| `execution_id` | yes | ESC store (generated) | no |
| `parent_execution_id` / attempt number | yes | ESC store | no |
| `principal` (requesting) | yes | CR-01 requester binding | no |
| `agent` (`PrincipalRef`, ACTIVE at creation) | yes | owner-approved task-type → agent mapping (HR3-05) | no |
| `authority_leaf_id` | yes | v0.2.5 lineage for the task | no |
| `clearance_leaf_id` | yes | owner-issued clearance lineage for that agent and objective | no |
| `objective_ref` | yes | durable `ObjectiveRef` created via the owner channel | no |
| workspace/project (canonical chain) | yes | durable parent chain (HR3-12) | no |
| `purpose_class` | yes | owner-approved mapping (HR3-05) | no |
| `originating_task_id` | yes | task row | no |
| `node`, `environment_class` | yes | broker's own identity | no |
| `created_at` (trusted clock) | yes | trusted clock | no |
| `revocation_epoch_at_creation` | yes | external monotonic epoch (HR2-10) | no |
| `policy_version` (security policy) | yes | owner-approved digest | no |
| `destination_authorization` (provider/cloud policy) | yes | owner-approved allow-list (HR3-09) | no |
| `initial_label` (seed of `H_exec`) | yes | ⊔ of trusted structured inputs | no |
| `initial_integrity` | yes | from trusted structured inputs only | no |
| `taint_log_ref` | yes | durable append-only `H_exec` (HR3-02) | only grows |
| `acceptable_taint_ceiling` | recommended | owner/policy | no |

**Does the ESC solve the HR2 HIGHs?**

| Finding | Solved by ESC? | What remains |
|---|---|---|
| HR2-01 | **Yes**, fully, once `clearance_leaf_id` is ESC-only and immutable. | — |
| HR2-02 | **Partly.** The ESC gives taint a durable home. | The retry/attempt inheritance rule, serialization, and "state loss → terminate" must still be stated. |
| HR2-04 | **Partly.** The ESC removes per-request purpose choice. | The ESC's *creator* must take purpose from an owner-approved mapping, not from the planner. The ESC only moves the problem to a single, reviewable place. |
| HR2-05 | **Partly.** The ESC's `initial_label`/`initial_integrity` replaces "first delivery is the TASK_INSTRUCTION". | The TASK_INSTRUCTION channel must still refuse model prose. |
| HR3-10 | **Yes**, if the ESC names both leaves and step 4 uses the named authority leaf. | — |
| HR3-12 | **Yes**, for compartment derivation. | API ownership checks (deployment). |

Agents must be **prohibited** from choosing or changing any ESC field after
creation. The only agent-influenced value is the taint, which only grows.

## 12. Persistent information-flow analysis

**Finding.** Labels and provenance must follow brokered information after it
leaves RAM. Otherwise relabeling is trivial (HR3-03, HR3-04).

| Artifact | Needs a label binding? | Mechanism | If not bound |
|---|---|---|---|
| Database rows (item store) | yes (already items) | label is part of the item | — |
| Legacy content rows (`memories`, `evidence`, `tasks.output_data`, `agent_runs`, audit metadata) | yes | CR to convert to item references, or non-disclosable (CD-05 extended) | non-disclosable |
| Files written by Jarvis tools (sandbox, reports, generated code) | yes | artifact registry: `(path, content_digest) → item_id` whose label is ⊒ the writer's `H_exec` | non-ingestible |
| Caches (broker) | yes | §17.5 | — |
| Provider-side caches/conversation state | cannot be labeled | forbid cross-execution reuse (PROPOSED-INV-CB-058) | — |
| Embeddings and vector stores | yes | derived items, partitioned (§17.5) | forbidden outside the broker |
| Model-generated artifacts | yes | items (EXECUTION persistence) | — |
| Downloaded files (inbound) | yes | source policy at ingestion | NO_FLOW if unclassifiable |
| Reports, exports | terminal | EXPORT sink; `export_allowed` | — |
| Browser downloads/state | out of scope until a browser tool exists | treat any browser tool as EXPORT plus an untrusted source | — |
| Tool-created external records (SaaS) | terminal | `TOOL_ARG_EXTERNAL`; read-back = fresh UNTRUSTED ingestion, **and** the content cannot be re-labeled below the writer's label if Jarvis can correlate it (digest match) | treat as EXPORT |

Every persistent artifact containing brokered information needs:

- an attached label (or item reference);
- provenance (writer's ESC and `H_exec` snapshot);
- owner/project scope (compartments);
- reader constraints (via the label's compartments and `excluded_principals`,
  checked against the reader's clearance).

Where Jarvis cannot keep a binding (outside systems), the write must be a
terminal EXPORT that requires `export_allowed`. Relabeling is then prevented
by construction: nothing below the writer's label can re-enter from a
location Jarvis controls, and anything returning from outside is UNTRUSTED
and cannot be *more* trusted than before.

**Residual:** an external system can echo exported content back as "new"
data at a lower label. This is inherent. It is bounded by `export_allowed`,
which is false for every non-PUBLIC category in §10.5.

## 13. Isolation analysis

| Level | Meaning | Defends against |
|---|---|---|
| 0 | Application convention | Nothing, beyond honest code |
| 1 | Python module separation, sealed contracts | Model-driven attacker M only |
| 2 | Separate worker processes, restricted IPC, no DB handle | In-process code in the worker (C-in), if the worker has no file access |
| 3 | OS sandbox/container, separate OS user, network policy | Same-user code (C-os) inside the sandbox; egress control |
| 4 | Separate host/node | Host compromise of the other host |

**Minimum required:**

| Component | Minimum | Justification |
|---|---|---|
| Ordinary agents (reviewed Jarvis code, untrusted model I/O) | **Level 1** | The attacker is M. Agent code is trusted Jarvis code. Sufficient if every model output reaches the control plane only through trusted code (§7). |
| Reviewed ToolAdapters without secrets | **Level 1** | Trusted, protected-target code. |
| Secret-using tools | **Level 2**, with egress enforced outside the adapter (**Level 3** network policy for the audience binding) | Audience binding cannot be enforced by the adapter's own declaration (HR2-06). |
| Third-party connectors/plugins | **Level 3** (no credentials, no DB/`.env` access) | Class C-in by assumption. |
| Self-improvement / development agents | **Level 3** (separate OS user or container; no `jarvis.db`, `.env`, `.venv` write, or production network) | Can author code, which is class C-in by construction. |
| Untrusted code execution | **Level 3** minimum; **Level 4** for anything touching production data | Arbitrary code. |
| Context Broker and stores | Level 1 now; **Level 2** (broker as its own process owning the DB, with agents holding no DB handle) before any secret-bearing or connector capability ships | Complete mediation needs the monitor to own the store. |

**What v0.2.6 promises (and should say):**

- **policy isolation** against model-driven attackers;
- **no** process isolation;
- **no** OS isolation.

INV-CB-002 must be scoped to "within the reviewed Jarvis codebase, against
model-driven attackers". The Level-2/3 requirements are preconditions for
enabling the capabilities in the table, not for the pure stages.

## 14. Owner-channel analysis (design review only)

Properties required before any owner-only rule becomes meaningful:

1. **Authentication** of the human owner. Authenticating a client process
   (OpenDex, CLI) is not enough. Use a phishing-resistant factor (passkey
   / WebAuthn or equivalent) or an OS-local authenticated channel with
   documented limits.
2. **Principal binding**: a session maps to exactly the canonical
   `PrincipalRef(HUMAN_OWNER, id)` (HR3-13), never to a body field.
   `resolved_by` and similar fields are removed from request schemas.
3. **Session binding and expiry**: short-lived sessions, bound to the device
   and origin; re-authentication for high-impact acts (declassification,
   policy approval, clearance roots, node enrollment, deployment).
4. **CSRF protection** for browser-reachable endpoints (same-site cookies
   plus an anti-CSRF token or Origin checks). Loopback binding alone is not
   CSRF protection.
5. **Explicit approval action**: the owner sees the exact canonical content,
   digest, destination and scope (§33), and confirms that specific action
   identity. There are no blanket approvals.
6. **Replay resistance**: every owner act carries a unique, single-use
   `owner_event_id` bound to the digest of the approved request (v0.2.5
   HR-06 pattern).
7. **Audit**: owner acts are recorded before they take effect (audit-before-
   release) in an append-only, hash-chained log.
8. **Remote access**: disabled by default. If enabled, it uses mutual
   authentication and must not be reachable from agents, tools or the
   sandbox network.
9. **Device trust**: owner-channel devices are registered nodes with their
   own data ceilings (display is a node-bound flow). A device running a
   screen-capturing agent is an EXPORT destination.
10. **Separation from agents**: no agent, tool, model or connector can reach
    owner-channel endpoints or forge an owner session (process or network
    separation, Level 2+).

**Ordering.** Owner-channel work **must precede v0.2.6 runtime
integration** (v0.2.6.9) and the enabling of any owner-dependent operation. It
need **not** precede the pure, disconnected stages v0.2.6.1–.8, which are
unreachable at runtime, like v0.2.5.1.

## 15. Cloud / provider boundary analysis

| Question | Answer |
|---|---|
| Is cloud use currently default-allow? | **Yes, unconditionally** on the live path (F-11, F-12). It is default-allow in the v0.2.3 contract (F-13), and label-gated default-allow in the design (§15.6). |
| Could context labels accidentally permit cloud? | **Yes.** §10.5 defaults put `MODEL_CLOUD` on agent-internal state, project data and untrusted web content. INTERNAL items reach any listed cloud provider without a destination decision. |
| Can provider choice widen exposure? | Yes. The provider id is agent-supplied (§11), and grants do not bind the router's actual choice (HR3-11). |
| Can retry/fallback switch to a less-trusted provider? | Within v0.2.3, only among providers meeting the same `PrivacyRequirement`. That requirement is binary (LOCAL_ONLY/CLOUD_ALLOWED), so every cloud provider is interchangeable to the router. Per-level allow-lists exist only in the design text and are not bound into the grant. |
| May sensitive context cross provider boundaries? | Today, yes: everything. Under the design, CONFIDENTIAL can, via the allow-list. Provider-side state can carry content across executions (HR2-15 half). |

**Recommended frozen semantic** (verified as necessary above, and adopted):

> **Cloud and provider transmission requires explicit destination
> authorization; absence of authorization is DENY.**

That means:

- `MODEL_CLOUD` (and every external destination, including search and
  research APIs) must be in the label **and** the ESC clearance **and** an
  owner-approved destination allow-list naming provider id, retention and
  training terms, maximum level and compartments;
- RESTRICTED is never cloud-eligible;
- the grant binds the exact provider/model;
- the router receives a privacy requirement derived by the broker, and its
  default is never used for content-bearing requests;
- provider-side conversation state is never reused across executions;
- no fallback leaves the authorization.

A containment CR for `get_default_provider()` and the research providers
must precede any claim that Jarvis enforces locality.

## 16. ContextClearance analysis

- **The type is sound.** Order, meet, check-not-clip issuance, owner roots and
  NO_CLEARANCE mirror v0.2.5.1 correctly. No join is provided (correct).
- **Anchoring (CD-01).** A separate type with its own algebra is right:
  it avoids mixing restriction-sets and permission-sets in one `meet`, as
  HR2 §8 B.3 argues correctly. What is missing is **coupling**:
  - both leaves named once in the ESC;
  - the authority leaf checked specifically (HR3-10);
  - revocation of either leaf ends the execution's access;
  - child creation issues both edges in one transaction.

  Carrying clearance on the `DelegationRecord` edge (HR2 option C) is one
  valid realization. It is not the only one, and requires a v0.2.5
  amendment.
- **`memory_scope`.** Map it explicitly: PERSIST sinks plus maximum
  persistence class plus compartments writable. A clearance without
  `PERSIST` grants zero memory scope.
- **Redelegation.** `redelegation: (redelegable_clearance, depth)` is
  correct, but the design never says the child clearance's `objective_ref`
  must equal the parent's. It says so only in the order relation ("same
  objective"). State it at issuance.

## 17. Label / provenance analysis

- **The lattice is correct** (verified independently). The product order is
  a join-semilattice; ⊔ is commutative, associative and idempotent; NO_FLOW
  is absorbing. `F(L1⊔L2) = F(L1) ∩ F(L2)` holds per dimension. HR2's table
  is accurate.
- **Who supplies ⊔ inputs** is the weakness:
  - requested floors (HR2-08);
  - tool-read labels (HR3-04);
  - the initial label (HR3-06);
  - node sets (HR2-16).
- **`label.nodes` must be non-empty with "no any-node value"**, but no node
  registry exists. For the single-node phase, fix `nodes = {local}` for all
  constructible labels (HR2-16).
- **Provenance `inputs` = all of `H_exec`**: correct for soundness. Use an
  `H_exec` snapshot reference to bound size (HR2-13). Acyclicity follows
  from "inputs pre-exist", but must be stated (PROPOSED-INV-CB-060).
- **Declassification** changes confidentiality only. It must never change
  integrity: the declassified item's integrity equals the source's (see the
  PROPOSED-INV-CB-059 correction in §23).

## 18. Purpose analysis

- **The closed vocabulary with no `GENERAL`/`ANY` is correct.**
- **The source of purpose is the defect** (HR3-05). The only acceptable
  source is an owner-approved mapping, resolved by trusted code at ESC
  creation.
- **Purpose classes are coarse.** Objective-level isolation comes only from
  compartments. The design documents this, and it is acceptable if stated as
  a limitation.
- **Rule 3** ("derived items born confined") is correct and important.

## 19. Capability / TOCTOU analysis

- **Store-held grants and a reference monitor are the correct choice** in a
  single trust domain. Bearer tokens are correctly rejected.
- **Binding gaps:**
  - environment (HR3-15);
  - exact provider/destination (HR3-11);
  - ESC id rather than loose fields (HR3-01).
- **TOCTOU:** adopt a delivery commit mirroring v0.2.5 R-10:
  1. revalidate grant, items, clearance, authority leaf, policy version and
     external epoch;
  2. consume;
  3. append taint;
  4. write audit;
  5. commit;
  6. then transmit.

  Transmission is the declared point of no return (HR2-11).
- **Rollback:** a monotonic epoch anchored outside the revocable store, and a
  policy high-water mark (HR2-10). Until an external anchor exists, a
  detected restore (epoch regression) must deny everything.

## 20. Multi-node analysis

- **CD-04 (single-node only) is correct and necessary.**
- Freeze these rules:
  - until key-bound node identity exists, every label's `nodes` is exactly
    `{local}`, and `CROSS_NODE_TRANSFER` never appears in constructible
    labels;
  - the "owner-rooted locally" offline exception is TTL-bounded;
  - at-rest encryption with a node-bound key is a prerequisite for any
    device-local confidentiality claim (HR2-16, HR2 §19).
- **Stolen laptop:** the broker gives no protection against disk reads. The
  design must not imply otherwise.

## 21. Self-improvement analysis

- **The policy-activation-by-owner-digest idea is sound**, but it depends on:
  - owner authentication (HR3-08);
  - OS isolation of the dev sandbox (HR3-07; Level 3);
  - a policy high-water mark (HR2-10).
- **Protected targets must add:**
  - build and deploy scripts;
  - dependency manifests and the installed environment (`requirements.txt`,
    `pyproject.toml`, `.venv`);
  - migrations;
  - `.env`/settings;
  - validator scripts;
  - generated code.
- **INV-CB-033** ("no secret resolution in DEV_SANDBOX") is false today: raw
  keys are in `.env` and in-process settings (F-15). It holds only under
  Level-3 isolation, with the sandbox unable to read `.env` or `jarvis.db`.

## 22. Invariant audit (INV-CB-001 … 045)

Independent classification. Where it differs from HR2, the difference is
noted.

| INV | Class | Reason |
|---|---|---|
| 001 | INCOMPLETE | Requires environment binding, but the grant has no environment field (HR3-15). The binding creator is unspecified (HR3-01). |
| 002 | INCOMPLETE | Holds only against model-driven attackers at Level 1 (HR3-07). |
| 003 | VALID | |
| 004 | VALID | Valid as a statement. Its effectiveness depends on HR3-08. |
| 005 | AMBIGUOUS | "Per request" vs per execution; conflicts with §22 (HR3-01). *(HR2: UNSOUND)* |
| 006 | INCOMPLETE | Tightening abuse (HR2-08); tool-read labels (HR3-04). |
| 007 | VALID | |
| 008 | INCOMPLETE | Durability and serialization (HR3-02); tool reads (HR3-04); implicit flows (HR2-09). |
| 009 | VALID | |
| 010 | AMBIGUOUS | Canonicalization; integrity of the declassified item (HR2-14). |
| 011 | VALID | Correct statement. The design violates it via TASK_INSTRUCTION (HR3-06). |
| 012 | VALID | |
| 013 | VALID | |
| 014 | INCOMPLETE | Covers broker stores only; unbounded walk. |
| 015 | VALID | |
| 016 | VALID | |
| 017 | INCOMPLETE | Binding origin (HR3-05). |
| 018 | VALID | |
| 019 | AMBIGUOUS | Rule scope (HR2-18). |
| 020 | VALID | Scope is items. Non-item stores are handled by HR3-14. |
| 021 | INCOMPLETE | Rollback (HR2-10); provider binding (HR3-11). |
| 022 | INCOMPLETE | Rollback. Authority-leaf revocation does not end clearance (HR3-10). |
| 023 | INCOMPLETE | Audience enforced by adapter declaration (HR3-07). |
| 024 | UNSOUND | An absolute that cannot hold against adapter code, crash dumps or screens. |
| 025 | INCOMPLETE | TASK_INSTRUCTION (HR3-06); live non-assembler path (HR3-09). |
| 026 | VALID | |
| 027 | INCOMPLETE | Label-gated default-allow; needs explicit destination authorization (HR3-09). |
| 028 | INCOMPLETE | Re-ingestible internal writes (HR3-03). |
| 029 | INCOMPLETE | Self-asserted node (HR2-16). |
| 030 | REDUNDANT | Subsumed by 023. |
| 031 | AMBIGUOUS | Unbounded local exception. |
| 032 | VALID | |
| 033 | INCOMPLETE | False without Level-3 isolation (§21). *(HR2: VALID)* |
| 034 | INCOMPLETE | Approval authenticity, high-water mark, protected targets. |
| 035 | AMBIGUOUS | Audit-failure behaviour unspecified. |
| 036 | VALID | |
| 037 | VALID | |
| 038 | VALID | |
| 039 | VALID | Correct statement. Violated upstream by HR3-05. |
| 040 | VALID | |
| 041 | VALID | |
| 042 | INCOMPLETE | Quoted untrusted text in owner messages (HR2-26). |
| 043 | VALID | |
| 044 | VALID | |
| 045 | VALID | Side channels are an accepted limitation. |

**Totals (45):**

| Class | Count |
|---|---|
| VALID | 22 |
| AMBIGUOUS | 5 |
| INCOMPLETE | 16 |
| UNSOUND | 1 |
| REDUNDANT | 1 |

HR2 reported VALID 23, AMBIGUOUS 4, INCOMPLETE 15, UNSOUND 2, REDUNDANT 1.
The differences are INV-CB-005 (HR2 UNSOUND → HR3 AMBIGUOUS) and INV-CB-033
(HR2 VALID → HR3 INCOMPLETE).

## 23. Proposed invariant audit

### HR2's proposals (046–060)

| ID | Class | Comment |
|---|---|---|
| 046 | REQUIRED | Generalize to the ESC (INV-CB-061). |
| 047 | REQUIRED | Add the retry-inheritance rule (HR3-02). |
| 048 | USEFUL | Prefer "closed, reviewed low-bandwidth observable set, plus an accepted residual" over labeling every observable. |
| 049 | REQUIRED | Extend to agent identity and approval class (HR3-05). |
| 050 | REQUIRED | |
| 051 | REQUIRED | |
| 052 | REQUIRED | |
| 053 | REQUIRED | Before any durable store. |
| 054 | REQUIRED | |
| 055 | REQUIRED | |
| 056 | REQUIRED | The principle is required now; numeric bounds may be deferred. |
| 057 | REQUIRED | |
| 058 | REQUIRED | Strengthen to explicit destination authorization (INV-CB-063). |
| 059 | USEFUL | The canonicalization is required. The rule "keeps UNTRUSTED integrity unless endorsed" is imprecise. The correct rule is that declassification never changes integrity (the new item has the source's integrity). |
| 060 | REQUIRED | |

Tally: REQUIRED 13, USEFUL 2, UNNECESSARY 0, INCORRECT 0.

### Additional proposed invariants (not applied)

| ID | Proposed invariant |
|---|---|
| PROPOSED-INV-CB-061 | Every execution has exactly one sealed, insert-once ExecutionSecurityContext, created only by trusted orchestration from trusted inputs. No agent-, model- or request-supplied value populates any ESC field, and no ESC field changes after creation. |
| PROPOSED-INV-CB-062 | A read-capable tool is a source. Its result is labeled `source_policy(resource) ⊔ H_exec`. An unclassifiable resource yields NO_FLOW. Tools never read broker-managed stores directly. |
| PROPOSED-INV-CB-063 | No item, or derivative of an item, leaves the local node (cloud model, search/research API, external tool) without an explicit owner-rooted destination authorization bound into the grant (exact destination identity). Absence is DENY. The router default is never an input. |
| PROPOSED-INV-CB-064 | Compartments of an execution and its emissions derive only from the canonical durable parent chain in the ESC. An inconsistent chain is DENY. |
| PROPOSED-INV-CB-065 | A grant binds the exact provider/model or destination actually used. Any router re-selection requires a new grant. Delivery verifies dispatched = bound. |
| PROPOSED-INV-CB-066 | Context access for an execution requires that the ESC's named authority leaf **and** clearance leaf are both effective at `t`. Revoking either ends access. |
| PROPOSED-INV-CB-067 | Exactly one canonical HUMAN_OWNER principal exists, reachable only through the authenticated owner channel. No other human `User` is a principal, and none may perform an owner act. |
| PROPOSED-INV-CB-068 | Every v0.2.6 guarantee states the attacker class it holds against. Guarantees against code-level attackers require the isolation level named in the contract, and are disabled (capability not enabled) until that level exists. |
| PROPOSED-INV-CB-069 | A retry or continuation that receives any artifact of a prior attempt (output, error text, QA feedback) starts with `H_exec` ⊒ the prior attempt's `H_exec`. |

## 24. CD-01 through CD-06 decisions

| CD | HR2 | HR3 | Agree? | Reasoning | Security consequence |
|---|---|---|---|---|---|
| CD-01 separate ContextClearance lineage | REVISE | **REVISE** | Yes (on outcome; differs on mechanism) | Keep a separate type and algebra. Require coupling: both leaves are fixed in the ESC, the named authority leaf is checked, revocation of either ends access, and issuance is atomic. HR2's option C (on the `DelegationRecord` edge) is acceptable but not mandatory. Reclassify against v0.2 §8 and map `memory_scope`. | Removes lineage shopping (HR2-01) and revocation decoupling (HR3-10). |
| CD-02 execution-level taint | REVISE | **REVISE** | Yes | Approve execution taint in principle. Require a durable, serialized taint log in the ESC, retry inheritance (INV-CB-069), bounded observables, and an acceptable-taint ceiling. | Closes restart/retry laundering (HR3-02). |
| CD-03 owner-only per-item declassification | REVISE | **REVISE** | Yes | Keep owner-only and per-item. Add canonicalization. Integrity is unchanged by declassification. **Disabled until the owner channel exists.** | Prevents forged or steganographic declassification. |
| CD-04 single-node only | APPROVE | **APPROVE** (with constraints) | Yes | Plus: `nodes = {local}` only; bounded offline exception; key-bound identity before any second node. | Keeps residency claims honest. |
| CD-05 legacy Memory/Evidence non-disclosable | APPROVE | **APPROVE** | Yes | Correct and fail-closed. Recommend extending the same rule to `tasks.output_data`, `agent_runs`, and audit metadata (HR3-14) as a separate scope item. | Prevents unlabeled legacy data entering the broker. |
| CD-06 per-level provider eligibility | REVISE | **REVISE** | Yes (stronger) | Replace the label-gated default with explicit destination authorization; absence = DENY (§15). RESTRICTED is never cloud. CONFIDENTIAL and INTERNAL cloud use require allow-listed providers with recorded retention/training terms. The grant binds the provider. | Closes cloud default-allow (HR3-09, HR3-11). |

## 25. Change-request dependency graph

**New CRs identified by this review (not authorized):**

| ID | Change |
|---|---|
| CR-OWN-01 | Owner-channel authentication and owner principal binding (§14; HR3-08, HR3-13) |
| CR-API-01 | API authorization: ownership checks on workspace/project/task routes; audit and task routes owner-only (HR3-12, HR3-14) |
| CR-ESC-01 | ExecutionSecurityContext store and trusted creation, including the owner-approved task-type → (agent, purpose, clearance, approval class) mapping (HR3-01, HR3-05) |
| CR-EGR-01 | Egress containment: `get_default_provider()` and research providers are reachable only through broker-derived requirements and destination authorization. The router default is never used for content (HR3-09). |
| CR-ART-01 | Artifact label registry for Jarvis-written files and records; re-ingestion join (HR3-03) |
| CR-LEG-01 | Convert or retire content fields in `tasks`, `agent_runs` and audit metadata (HR3-14) |
| CR-ISO-01 | Isolation prerequisites: broker as the store-owning process (Level 2); dev sandbox and connectors at Level 3; egress enforcement for secret-bearing adapters (HR3-07) |
| CR-EPOCH-01 | External monotonic revocation epoch and policy high-water mark (HR2-10) |

**Dependency graph:**

```text
CR-OWN-01 (owner auth) ──► v0.2.5 CR-03 (decided_by = HUMAN_OWNER)
        │                         │
        └──► CR-API-01            │
                                  ▼
v0.2.5.2/.3 (delegation store/evaluator) ──► v0.2.5 CR-01 (requester + leaf binding)
                                                     │
v0.2.4 CR-04 (lifecycle history) ────────────────────┤
                                                     ▼
                                       CR-ESC-01 (ESC + owner-approved mapping)
                                                     │
                     ┌───────────────────────────────┼─────────────────────────┐
                     ▼                               ▼                         ▼
       v0.2.5 CR-05 (C′) ──► CR-CB-05       CR-CB-07 ──► CR-CB-02 ──► CR-CB-01  CR-CB-04 (agent context via broker)
                                                                               ▲
                                   CR-EGR-01 ──────────────────────────────────┤
                                   CR-ART-01 ──────────────────────────────────┤
                                   CR-LEG-01 ──────────────────────────────────┘
CR-EPOCH-01 ──► any durable clearance/grant/item store
CR-ISO-01  ──► CR-CB-08 (SecretRef / Credential Broker) ──► any secret-bearing adapter
CR-CB-03, CR-CB-06, N-3 fix ── independent leakage reductions (can go first)
```

**No circular dependency** was found.

- CR-ESC-01 needs CR-01 (principal and authority leaf) and an owner-issued
  clearance.
- Clearance issuance needs CR-OWN-01.
- CR-OWN-01 needs nothing in v0.2.6.
- The pure stages v0.2.6.1–.8 depend on none of these, and none of these
  depends on runtime v0.2.6 code. Only on the frozen, corrected contract.

**Must exist before any Context Broker runtime integration (v0.2.6.9):**

1. CR-OWN-01;
2. CR-API-01;
3. v0.2.5 CR-03;
4. v0.2.5.2/.3 and CR-01;
5. v0.2.4 CR-04;
6. CR-ESC-01;
7. v0.2.5 CR-05;
8. CR-EGR-01;
9. CR-EPOCH-01 (for durable stores);
10. CR-CB-07 (before CR-CB-02);
11. CR-CB-03, CR-CB-06 and the N-3 fix.

**May be built as isolated foundational components** (pure, disconnected,
after the contract is corrected and frozen):

- v0.2.6.1 label algebra, with corrected constraints (local-only nodes,
  floor rules);
- v0.2.6.2 clearance algebra;
- v0.2.6.3/.4 in-memory stores;
- v0.2.6.5 decision procedure with fakes, *including an in-memory ESC fake*;
- v0.2.6.6 assembler (with the structured TASK_INSTRUCTION rule);
- v0.2.6.7 SecretRef contract and scrubber;
- v0.2.6.8 hostile benchmark.

**May follow Context Broker enforcement:**

- CR-CB-01 labeling migration (legacy stays non-disclosable until then);
- CR-ART-01 extensions beyond sandbox files;
- CR-CB-08 plus the Credential Broker (secret-bearing adapters stay disabled
  until then);
- node identity and signing, then multi-node;
- tenant compartments;
- segment-level taint (HR2-24).

## 26. Freeze blockers

Design-contract problems that must be resolved in text before freeze.

**HR3 findings:** HR3-01, HR3-02, HR3-03, HR3-04, HR3-05, HR3-06, HR3-07,
HR3-08, HR3-09, HR3-10, HR3-11, HR3-12, HR3-13, HR3-15.

**HR2 findings (confirmed or partially confirmed):** HR2-08, HR2-09,
HR2-10, HR2-11, HR2-12, HR2-14, HR2-16, HR2-17, HR2-18, HR2-19, HR2-23,
HR2-26. HR2-01, HR2-02, HR2-03, HR2-04, HR2-05, HR2-06, HR2-07 and HR2-15
are carried through HR3-01 to HR3-09.

## 27. Implementation blockers

Runtime prerequisites before the corresponding enforcement can be enabled.
None of these blocks the pure stages v0.2.6.1–.8 once the contract is
corrected.

**HR3 findings:** HR3-01 (CR-ESC-01), HR3-02 (durable taint store), HR3-03
(CR-ART-01), HR3-04, HR3-05 (owner-approved mapping), HR3-06, HR3-07
(CR-ISO-01 for secret, connector and dev capabilities), HR3-08 (CR-OWN-01),
HR3-09 (CR-EGR-01), HR3-10, HR3-11, HR3-12 (CR-API-01), HR3-13, HR3-14
(CR-LEG-01).

**HR2 findings:** HR2-08, HR2-09, HR2-10 (CR-EPOCH-01), HR2-11, HR2-12,
HR2-13, HR2-14, HR2-18, HR2-19, HR2-22, HR2-26. Also v0.2.5 CR-01, CR-03
and CR-05.

## 28. Deployment blockers

These must prevent any production or networked deployment.

| Finding | Status |
|---|---|
| HR3-01, HR3-02, HR3-03, HR3-04, HR3-05 | Apply once the broker is integrated |
| HR3-07 | No code-level isolation |
| HR3-08 | No owner authentication; **already live** |
| HR3-09 | Unconditional cloud egress; **already live** |
| HR3-10 | — |
| HR3-12 | Cross-workspace IDOR; **already live** |
| HR3-13 | Arbitrary user creation; **already live** |
| HR3-14 | Unauthenticated task-output disclosure; **already live** |
| HR2-10 | Rollback |
| HR2-12 | Audit route and audit content; **already live** |
| HR2-16 | Only if more than one node is ever deployed |

The "already live" items are pre-existing v0.1.x defects. They are not
caused by v0.2.6, but v0.2.6's guarantees are void while they exist.

## 29. Residual risks

These remain even after all corrections:

- Content transmitted to a provider or exported cannot be recalled. Provider
  retention is contractual, not technical.
- Timing, size and resource side channels, and bounded control-plane
  observables.
- Prompt injection can steer use of authority and clearance within their
  bounds (HR2-20).
- Code-level compromise inside the TCB defeats the broker, below the isolation
  levels actually deployed.
- Over-tainting and owner declassification fatigue (HR2-24).
- No deletion guarantee outside broker-managed stores (backups, providers,
  exports, Git).
- An external system may echo exported content back at a lower label. This is
  bounded by `export_allowed`.
- Same-model-family review limitation (HR3-16).

## 30. Required design corrections (ordered)

1. **Define the ExecutionSecurityContext** (§11). Make `clearance_leaf_id`,
   `execution_id`, purpose, agent, objective and compartments ESC-only and
   immutable. Restate INV-CB-005 per execution (HR3-01; HR2-01).
2. **State the attacker classes and isolation level** v0.2.6 provides (policy
   isolation vs model-driven attackers). Name the OS account as the TCB
   boundary. Scope INV-CB-002/023/024/030/033. Extend protected targets
   (HR3-07; HR2-06).
3. **Disable owner-dependent operations** until an owner channel with the §14
   properties exists. Define the single canonical owner principal and the
   status of other `User`s (HR3-08, HR3-13; HR2-07).
4. **Remove model output from the control plane.** Derive agent, purpose,
   clearance and approval class from an owner-approved mapping. TASK_INSTRUCTION
   takes structured trusted fields only. Seed `H_exec` from the ESC (HR3-05,
   HR3-06; HR2-04, HR2-05).
5. **Durable, serialized taint** with retry inheritance. Define a delivery
   commit and the point of no return (HR3-02; HR2-02, HR2-11).
6. **Label tool reads by source policy** ⊔ `H_exec` (HR3-04).
7. **Persistent IFC.** Artifact label bindings, non-ingestible unbound
   Jarvis-origin artifacts, and external writes treated as EXPORT (HR3-03;
   HR2-03).
8. **Explicit destination authorization** for all egress; absence is DENY. The
   grant binds the exact provider. Router re-selection needs a new grant.
   Search queries are external flows (HR3-09, HR3-11; HR2-15; CD-06).
9. **Couple authority and clearance leaves.** Check the named authority leaf.
   Map `memory_scope`. Reclassify against v0.2 §8 (HR3-10; HR2-19; CD-01).
10. **Compartments from the canonical parent chain only** (HR3-12).
11. **Requested-floor limits and acceptable-taint ceiling** (HR2-08).
12. **Monotonic external epoch and policy high-water mark** (HR2-10).
13. **Audit-before-release; keyed digests; no content in audit** (objective
    text, reasons, titles, exception text) (HR2-12, HR3-14).
14. **Declassification canonicalization.** Integrity is unchanged. Disabled
    before the owner channel (HR2-14; CD-03).
15. **Single-node label constraints** (HR2-16; CD-04).
16. **Persistence order (CACHE/AUDIT) and rule scope** (HR2-18).
17. **Replace INSTRUCTION memory** with protected policy artifacts. Owner
    messages embedding items take min integrity (HR2-26).
18. **Honest deletion wording** (HR2-17).
19. **Control-plane observable bound** (HR2-09). Resource-bound principle and
    acyclicity (HR2-13, PROPOSED-INV-CB-060).
20. **Schema consistency**: grant `environment` and typed `sink_target`;
    request `uses`; DERIVE (HR3-15).
21. **Correct the §4.3 observations.** Add F-4, F-5, F-7, F-8, F-11, F-12,
    F-17 and the new CRs in §25 (HR2-23, HR3-14).
22. **Adopt the REQUIRED proposed invariants** (046, 047, 049–058, 060, 061–069)
    and the USEFUL ones as revised. Update TST-CB rows accordingly.

## 31. Final verification status

**DESIGN CORRECTIONS REQUIRED BEFORE FREEZE**

- Nine HIGH findings remain unresolved (HR3-01 to HR3-09):
  - HR3-02, 03, 05, 06, 07 and 08 confirm HR2 HIGHs;
  - HR3-01 supersedes HR2-01;
  - HR3-09 supersedes HR2-15 and upgrades it from MEDIUM;
  - HR3-04 is new.
- The core architecture is sound and does **not** require fundamental
  redesign: the label lattice, four-gate conjunction, store-held grants,
  owner-rooted check-not-clip clearance, filter-before-rank, and
  single-node-first.
- The defects are at the **edges** of the design:
  - who creates execution bindings;
  - who labels tool reads and persistent artifacts;
  - whether model output reaches the control plane;
  - what isolation is actually promised;
  - whether the owner and egress roots exist at all.
- Every one of them is correctable in contract text before freeze, with
  runtime prerequisites sequenced as in §25.

No v0.2.6 production implementation has been authorized or created.
