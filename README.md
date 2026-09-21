# Jarvis OS v0.1.1

A personal AI CEO / business operating system — the orchestration foundation
for one human operator to hand a high-level business objective to an AI
executive orchestrator (Jarvis), which plans it, delegates it to specialist
agents, executes approved work, evaluates the results, and reports back with
an evidence-labeled executive summary.

This is v0.1.1: a real, runnable, tested foundation for **5 agents** (Jarvis +
Research, Strategy, Execution, QA), not a 1000-agent workforce. The
architecture is built so hundreds of agents/departments can be added later
without rewriting the core (see [docs/architecture.md](docs/architecture.md#future-hierarchy)).

v0.1.1 adds a controlled research-tool abstraction, a structured evidence
model, deterministic evidence-QA checks, model-usage accounting, and mission
budget guardrails on top of the same v0.1 architecture — see
[docs/evidence.md](docs/evidence.md).

## What it actually does today

- Takes an objective (via API `/chat` or the CLI) and has Jarvis turn it into a
  structured, dependency-ordered `ExecutionPlan` — never free text.
- Persists every task to a real database with an explicit state machine
  (`PENDING → PLANNED → READY → RUNNING → COMPLETED/FAILED/...`).
- Runs independent tasks concurrently (bounded by `MAX_CONCURRENT_AGENTS`),
  and enforces dependencies in Python, not by asking the model to remember.
- Every research/strategy/execution task self-evaluates against a QA agent and
  retries with feedback up to `MAX_AGENT_RETRIES` times before being marked
  complete (never marked FAILED just for a QA disagreement — it's escalated
  instead, and reported).
- Gates any task that looks consequential (money, purchases, publishing,
  external messaging, deletion) behind a human approval step — no agent has
  `EXTERNAL_ACTION`, `FINANCIAL_ACTION`, or `ADMIN` permission by default.
- Logs every significant event to an audit trail.
- Produces a structured executive report that separates FACT / ASSUMPTION /
  RECOMMENDATION / UNKNOWN.
- Runs entirely offline against a deterministic `MockProvider` (no
  `OPENAI_API_KEY` required) for development and the full test suite, or
  against real OpenAI models when a key is configured.

### What it honestly does not do (yet)

- **No live web research vendor is selected.** `ResearchProvider` is a real
  interface (`search`/`fetch`/`extract`) with two implementations:
  `DevResearchProvider` (default, `RESEARCH_PROVIDER=dev`), which always
  raises `ResearchUnavailableError` rather than pretending to search the web,
  and `MockResearchProvider` (`RESEARCH_PROVIDER=mock`), deterministic and
  offline, for exercising the evidence pipeline without a live vendor. With
  the default, Research Agent output is explicitly labeled
  `[DEVELOPMENT/SAMPLE DATA]` end-to-end. See [docs/evidence.md](docs/evidence.md)
  for the evidence model, deterministic QA checks, usage accounting, and
  budget guardrails this build adds, and [Known Limitations](#known-limitations).
- No shell execution, filesystem access, browser control, financial
  transactions, or autonomous external messaging — by design (section 20/21 of
  the build spec). `app/tools/url_safety.py` bounds any future research fetch
  (SSRF/size/timeout guards); it is not a general browsing tool.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full component map,
sequence diagrams, and the future department/hierarchy design. Short version:

```
User → API (/chat) or CLI → Jarvis (planner) → Dispatcher (persists tasks,
enforces dependencies) → Executor (runs READY tasks concurrently, permission +
approval gated) → Worker agent → QA agent (bounded retry loop) → Database →
Executive Report
```

Agent details: [docs/agents.md](docs/agents.md).
Security/permissions/approval model: [docs/security.md](docs/security.md).
Full dev workflow: [docs/development.md](docs/development.md).

## Requirements

- Windows + PowerShell
- Python 3.13 recommended; this build was created and verified on **3.14**
  (no 3.13 was available in this environment — see
  [docs/development.md](docs/development.md#known-deviations-from-a-from-scratch-ideal)
  for why and what that changed in `requirements.txt`)
- (Optional) an `OPENAI_API_KEY` — everything works without one, using the
  offline `MockProvider`

## Quick start (Windows PowerShell)

```powershell
cd jarvis-os
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# Leave OPENAI_API_KEY blank to run fully offline, or set it for live model calls.

python scripts/init_db.py
# or, for versioned migrations:
alembic upgrade head

pytest -q

python scripts/seed_demo.py
```

## Running the API

```powershell
uvicorn app.main:app --reload
```

- `GET /health`
- `POST /workspaces`, `GET /workspaces/{id}`
- `POST /projects`, `GET /projects/{id}`
- `POST /projects/{id}/objectives`
- `GET /projects/{id}/tasks`, `GET /tasks/{id}`
- `POST /tasks/{id}/approve`, `POST /tasks/{id}/reject`
- `GET /projects/{id}/audit`
- `POST /chat` — send an objective, get back `run_id`, `status`, the full task
  list, and any `approvals_required`, all driven end-to-end by Jarvis

Example:

```powershell
curl -X POST http://127.0.0.1:8000/chat -H "Content-Type: application/json" -d '{\"user_email\": \"you@example.com\", \"objective\": \"Find three potential digital-product opportunities and recommend the strongest one.\"}'
```

## Running the CLI

```powershell
python -m app.main
```

Prompts for your email, then accepts objectives interactively, printing each
task as it runs (`Jarvis: Running research task — ...`) and the final
executive report. Type `exit` to quit.

## Testing

```powershell
pytest -q
```

116 tests covering the agent registry, individual agent schemas, the task
state machine, dependency enforcement, parallel task execution, the QA retry
loop (including the max-retries ceiling), permission enforcement, the
approval workflow, memory storage/retrieval/workspace-isolation, the FastAPI
endpoints, and (v0.1.1) the research-provider abstraction, evidence schema
and persistence, deterministic evidence-QA checks, model-usage accounting
(including per-retry tagging and concurrency isolation), budget guardrails
and partial-completion behavior, and URL-safety/SSRF rejection. All run
offline against a fresh temp-file SQLite database per test and the
deterministic `MockProvider`/`MockResearchProvider` — no live API key,
network access, or shared dev database is touched. See
[docs/development.md](docs/development.md#testing).

## Agent architecture

Jarvis (Executive Orchestrator) + Research, Strategy, Execution, QA. Full
detail, including each agent's rules and how to add a new one, in
[docs/agents.md](docs/agents.md).

## Security model

READ / WRITE / EXTERNAL_ACTION / FINANCIAL_ACTION / ADMIN permission levels;
no agent gets the last three by default. Full detail in
[docs/security.md](docs/security.md).

## Approval model

Tasks that match a consequential-action pattern (or are explicitly flagged by
the planner) are routed to `NEEDS_APPROVAL` before any agent runs them, and
stay there until a human calls `/tasks/{id}/approve` or `/reject`. Detail in
[docs/security.md#approval-gate](docs/security.md#approval-gate).

## Memory model

Working memory is an in-process, per-run object — never persisted as-is.
Long-term memory (`memories` table) is written only when something is
explicitly promoted (a decision, a lesson, a research summary), retrievable by
workspace/type/keyword/importance, and designed so a vector store can slot in
later without changing callers. Detail in
[docs/architecture.md#memory-model](docs/architecture.md#memory-model).

## Known limitations

- **No live web research vendor is selected yet.** This remains the biggest
  gap between "demo" and "real business assistant." With the default
  `RESEARCH_PROVIDER=dev`, Research Agent output is clearly labeled
  development/sample data and always reports `insufficient_evidence=true`.
  `RESEARCH_PROVIDER=mock` exercises the full evidence/QA/usage pipeline
  offline. Wiring in a real vendor (Tavily, Brave Search API, Bing Web
  Search, SerpAPI, You.com) is the natural next step — see
  [docs/evidence.md#choosing-a-live-vendor-not-yet-decided](docs/evidence.md#choosing-a-live-vendor-not-yet-decided) —
  and requires no change to the Research Agent's core logic, only a new
  `LiveResearchProvider` implementation.
- Only 5 agents are registered; the registry/hierarchy support many more (see
  [Future Architecture](#future-architecture)), but no department beyond the
  core 4 specialists is implemented.
- Token/cost usage tracking (v0.1.1) reports exactly what each provider
  returns — never guessed — but estimated cost is only computed when
  `MODEL_PRICING_JSON` is explicitly configured for the model in use; v0.1.1
  does not ship any built-in pricing table.
- Postgres is supported by SQLAlchemy/Alembic configuration but has not been
  run against a live Postgres instance in this environment (only SQLite was
  available); switching `DATABASE_URL` is the only change required.
- Built and verified on Python 3.14, not the requested 3.13 (unavailable in
  this environment) — see [docs/development.md](docs/development.md#known-deviations-from-a-from-scratch-ideal).

## Future architecture

```
Jarvis → Department Director → Team Manager → Specialist → Temporary Worker
```

The registry, task model (`parent_task_id`), and state machine already
support this without a rewrite. See
[docs/architecture.md#future-hierarchy](docs/architecture.md#future-hierarchy).
