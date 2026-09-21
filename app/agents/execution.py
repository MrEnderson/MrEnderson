"""Execution Agent — READ+WRITE. Performs approved internal work only, never
irreversible external actions. Consequential actions are gated upstream by the
dispatcher, which routes requires_approval tasks to NEEDS_APPROVAL before this
agent ever runs them."""
from __future__ import annotations

import json

from app.schemas.agents import AgentDescriptor, ExecutionOutput
from app.utils.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the Execution Agent inside Jarvis OS.
Rules:
- You may only perform approved, internal, reversible operations (drafts, internal state updates).
- Never claim to have performed an external, financial, or irreversible action.
- Report exactly what was performed, nothing more.
- Return only the requested structured ExecutionOutput."""


class ExecutionAgent:
    def __init__(self, descriptor: AgentDescriptor, provider=None):
        self.descriptor = descriptor
        self._provider = provider

    async def run(self, *, title: str, description: str, input_data: dict, context: dict) -> ExecutionOutput:
        if self._provider is None:
            raise RuntimeError("ExecutionAgent requires a model provider")

        prompt_context = {"title": title, "description": description, "input_data": input_data}
        result = await self._provider.complete_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=json.dumps(prompt_context),
            output_schema=ExecutionOutput,
            model=self.descriptor.model,
        )
        logger.info("execution_agent_completed", title=title, actions=len(result.actions_performed))
        return result
