"""Model-usage persistence and mission-level rollups. USAGE (tokens/calls) is
always what the provider reported (see app/agents/usage.py); estimated cost is
computed only when pricing is configured for the exact model id
(app/config/pricing.py) and stays NULL otherwise."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.usage import ModelUsage
from app.config.pricing import estimate_cost_usd, get_pricing_table
from app.database.repositories import UsageRepository, UsageTotals


class UsageService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.usage = UsageRepository(session)

    async def record_many(
        self,
        *,
        workspace_id: str,
        project_id: str,
        task_id: str | None,
        agent_type: str,
        events: list[ModelUsage],
    ) -> None:
        for event in events:
            cost = estimate_cost_usd(
                model=event.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
            )
            await self.usage.create(
                workspace_id=workspace_id,
                project_id=project_id,
                task_id=task_id,
                agent_type=agent_type,
                provider=event.provider,
                model=event.model,
                input_tokens=event.input_tokens,
                output_tokens=event.output_tokens,
                total_tokens=event.total_tokens,
                api_calls=event.api_calls,
                retry_number=event.retry_number,
                elapsed_ms=event.elapsed_ms,
                estimated_cost_usd=cost,
            )

    async def totals_for_project(self, project_id: str) -> UsageTotals:
        return await self.usage.totals_for_project(project_id)

    async def breakdown_by_agent(self, project_id: str) -> dict[str, UsageTotals]:
        records = await self.usage.list_for_project(project_id)
        by_agent: dict[str, UsageTotals] = {}
        for r in records:
            totals = by_agent.setdefault(r.agent_type, UsageTotals())
            totals.api_calls += r.api_calls
            totals.input_tokens += r.input_tokens or 0
            totals.output_tokens += r.output_tokens or 0
            totals.total_tokens += r.total_tokens or 0
        return by_agent

    async def breakdown_by_agent_and_provider(
        self, project_id: str
    ) -> dict[tuple[str, str, str], UsageTotals]:
        """Keyed by (agent_type, provider, model) so different providers
        within the same agent_type stay apart (e.g. a research task's
        Anthropic token usage vs. its Tavily search calls), and — since
        Tavily's `model` field is "search"/"extract" — so those two
        operations are individually visible too. Also splits each bucket
        into initial vs. retry calls (UsageRecord.retry_number == 0 vs > 0).
        See AgentUsageBreakdown."""
        records = await self.usage.list_for_project(project_id)
        by_agent_provider_model: dict[tuple[str, str, str], UsageTotals] = {}
        for r in records:
            key = (r.agent_type, r.provider, r.model)
            totals = by_agent_provider_model.setdefault(key, UsageTotals())
            totals.api_calls += r.api_calls
            totals.input_tokens += r.input_tokens or 0
            totals.output_tokens += r.output_tokens or 0
            totals.total_tokens += r.total_tokens or 0
            if r.retry_number == 0:
                totals.initial_calls += r.api_calls
            else:
                totals.retry_calls += r.api_calls
        return by_agent_provider_model

    async def total_cost_for_workspace_today(self, workspace_id: str) -> float | None:
        return await self.usage.total_cost_for_workspace_today(workspace_id)

    @staticmethod
    def pricing_configured() -> bool:
        return bool(get_pricing_table())
