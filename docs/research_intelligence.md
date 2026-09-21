# Research Intelligence Pipeline (v0.1.2)

v0.1.1 gave Jarvis live research, structured evidence, and evidence-quality
QA checks — but it had no idea *what evidence it actually needed* before
searching, no notion of what a source *can prove*, and no way to refuse
comparing candidates that weren't researched to a comparable standard. A
live benchmark on "find three digital-product opportunities and recommend
the strongest one" failed final QA for exactly that reason: the three
candidates leaned on YouTube/blog/Reddit generalities and didn't have
comparable coverage of demand, competition, pricing, customer pain, market
size, or feasibility.

v0.1.2 is additive — nothing in v0.1.1's orchestration, structured-output
repair, or QA-retry architecture was changed. It adds one new package,
`app/research_intelligence/`, and wires a handful of call-sites into the
existing Research/Strategy/QA agents and the executive report.

## Pipeline

```
Objective
  |
  v
Requirement Planning        app/research_intelligence/requirements.py
  |                          (deterministic per-candidate requirement set)
  v
Candidate Discovery          one research Task per candidate (existing
  |                           planner/dispatcher — not redesigned; see
  |                           app/research_intelligence/candidates.py)
  v
Source-Aware Search          app/agents/research.py (existing gather loop,
  |                           now candidate/requirement aware)
  v
Relevance Filter             app/research_intelligence/relevance.py
  |                          (excludes REJECT-scored evidence from the
  |                           model prompt and the coverage matrix — never
  |                           deletes it from result.evidence)
  v
Evidence Classification      app/research_intelligence/source_roles.py +
  |                           suitability.py (what KIND of source, and what
  |                           it's suitable to prove)
  v
Coverage Matrix               app/research_intelligence/coverage.py
  |
  v
Gap Search                    existing EvidenceGap/_build_queries retry
  |                            loop (per-candidate); cross-candidate
  |                            remediation queries surfaced as advice, see
  |                            app/research_intelligence/completeness.py
  v
Completeness Gate              app/research_intelligence/gate.py +
  |                             completeness.py
  v
Strategy                       app/agents/strategy.py (reads
  |                             comparison_readiness, cannot bypass it)
  v
QA                             app/security/evidence_qa.py
                                (independently recomputes the gate)
```

## What "candidate" means here

This architecture was **not** redesigned to add a database `Candidate`
entity. Two shapes are supported, and `app/research_intelligence/gate.py`
detects which one it's looking at automatically:

- **Discovery/Validation (v0.1.2.1 — preferred for "find N opportunities")**:
  candidates don't exist at mission start. A DISCOVERY research task
  identifies them (structured `ResearchCandidate`s), and ONE bounded
  VALIDATION research task — which depends on the DISCOVERY task through
  the *existing* Task dependency graph, no new orchestration mechanism —
  gathers candidate-specific evidence for all of them at once. Its single
  `research_results[i]` entry carries multiple candidates via its own
  `candidates` field, with every evidence item already tagged with the
  `candidate_id` it belongs to.
- **Legacy/GENERAL (v0.1.2 — one task per candidate)**: Jarvis's planner
  produces one research `Task` per candidate up front; each
  `research_results[i]` entry is treated as one candidate, identified by
  its task `title`. Still fully supported — nothing here was removed.

