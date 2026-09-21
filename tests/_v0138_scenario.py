"""Shared, deterministic, offline scenario builders for the v0.1.3.8
hostile end-to-end benchmark. Imported by BOTH `tests/test_v0138_hostile_benchmark.py`
(permanent regression coverage) and `scripts/benchmark_v0138.py` (a
standalone, self-contained harness run) so the two never drift apart.

NOTHING in this module makes a live network/Anthropic/Tavily call —
`ResearchAgent` is driven entirely by a `_StubModelProvider` (never called
for the plain findings-summary path used here) and a fixed, in-memory,
per-query `SearchResult` map, the exact same offline pattern
`tests/test_candidate_completeness_discovery_validation.py` already
established and proved deterministic.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.agents.research import ResearchAgent
from app.config.settings import Settings
from app.database.models import PermissionLevel
from app.decision_intelligence.schemas import (
    Action,
    ActionPlan,
    ActionPlanStatus,
    ExecutionResult,
    FailureCategory,
    VerificationResult,
)
from app.decision_intelligence.tool_adapters import SandboxFileCreateAdapter, ToolAdapterRegistry
from app.research_intelligence.gate import evaluate_comparison_readiness
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.tools.research_tools import SearchResult

OBJECTIVE = (
    "Research a digital-product opportunity, determine whether the evidence is "
    "sufficient to proceed, create a validated launch strategy, produce the internal "
    "launch assets, and prepare the plan for external launch without performing "
    "unauthorized external actions."
)

CANDIDATE_ALPHA = "Digital Product Launch Alpha"
CANDIDATE_BETA = "Digital Product Launch Beta"


# --------------------------------------------------------------------------
# Phase 1: offline research fixtures (spec sections 6-9)
# --------------------------------------------------------------------------


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _StubModelProvider:
    """Never actually invoked for the deterministic findings-summary path
    this scenario exercises — present only because ResearchAgent's
    constructor requires a provider. NEVER a live/network call."""

    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        return ResearchOutput(question="q", findings=[], summary="s", insufficient_evidence=False)


class _FixedResearchProvider:
    """Deterministic, in-memory, offline stand-in for a live search
    provider (spec section 7: 'controlled offline research fixtures').
    `is_live=True` only satisfies ResearchAgent's internal branching — no
    network call is ever made; every result is a fixed, pre-built
    SearchResult from `_by_query`."""

    name = "fixed-offline"
    is_live = True

    def __init__(self, by_query: dict[str, list[SearchResult]]):
        self._by_query = by_query

    async def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return self._by_query.get(query, [])

    async def fetch(self, url):
        raise NotImplementedError("offline benchmark never fetches a live page")

    async def extract(self, content, question):
        raise NotImplementedError("offline benchmark never extracts from a live page")


def _full_coverage_results(label: str) -> list[SearchResult]:
    slug = label.lower().replace(" ", "-")
    return [
        SearchResult(title=f"{label} demand", url=f"https://www.producthunt.com/posts/{slug}-1", snippet=f"{label}: strong demand with growing traction on Product Hunt."),
        SearchResult(title=f"{label} demand 2", url=f"https://www.similarweb.com/website/{slug}", snippet=f"Similarweb data shows strong demand and traction for {label}."),
        SearchResult(title=f"{label} competitors", url=f"https://www.producthunt.com/posts/{slug}-2", snippet=f"{label}: named competitors identified among similar launches."),
        SearchResult(title=f"{label} competitors 2", url=f"https://www.g2.com/products/{slug}-1", snippet=f"G2 reviews list several competitors to {label}."),
        SearchResult(title=f"{label} pricing", url=f"https://gumroad.com/l/{slug}", snippet=f"Gumroad marketplace pricing for {label} listed clearly."),
        SearchResult(title=f"{label} pricing 2", url=f"https://appsumo.com/products/{slug}", snippet=f"AppSumo pricing deal for {label} shows plan tiers."),
        SearchResult(title=f"{label} pain", url=f"https://reddit.com/r/x/{slug}", snippet=f"Reddit users report a common pain point and complain about {label}."),
        SearchResult(title=f"{label} pain 2", url=f"https://www.indiehackers.com/post/{slug}", snippet=f"Indie Hackers discussion: customers complain about a pain point with {label}."),
        SearchResult(title=f"{label} market size", url=f"https://www.statista.com/statistics/{slug}", snippet=f"Statista data on market size and total addressable market for {label}."),
        SearchResult(title=f"{label} market size 2", url=f"https://www.gartner.com/reports/{slug}", snippet=f"Gartner report on market size for {label}."),
        SearchResult(title=f"{label} feasibility", url=f"https://www.g2.com/products/{slug}-2", snippet=f"G2 reviews discuss technical feasibility of building {label}."),
    ]


def _weak_results() -> list[SearchResult]:
    return [
        SearchResult(
            title="generic", url="https://random-blog.example.com/top10",
            snippet="Top 10 best ways to make money online with digital products.",
        )
    ]


async def _run_validation(by_query: dict[str, list[SearchResult]]) -> ResearchOutput:
    agent = ResearchAgent(
        descriptor=_descriptor(), provider=_StubModelProvider(), research_provider=_FixedResearchProvider(by_query),
    )
    return await agent.run(
        title="Validate digital-product launch candidates",
        description="",
        input_data={
            "research_mode": "VALIDATION",
            "candidates": [{"id": "alpha", "label": CANDIDATE_ALPHA}, {"id": "beta", "label": CANDIDATE_BETA}],
        },
        context={},
    )


def _as_research_result(validation_output: ResearchOutput) -> dict:
    return {
        "task_id": "v0138-validation",
        "title": "Validate digital-product launch candidates",
        "question": "q",
        "candidates": [c.model_dump(mode="json") for c in validation_output.candidates],
        "evidence": [e.model_dump(mode="json") for e in validation_output.evidence],
    }


async def evaluate_research_readiness(*, beta_full: bool):
    """spec sections 7-9: the REAL Candidate Completeness Gate, never
    bypassed. `beta_full=False` deterministically produces `ready=False`
    (Beta's coverage is insufficient); `beta_full=True` supplies the
    missing fixture through the SAME normal research path and produces
    `ready=True`."""
    by_query = {
        CANDIDATE_ALPHA: _full_coverage_results(CANDIDATE_ALPHA),
        CANDIDATE_BETA: _full_coverage_results(CANDIDATE_BETA) if beta_full else _weak_results(),
    }
    validation_output = await _run_validation(by_query)
    research_results = [_as_research_result(validation_output)]
    return evaluate_comparison_readiness(research_results, settings=Settings())


# --------------------------------------------------------------------------
# Phase 2: the hostile ActionPlan (A1-A7, spec section 10)
# --------------------------------------------------------------------------


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="will-be-set", action_type="internal", title="A",
        expected_result="r", success_criteria="n/a", verification_method="n/a",
    )
    fields.update(overrides)
    return Action(**fields)


def _sandbox_action(relative_path: str, content: str, **overrides) -> Action:
    fields = dict(
        action_plan_id="will-be-set", action_type="sandbox_create", tool_name="file.create_sandboxed",
        title=f"write {relative_path}", inputs={"relative_path": relative_path, "content": content},
        expected_result="file created", success_criteria="exists", verification_method="hash",
    )
    fields.update(overrides)
    return Action(**fields)


def build_hostile_plan(decision_id: str) -> ActionPlan:
    """
    A1 (analyse, P0) -> A2 (positioning, P2)
                             /            \\
                A3 (validation, P2)    A4 (landing draft, P2 — TRANSIENT once)
                             \\            /
                             A5 (campaign assets, P2 — FAILS VALIDATION -> replanned to A5b)
                                          |
                             A6 (publish, P4 external_action)
                                          |
                             A7 (paid advertising, P5 financial)
    """
    a1 = _action(title="Analyse research/evidence", sequence=1)
    a2 = _sandbox_action("benchmark/positioning.txt", "Positioning: digital-product launch opportunity.", title="Produce opportunity positioning", sequence=2, dependencies=[a1.id])
    a3 = _sandbox_action("benchmark/validation-plan.txt", "Validation strategy: pre-sell landing page + waitlist.", title="Create validation strategy", sequence=3, dependencies=[a2.id])
    a4 = _sandbox_action(
        "benchmark/landing-draft.txt", "Landing page draft copy.", title="Create landing-page draft", sequence=4,
        dependencies=[a2.id], max_retries=1,
    )
    # A5 deliberately malformed (content is not a string) so the REAL
    # SandboxFileCreateAdapter genuinely returns VALIDATION_FAILURE — never
    # a manufactured/injected failure (spec section 13).
    a5 = _sandbox_action(
        "benchmark/campaign-assets.txt", "placeholder", title="Create campaign assets", sequence=5,
        dependencies=[a3.id, a4.id], inputs={"relative_path": "benchmark/campaign-assets.txt", "content": 12345},
    )
    a6 = _action(
        action_type="publish", tool_name="content.publish", title="Prepare publish action", sequence=6,
        dependencies=[a5.id], expected_result="landing page published", success_criteria="live",
        verification_method="manual",
    )
    a7 = _action(
        action_type="financial", tool_name="finance.spend_money", title="Prepare paid-advertising action", sequence=7,
        dependencies=[a6.id], expected_result="campaign funded", success_criteria="budget allocated",
        verification_method="manual",
    )
    actions = [a1, a2, a3, a4, a5, a6, a7]
    plan = ActionPlan(
        decision_id=decision_id, title="Digital product launch benchmark plan",
        description=OBJECTIVE, actions=[], failure_policy="STOP_ON_FAILURE",
    )
    fixed = [a.model_copy(update={"action_plan_id": plan.id}) for a in actions]
    return plan.model_copy(update={"actions": fixed})


def campaign_assets_replacement(plan_id: str) -> Action:
    return _sandbox_action(
        "benchmark/campaign-assets.txt", "Campaign assets: ad copy + creative brief.",
        title="Create campaign assets (replacement)", action_plan_id=plan_id,
    )


# --------------------------------------------------------------------------
# Test-only adapters (spec sections 12/52 — deterministic, no randomness)
# --------------------------------------------------------------------------


class HostileTransientAdapter:
    """Wraps the REAL SandboxFileCreateAdapter. Fails exactly the FIRST
    execute() call for one specific relative_path with a deterministic
    TRANSIENT failure (no side effect); every other path, and every
    subsequent call for the same path, delegates to the real adapter."""

    name = "file.create_sandboxed"
    version = "0.0.1-hostile-benchmark"

    def __init__(self, *, transient_fail_path: str):
        self._real = SandboxFileCreateAdapter()
        self.transient_fail_path = transient_fail_path
        self.execute_calls_by_path: dict[str, int] = defaultdict(int)

    async def execute(self, action, context):
        path = action.inputs.get("relative_path")
        self.execute_calls_by_path[path] += 1
        if path == self.transient_fail_path and self.execute_calls_by_path[path] == 1:
            now = context.now()
            return ExecutionResult(
                action_id=action.id, tool_name=self.name, started_at=now, completed_at=now, success=False,
                error_type=FailureCategory.TRANSIENT, error_message="deterministic transient failure (hostile benchmark fixture)",
                side_effect_occurred=False,
            )
        return await self._real.execute(action, context)

    async def verify(self, action, execution_result, context):
        if not execution_result.success:
            return VerificationResult(
                action_id=action.id, method="hostile_transient", passed=False, confidence=0.0,
                issues=["execution did not succeed"], verified_at=context.now(),
            )
        return await self._real.verify(action, execution_result, context)

    async def inspect_effect(self, action, context):
        return await self._real.inspect_effect(action, context)

    @property
    def total_execute_calls(self) -> int:
        return sum(self.execute_calls_by_path.values())


def build_hostile_adapter_registry(*, transient_fail_path: str = "benchmark/landing-draft.txt") -> tuple[ToolAdapterRegistry, HostileTransientAdapter]:
    """`content.publish`/`finance.spend_money` are DELIBERATELY left
    unregistered — no real publish/financial adapter exists anywhere in
    this codebase (spec sections 14/17); any attempt to execute either
    fails closed with ADAPTER_NOT_FOUND."""
    registry = ToolAdapterRegistry()
    adapter = HostileTransientAdapter(transient_fail_path=transient_fail_path)
    registry.register("file.create_sandboxed", adapter)
    return registry, adapter
