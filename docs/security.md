# Security Model (v0.1)

## Secrets

- `OPENAI_API_KEY`, `DATABASE_URL`, etc. are read exclusively through
  `app/config/settings.py::Settings` (pydantic-settings, `.env`-backed). No
  module reads `os.environ` directly.
- `.env` is git-ignored (`.gitignore`); `.env.example` documents every
  variable with empty/placeholder values.
- `app/utils/logging.py` redacts any log field named `api_key`,
  `openai_api_key`, `authorization`, `password`, or `token` before rendering.
  `LOG_SENSITIVE_DATA` is reserved for future fine-grained control over
  payload logging; it defaults to `false`.

## Permission levels

`READ`, `WRITE`, `EXTERNAL_ACTION`, `FINANCIAL_ACTION`, `ADMIN`
(`app/database/models.py::PermissionLevel`).

| Agent | Granted permissions |
|---|---|
| Research, Strategy, QA | READ |
| Execution | READ, WRITE |
| Jarvis | READ, WRITE |

No agent is granted `EXTERNAL_ACTION`, `FINANCIAL_ACTION`, or `ADMIN` in
`build_default_registry` — see `test_permissions.py::test_no_agent_has_elevated_permissions_by_default`.
Every call to a task/memory/approval tool in `app/tools/*.py` is
permission-checked against the registry via
`app/security/permissions.py::check_permission` before it touches the
database; a missing permission raises `PermissionDeniedError`, which the
executor converts into a `FAILED` task with the reason recorded, never a
silent no-op.

## Approval gate

Two independent triggers push a task into `NEEDS_APPROVAL`, enforced by
`app/orchestration/executor.py::AgentExecutor._run_one` before any agent code
runs:

1. The planner explicitly set `TaskPlan.requires_approval = true`.
2. **Defense in depth**: `app/security/approvals.py::classify_risk` pattern-
   matches the task's title + description against keyword families for
   purchases/payments (`CRITICAL`), publishing/messaging/deletion
   (`HIGH`), and external contact (`MEDIUM`) — this catches consequential
   actions even if the planner's own model missed flagging them, and is
   applied both when the plan is persisted (`dispatcher.persist_plan`) and
   again at execution time.

When either trigger fires, `ApprovalService.request_approval` creates an
`Approval` row and moves the task `RUNNING -> NEEDS_APPROVAL` (never straight
from `READY`, so the transition is always valid per the state machine). The
task will not run until a human calls `POST /tasks/{id}/approve` or
`/reject` (or the CLI's equivalent), which is the *only* way an approval is
resolved — no code path resolves an approval automatically.

- **Approve**: `NEEDS_APPROVAL -> READY`; the dispatcher will pick it back up
  on the next loop iteration and it runs from scratch (no partial work had
  been done — the gate fires before the agent is ever invoked).
- **Reject**: `NEEDS_APPROVAL -> FAILED`, with the rejection reason recorded
  as the task's `error`.

Every request/approve/reject is written to `audit_events`
(`APPROVAL_REQUESTED`, `APPROVAL_GRANTED`, `APPROVAL_REJECTED`).

## Audit log

`app/security/audit.py::AuditEventType` enumerates every event type from the
build spec. `record_event` is called from the services layer
(`TaskService`, `ApprovalService`, `MemoryService`, `ProjectService`) — never
skipped, never given secrets as metadata. `GET /projects/{id}/audit` returns
the full trail for a project (its own events plus every task under it).

## Workspace isolation

Every `Project`, `Task`, `Memory`, `Approval`, `AuditEvent`, `Evidence`, and
`UsageRecord` row carries a `workspace_id` (directly or via its project).
Repository methods that list or search always filter by `workspace_id` — see
`MemoryRepository.search`, `ApprovalRepository.list_for_workspace`,
`AuditRepository.list_for_workspace`. `test_memory.py::test_memory_is_scoped_to_workspace`
verifies a memory written in one workspace never leaks into another's query
results.

## Research fetch safety (v0.1.1)

`app/tools/url_safety.py` is the vendor-agnostic guard any future live
research fetch must use: http/https only, no `file://`, rejects `localhost`/
loopback/private/link-local/reserved/multicast addresses (both as literals and
via DNS resolution), re-validates every redirect hop, and enforces a byte cap,
a content-type allowlist, and a timeout. See `docs/evidence.md#security` for
the full detail and `docs/evidence.md#budget-guardrails` for
`MAX_API_CALLS_PER_MISSION`/`MAX_TOKENS_PER_MISSION`/cost limits, which stop a
mission cleanly (preserving completed work, recording a `BUDGET_LIMIT_REACHED`
audit event, and still producing a partial executive report) rather than
letting it spend without bound.

## What v0.1 deliberately does not do

Per the build spec, none of the following are implemented, and nothing in the
codebase claims otherwise:

- No arbitrary shell execution.
- No unrestricted filesystem access.
- No unrestricted browser control — `url_safety.py` bounds any future fetch,
  it does not add general browsing.
- No financial transactions or autonomous purchases.
- No autonomous external messaging.
- No live web search vendor is wired up (`RESEARCH_PROVIDER=dev` by default,
  always raising `ResearchUnavailableError` rather than fabricating a result;
  `RESEARCH_PROVIDER=mock` is available for offline pipeline testing — see
  `docs/evidence.md`).

## Failure handling

Every task-level exception (agent error, invalid structured output, unknown
`agent_type`, permission denial) is caught in
`AgentExecutor._run_one`, recorded on the `AgentRun` row, and turned into a
`Task.FAILED` transition with the error message preserved — it never crashes
the surrounding `asyncio.gather` batch, and it is never silently swallowed.