`app/research_intelligence/candidates.py::normalize_candidate_id` derives a
stable, deterministic id from a label (a candidate's own `label` in the
Discovery/Validation shape; a task's `title` in the legacy shape) — the
same normalization is used everywhere a candidate identity is needed, so
identity always agrees regardless of which shape is in play.

A single-candidate research task (not a comparison objective) is never
gated — `evaluate_comparison_readiness` requires at least 2 distinct
candidates before it applies at all.

### Discovery vs. Validation

Discovery evidence establishes that a candidate is *worth investigating* —
it never, by itself, means the candidate has been validated. A DISCOVERY
research task (`app/agents/research.py::_run_discovery`) never generates
per-candidate `ResearchRequirement`s and never runs the completeness gate;
it only proposes up to `RESEARCH_MAX_CANDIDATES_PER_MISSION` candidates
(model-proposed `label`/`description`; `id`/`discovery_evidence_ids`/
`status` are always recomputed deterministically, never trusted from the
model).

A VALIDATION research task (`_run_validation`) receives that candidate list
— merged in from its DISCOVERY dependency's output by
`AgentExecutor._build_input`, or via an explicit `research_mode` tag — and
for each candidate: generates the common core requirement set, runs one
bounded search per candidate on the first attempt (`_build_queries`), and
scores every gathered item against **every** candidate's own requirement
set, keeping whichever (candidate, requirement) pairing scores highest
overall (`_tag_validation_evidence`). This is what guarantees evidence for
Candidate A can never satisfy Candidate B's requirement — a search result
about A scores far higher against A's own requirements than against B's,
and is explicitly penalized as `WRONG_CANDIDATE` if it's clearly about a
different candidate (`app/research_intelligence/relevance.py`).

Non-SUFFICIENT coverage cells become candidate-scoped `EvidenceGap`s for the
*next retry of the same VALIDATION task* — reusing the existing bounded
`evidence_gaps`/`_build_queries` retry loop
(`app/orchestration/evaluator.py`) unchanged. No new workflow engine, no
dynamic task spawning.

### research_mode

`app/schemas/evidence.py::ResearchMode` (`DISCOVERY` / `VALIDATION` /
`GENERAL`) is explicit, structured intent — set by the planner via
`TaskPlan.research_mode` (optional; `None` means ordinary single-topic
research) and carried into `Task.input_data` by
`app/orchestration/dispatcher.py::persist_plan`.
`app/agents/research.py::_resolve_research_mode` prefers that explicit tag;
its only fallback is a **structural** signal (a `candidates` list already
present in `input_data`, merged in from a DISCOVERY dependency implies
validation intent) — never free-text keyword parsing. Everything else
defaults to `GENERAL`, the unchanged v0.1.1/v0.1.2 behavior, so ordinary
research is unaffected either way.

## Requirement Planner

`app/research_intelligence/requirements.py::generate_requirement_set` builds
a `ResearchRequirement` list for one candidate. `CORE_COMPARISON_CATEGORIES`
(demand, competition, pricing, customer_pain, market_size, feasibility) is
the common minimum core for a comparison objective — every candidate gets
the *same* categories, so coverage stays comparable. The full category
taxonomy (`RequirementCategory` in `app/schemas/evidence.py`) also covers
growth, willingness_to_pay, unit_economics, and customer_validation for
non-comparison research. Nothing here is specific to digital products — the
same machinery works for SaaS, ecommerce, services, marketplaces, or any
future business type Jarvis researches.

## Source roles vs. relevance vs. suitability — three different concepts

- **Source role** (`source_roles.py`) describes *provenance/function*:
  PRIMARY, AUTHORITATIVE, COMMERCIAL_RESEARCH, MARKETPLACE, COMMUNITY,
  DISCOVERY, UNKNOWN. **Discovery is not validation** — a YouTube video or
  blog post may generate a hypothesis, but it never by itself establishes a
  high-confidence commercial/financial conclusion (see `suitability.py`'s
  policy table). **Community evidence is not automatically weak** — Reddit
  and forum discussion are the *preferred* source for customer pain.
  **Primary evidence is not automatically unbiased** — a company's own
  pricing page is PRIMARY, but that only means "first-party," not "neutral."
- **Source suitability** (`suitability.py::evaluate_source_suitability`) is
  a small, explicit, fully-tested table: for THIS requirement category, how
  much weight can THIS source role carry (STRONG / ACCEPTABLE / WEAK /
  UNSUITABLE)? Never a machine-learning ranker.
- **Relevance** (`relevance.py::score_relevance`) is a retrieval-relevance
  *heuristic* (query/candidate/requirement keyword overlap, genericness,
  source-role bonus) in `[0.0, 1.0]`, bucketed into HIGH / MEDIUM / LOW /
  REJECT. It answers "is this evidence about the right thing at all?" —
  independent of whether the source role is a good one for the claim.
  REJECT-scored evidence is excluded from the model prompt and the coverage
  matrix, but is **never deleted** — it stays on `EvidenceItem.evidence`
  with a `rejection_reason`, so nothing gathered is silently discarded.

## Coverage Matrix and Completeness Gate

`coverage.py::build_coverage_matrix` produces one `CoverageCell` per
(candidate, requirement): how many STRONG/ACCEPTABLE/WEAK items, how many
*independent canonical domains* (three pages from the same domain never
count as three independent sources), and a `MISSING` / `WEAK` / `PARTIAL` /
`SUFFICIENT` status. `completeness.py::evaluate_completeness` rolls that up
per candidate (`CandidateResearchStatus.ready_for_comparison`) and overall
(`ComparisonReadiness.ready`) — a candidate is only ready once its weighted
coverage crosses `RESEARCH_MIN_COMPARISON_COVERAGE` **and** none of the
three critical categories (demand/competition/pricing) is entirely missing.

`gate.py::evaluate_comparison_readiness` is the single entry point both
`app/agents/strategy.py` (to gate its own output) and
`app/security/evidence_qa.py` (to independently verify Strategy respected
that gate) call — neither module depends on the other.

## Strategy precondition

`StrategyAgent.run` always computes `comparison_readiness` before calling
the model, passes it into the prompt so the model is *informed*, and then
**deterministically overwrites** `comparison_ready` /
`candidate_statuses` / `missing_requirements` / `remediation_queries` after
the call — a model cannot bypass the gate by writing a confident
recommendation.

**Authoritative source, not the compacted prompt (v0.1.2.1 — Issue 2):**
`comparison_readiness` is computed exactly ONCE per attempt sequence by
`app/orchestration/evaluator.py::run_worker_with_qa`, from the FULL,
pre-compaction `research_results` it was originally called with (each
dependency research task's own persisted `Task.output_data`) — never from
the bounded view `app/agents/strategy_context.py::compact_research_results`
builds for the model prompt. That precomputed value is injected into
`run_input["comparison_readiness"]` on every retry attempt, bypassing
compaction entirely:

```
AUTHORITATIVE research_results (full)
    |
    +--> evaluate_comparison_readiness()  ->  comparison_readiness  --> run_input (every attempt)
    |
    +--> compact_research_results()       ->  bounded research_results  --> Strategy model prompt
```

`StrategyAgent.run` reads `input_data["comparison_readiness"]` when present
(the authoritative, precomputed value) and only falls back to computing it
itself from `research_results` when absent (direct calls that bypass the
evaluator, e.g. tests exercising `StrategyAgent` in isolation — there
`research_results` IS the full set, so self-computing is still correct).
This is deliberately a SEPARATE concept from evidence-id visibility:
`valid_evidence_ids`/`evidence_used` validation is untouched and still
scoped to exactly what THIS attempt's compacted prompt showed — the gate
may see (and use) evidence Strategy was never shown, but Strategy may still
only ever *cite* evidence it actually saw. See
`tests/test_gate_authoritative_evidence.py`.

If not ready, `recommendation` is rewritten (unless the model already wrote
it correctly) to:

```
DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE
MOST PROMISING VALIDATION CANDIDATE: <highest-coverage candidate> (provisional — not yet comparably validated)
MISSING INFORMATION: <bounded list>
NEXT VALIDATION: Run targeted follow-up research on the missing requirements above before ranking candidates.
```

## QA integration

`app/security/evidence_qa.py::_check_comparison_readiness` prefers the same
precomputed, authoritative `comparison_readiness` Strategy itself used
(falling back to recomputing from `research_results` only for direct calls
that bypass the evaluator) and compares it to what the output claims —
catching both "ranked despite comparison_ready=false" and a
`comparison_ready` value that doesn't match. This complements (never
replaces) the model QA verdict, the same defense-in-depth pattern as the
rest of `evidence_qa.py`.

## Executive report

When a comparison wasn't ready (or QA didn't pass), the report's
`recommendation` already carries the `DECISION STATUS:` framing (Strategy
wrote it); `ExecutiveReport.to_text()` never prefixes an already-framed
`DECISION STATUS:` recommendation with a generic `RECOMMENDATION:` label.
`ExecutiveReport` also gains `comparison_ready`, `evidence_coverage` (one
line per candidate), `critical_gaps`, and `next_research` (bounded
remediation queries) — all deterministically populated from the final
Strategy output in `app/orchestration/executor.py::build_report`.

