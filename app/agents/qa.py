"""QA Agent — READ only. Evaluator loop: PASS / FAIL / NEEDS_REVIEW with actionable feedback."""
from __future__ import annotations

import json

from app.schemas.agents import AgentDescriptor, QAVerdict
from app.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the QA Agent inside Jarvis OS.
Rules:
- Inspect the given output for completeness, missing information, and unsupported claims.
- Score quality from 0.0 to 1.0.
- Return a verdict of PASS, FAIL, or NEEDS_REVIEW.
- Provide specific, actionable feedback the original agent can act on for a retry.
- If the output being reviewed is a Strategy recommendation, it carries a `comparison_ready`
  field — a deterministic Candidate Completeness Gate verdict, computed by Jarvis, not by the
  Strategy agent. Read it explicitly:
  - If `comparison_ready` is false, at least one candidate was not researched to a comparable
    minimum standard. Strategy is REQUIRED to refuse to declare a winner in that case. Do NOT
    fail or penalize Strategy merely because it refused to name a single strongest opportunity
    — that refusal is the CORRECT behavior, not a shortcoming. Evaluate instead whether it: (a)
    clearly stated the evidence is insufficient, (b) avoided an unsupported ranking, (c)
    identified the missing requirements, (d) gave useful next-validation steps, and (e) if it
    named a preliminary candidate, was explicit that this is provisional. If all of that holds,
    PASS it — PASS here means "correctly handled insufficient evidence," not "business
    opportunity validated." Never instruct Strategy to override the gate and pick a winner
    anyway.
  - If `comparison_ready` is true, normal evaluation of the recommendation's evidence and
    reasoning applies.
- Return only the requested structured QAVerdict."""


class QAAgent:
    def __init__(self, descriptor: AgentDescriptor, provider=None):
        self.descriptor = descriptor
        self._provider = provider

    async def run(self, *, title: str, description: str, input_data: dict, context: dict) -> QAVerdict:
        if self._provider is None:
            raise RuntimeError("QAAgent requires a model provider")

        prompt_context = {
            "title": title,
            "description": description,
            "output": input_data.get("output", {}),
            "success_criteria": input_data.get("success_criteria"),
        }
        result = await self._provider.complete_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=json.dumps(prompt_context),
            output_schema=QAVerdict,
            model=self.descriptor.model,
        )
        logger.info("qa_agent_completed", title=title, verdict=result.verdict, score=result.score)
        return result
