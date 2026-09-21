"""Central application configuration. All environment reads happen here."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    jarvis_env: str = "development"
    log_level: str = "INFO"
    log_sensitive_data: bool = False

    database_url: str = "sqlite+aiosqlite:///./jarvis.db"

    model_provider: str = "openai"

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    # Optional. Only needed when ANTHROPIC_API_KEY is NOT already scoped to a
    # single workspace — such a key is rejected with HTTP 400 ("this API key
    # is not scoped to a workspace") unless every request carries an
    # anthropic-workspace-id header. A workspace-scoped key keeps working
    # unchanged with this left unset. See AnthropicProvider in
    # app/agents/providers.py.
    anthropic_workspace_id: str | None = None

    jarvis_model: str = "gpt-4o"
    research_model: str = "gpt-4o-mini"
    strategy_model: str = "gpt-4o"
    qa_model: str = "gpt-4o-mini"
    execution_model: str = "gpt-4o-mini"

    max_agent_retries: int = 2
    max_concurrent_agents: int = 3
    max_tasks_per_run: int = 25
    max_tool_calls_per_task: int = 10

    # Research capability (v0.1.1). "dev" preserves exact v0.1 behavior (no
    # provider call, ResearchAgent falls back to labeled sample data). "mock"
    # enables the deterministic MockResearchProvider (no network, safe for
    # tests/demos of the evidence pipeline). "live" is reserved until a real
    # web-search vendor is selected and implemented — see docs/evidence.md.
    research_provider: str = "dev"
    research_max_results: int = 5
    research_fetch_timeout_seconds: float = 10.0
    research_max_response_bytes: int = 2_000_000
    research_max_redirects: int = 3

    # Selective evidence extraction (v0.1.1 checkpoint 3). Bounded, provider-
    # neutral upgrade of search-snippet evidence to page-extract evidence via
    # ResearchProvider.fetch() — see app/agents/research.py. Conservative
    # defaults: a handful of pages per attempt, capped extracted text.
    research_enable_fetch: bool = True
    research_max_fetch_per_task: int = 2
    research_fetch_max_chars: int = 12_000

    # Bounds on the Research Agent's structured OUTPUT (never grows without
    # bound across retries — see docs/evidence.md). Enforced deterministically
    # after the model responds, not just requested via the prompt. Evidence
    # kept in the persisted Evidence table is NOT capped by these — only what
    # is embedded in ResearchOutput/the prompt is.
    research_max_findings: int = 12
    research_max_evidence_items: int = 15
    research_max_open_questions: int = 8
    research_max_assumptions: int = 8
    research_max_gaps: int = 8
    research_max_finding_chars: int = 1000
    # Prompt-facing excerpt bound (what the model SEES per evidence item) —
    # deliberately much smaller than research_fetch_max_chars (what gets
    # STORED): the model needs enough to cite/summarize, not the full page.
    research_max_evidence_excerpt_chars: int = 600

    # Tavily live ResearchProvider (v0.1.1). Only read when RESEARCH_PROVIDER=tavily.
    tavily_api_key: str | None = None
    # "basic" (default, low-cost) or "advanced" (deeper, more expensive) — see
    # https://docs.tavily.com. Never escalated automatically; a caller that
    # wants deeper research must configure this explicitly.
    tavily_search_depth: str = "basic"

    # Budget guardrails (v0.1.1). A mission is one project/objective run.
    max_api_calls_per_mission: int = 40
    max_tokens_per_mission: int = 200_000
    max_estimated_cost_per_mission_usd: float | None = None
    daily_cost_limit_usd: float | None = None

    # JSON map of model id -> {"input_per_million_usd": x, "output_per_million_usd": y}.
    # Empty by default: no pricing is assumed, so estimated cost stays unset
    # (None) rather than guessed. See app/config/pricing.py.
    model_pricing_json: str = "{}"

    evidence_stale_after_days: int = 540

    # Research Intelligence (v0.1.2). Bounded, deterministic requirement
    # planning / source-role / relevance / coverage / completeness controls —
    # see app/research_intelligence/. The objective is better evidence per
    # token, not more searches, so these stay conservative by default.
    research_max_requirements_per_candidate: int = 6
    # Bounded follow-up searches per retry attempt, one per unresolved
    # evidence gap (highest-importance first) — see
    # app/agents/research.py::_build_queries. Was a hardcoded constant
    # (MAX_FOLLOWUP_QUERIES) before v0.1.2.
    research_max_gap_queries_per_attempt: int = 3
    # Evidence scoring below this relevance is excluded from model-facing
    # evidence/coverage (still recorded with a rejection_reason, never
    # silently deleted) — see app/research_intelligence/relevance.py.
    research_min_relevance: float = 0.30
    # A candidate's weighted coverage across its core requirement categories
    # must reach this fraction before it's eligible for comparison — see
    # app/research_intelligence/completeness.py.
    research_min_comparison_coverage: float = 0.70
    # Minimum distinct canonical domains required for a requirement that
    # `requires_independent_sources` to count as SUFFICIENT — see
    # app/research_intelligence/coverage.py.
    research_min_independent_sources: int = 2
    # Caps how many evidence items count toward one requirement's coverage
    # cell — prevents a flood of near-duplicate snippets from manufacturing
    # SUFFICIENT status. See app/research_intelligence/coverage.py.
    research_max_evidence_per_requirement: int = 4

    # Evidence Admission Gate (v0.1.2.4 Defect 3). relevance_label/
    # relevance_score answer "how well does this match the requirement's
    # KEYWORDS" — that alone let an authoritative, well-matched-on-keywords
    # source about the WRONG topic (e.g. an HR "candidate skills assessment
    # market size" page, for a data-analytics-dashboard candidate's own
    # market_size requirement) through, because relevance.py's own
    # candidate-name overlap is only a partial (40%) weight in that score,
    # not a hard gate. This threshold requires strictly MORE than
    # research_min_relevance (MEDIUM+, not just LOW+) before an item may
    # enter authoritative VALIDATION evidence. See
    # app/research_intelligence/admission.py.
    research_admission_min_relevance_score: float = 0.50
    # Deterministic candidate-specific semantic overlap floor (Phase 4 rule
    # 6): the fraction of the candidate's own significant label/description
    # tokens that must appear in the evidence text. Catches exactly the
    # case above — score_relevance's keyword match can be high while this
    # is 0.0. 0.34 matches the "clearly about this candidate" cutoff
    # app/research_intelligence/relevance.py already uses for its own
    # genericness check — high enough that a single incidental shared word
    # (e.g. both the candidate's name and unrelated evidence happening to
    # say "platform") can't pass alone; a real topical match hits several
    # tokens, not one. See app/research_intelligence/admission.py.
    research_admission_min_candidate_overlap: float = 0.34

    # Discovery/Validation split (v0.1.2.1). Hard bound on how many
    # candidates a DISCOVERY task may propose (and a VALIDATION task may
    # accept) per mission — no unbounded candidate/task expansion. See
    # app/agents/research.py.
    research_max_candidates_per_mission: int = 3
    # A VALIDATION-mode research task's own persisted output.evidence needs
    # to stay non-lossy — it is the authoritative source the Candidate
    # Completeness Gate reads from (never the compacted Strategy-prompt
    # view; see app/orchestration/evaluator.py and
    # docs/research_intelligence.md, "Issue 2"). Sized for
    # research_max_candidates_per_mission candidates x
    # CORE_COMPARISON_CATEGORIES x research_max_evidence_per_requirement
    # (3 x 6 x 4 = 72), rounded down to a clean bound — still a hard cap,
    # not unbounded, and does not raise the mission API-call/token budget.
    research_max_validation_evidence_items: int = 60

    # Research Context Compactor (v0.1.2.2). Bounds ONLY what's shown to
    # the Research MODEL PROMPT on a given attempt — never the persisted
    # Evidence table, the coverage matrix, or the completeness gate, all of
    # which keep seeing everything (see docs/research_intelligence.md,
    # "Issue 2" and this version's token-efficiency patch notes).
    # research_max_evidence_items / research_max_evidence_excerpt_chars
    # (above) already provide the equivalent item-count/per-item-excerpt
    # bounds, so they are reused rather than duplicated here.
    research_prompt_max_evidence_per_requirement: int = 2
    research_prompt_max_total_evidence_chars: int = 4000
    research_prompt_max_qa_feedback_chars: int = 400

    # Strategy prompt/context compaction (v0.1.1 efficiency patch). Bounds
    # what's shown to the Strategy Agent on each attempt — never touches
    # persisted Evidence or the research task's own stored output. See
    # app/agents/strategy_context.py.
    strategy_max_evidence_items: int = 12
    strategy_max_evidence_excerpt_chars: int = 400
    strategy_max_findings: int = 8
    strategy_max_open_questions: int = 5
    strategy_max_assumptions: int = 5
    strategy_max_qa_feedback_chars: int = 500

    # QA Context Compactor (v0.1.2.6, Phase 3/4). Bounds ONLY the LLM-facing
    # QA prompt — never the authoritative worker output the deterministic
    # evidence checks/coverage/completeness gate use (see
    # app/orchestration/evaluator.py::run_worker_with_qa and
    # app/agents/qa_context.py). Root cause this checkpoint: QAAgent.run()
    # was receiving the ENTIRE worker output dump verbatim (full,
    # uncompacted evidence — every field, up to
    # research_max_validation_evidence_items=60 items — while
    # ResearchAgent's own prompt already bounded this via
    # research_prompt_max_*). That is why the QA request grew ~2.2x across
    # retries while the Research request shrank.
    qa_prompt_max_evidence_items: int = 10
    qa_prompt_max_evidence_per_requirement: int = 2
    qa_prompt_max_evidence_chars: int = 3000
    qa_prompt_max_evidence_claim_chars: int = 250
    qa_prompt_max_findings: int = 8
    qa_prompt_max_finding_chars: int = 300
    qa_prompt_max_open_questions: int = 5
    qa_prompt_max_open_question_chars: int = 200
    qa_prompt_max_gaps: int = 6
    qa_prompt_max_gap_chars: int = 200
    qa_prompt_max_total_context_chars: int = 6000

    # Pre-call budget reservation (v0.1.1 efficiency patch). A conservative,
    # flat reservation added on top of already-committed + in-flight mission
    # usage before a retry attempt is allowed to start — never a precise
    # token prediction (the provider API doesn't make that reliable ahead of
    # a call). See app/orchestration/budget.py::reserved_totals.
    budget_reserved_output_tokens: int = 4096
    budget_reservation_safety_margin_tokens: int = 2000

    # Sandboxed Action Executor (v0.1.3.4). The ONLY root directory
    # file.create_sandboxed is ever allowed to write under — trusted
    # application configuration only, NEVER an Action/model input (see
    # app/decision_intelligence/sandbox_fs.py). Relative paths are resolved
    # against the process working directory; tests always override this with
    # a pytest tmp_path, never the real value, so a real user's filesystem is
    # never touched by the test suite.
    sandbox_root: str = "runtime/sandbox"

    @property
    def is_production(self) -> bool:
        return self.jarvis_env.lower() == "production"

    @property
    def has_llm_credentials(self) -> bool:
        """Whether an API key is configured for the currently-selected MODEL_PROVIDER."""
        provider = self.model_provider.strip().lower()
        if provider == "anthropic":
            return bool(self.anthropic_api_key)
        if provider == "openai":
            return bool(self.openai_api_key)
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