## Settings (all in `app/config/settings.py`)

| Setting | Default | Purpose |
|---|---|---|
| `RESEARCH_MAX_REQUIREMENTS_PER_CANDIDATE` | 6 | Bounds the requirement set generated per candidate |
| `RESEARCH_MAX_GAP_QUERIES_PER_ATTEMPT` | 3 | Bounded follow-up searches per retry attempt (was the hardcoded `MAX_FOLLOWUP_QUERIES`) |
| `RESEARCH_MIN_RELEVANCE` | 0.30 | Below this, evidence is excluded from model-facing context/coverage (REJECT threshold) |
| `RESEARCH_MIN_COMPARISON_COVERAGE` | 0.70 | Weighted coverage fraction a candidate needs to be `ready_for_comparison` |
| `RESEARCH_MIN_INDEPENDENT_SOURCES` | 2 | Distinct canonical domains required for an independence-requiring requirement to reach SUFFICIENT |
| `RESEARCH_MAX_EVIDENCE_PER_REQUIREMENT` | 4 | Caps how many items count toward one requirement's coverage cell (domain-diversity preferred when trimming) |
| `RESEARCH_MAX_CANDIDATES_PER_MISSION` | 3 | Hard bound on candidates a DISCOVERY task may propose / a VALIDATION task may accept (v0.1.2.1) |
| `RESEARCH_MAX_VALIDATION_EVIDENCE_ITEMS` | 60 | Non-lossy evidence cap for a VALIDATION task's own persisted output — the authoritative gate source (v0.1.2.1) |
| `RESEARCH_PROMPT_MAX_EVIDENCE_PER_REQUIREMENT` | 2 | Caps how many items one (candidate, requirement) pair contributes to the MODEL PROMPT specifically (v0.1.2.2) |
| `RESEARCH_PROMPT_MAX_TOTAL_EVIDENCE_CHARS` | 4000 | Aggregate excerpt-chars budget for the model prompt — never persistence/coverage/completeness (v0.1.2.2) |
| `RESEARCH_PROMPT_MAX_QA_FEEDBACK_CHARS` | 400 | Bounds the `qa_feedback` string shown to Research on a retry — previously unbounded (v0.1.2.2) |

`RESEARCH_MAX_EVIDENCE_ITEMS`/`RESEARCH_MAX_EVIDENCE_EXCERPT_CHARS` already
provided the item-count/per-item-excerpt equivalents, so v0.1.2.2 reuses
them rather than duplicating settings.

The objective is **better evidence per token**, not more searches — none of
these defaults increase the mission's `MAX_API_CALLS_PER_MISSION` /
`MAX_TOKENS_PER_MISSION` budget.

## v0.1.2.2 — Retrieval precision + token efficiency

A live benchmark surfaced three defects after the Discovery/Validation and
grammar-size checkpoints:

**Defect 1 — search query semantic contamination.** Jarvis's own
orchestration vocabulary ("candidate", "opportunity", "validation task", …)
was leaking into external search queries — a DISCOVERY task titled
"Discover candidate digital-product opportunities" sent that string
*verbatim* to Tavily, which returned political-candidate and HR-recruitment
content instead of digital-product research. Fixed by
`app/research_intelligence/query_builder.py::build_external_research_query`
— a deterministic (never LLM-based) normalizer that strips a fixed
orchestration stopword/phrase list, flattens punctuation (keeping
parenthetical content, since it's usually meaningful business detail — e.g.
"(Courses/Templates)"), and applies small per-category search-intent
templates (pricing/competition/demand/…). Every query-generating call site
(`_external_query_from_title`, the VALIDATION candidate-label branch of
`_build_queries`, and `_validation_gaps`) now routes through it.

**Defect 2 — Research input token explosion.** The Research model prompt
was assembling `input_data` *wholesale* (duplicating `candidates`, which
was also passed explicitly, and embedding an unbounded `qa_feedback`
string) plus up to 15 full `EvidenceItem` dicts. Fixed by the **Research
Context Compactor** (`app/agents/research.py::_select_prompt_evidence` +
`_build_prompt_context`): evidence selection now also enforces a
per-requirement cap and an aggregate excerpt-chars budget, prioritizes
domain diversity (a second pass only allows a repeated domain once every
requirement slot has tried a fresh one first), and on a gap retry
emphasizes evidence for requirements that are NOT YET SUFFICIENT
(requirement-local locality) over the full historical corpus. `input_data`
is never embedded wholesale anymore — only a bounded `qa_feedback` string
and a compact `unresolved_gaps` summary. Measured on an offline benchmark
matching the live mission's three candidates
(`tests/test_research_prompt_benchmark.py`): **~56% smaller** prompt for
the same gathered evidence, with retry prompt size staying flat across 5
consecutive retries (no "previous output" accumulation).

**Defect 3 — QA vs. completeness-gate conflict.** The QA agent's own model
judgment penalized Strategy for correctly refusing to declare a winner
under `comparison_ready=false`, and even told it to override the gate.
Fixed in two layers: (1) `app/agents/qa.py`'s system prompt now explicitly
teaches the READINESS CONTRACT — PASS means "correctly handled insufficient
evidence," never "business opportunity validated," and QA must never
instruct Strategy to override the gate; (2)
`app/security/evidence_qa.py`'s deterministic layer gained a
`verdict_override` — when Strategy correctly refuses (has the
`INSUFFICIENT COMPARABLE EVIDENCE` marker, names what's missing, and makes
no unqualified winner claim), the merged verdict is **forced to PASS**
regardless of what the model QA argued; conversely, an unqualified winner
claim ("strongest", "pursue", …) without a provisional qualifier
("provisional", "preliminary", "not yet validated") despite
`comparison_ready=false` forces at least `NEEDS_REVIEW` even if the model
QA said PASS.

