"""Jarvis — the Executive Orchestrator.

Jarvis never invents completed work, never claims a tool was used when it wasn't,
and never claims a task completed unless the database records it as COMPLETED.
Its two structured responsibilities are planning (turn an objective into an
ExecutionPlan) and reporting (turn recorded task results into an ExecutiveReport).
Actual delegation/dispatch is handled by app.orchestration, which only ever reads
real task state from the database.
"""
from __future__ import annotations

import json

from app.schemas.agents import AgentDescriptor
from app.schemas.reports import ExecutiveReport
from app.schemas.tasks import ExecutionPlan
from app.utils.logging import get_logger

logger = get_logger(__name__)

PLANNING_SYSTEM_PROMPT = """You are Jarvis, the Executive Orchestrator of Jarvis OS.
Given a business objective, produce a structured ExecutionPlan of tasks assigned to
specialist agent types (research, strategy, execution, qa). Rules:
- Break the objective into concrete tasks with clear success criteria.
- Use dependencies so downstream tasks (e.g. strategy) wait on upstream tasks (e.g. research).
- Mark requires_approval=true for any task implying money, purchases, external messaging,
  publishing, deleting data, account changes, or other irreversible actions.
- Do not invent work that isn't represented as a task.
- If the objective asks you to FIND/DISCOVER/IDENTIFY multiple candidate opportunities and
  then compare or recommend the strongest one (the candidates do not exist yet at plan time),
  use TWO research tasks instead of one broad task or several independent guesses:
  (1) one research task with research_mode="DISCOVERY" whose job is only to identify the
  candidates (it returns them structured, it does not deep-validate them), and
  (2) one research task with research_mode="VALIDATION" that depends on the DISCOVERY task
  and gathers candidate-specific evidence for comparison. Then a strategy task depends on the
  VALIDATION task, and a qa task depends on strategy — exactly as usual.
- If the objective is a single, already-known topic (not a "find N opportunities" objective),
  leave research_mode unset (ordinary single-topic research) — do not use DISCOVERY/VALIDATION
  for objectives that don't need candidate discovery.
- Return only the requested structured ExecutionPlan."""

REPORT_SYSTEM_PROMPT = """You are Jarvis, the Executive Orchestrator of Jarvis OS.
Produce a structured ExecutiveReport strictly from the provided task results. Rules:
- Never claim a task completed unless it is present in the provided completed-task results.
- Clearly separate FACT, ASSUMPTION, RECOMMENDATION, and UNKNOWN — assumptions and
  recommendations must not be presented as facts.
- List every approval that is still pending.
- Return only the requested structured ExecutiveReport."""


class JarvisAgent:
    def __init__(self, descriptor: AgentDescriptor, provider=None):
        self.descriptor = descriptor
        self._provider = provider

    async def plan(self, objective: str) -> ExecutionPlan:
        if self._provider is None:
            raise RuntimeError("JarvisAgent requires a model provider")
        plan = await self._provider.complete_structured(
            system_prompt=PLANNING_SYSTEM_PROMPT,
            user_prompt=json.dumps({"objective": objective}),
            output_schema=ExecutionPlan,
            model=self.descriptor.model,
        )
        logger.info("jarvis_plan_created", objective=objective, task_count=len(plan.tasks))
        return plan

    async def generate_report(self, report_context: dict) -> ExecutiveReport:
        if self._provider is None:
            raise RuntimeError("JarvisAgent requires a model provider")
        report = await self._provider.complete_structured(
            system_prompt=REPORT_SYSTEM_PROMPT,
            user_prompt=json.dumps(report_context),
            output_schema=ExecutiveReport,
            model=self.descriptor.model,
        )
        logger.info("jarvis_report_created", objective=report.objective, status=report.status)
        return report

    async def run(self, *, title: str, description: str, input_data: dict, context: dict):
        raise NotImplementedError(
            "JarvisAgent is the orchestrator itself and is not dispatched as a worker task; "
            "use plan()/generate_report() instead."
        )
