# Model DTO vs. Domain Model (v0.1.2.1)

## What happened

The first controlled live benchmark after the Discovery/Validation
integration checkpoint failed on its very first Research model call:

```
HTTP 400 — "The compiled grammar is too large, which would cause
performance issues. Simplify your tool schemas or reduce the number of
strict tools."
```

Tavily had already returned a successful search (HTTP 200) for the
DISCOVERY task; the failure was Anthropic rejecting the **structured-output
schema** `ResearchAgent` was asking it to fill in via
`messages.parse(..., output_format=ResearchOutput)`.

## Root cause (measured, not assumed)

`app/schemas/agents.py::ResearchOutput` had accumulated every Research
Intelligence structure introduced across v0.1.2/v0.1.2.1 — `EvidenceItem`
(with its new `source_role`/`requirement_category`/`relevance_label`/
`rejection_reason` enum fields), `EvidenceGap`, `ResearchRequirement`
(itself embedding a `list[SourceRole]` and an 11-value `RequirementCategory`
Literal), and `ResearchCandidate`. All three research modes
(`_run_general`/`_run_discovery`/`_run_validation`) called
`complete_structured(..., output_schema=ResearchOutput, ...)` — the SAME
schema for every mode.

Measured directly via `ResearchOutput.model_json_schema()`:

| Schema | Serialized size | `$defs` |
|---|---|---|
| `ResearchOutput` (before) | **9,652 chars** | 7 (`EvidenceGap`, `EvidenceItem`, `EvidenceKind`, `EvidenceVerificationStatus`, `ResearchCandidate`, `ResearchFinding`, `ResearchRequirement`) |
| `StrategyOutput` | 2,999 chars | 2 |
| `ExecutionPlan` (Jarvis planner) | 2,257 chars | 2 |
| `QAVerdict` | 505 chars | 0 |

`ResearchOutput` was 3–19x larger than every other model-facing schema in
the system, confirming the hypothesis: Anthropic's structured-output
grammar compiler was choking specifically on Research's schema, not on
Strategy/QA/the planner (see Phase 7 below).

The deeper problem: almost none of those nested structures actually needed
model reasoning. `_run_general`/`_run_discovery`/`_run_validation` already
**overwrote** `evidence`, `requirements`, `research_mode`, `candidates`,
and `evidence_gaps` deterministically after every model call, regardless
of what the model put there — the model was being asked to *compile a
grammar for* fields whose values were thrown away immediately.

## The fix: MODEL DTO ≠ DOMAIN MODEL

`app/schemas/agents.py::ResearchOutput` remains Jarvis's rich **internal/
domain** contract — nothing about it changed, and no downstream code
(`app/orchestration/evaluator.py`, `app/security/evidence_qa.py`,
`app/agents/strategy.py`, the executive report) needed to change either.

Anthropic (or any LLM) does not need to generate that whole contract. Three
new, deliberately small **model-facing DTOs** were introduced in
`app/schemas/research_dto.py` — one per research mode — carrying only the
fields that genuinely require model reasoning:

```python
class DiscoveryCandidateProposal(BaseModel):
    label: str
    description: str = ""

class DiscoveryModelOutput(BaseModel):
    candidates: list[DiscoveryCandidateProposal] = []
    findings: list[str] = []
    insufficient_evidence: bool = False
    open_questions: list[str] = []
    assumptions: list[str] = []
    summary: str = ""

class ValidationModelOutput(BaseModel):
    findings: list[str] = []
    insufficient_evidence: bool = False
    open_questions: list[str] = []
    assumptions: list[str] = []
    summary: str = ""

class GeneralResearchModelOutput(BaseModel):
    findings: list[str] = []
    unsupported_claims: list[str] = []   # kept: the grounded prompt genuinely
    insufficient_evidence: bool = False  # needs this model judgment; see
    open_questions: list[str] = []       # app/security/evidence_qa.py
    assumptions: list[str] = []
    summary: str = ""
```

Measured after the fix:

| DTO | Serialized size | `$defs` | vs. `ResearchOutput` |
|---|---|---|---|
| `DiscoveryModelOutput` | 1,373 chars | 1 (`DiscoveryCandidateProposal` only) | 7.0x smaller |
| `ValidationModelOutput` | 781 chars | 0 | 12.4x smaller |
| `GeneralResearchModelOutput` | 1,151 chars | 0 | 8.4x smaller |

None of the three contain `EvidenceItem`, `ResearchRequirement`,
`ResearchCandidate` (the rich one), `CandidateResearchStatus`,
`CoverageCell`, or `ComparisonReadiness` — enforced by an offline
regression guard (Phase 4, below).

The model is responsible for exactly what benefits from real reasoning —
identifying candidates (Discovery), synthesizing findings/open questions/
assumptions over what was gathered (all three modes) — and nothing Jarvis
already computes deterministically.

## Deterministic enrichment flow

