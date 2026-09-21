# Live Research, Evidence, and Cost Controls (v0.1.1 / v0.1.2)

This extends v0.1's Research Agent (previously always `insufficient_evidence=true`,
with model-generated sample findings only) with a controlled research-tool
abstraction, a structured evidence model, deterministic evidence-QA checks,
model-usage accounting, and budget guardrails. Nothing in v0.1's architecture
was rewritten — every piece here is an additive extension. See
[architecture.md](architecture.md) for the component map and
[security.md](security.md) for the permission/approval model this builds on.

## ResearchProvider

`app/tools/research_tools.py::ResearchProvider` is the Protocol seam
(`search()` / `fetch()` / `extract()`) between the Research Agent and whatever
does the actual retrieval. Selected via `RESEARCH_PROVIDER`:

| Value | Implementation | Behavior |
|---|---|---|
| `dev` (default) | `DevResearchProvider` | Exact v0.1 behavior: no provider call, `ResearchAgent` falls back to labeled `[DEVELOPMENT/SAMPLE DATA]` findings with `insufficient_evidence=true`. |
| `mock` | `MockResearchProvider` | Deterministic, offline, no network. Returns clearly-labeled placeholder search results so the full evidence pipeline (search → `EvidenceItem` → Strategy → QA → report) can be exercised in tests/demos. |
| `tavily` | `TavilyResearchProvider` | Live search/extract via the Tavily REST API (https://api.tavily.com). Requires `TAVILY_API_KEY`. See [Tavily provider](#tavily-provider) below. |
| `live` | *(not implemented)* | Reserved for any *other* vendor. Raises `ResearchUnavailableError` with an actionable message pointing at `tavily` or the other compatible options. |

`ResearchAgent` (`app/agents/research.py`) only calls the provider when
`provider.is_live` is true. When it gathers real results, it builds
`EvidenceItem`s **in Python, directly from the provider's returned
title/url/snippet** — never from model output — then attaches that evidence
list to `ResearchOutput` regardless of what the LLM echoed back, so URLs,
titles, and publishers can never be fabricated. The LLM is given the evidence
as grounding context (`GROUNDED_SYSTEM_PROMPT`) and told to label anything not
traceable to it as an assumption or unsupported claim, not a fact.

## Tavily provider

`TavilyResearchProvider` (`app/tools/research_tools.py`) talks to Tavily's
REST API directly via `httpx` (the same client already used by
`app/tools/url_safety.py`) rather than adding the `tavily-python` SDK as a
dependency. No Tavily-specific type ever leaves this module — `search()`
returns the same vendor-neutral `SearchResult` (`title`/`url`/`snippet`) every
other provider returns, so Strategy, QA, orchestration, and the `evidence`
table never know Tavily exists.

- **Bounded by default**: `search_depth="basic"` (configurable via
  `TAVILY_SEARCH_DEPTH`; `"advanced"` costs more per Tavily's own pricing and
  is never selected automatically), `max_results` clamped to a hard ceiling of
  10 regardless of what's requested, timeout from `RESEARCH_FETCH_TIMEOUT_SECONDS`.
- **No fabricated metadata**: Tavily's search response has no publisher or
  publication-date field, so `EvidenceItem.published_at` stays `None` and
  `publisher` is derived only from the URL's domain — never guessed.
- **`fetch()`** uses Tavily's `/extract` endpoint, after first rejecting the
  URL locally via `app/tools/url_safety.py::validate_url()` (defense in
  depth, even though Tavily does the actual retrieval server-side).
- **Errors** (401/429/5xx/timeout/malformed JSON) are all normalized to
  `ResearchUnavailableError`, which `ResearchAgent._gather_evidence()` already
  catches and treats as "no evidence" — exactly like `DevResearchProvider`
  today, so a Tavily outage degrades gracefully rather than crashing a task.
- **Usage**: every completed HTTP response (success or Tavily-side error)
  records one `ModelUsage(provider="tavily", model="search"|"extract")` event
  via the same `app/agents/usage.py` side channel LLM calls use — see
  [Usage accounting](#usage-accounting).
- **Key handling**: sent only in the POST body (never a URL query string),
  never included in any log field or exception message, and `tavily_api_key`
  is in `app/utils/logging.py::_REDACT_KEYS` as a redaction backstop.

Other vendors remain compatible with the same `ResearchProvider` Protocol if
a second live backend is ever wanted: **Brave Search API**, **Bing Web Search
API**, **SerpAPI**, **You.com API**.

## EvidenceItem

`app/schemas/evidence.py::EvidenceItem` — `id`, `claim`, `source_title`,
`source_url`, `publisher`, `published_at`, `retrieved_at`, `excerpt`,
`evidence_type` (`EvidenceKind`), `confidence`, `query_used`,
`verification_status` (`RETRIEVED` / `VERIFIED` / `UNVERIFIED` / `MOCK`).

`ResearchOutput` (`app/schemas/agents.py`) now carries `evidence:
list[EvidenceItem]` alongside the existing `findings`/`assumptions`/
`insufficient_evidence`, plus new `unsupported_claims` and `open_questions`
lists. `StrategyOutput` gained `evidence_used: list[str]` (EvidenceItem ids
backing the recommendation) and `unsupported_claims: list[str]`.

## Evidence flow

```
ResearchAgent._gather_evidence()  ->  EvidenceItem[] (from real provider results)
    -> attached to ResearchOutput.evidence
    -> AgentExecutor._build_input already forwards the full research task
       output (including `evidence`) into StrategyAgent's `research_results`
       input — no executor change was needed for this hop
    -> AgentExecutor._maybe_persist_evidence() stores it via EvidenceService
       into the `evidence` table (workspace/project/task/query/confidence/
       verification_status — see docs/security.md#workspace-isolation)
```

## QA evidence validation

`app/security/evidence_qa.py::evaluate_evidence()` is a **deterministic**
Python check layered in front of the QA agent's LLM verdict — the same
defense-in-depth pattern as `app/security/approvals.py::classify_risk` sitting
in front of the planner. It runs identically under `MockProvider` and any live
provider, so evidence discipline can't be skipped by a weak QA-model verdict,
and it's fully testable without a live API key.

Checks: FACT-labeled research findings with no attached evidence; evidence
items missing a source URL; excessively duplicated sources; evidence older
than `EVIDENCE_STALE_AFTER_DAYS`; quantitative strategy claims (market size,
growth rate, price, competitor count, revenue, CAC, conversion rate, market
share, user count) stated without an `evidence_used` citation;
`evidence_used` ids that don't exist in the upstream research evidence; a
recommendation given with no assumptions and no evidence.

`merge_into_verdict()` downgrades a `PASS` to `NEEDS_REVIEW` when any check
fires (never straight to `FAIL` — this is a review flag, not a hard block),
appends the specific gap(s) to `QAVerdict.feedback` so a retry knows exactly
what's missing, and is wired into both the inline worker→QA retry loop
(`app/orchestration/evaluator.py`) and the standalone `qa` task path
(`AgentExecutor._run_qa_task`). Retries stay bounded by `MAX_AGENT_RETRIES` as
before — this never creates a new retry path.

## Usage accounting

`ModelProvider.complete_structured()` still returns the parsed schema object
directly — every agent call site is unchanged. Usage rides a separate
`contextvars`-based side channel (`app/agents/usage.py::collect_usage()` /
`record_usage()`), safe across the `asyncio.gather`-based concurrent task
execution in `AgentExecutor` (each asyncio Task gets an isolated context).
`AnthropicProvider`/`OpenAIProvider` record real `input_tokens`/
`output_tokens`/`total_tokens` from the SDK response; `MockProvider` records
`api_calls`/`elapsed_ms` only — it never guesses token counts.

Persisted per call to the `usage_records` table (workspace/project/task/
agent_type/provider/model/tokens/api_calls/retry_number/elapsed_ms/
estimated_cost_usd) via `UsageService`. **USAGE and ESTIMATED_COST are always
kept separate**: cost is computed by `app/config/pricing.py::estimate_cost_usd()`
only when `MODEL_PRICING_JSON` has an entry for the exact model id used;
otherwise it stays `None` rather than guessed. `ExecutiveReport.usage`
(`MissionUsage`) rolls this up per agent type plus totals, elapsed time, and
`estimated_cost_usd` (with `pricing_configured` telling you whether that
number means anything).

## Budget guardrails

Checked in `run_objective`'s dispatch loop, once per iteration, **before**
starting a new batch of ready tasks — never mid-batch, since in-flight API
calls can't be safely cancelled. `app/orchestration/budget.py::check_budget()`
compares mission-to-date usage against `MAX_API_CALLS_PER_MISSION`,
`MAX_TOKENS_PER_MISSION`, and (only if pricing is configured)
`MAX_ESTIMATED_COST_PER_MISSION_USD` / `DAILY_COST_LIMIT_USD` (the latter
scoped to the whole workspace for the current UTC day). On a hit: the loop
stops, a `BUDGET_LIMIT_REACHED` audit event is recorded, already-completed
task output is untouched, and `build_report()` still runs — producing an
`ExecutiveReport` with `status="STOPPED_BUDGET_LIMIT"` and
`usage.budget_stopped_reason` set, never a silent continuation.

## Security

`app/tools/url_safety.py` is vendor-agnostic infrastructure any future
`LiveResearchProvider.fetch()` must route through:

- `validate_url()`: http/https only (no `file://`), rejects missing host,
  `localhost`, loopback/private/link-local/reserved/multicast IP literals —
  both as literals and via DNS resolution of a hostname.
- `bounded_get()`: re-validates every redirect hop, enforces
  `RESEARCH_MAX_REDIRECTS`, a content-type allowlist (`text/html`,
  `text/plain`, `application/json`, `application/xml`, `text/xml`), a byte cap
  (`RESEARCH_MAX_RESPONSE_BYTES`), and a timeout (`RESEARCH_FETCH_TIMEOUT_SECONDS`).

No shell execution, no unrestricted filesystem access, no general-purpose
browser tool — this is exactly the same set of promises v0.1 already made in
[security.md](security.md#what-v01-deliberately-does-not-do); the fetch path
just now has the guardrails a real vendor integration will need.

## Required environment variables

See `.env.example` for the full annotated list. New in v0.1.1/v0.1.2:
`RESEARCH_PROVIDER`, `RESEARCH_MAX_RESULTS`, `RESEARCH_FETCH_TIMEOUT_SECONDS`,
`RESEARCH_MAX_RESPONSE_BYTES`, `RESEARCH_MAX_REDIRECTS`,
`EVIDENCE_STALE_AFTER_DAYS`, `TAVILY_API_KEY` (only read when
`RESEARCH_PROVIDER=tavily`), `TAVILY_SEARCH_DEPTH`,
`MAX_API_CALLS_PER_MISSION`, `MAX_TOKENS_PER_MISSION`,
`MAX_ESTIMATED_COST_PER_MISSION_USD` (optional),
`DAILY_COST_LIMIT_USD` (optional), `MODEL_PRICING_JSON` (optional).

## Testing without spending API credit

`RESEARCH_PROVIDER=mock` (or passing `MockResearchProvider()` directly to
`ResearchAgent`) exercises the full evidence pipeline with zero network
access. Every test in `tests/test_research_provider.py`,
`tests/test_tavily_provider.py`, `tests/test_evidence.py`, `tests/test_usage.py`,
`tests/test_budget.py`, and `tests/test_url_safety.py` runs this way — Tavily
tests mock the `httpx` transport boundary, so no live API key or network
access is used anywhere in the suite. Run `pytest -q`.

The test suite also never depends on the developer's real `.env` selecting a
live provider: `tests/conftest.py::_safe_research_provider_env` (autouse,
applies to every test) forces `RESEARCH_PROVIDER=dev` regardless of what's
configured locally — the same defense `tests/test_api.py`'s `client` fixture
already applied to `MODEL_PROVIDER`. This matters because pydantic-settings
falls back to reading `.env` for any key not explicitly set in the process
environment, so `monkeypatch.delenv()` alone is not sufficient isolation —
tests must `monkeypatch.setenv()` an explicit safe value.

To spend exactly one real Tavily call and confirm connectivity, run
`python scripts/test_tavily_connection.py` manually (never invoked by the
test suite or any other script).
