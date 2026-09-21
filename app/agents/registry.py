"""Agent Registry — the single catalog of available agent types.

Jarvis never hard-codes a chain of specialist logic; it looks up capabilities,
permissions, and an executable instance through this registry. Adding a new
department/agent later means registering it here, not modifying Jarvis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from app.config.settings import Settings, get_settings
from app.database.models import PermissionLevel
from app.schemas.agents import AgentDescriptor


class AgentProtocol(Protocol):
    """Every registered agent implements this shape (duck-typed, no forced inheritance)."""

    descriptor: AgentDescriptor

    def __init__(self, descriptor: AgentDescriptor, provider: Any = None) -> None: ...

    async def run(
        self, *, title: str, description: str, input_data: dict, context: dict
    ) -> BaseModel: ...


@dataclass(frozen=True)
class RegisteredAgent:
    descriptor: AgentDescriptor
    factory: "AgentFactory"


AgentFactory = "type"  # populated below; avoids circular import at module load


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, RegisteredAgent] = {}

    def register(self, descriptor: AgentDescriptor, factory) -> None:
        self._agents[descriptor.name] = RegisteredAgent(descriptor=descriptor, factory=factory)

    def get_descriptor(self, agent_type: str) -> AgentDescriptor:
        entry = self._agents.get(agent_type)
        if entry is None:
            raise KeyError(f"No agent registered for type '{agent_type}'")
        return entry.descriptor

    def create(self, agent_type: str, provider=None):
        entry = self._agents.get(agent_type)
        if entry is None:
            raise KeyError(f"No agent registered for type '{agent_type}'")
        return entry.factory(descriptor=entry.descriptor, provider=provider)

    def has_permission(self, agent_type: str, permission: PermissionLevel) -> bool:
        return permission in self.get_descriptor(agent_type).permissions

    def list_agents(self) -> list[AgentDescriptor]:
        return [entry.descriptor for entry in self._agents.values()]


def build_default_registry(settings: Settings | None = None) -> AgentRegistry:
    from app.agents.execution import ExecutionAgent
    from app.agents.jarvis import JarvisAgent
    from app.agents.qa import QAAgent
    from app.agents.research import ResearchAgent
    from app.agents.strategy import StrategyAgent

    settings = settings or get_settings()
    registry = AgentRegistry()

    registry.register(
        AgentDescriptor(
            name="jarvis",
            role="Executive Orchestrator",
            description="Owns the objective end-to-end: plans, delegates, evaluates, reports.",
            capabilities=["planning", "delegation", "reporting"],
            permissions=[PermissionLevel.READ, PermissionLevel.WRITE],
            model=settings.jarvis_model,
        ),
        JarvisAgent,
    )
    registry.register(
        AgentDescriptor(
            name="research",
            role="Research Agent",
            description="Researches assigned questions and returns structured, evidence-labeled findings.",
            capabilities=["research", "analysis", "evidence_collection"],
            permissions=[PermissionLevel.READ],
            model=settings.research_model,
        ),
        ResearchAgent,
    )
    registry.register(
        AgentDescriptor(
            name="strategy",
            role="Strategy Agent",
            description="Compares researched options and produces an evidence-based recommendation.",
            capabilities=["strategy", "comparison", "recommendation"],
            permissions=[PermissionLevel.READ],
            model=settings.strategy_model,
        ),
        StrategyAgent,
    )
    registry.register(
        AgentDescriptor(
            name="execution",
            role="Execution Agent",
            description="Performs approved internal operational work (drafts, state updates).",
            capabilities=["approved_operations", "drafting", "internal_updates"],
            permissions=[PermissionLevel.READ, PermissionLevel.WRITE],
            model=settings.execution_model,
        ),
        ExecutionAgent,
    )
    registry.register(
        AgentDescriptor(
            name="qa",
            role="QA Agent",
            description="Evaluates agent outputs for completeness, unsupported claims, and quality.",
            capabilities=["validation", "quality_control", "evaluation"],
            permissions=[PermissionLevel.READ],
            model=settings.qa_model,
        ),
        QAAgent,
    )
    return registry