**Report fix (Phase 13).** A token/API-call safety-limit stop is a
*feature*, not an obstacle — `build_report` no longer suggests raising
`MAX_TOKENS_PER_MISSION`/`MAX_API_CALLS_PER_MISSION`; it recommends
narrowing the research scope or continuing in a new bounded mission
instead. Cost-based limits (estimated/daily cost) keep the previous
"raise the limit" framing, since that's a different, legitimately
adjustable axis.

## v0.1.2.3 — Evidence provenance + Research token root-cause

A second live benchmark, after v0.1.2.2, surfaced two remaining defects and
one report-quality anomaly.

**Defect 1 — validation evidence contamination.** VALIDATION's accumulated
evidence contained unrelated HR/recruiting material (candidate screening,
ATS tools, …) despite the v0.1.2.2 query-builder fix. Root cause: (a)
generic business concepts ("workflow automation software") genuinely
overlap with unrelated verticals in real search results — no query fix
eliminates this; the defense has to be at the evidence layer; (b) a REAL
bug in `app/research_intelligence/gate.py::_evaluate_embedded_candidates`'s
"defensive fallback" — evidence that arrived without a `candidate_id` tag
(e.g. a DISCOVERY task's own broad-search evidence, if a research_results
list ever included it) got RE-TAGGED against the VALIDATION candidates and
could enter the coverage matrix, even though discovery evidence only
establishes a candidate is worth investigating, never that it's validated.

Fixed with new **evidence provenance** metadata on `EvidenceItem`
(`research_task_id`, `research_mode`, `attempt_number` — `query_used`
already served as "originating_query"; all optional, all deterministic,
no DB migration — same pattern as `candidate_id`/`source_role`/etc., never
persisted to the `Evidence` ORM table's fixed columns, carried through
`Task.output_data` JSON instead). `app/agents/research.py` stamps every
item with its `research_mode` right after gathering it;
`AgentExecutor._build_input` adds `task_id`; `evaluator.py`'s retry loop
adds `attempt_number`. `gate.py` now refuses to count ANY evidence whose
`research_mode` is explicitly set to something other than `"VALIDATION"` —
closing the DISCOVERY/GENERAL leak at its root, not just filtering by
relevance.

**Defect 2 — Research token usage remains high.** The v0.1.2.2 offline
benchmark measured ~56% reduction with short synthetic snippets, but real
Tavily "basic" search snippets run far longer. Root cause, found by
tracing the actual request construction: `app/agents/research.py::
_gather_evidence` sets `claim` and `excerpt` to the exact SAME raw
snippet — but only `excerpt` was ever bounded for the model prompt
(`_prompt_evidence`); `claim` was sent in full, unbounded, for every
item. Combined with dumping the FULL `EvidenceItem` (~23 fields including
provenance/relevance/tagging metadata the model never needs) per item,
this multiplied prompt size well beyond what the short-snippet benchmark
showed. Fixed by bounding `claim` (`_PROMPT_CLAIM_MAX_CHARS = 200`, same
mechanism as `excerpt`) and reducing the per-item prompt dict to 9 fields
the model actually needs (`_PROMPT_EVIDENCE_FIELDS`). Re-measured with
1,800-char realistic snippets: **50,551 → 10,641 chars per attempt
(78.9% reduction)** — see `tests/test_research_prompt_diagnostics.py` and
`app/research_intelligence/prompt_diagnostics.py::diagnose_prompt_size`,
a new offline, per-component (system prompt / question / candidates /
evidence / qa_feedback / unresolved_gaps) diagnostic that never makes a
live call and never touches secrets.

**Structured-output schema** was re-measured and confirmed NOT to be a
factor here: `DiscoveryModelOutput`/`ValidationModelOutput`/
`GeneralResearchModelOutput` are all still far under 2,500 chars (the
v0.1.2.1 fix). No schema changes were made in this patch.

**Source quality/coverage.** The report displayed the OLD, coarse
`source_quality` field (only recognizes gov/edu/community — everything
else, including legitimate vendor/marketplace domains, showed
`UNKNOWN`), never the richer v0.1.2 `source_role` field computed
internally. Fixed by adding a "Source role" line to the report's evidence
section. Separately, `source_roles.py::classify_source_role`'s PRIMARY
heuristic used to require the domain to match the CANDIDATE's own label —
missing the common case of a NAMED COMPETITOR's own official page, which
is just as legitimately PRIMARY for that competitor's own claims. Now any
unrecognized domain (not a known marketplace/research/community/discovery
site) with an official-looking path segment (pricing/plans/docs/product/
features/investors/about) is PRIMARY — for THAT vendor's own claims only;
`suitability.py`'s policy table already correctly caps PRIMARY at
ACCEPTABLE (never STRONG) for `market_size`/`growth`, so a vendor's own
page still can't single-handedly validate total market size.

**Final QA state anomaly.** Traced, not assumed: the STANDALONE final
"qa" task (reviewing an already-completed Strategy task) never received
`research_results`/`comparison_readiness` in its `input_data` at all
(`AgentExecutor._build_input`'s qa branch only sets `output`/
`success_criteria`) — making the v0.1.2.2 QA readiness-contract override
silently INERT for exactly that call path, leaving only the generic
evidence-quality checks to decide the verdict. This was a genuine bug, now
fixed: `_check_comparison_readiness` falls back to trusting Strategy's own
authoritative `output["comparison_ready"]` (never model-generated —
`app/agents/strategy.py` sets it unconditionally) when neither
`comparison_readiness` nor `research_results` is present in `input_data`.
A SEPARATE, genuinely-intentional downgrade path (evidence_qa.py's generic
"no assumptions and no cited evidence" check, unrelated to comparison
readiness) is documented and regression-tested as intended defense-in-depth
behavior, not touched.

**Report cleanup.** OPEN QUESTIONS no longer embeds an entire raw,
potentially multi-hundred-char QA feedback essay — bounded to 300 chars.
REJECT-relevance evidence (off-topic/too-generic) is excluded from
`evidence_details`/`key_findings` and summarized as a count
(`ExecutiveReport.rejected_evidence_count`) instead of being mixed into
business findings — never deleted, still in the persisted Evidence table
and this count.