```
TAVILY / RESEARCH PROVIDER
        |
        v
   REAL EVIDENCE  (app/agents/research.py::_gather_evidence)
        |
        +-------------------------------+
        |                               |
        v                               v
 COMPACT MODEL DTO                DETERMINISTIC ENRICHMENT
 (findings/assumptions/            (candidate ids, requirements,
  open_questions/summary/          source-role + relevance tagging,
  candidates[label,description]    coverage matrix, evidence_gaps —
  — genuinely needs the model)     app/research_intelligence/*)
        |                               |
        +---------------+---------------+
                         |
                         v
                  ResearchOutput
             (rich domain contract)
                         |
                         v
              Evidence Intelligence
           (coverage / completeness gate)
                         |
                         v
                      Strategy
```

Concretely, each mode:

1. Gathers real evidence via the `ResearchProvider` (Tavily/mock/dev) —
   unchanged, never touches the model.
2. Calls `complete_structured(..., output_schema=<CompactDTO>, ...)` — the
   model only ever sees/produces the small DTO.
3. Builds the rich `ResearchOutput` deterministically:
   `_build_general_output` / `_build_discovery_output` /
   `_build_validation_output` (all in `app/agents/research.py`) copy the
   DTO's own fields (`findings` wrapped into `ResearchFinding` objects,
   `assumptions`, `open_questions`, `insufficient_evidence`, `summary`
   with a deterministic fallback if the model left it empty) and leave
   `evidence`/`requirements`/`candidates`/`research_mode`/`evidence_gaps`
   for the caller to attach — exactly the same deterministic computation
   that already existed (`generate_requirement_set`, `tag_evidence_for_
   candidate`, `build_coverage_matrix`, `_finalize_candidates`,
   `_validation_gaps`), just no longer routed through the model schema.

Candidate ids, discovery-evidence links, requirements, evidence tagging,
and gaps are **recomputed deterministically exactly as before** — nothing
about the Discovery/Validation architecture changed, only what the model
is asked to fill in on the way there.

## Provider repair path (Phase 3) — unchanged, verified compatible

`AnthropicProvider.complete_structured`/`_retry_or_raise` are generic over
`output_schema: type[T]` — they were never Research-specific, so the
one-shot repair mechanism needed **zero code changes** to work with the
new compact DTOs. Verified in
`tests/test_provider_repair_compact_dto.py`: a first-attempt parse failure
gets exactly one repair attempt using the SAME compact DTO (never falling
back to the rich `ResearchOutput`), a second failure raises the typed
`ModelOutputParsingError`, and the repair-then-success path is invisible
to `app/orchestration/evaluator.py`'s mission-level `attempt` counter.

## Schema-size regression guard (Phase 4)

`tests/test_research_dto_schema_size.py` measures each compact DTO's
`model_json_schema()` directly (`json.dumps(...)` length) against a
project-owned budget (`RESEARCH_DTO_SIZE_BUDGET_CHARS = 2500` — generous
headroom over the largest actual DTO, ~1,400 chars) and asserts none of the
five domain-only definitions (`EvidenceItem`, `ResearchRequirement`,
`CandidateResearchStatus`, `CoverageCell`, `ComparisonReadiness`) appear in
any of them. This never depends on Anthropic's own undocumented grammar
limit — it's a conservative internal tripwire that fails loudly if a
future change re-embeds a rich domain structure into a model-facing
schema.

## Phase 7 — Strategy / QA / planner schema audit

Measured, not redesigned (all three are comfortably small — see the table
above): `StrategyOutput` (2,999 chars), `ExecutionPlan`/Jarvis planner
(2,257 chars), `QAVerdict` (505 chars). None embed a deterministic
Research Intelligence structure the way `ResearchOutput` did. No changes
were made to any of them.

## Stale next-action fix (Phase 8)

A related report-quality bug surfaced during this investigation: the
executive report's "Connect a live ResearchProvider to replace
development/sample research data" next action could fire even when a live
research provider had *already* succeeded — because evidence gathered
before a same-attempt Research-model failure was never attached to a
returned `ResearchOutput` (the exception propagated first), so nothing
reached `EvidenceService`. `app/orchestration/executor.py::build_report`
now also checks for a persisted **usage** record from a non-LLM provider
(`provider not in {"anthropic", "openai", "mock"}` — Tavily today), which
survives a mid-attempt failure regardless of whether evidence was
persisted (see `app/orchestration/evaluator.py`'s exception handling,
unchanged). Combined with a new typed failure classifier,
`app/agents/providers.py::classify_error_text` (recognizing each
`ModelProviderError` subtype's own fixed message prefix — never Anthropic's
raw vendor-specific text), a Research-model failure
(`PARSING`/`INVALID_REQUEST`) now always produces "Resolve the Research
model structured-output failure, then rerun the mission." instead of the
stale provider-connection suggestion.
