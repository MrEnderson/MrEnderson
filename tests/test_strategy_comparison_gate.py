"""Strategy precondition (Phase 11): Strategy must not manufacture a winner
when candidates haven't been researched to a comparable minimum standard.
Deterministic, offline — uses the MockProvider so no live API key is
required (see tests/conftest.py)."""
from __future__ import annotations

import uuid

from app.research_intelligence.gate import evaluate_comparison_readiness
from app.config.settings import Settings


def _item(url: str, claim: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "claim": claim,
        "source_title": claim[:60],
        "source_url": url,
        "excerpt": claim,
    }


def _full_coverage_evidence(label: str) -> list[dict]:
    return [
        _item("https://www.producthunt.com/posts/x", f"{label}: strong demand with growing traction on Product Hunt."),
        _item("https://www.similarweb.com/website/x", f"Similarweb traffic data shows strong demand and traction for {label}."),
        _item("https://www.producthunt.com/posts/y", f"{label}: named competitors identified among similar launches."),
        _item("https://www.g2.com/products/x", f"G2 reviews list several competitors to {label}."),
        _item("https://gumroad.com/l/x", f"Gumroad marketplace pricing for {label} listed clearly."),
        _item("https://appsumo.com/products/x", f"AppSumo pricing deal for {label} shows plan tiers."),
        _item("https://reddit.com/r/x/comments/1", f"Reddit users report a common pain point and complain about {label}."),
        _item("https://www.indiehackers.com/post/1", f"Indie Hackers discussion: customers complain about a pain point with {label}."),
        _item("https://www.statista.com/statistics/x", f"Statista data on market size and total addressable market for {label}."),
        _item("https://www.gartner.com/reports/x", f"Gartner report on market size for {label}."),
        _item("https://www.g2.com/products/y", f"G2 reviews discuss technical feasibility of building {label}."),
    ]


def _weak_evidence() -> list[dict]:
    return [
        _item("https://random-blog.example.com/top10", "Top 10 best ways to make money online with digital products.")
    ]


def _research_result(title: str, evidence: list[dict]) -> dict:
    return {
        "task_id": title,
        "title": title,
        "agent_type": "research",
        "question": title,
        "summary": "s",
        "insufficient_evidence": False,
        "findings": [],
        "assumptions": [],
        "open_questions": [],
        "evidence_gaps": [],
        "evidence": evidence,
    }


async def test_strategy_cannot_rank_when_comparison_not_ready(registry, provider):
    research_results = [
        _research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace")),
        _research_result("Coda template hub", _weak_evidence()),
    ]
    agent = registry.create("strategy", provider=provider)
    result = await agent.run(
        title="Recommend the strongest opportunity",
        description="",
        input_data={"research_results": research_results},
        context={},
    )
    assert result.comparison_ready is False
    assert result.recommendation.upper().startswith("DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE")
    assert "MISSING INFORMATION" in result.recommendation
    assert "NEXT VALIDATION" in result.recommendation
    assert result.missing_requirements


async def test_strategy_may_rank_when_comparison_ready(registry, provider):
    research_results = [
        _research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace")),
        _research_result("Coda template hub", _full_coverage_evidence("Coda template hub")),
    ]
    agent = registry.create("strategy", provider=provider)
    result = await agent.run(
        title="Recommend the strongest opportunity",
        description="",
        input_data={"research_results": research_results},
        context={},
    )
    assert result.comparison_ready is True
    assert not result.recommendation.upper().startswith("DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE")


async def test_single_candidate_research_task_is_never_gated(registry, provider):
    """A single research task isn't a comparison objective — nothing to gate."""
    research_results = [_research_result("Notion template marketplace", _weak_evidence())]
    agent = registry.create("strategy", provider=provider)
    result = await agent.run(
        title="Assess this opportunity", description="", input_data={"research_results": research_results}, context={}
    )
    assert result.comparison_ready is True


async def test_valid_evidence_ids_preserved_regardless_of_gate_outcome(registry, provider):
    research_results = [
        _research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace")),
        _research_result("Coda template hub", _weak_evidence()),
    ]
    agent = registry.create("strategy", provider=provider)
    result = await agent.run(
        title="Recommend the strongest opportunity",
        description="",
        input_data={"research_results": research_results},
        context={},
    )
    # The MockProvider's evidence_used citations (if any) must still only
    # ever reference real evidence ids — the gate rewrites `recommendation`,
    # never `evidence_used`.
    all_ids = {e["id"] for r in research_results for e in r["evidence"]}
    assert set(result.evidence_used).issubset(all_ids)


def test_readiness_recomputation_is_deterministic():
    research_results = [
        _research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace")),
        _research_result("Coda template hub", _weak_evidence()),
    ]
    settings = Settings()
    first = evaluate_comparison_readiness(research_results, settings=settings)
    second = evaluate_comparison_readiness(research_results, settings=settings)
    assert first.ready == second.ready
    assert first.missing_requirements == second.missing_requirements