## Known limitations

- Cross-candidate remediation queries computed AFTER a VALIDATION task has
  already completed (`ComparisonReadiness.remediation_queries`, surfaced via
  `StrategyOutput`/`ExecutiveReport`) remain advisory — they are not turned
  into new Tasks, because re-opening an already-COMPLETED dependency would
  require a new workflow engine (explicitly out of scope). Coverage gaps
  discovered *during* a VALIDATION task's own retries ARE executable,
  though — see `app/agents/research.py::_validation_gaps`, which reuses the
  existing bounded `evidence_gaps`/`_build_queries` retry loop.
- A VALIDATION task performs one bounded search per candidate on its first
  attempt (Approach B: one task validates every discovered candidate,
  chosen over dynamically spawning one task per candidate, to avoid
  uncontrolled task expansion). This is less parallel than N independent
  tasks would be, but stays within the existing fixed-plan architecture and
  every existing hard bound (API calls, tokens, retries, diminishing
  returns).
- `research_max_validation_evidence_items` (60) is a hard cap, not
  unbounded — a mission validating exactly
  `research_max_candidates_per_mission` (3) candidates against
  `CORE_COMPARISON_CATEGORIES` (6) with
  `research_max_evidence_per_requirement` (4) each could in principle want
  up to 72 items; 60 is a deliberately reasonable, bounded compromise, not
  a precise product of the other three settings.
- `PRIMARY` source-role classification is a conservative heuristic (domain
  name contains the candidate's own significant tokens + an official-looking
  path like `/pricing`, `/docs`, `/product`). It will under-classify a
  legitimate first-party source whose domain doesn't resemble the
  candidate's name (e.g. a company operating under a different brand).
- `app/research_intelligence/dossier.py::build_research_dossier` is
  implemented and tested but not yet wired into a task output — the report
  changes (Phase 13) already surface the same coverage/gap information more
  concisely; the dossier is available for a future, richer research-summary
  surface.

## v0.1.2.5 — Requirement-driven retrieval

A live v0.1.2.4 benchmark showed all three candidates stuck at 5% coverage
after three VALIDATION attempts, with 32 evidence items rejected/off-topic.
Root-caused to TWO separate defects, both fixed this checkpoint (neither
required touching the Admission Gate's own thresholds — Phase 12 keeps
those exactly as v0.1.2.4 set them):

1. **Retrieval precision, upstream of the gate.** Real Tavily results
   surfaced HR/ATS and other off-topic noise that survived relevance
   scoring well enough to reach the Admission Gate before being rejected
   there — correctly rejected, but only after paying for tagging,
   relevance scoring, and (worse) PAGE_EXTRACT calls on it.
2. **Gap-retry cross-candidate collision (the dominant cause of the 5%
   plateau).** `app/orchestration/evaluator.py`'s retry loop accumulated
   gaps keyed by `gap_type` ALONE — with three candidates all needing e.g.
   `pricing` evidence, each candidate's own gap (already correctly
   candidate-scoped by `app/agents/research.py::_validation_gaps`) was
   silently overwritten by the next candidate sharing that gap_type, and
   the WORKER's own rich per-cell gaps were being discarded entirely in
   favor of `evidence_qa.py`'s generic, candidate-agnostic gap detector.
   At most one candidate's cell per category could ever receive a
   targeted retry query, no matter how many candidates needed one. Fixed
   by keying `_merge_gaps` on `(candidate_id, gap_type)` and merging the
   worker's own `output.evidence_gaps` before it gets overwritten — see
   `tests/test_gap_retry_cell_targeting.py`.

### Updated pipeline

```
REQUIREMENT                  app/research_intelligence/requirements.py
  |                          (per-candidate requirement set; unchanged)
  v
QUERY PLAN                   app/research_intelligence/query_builder.py
  |                          ::build_query_plan / ResearchQueryPlan —
  |                          CANDIDATE CONCEPT + REQUIREMENT-SPECIFIC
  |                          INTENT only, never orchestration wording.
  |                          build_candidate_concepts() gives a bounded,
  |                          deterministic concept set per candidate.
  v
SEARCH                        app/tools/research_tools.py (unchanged
  |                           ResearchProvider.search())
  v
PRE-SCREEN                    app/research_intelligence/prescreen.py —
  |                           cheap, conservative, cost-saving filter on
  |                           the raw SearchResult, BEFORE it becomes an
  |                           EvidenceItem. Negative retrieval guards
  |                           (HR/ATS/political noise markers) apply only
  |                           when the candidate's OWN concepts don't
  |                           already relate to that domain — never a
  |                           global ban.
  v
EXTRACT (optional)             app/agents/research.py::_maybe_upgrade_with_fetch
  |                             — only ever sees items that survived
  |                             pre-screen; PAGE_EXTRACT is never spent on
  |                             pre-screen-rejected noise.
  v
ADMISSION                      app/research_intelligence/admission.py —
  |                             the ONLY authority on ACCEPT/REJECT for
  |                             authoritative validation evidence.
  v
COVERAGE                       app/research_intelligence/coverage.py
  |                             (admitted_only() evidence exclusively)
  v
COMPLETENESS                   app/research_intelligence/completeness.py
```

### Explicit semantic distinctions

- **Search relevance ≠ evidence admission.** `relevance.py`'s
  score/label answers "how well does this match the requirement's
  keywords." `admission.py` answers "should this be counted as
  authoritative validation evidence" — a MEDIUM-relevance, keyword-matched
  item can still fail admission on candidate-overlap or source suitability.
- **Pre-screen ≠ Admission Gate.** Pre-screen (`prescreen.py`) is a cheap,
  conservative, cost-saving filter on raw `SearchResult`s, applied before
  an `EvidenceItem` even exists. It never decides ACCEPT/REJECT for
  authoritative evidence — only the Admission Gate does that, and only
  after tagging/relevance/suitability have run.
- **Rejected evidence ≠ deleted evidence.** Every admission-rejected
  `EvidenceItem` keeps its `admission_status`/`admission_rejection_reasons`
  and survives in `result.evidence` for audit. Pre-screen-rejected raw
  `SearchResult`s are counted in yield diagnostics but never even become
  an `EvidenceItem` — there was never "evidence" to delete.
