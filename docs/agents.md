# Agents (v0.1)

All five agents are registered in `app/agents/registry.py::build_default_registry`.
Every agent talks to a `ModelProvider` (`app/agents/providers.py`) — never to
the OpenAI SDK directly — so the whole orchestration layer is testable without
a live API key (see `MockProvider`).

| Agent | File | Capabilities | Permissions | Default model setting |
|---|---|---|---|---|
| Jarvis | `app/agents/jarvis.py` | planning, delegation, reporting | READ, WRITE | `JARVIS_MODEL` |
| Research | `app/agents/research.py` | research, analysis, evidence_collection | READ | `RESEARCH_MODEL` |
| Strategy | `app/agents/strategy.py` | strategy, comparison, recommendation | READ | `STRATEGY_MODEL` |
| Execution | `app/agents/execution.py` | approved_operations, drafting, internal_updates | READ, WRITE | `EXECUTION_MODEL` |
| QA | `app/agents/qa.py` | validation, quality_control, evaluation | READ | `QA_MODEL` |

No agent is granted `EXTERNAL_ACTION`, `FINANCIAL_ACTION`, or `ADMIN`. Those
require a human approval decision (see `docs/security.md`).

## Jarvis — Executive Orchestrator

Two structured responsibilities, both strictly schema-validated:

- `plan(objective) -> ExecutionPlan` — turns a free-text objective into a
  dependency-ordered list of `TaskPlan`s. `app/orchestration/planner.py`
  additionally rejects empty objectives, duplicate task keys, references to
  unknown task keys, and cyclic dependencies before any task is persisted.
- `generate_report(context) -> ExecutiveReport` — used ad hoc;
  `app/orchestration/executor.py::build_report` builds the report directly
  from **recorded task state**, not from a free-form model call, so Jarvis can
  never claim a task completed that the database doesn't show as `COMPLETED`.

Jarvis is never dispatched as a worker task (`JarvisAgent.run` raises
`NotImplementedError` by design) — it is the orchestrator, not a specialist.

## Research Agent

Rules enforced in the system prompt and in `ResearchOutput`'s shape:

- Every claim is labeled `FACT`, `ASSUMPTION`, or `UNKNOWN`.
- `insufficient_evidence: bool` must be set honestly.
- With the default `RESEARCH_PROVIDER=dev`, no live web research is connected
  (see `ResearchProvider` in `docs/evidence.md`) — the `MockProvider`'s
  research output is explicitly prefixed `[DEVELOPMENT/SAMPLE DATA — no live
  web research is connected...]` and always sets `insufficient_evidence=True`.
- With `RESEARCH_PROVIDER=mock` (or a live provider once one exists), the
  agent builds `EvidenceItem`s directly from the provider's real search
  results in Python — never from model output — and attaches them to
  `ResearchOutput.evidence`, so URLs/titles/publishers can never be
  fabricated. See `docs/evidence.md` for the full evidence flow.

## Strategy Agent

Takes the `research_results` gathered from its task's dependencies (never asks
the model to "remember" — dependency outputs are assembled in Python by
`AgentExecutor._build_input`, which now includes each research task's
`evidence` list automatically), and must return `assumptions` alongside any
`recommendation`. Its system prompt requires quantitative claims (market size,
growth rate, price, competitor count, revenue, CAC, conversion rate, market
share, user count) to cite an evidence id in `evidence_used` or be labeled an
assumption/unsupported claim rather than stated as fact. The QA agent — plus
the deterministic evidence-QA layer in `docs/evidence.md` — checks for a
recommendation given with no stated assumptions/evidence and flags it.

## Execution Agent

READ + WRITE only. Its system prompt and `ExecutionOutput` schema both forbid
claiming an external, financial, or irreversible action. Tasks that need such
an action are routed to `NEEDS_APPROVAL` by the executor **before** the
Execution Agent ever runs (see `docs/security.md#approval-gate`), so by the
time this agent executes, the action has already been approved or the task
never reached it.

## QA Agent

Returns `PASS | FAIL | NEEDS_REVIEW`, a `score`, `issues`, `unsupported_claims`,
and `feedback`. Used two ways:

1. **Inline, per-worker retry loop** (`app/orchestration/evaluator.py`) — every
   research/strategy/execution task is self-QA'd up to `MAX_AGENT_RETRIES`
   times before being marked `COMPLETED`.
2. **Standalone gate task** — the planner's default plan shape includes an
   explicit `qa` task that reviews the final strategy output once, feeding the
   executive report directly (matches the `Research → Strategy → QA → Jarvis`
   flow in the build spec).

Both paths also run `app/security/evidence_qa.py::evaluate_evidence()` — a
deterministic Python check (unsupported FACT claims, missing/duplicated/stale
evidence, uncited quantitative claims) merged into the LLM's verdict, so
evidence discipline holds even under a weak QA-model call. See
`docs/evidence.md#qa-evidence-validation`.

## Adding a new agent (future departments)

1. Add a Pydantic output schema to `app/schemas/agents.py` if the new agent's
   output doesn't fit an existing one.
2. Implement the agent class with the shape every agent already follows:
   `__init__(self, descriptor, provider=None)` and
   `async def run(self, *, title, description, input_data, context) -> BaseModel`.
3. Register it in `build_default_registry` with its capabilities and
   permissions — grant only `READ`/`WRITE` by default; elevated permissions
   require a product decision, not just a registry entry.
4. No change to `dispatcher.py`, `executor.py`, or the API is required — the
   planner can now assign tasks to the new `agent_type` by name.
