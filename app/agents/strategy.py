"""Strategy Agent — READ permission only. Never presents assumptions as facts."""
from __future__ import annotations

import json

from app.config.settings import get_settings
from app.research_intelligence.gate import evaluate_comparison_readiness
from app.research_intelligence.schemas import ComparisonReadiness
from app.schemas.agents import AgentDescriptor, StrategyOutput
from app.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the Strategy Agent inside Jarvis OS.
Rules:
- Base your comparison and recommendation only on the research results provided.
- The research results include a structured `evidence` list (real, retrieved sources) on
  each research result. Distinguish four kinds of statement and never blur them together:
  VERIFIED/RETRIEVED FACT (backed by an evidence id from the research results),
  ASSUMPTION (explicitly stated as unverified), MODEL INFERENCE (your own reasoning about
  what the facts imply), and UNSUPPORTED CLAIM (a factual-sounding statement with no
  backing evidence — this must go in `unsupported_claims`, never stated as fact).
- Never present an assumption, inference, or unsupported claim as a verified fact.
- For quantitative claims — market size, growth rate, price, competitor count, revenue,
  CAC, conversion rate, market share, user count — only state a specific figure if it is
  backed by an evidence id (add that id to `evidence_used`). If no such evidence exists,
  say the figure is unknown/an assumption rather than inventing one. Prefer PAGE_EXTRACT
  or AUTHORITATIVE/PRIMARY evidence for these claims where available.
- `valid_evidence_ids` is the complete, exhaustive list of evidence ids you may cite in
  `evidence_used`. Never invent, guess, or reuse an id that is not in that list — an id
  that looks plausible but isn't listed is not valid evidence.
- `comparison_readiness` is a deterministic Candidate Completeness Gate verdict computed
  by Jarvis, not by you. If `comparison_readiness.ready` is false, at least one candidate
  has not been researched to a comparable minimum standard — do NOT declare a winner or
  say one candidate is "the strongest"; instead state that comparison is not yet possible,
  name the most promising candidate only as a PROVISIONAL validation candidate, and list
  what's missing. This will also be enforced deterministically after your response, but
  write it that way regardless.
- The research results shown to you have been bounded for efficiency; this does not
  shrink what was actually gathered, only what's shown to you this attempt.
- If `previous_qa_feedback` is present, this is a retry — directly address that feedback.
  If `previous_conclusion` is present, treat it as your own prior attempt and revise it
  rather than starting over from scratch.
- Explicitly list assumptions your recommendation depends on, and list any unsupported
  claims separately so they are never mistaken for verified facts.
- Return only the requested structured StrategyOutput."""

_INSUFFICIENT_MARKER = "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE"


class StrategyAgent:
    def __init__(self, descriptor: AgentDescriptor, provider=None):
        self.descriptor = descriptor
        self._provider = provider

    async def run(self, *, title: str, description: str, input_data: dict, context: dict) -> StrategyOutput:
        if self._provider is None:
            raise RuntimeError("StrategyAgent requires a model provider")

        settings = get_settings()
        research_results = input_data.get("research_results", [])
        valid_evidence_ids = sorted(
            {
                e.get("id")
                for r in research_results
                for e in (r.get("evidence") or [])
                if e.get("id")
            }
        )
        # Prefer the AUTHORITATIVE readiness precomputed by the evaluator
        # from the full, pre-compaction research_results (see
        # app/orchestration/evaluator.py) — `research_results` here may
        # already be the bounded/compacted view shown to this attempt's
        # prompt. Only self-compute as a fallback for direct calls that
        # bypass the evaluator (e.g. tests exercising StrategyAgent in
        # isolation), where `research_results` IS the full, authoritative
        # set. See docs/research_intelligence.md, "Issue 2".
        precomputed = input_data.get("comparison_readiness")
        readiness: ComparisonReadiness = (
            ComparisonReadiness.model_validate(precomputed)
            if precomputed is not None
            else evaluate_comparison_readiness(research_results, settings=settings)
        )

        prompt_context = {
            "title": title,
            "description": description,
            "research_results": research_results,
            "valid_evidence_ids": valid_evidence_ids,
            "previous_qa_feedback": input_data.get("previous_qa_feedback"),
            "previous_conclusion": input_data.get("previous_conclusion"),
            "comparison_readiness": readiness.model_dump(mode="json"),
        }
        result = await self._provider.complete_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=json.dumps(prompt_context),
            output_schema=StrategyOutput,
            model=self.descriptor.model,
        )

        # Candidate Completeness Gate (v0.1.2): always overwritten
        # deterministically, never left to the model — see
        # app/research_intelligence/completeness.py. A model cannot bypass
        # this by writing a confident recommendation anyway.
        result.comparison_ready = readiness.ready
        result.candidate_statuses = readiness.candidate_statuses
        result.missing_requirements = readiness.missing_requirements
        result.other_material_gaps = readiness.other_material_gaps
        result.remediation_queries = readiness.remediation_queries
        if not readiness.ready:
            result.recommendation = _enforce_insufficient_evidence_framing(
                result.recommendation, readiness=readiness
            )

        logger.info(
            "strategy_agent_completed",
            title=title,
            confidence=result.confidence,
            comparison_ready=result.comparison_ready,
        )
        return result


def _enforce_insufficient_evidence_framing(recommendation: str, *, readiness: ComparisonReadiness) -> str:
    if _INSUFFICIENT_MARKER in (recommendation or "").upper():
        return recommendation
    candidate = _best_provisional_candidate(readiness)
    missing = "; ".join(readiness.missing_requirements[:6]) or "comparable evidence across all candidates"
    lines = [
        _INSUFFICIENT_MARKER,
        f"MOST PROMISING VALIDATION CANDIDATE: {candidate} (provisional — not yet comparably validated)",
        f"MISSING INFORMATION: {missing}",
        "NEXT VALIDATION: Run targeted follow-up research on the missing requirements above before ranking candidates.",
    ]
    return "\n".join(lines)


def _best_provisional_candidate(readiness: ComparisonReadiness) -> str:
    if not readiness.candidate_statuses:
        return "unknown"
    best = max(readiness.candidate_statuses, key=lambda s: s.coverage_percentage)
    return best.candidate_label