- **Coverage ≠ amount of retrieved content.** Only `admitted_only()`
  evidence ever counts toward a `CoverageCell`'s status — a flood of
  pre-screen-rejected or admission-rejected material can never manufacture
  SUFFICIENT coverage (see `tests/test_coverage_semantics_regression.py`).
- **PASS ≠ business opportunity validated.** A QA `PASS` (model or
  deterministic-merged) means the output correctly reflects the evidence
  it has — including, when `comparison_ready=false`, correctly refusing to
  declare a winner. It is never a claim that any candidate is validated as
  a real business opportunity.

### Evidence yield diagnostics (Phase 8)

`app/research_intelligence/yield_diagnostics.py::compute_query_yield_metrics`
computes, per query: `results_returned`, `pre_screen_rejected`,
`evidence_created`, `admission_accepted`, `admission_rejected`,
`extracted_count`, and `accepted_evidence_yield = admission_accepted /
max(results_returned, 1)`. Logged (structured, bounded, secret-free) via
`app/agents/research.py::_log_query_yield` as a `research_query_yield`
event — never persisted to the database; no migration.

### Request diagnostics are now wired into the live mission path

v0.1.2.4 built `ModelRequestDiagnostic` and `collect_request_diagnostics()`
but nothing in the actual mission-execution path ever called them — the
v0.1.2.4 live benchmark therefore has NO historical per-call diagnostic
data. `app/orchestration/evaluator.py::run_worker_with_qa` now wraps every
attempt's worker/QA calls in `collect_request_diagnostics()` and logs a
bounded, secret-free summary (`app/research_intelligence/
prompt_diagnostics.py::format_diagnostic_summary`) as a
`research_request_diagnostics` event after every attempt — including a
failed one. The next live benchmark will be the first to actually capture
this data.

## v0.1.2.6 — QA context compaction + gap query integrity + coverage trace

A controlled v0.1.2.5 live benchmark showed the Research request bounded
and shrinking across retries (10,812 -> 9,637 -> 7,396 chars) while the QA
request exploded (71,254 -> 110,274 -> 157,232 chars, ~2.2x). Root cause
and fix below, plus two further defects the same benchmark surfaced.

### 1. Authoritative evaluator state vs. QA model-facing context

Root cause: `app/agents/qa.py::QAAgent.run()` received
`output.model_dump(mode="json")` — the ENTIRE worker output, verbatim,
uncompacted. For a VALIDATION research task this includes the full
`evidence` list (up to `research_max_validation_evidence_items`=60 items,
every field) and the full `evidence_gaps`/`requirements` lists — unlike
ResearchAgent's own model prompt, which has been bounded since
v0.1.2/v0.1.2.2/v0.1.2.3. Both `accumulated_evidence` and (after
v0.1.2.5's own candidate-scoped gap-identity fix) `accumulated_gaps` grow
every retry, which is exactly why QA's request grew while Research's own
shrank.

```
AUTHORITATIVE WORKER STATE
  |
  +----> deterministic evidence checks / coverage / gate   (FULL state,
  |                                                          unchanged)
  +----> QA CONTEXT COMPACTOR
             |
             v
          QA MODEL (bounded)
```

`app/orchestration/evaluator.py::run_worker_with_qa` computes
`full_output_dump` ONCE per attempt and passes it, unmodified, to
`app/security/evidence_qa.py::evaluate_evidence` (deterministic checks),
`app/research_intelligence/coverage.py` and `gate.py` (via
`evaluate_comparison_readiness`, for Strategy) — none of those were
touched. Only `qa_view = _qa_facing_view(full_output_dump, settings=...)`
— fed to `qa_agent.run()` — is bounded.

### 2. QA Context Compactor

`app/agents/qa_context.py::compact_qa_context`. Keeps: task title/
description (via the call itself), research_mode, bounded summary/
findings/assumptions/open_questions/unsupported_claims, bounded ACCEPTED
evidence (id/candidate_id/requirement_category/source_role/
source_quality/evidence_depth/relevance_label/a short bounded claim —
never the excerpt), bounded unresolved gaps, and a `coverage_summary`
(candidate_id -> category -> status) derived from `requirements[].status`
— already computed deterministically by `build_coverage_matrix`, never
re-derived. Drops entirely: full historical ResearchOutput objects (never
in scope — this function only ever sees ONE attempt's own output),
previous QA responses (QA has never been stateful about its own past
feedback), rejected evidence bodies, page-extract excerpts, the full
authoritative evidence store, and full `ResearchRequirement` objects
(question text, preferred_source_roles, etc.). Bounded by
`qa_prompt_max_*` settings (`app/config/settings.py`), with a final
`qa_prompt_max_total_context_chars` safety net. Only applies to
research-shaped output (`"findings" in output and "question" in output`,
the same dispatch condition `evaluate_evidence` uses) — a Strategy/
Execution output passes through unchanged, since it has no large
`evidence` list to bound and needs its own fields untouched.

### 3. Retry stability

`compact_qa_context` is a pure function of ONE attempt's own output —
takes no retry-history parameter, so there is nothing to accumulate
through. Measured with realistic fixtures shaped like the live mission
(3 candidates x 6 categories): uncompacted QA-facing size grew
37,898 -> 64,588 -> 91,308 -> 118,994 -> 120,226 chars across 5 attempts;
compacted size stayed 2,886 -> 5,734 -> 5,714 -> 5,705 -> 5,696 chars —
flat after the first attempt, never scaling with accumulated evidence/
gaps. See `tests/test_qa_retry_stability_benchmark.py`.

### 4. Validation retry query invariant

A second, unrelated defect the same benchmark surfaced: a gap could carry
a real `candidate_id`/`requirement_category` (e.g.
`ai-powered-content-personalization-platform-for-e-commerce` /
`market_size`) but an orchestration-flavored `suggested_query`
("Validate and compare candidate opportunities market size"). Root
cause: `app/security/evidence_qa.py`'s own generic, candidate-agnostic
gap detector produces a gap for the SAME `gap_type` a candidate-scoped
VALIDATION gap already covers, built from the raw task title. After
v0.1.2.5's `(candidate_id, gap_type)`-keyed `_merge_gaps` fix, BOTH gaps
now survive independently in `accumulated_gaps` (before that fix they
collided and one won at random) — meaning the generic one reliably
competes for one of the bounded retry query slots every attempt.

Fixed in `app/agents/research.py::_query_for_gap`: whenever a gap carries
BOTH `candidate_id` and `requirement_category`, the external query is
ALWAYS rebuilt deterministically via `build_external_research_query`
(candidate concept + requirement-specific intent) — the gap's own
`suggested_query` is audit metadata only in that case, never executed. A
gap with no `candidate_id` (genuinely candidate-agnostic — GENERAL mode,
or a gap whose candidate was dropped) still falls back to its own
`suggested_query` / the broad title-based query, unchanged. See
`tests/test_gap_query_integrity.py`.

### 5. Coverage contribution semantics

The live benchmark showed substantial ACCEPTED evidence but coverage
stuck at 2%/5%/8%. Traced (not assumed) via
`app/research_intelligence/coverage_trace.py`: **source-role suitability**
is the root cause, via two distinct mechanisms, both stemming from real
commercial vendor domains this project doesn't recognize defaulting to
`source_role=UNKNOWN`:

- For `market_size`/`pricing`/`growth`/`unit_economics`/
  `willingness_to_pay`/`customer_validation`, UNKNOWN role is
  **UNSUITABLE** — the Evidence Admission Gate's rule 7 rejects the item
  outright; it never becomes evidence at all.
- For `demand`/`competition`/`customer_pain`/`feasibility`, UNKNOWN role
  is only **WEAK** (not UNSUITABLE) — the item IS admitted, but
  contributes only to a cell's `weak` count, which can never reach
  SUFFICIENT (`qualifying = strong+acceptable` stays 0) — capped at WEAK
  status regardless of how much such evidence exists.

Not a bug in coverage math, evidence dedup, candidate assignment, or
`requirement_category` tagging — all four were traced and confirmed
correct (candidate A's evidence never satisfies candidate B; independent,
suitable sources DO push a cell to SUFFICIENT). See
`tests/test_coverage_contribution_trace.py`.

### 6. Source-role semantics

`app/research_intelligence/source_roles.py`'s path-segment PRIMARY
heuristic now also recognizes `/integrations`/`/documentation` (alongside
the existing `/pricing`/`/docs`/`/product`/`/features`/etc.) — a vendor's
own page about ITS OWN product may be PRIMARY. This can never make a
vendor's MARKET-WIDE claim look authoritative: PRIMARY is only
`ACCEPTABLE` suitability for `market_size`/`growth`-type categories,
never `STRONG` (`app/research_intelligence/suitability.py`'s policy
table, unchanged) — source authority and topic/claim-type suitability
remain independent axes. See
`tests/test_source_role_vendor_classification.py`.

### 7. Report section semantics

OPEN QUESTIONS used to mix actual questions, unresolved evidence gaps, QA
feedback, and unsupported-claim warnings. Split into four
`ExecutiveReport` fields/sections: OPEN QUESTIONS (actual research/
business questions only), UNRESOLVED EVIDENCE GAPS (structured, one line
per unresolved gap), QA NOTES (bounded QA observations), UNSUPPORTED
CLAIMS (deterministic unsupported-claim warnings, from both Research's
own and Strategy's). See `app/orchestration/executor.py::build_report`
and `tests/test_report_section_semantics.py`.

### 8. Usage attribution

Task-level usage attribution (`UsageService.record_many`'s
`agent_type=task.agent_type`) is **unchanged and intentional** — a
Research task's usage rows are still recorded under `agent_type=
"research"`, which is why "Research (Anthropic/Haiku): 8 calls" in a
report includes both ResearchAgent's own calls AND the QA evaluator calls
that happen inside that same task. Added, without a migration: `ModelUsage.role`
("worker" or "qa"), tagged by splitting `run_worker_with_qa`'s usage
collection into two `collect_usage()` blocks; surfaced per completed task
via `Task.output_data["worker_model_calls"]`/`["qa_model_calls"]` (plain
JSON, same provenance pattern as every other optional field in this
project) and rendered as `ExecutiveReport.usage_role_breakdown`. See
`tests/test_usage_attribution_role.py`.

### 9. Diagnostic safety

Re-verified after this checkpoint's changes: `compact_qa_context`'s
output contains no secret-like markers (structurally — every evidence
field it keeps is an id/enum/short bounded string, excerpts are dropped
entirely) and `_log_request_diagnostics` (now logging
`worker_diagnostics + qa_diagnostics` combined per attempt) stays
secret-free. See `tests/test_diagnostic_safety_v0126.py`.

### What v0.1.2.5 ruled out for the token-accounting gap (Phase 10)

Offline-inspecting `anthropic.lib._parse._transform.transform_schema` (the
SDK's own local, offline conversion of a Pydantic schema into the actual
strict tool-schema JSON sent over the wire) shows it inflates this
project's real DTOs' raw `model_json_schema()` output by only ~5-8%, not
several-fold — ruling out "schema compilation overhead" as the dominant
explanation. `anthropic.AsyncAnthropic.messages.count_tokens` is a real
HTTP endpoint (confirmed by reading its source), not a local tokenizer —
Anthropic's exact tokenization of a given request cannot be reproduced
offline with this SDK version. See
`tests/test_token_discrepancy_analysis.py` and the v0.1.2.5 delivery report
for the full measurement.

## v0.1.2.7 — candidate/query identity invariant + worker-call accounting

A further live benchmark (three candidates: CMS Template & Component
Marketplace, Digital Product Creation & Distribution Course, Headless CMS +
E-commerce Integration Suite) showed VALIDATION evidence tagged with a
candidate_id that did not match the concept its own originating query was
built for, and an implausible `worker model calls: 16` for a task with no
matching Anthropic request volume in the live log. Both traced to root
cause (not guessed) and fixed below.

### Candidate Research Identity Invariant

```text
TARGET
  |-- candidate_id
  |-- candidate concept
  `-- requirement
        |
        v
      QUERY
        |
        v
    RESULTS
        |
        v
    EVIDENCE
```

All stages must preserve the same target identity. Root cause of the
violation: `app/agents/research.py::_build_queries` returned a bare
`list[str]` — once a query became plain text, WHICH candidate/requirement
it was built FOR was discarded. Every VALIDATION `EvidenceItem`'s
`candidate_id` was then decided from scratch by `_tag_validation_evidence`'s
cross-candidate keyword-overlap scoring, with no memory of which
candidate's own query actually retrieved it. An imperfect, adjacent search
result (real-world Tavily noise — e.g. a hit about a DIFFERENT candidate's
business surfacing under this candidate's own query) would then outscore
the correct candidate on keyword overlap and get reassigned to the wrong
`candidate_id` — reproduced exactly in
`tests/test_candidate_query_identity_v0127.py`.

Fix: `app/agents/research.py::QueryTarget` — a small, frozen dataclass
(`query`, `candidate_id`, `requirement_category`) — carries identity
alongside the query TEXT from construction (`_build_query_targets`, the new
home of `_build_queries`'s logic) through to `EvidenceItem` creation
(`ResearchAgent._gather_evidence`, which now stamps `candidate_id`/
`requirement_category` on every item AT CREATION TIME whenever its query
had an explicit target — before any relevance/candidate tagging runs).
`_build_queries` itself is unchanged for existing callers/tests — a thin
wrapper returning `[t.query for t in _build_query_targets(...)]`.

**Explicit query provenance always wins.** `_tag_validation_evidence` now
partitions evidence into: (1) items with a pre-stamped `candidate_id` — tagged
against THAT SAME candidate only (never compared against other candidates;
if the query also carried an explicit `requirement_category`, scoring is
further scoped to only that one requirement), and (2) untargeted items —
the ONLY case that still falls through to the pre-existing cross-candidate
best-match scoring. A REJECTED item (e.g. `WRONG_CANDIDATE` — its content
really was about a different candidate) still preserves its originating
`candidate_id`; rejection never erases or reassigns provenance.

A `CandidateResearchTarget`-style dataclass (Phase 2) WAS needed here —
tracing showed the missing piece was exactly "candidate label, candidate
id, and requirement passed separately, then discarded once flattened to a
bare query string"; `QueryTarget` is that structure, scoped to what
`_build_query_targets`/`_gather_evidence` actually need (query text +
identity), not a broader schema redesign.

### Validation Retry Identity Invariant

```text
(candidate_id, requirement_category)
        |
        v
canonical external query (build_external_research_query)
```

Unchanged from v0.1.2.6's `_query_for_gap` fix (still the single place a
gap's query text is rebuilt), but `_build_query_targets` now additionally
enforces: a gap that CLAIMS to be candidate-scoped (`candidate_id` is set)
but cannot resolve BOTH its candidate AND its `requirement_category`
consistently is malformed and is **skipped entirely** — never falls back to
a generic query under that candidate's identity, and never consumes one of
the bounded `research_max_gap_queries_per_attempt` retry slots (a
lower-ranked, resolvable gap can take the freed slot instead). The gap
itself is untouched — still audit-visible via `accumulated_gaps`/
`output.evidence_gaps`. A genuinely candidate-agnostic gap (`candidate_id`
is `None` — GENERAL mode, or `evidence_qa.py`'s own generic detector) is
unaffected and still falls back to its own `suggested_query`/the broad
title query exactly as before. Generic QA gap text (`suggested_query`) is
therefore never an executable candidate-specific search instruction when a
real candidate-scoped target exists — it remains audit metadata only. See
`tests/test_candidate_query_identity_v0127.py`.

### Worker/QA model-call accounting semantics

Root cause of `worker model calls: 16`: `app/tools/research_tools.py`'s
Tavily provider calls the SAME `app.agents.usage.record_usage()` side
channel every real LLM provider call goes through, and that call happens
INSIDE `run_worker_with_qa`'s `with collect_usage() as worker_events:`
block (the worker's own `agent.run()` is what issues the Tavily searches).
Every Tavily search/extract call was blanket-tagged `role="worker"`
alongside the one real Anthropic call, and `app/orchestration/executor.py`
summed ALL of them as `worker_model_calls` — `role` answers WHO issued a
call, never WHAT was called.

Fix: `ModelUsage.is_model_call: bool = True` (`app/agents/usage.py`) —
defaults `True` for every existing model-provider call site (Anthropic/
OpenAI/Mock, unaffected); `app/tools/research_tools.py`'s Tavily `_post`
explicitly passes `is_model_call=False`. Corrected semantics:

```text
worker_model_calls = sum(api_calls for events where role == "worker" AND is_model_call)
qa_model_calls     = sum(api_calls for events where role == "qa"     AND is_model_call)
```

Tavily search/extract calls are excluded regardless of which role's
`collect_usage()` block they were issued inside. A structured-output
repair attempt still records its own `ModelUsage` (an actual second
Anthropic request) and correctly increments the count. No change to
mission-level usage accounting (`UsageService`/`totals_for_project` still
sum every event, unchanged) and no database migration — `role`/
`is_model_call` are JSON-carried `Task.output_data` fields, never
persisted columns. See `tests/test_usage_accounting_v0127.py`.

### Discovery zero-candidate finding

Traced `app/agents/research.py::_finalize_candidates` (the deterministic
step between the model's raw `DiscoveryModelOutput.candidates` and the
`ResearchCandidate` objects actually returned): a valid 3-distinct-label
DTO always yields exactly 3 candidates; an empty model candidate list
always yields zero, safely; a normalization collision (two labels
resolving to the same `candidate_id`) deterministically keeps the
first-seen candidate and drops the rest, never crashing or silently
sharing an id. No reproducible deterministic bug was found — the live
benchmark's attempt-0 `candidate_count=0` is consistent with the MODEL
itself returning an empty list on that attempt (a valid, if suboptimal,
output variation), which the existing QA-driven retry already recovers
from correctly on attempt 1. Documented, not "fixed" — see
`tests/test_discovery_zero_candidate_v0127.py`.
