"""Phase 15 (v0.1.2.2): deterministic offline benchmark reproducing the
live mission's shape — "Find three potential digital-product
opportunities and recommend the strongest one" — with the same three
candidates. Prints BEFORE/AFTER estimated Research prompt sizes and the
generated external search queries. No network calls; run with
`pytest -s tests/test_research_prompt_benchmark.py` to see the printed
output, or read the assertions for the enforced invariants."""
from __future__ import annotations

import json

from app.agents.research import ResearchAgent
from app.database.models import PermissionLevel
from app.research_intelligence.query_builder import build_external_research_query
from app.schemas.agents import AgentDescriptor
from app.schemas.research_dto import ValidationModelOutput
from app.tools.research_tools import SearchResult

CANDIDATES = [
    {
        "id": "ai-tool-education-tutorials-courses-templates",
        "label": "AI Tool Education & Tutorials (Courses/Templates)",
        "description": "Courses and templates teaching people to use AI tools.",
    },
    {
        "id": "expertise-based-educational-products-ebooks-cohort-courses",
        "label": "Expertise-Based Educational Products (eBooks/Cohort Courses)",
        "description": "Ebooks and cohort-based courses built on niche expertise.",
    },
    {
        "id": "niche-templates-planners-design-assets",
        "label": "Niche Templates & Planners (Design Assets)",
        "description": "Digital planner and template design assets sold on marketplaces.",
    },
]


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _BenchmarkResearchProvider:
    name = "fake"
    is_live = True

    async def search(self, query, *, max_results=5):
        domains = ["producthunt.com", "gumroad.com", "reddit.com", "statista.com", "g2.com"]
        return [
            SearchResult(
                title=f"{query} result {i}",
                url=f"https://www.{d}/item/{abs(hash(query)) % 99999}-{i}",
                snippet=(
                    f"{query}: detailed market commentary about this niche, pricing, "
                    "competitors, demand signals, and community discussion. " * 3
                ),
            )
            for i, d in enumerate(domains[:max_results])
        ]

    async def fetch(self, url):
        return "PAGE EXTRACT CONTENT. " * 800

    async def extract(self, content, question):
        raise NotImplementedError


class _CapturingModel:
    name = "stub"

    def __init__(self):
        self.captured: list[dict] = []

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        self.captured.append({"system": system_prompt, "user": user_prompt})
        return ValidationModelOutput(findings=["f1"], summary="s")


def _naive_before_prompt_chars(evidence_items: list[dict], candidates: list[dict], input_data: dict) -> int:
    """Reconstructs what the PRE-v0.1.2.2 approach would have sent: up to
    15 evidence items (item-count cap only, no total-chars/per-requirement
    budget), each excerpt truncated to 600 chars, PLUS the whole raw
    input_data dict embedded wholesale (which duplicated `candidates` and
    any qa_feedback/evidence_gaps present) — see
    docs/research_intelligence.md, v0.1.2.2 token-efficiency patch notes."""
    selected = evidence_items[:15]
    for item in selected:
        if item.get("excerpt") and len(item["excerpt"]) > 600:
            item = dict(item)
            item["excerpt"] = item["excerpt"][:600] + " [truncated]"
    naive_context = {
        "question": "Validate and compare candidate opportunities",
        "description": "",
        "input_data": input_data,
        "candidates": candidates,
        "evidence": selected,
    }
    return len(json.dumps(naive_context))


async def test_offline_benchmark_before_after_prompt_size_and_queries(capsys):
    provider = _CapturingModel()
    agent = ResearchAgent(descriptor=_descriptor(), provider=provider, research_provider=_BenchmarkResearchProvider())
    input_data = {"research_mode": "VALIDATION", "candidates": CANDIDATES}
    result = await agent.run(
        title="Validate and compare candidate opportunities", description="", input_data=input_data, context={}
    )

    after_chars = len(provider.captured[0]["system"]) + len(provider.captured[0]["user"])

    all_evidence_dicts = [e.model_dump(mode="json") for e in result.evidence]
    before_chars = _naive_before_prompt_chars(all_evidence_dicts, CANDIDATES, input_data) + len(
        provider.captured[0]["system"]
    )

    reduction_pct = 100.0 * (before_chars - after_chars) / before_chars

    print(f"\nBEFORE (naive, pre-v0.1.2.2 shape): {before_chars} chars")
    print(f"AFTER  (Research Context Compactor): {after_chars} chars")
    print(f"REDUCTION: {reduction_pct:.1f}%")

    print("\nGenerated external search queries:")
    for label_key, category in (
        ("AI Tool Education & Tutorials (Courses/Templates)", "pricing"),
        ("AI Tool Education & Tutorials (Courses/Templates)", "competition"),
        ("Niche Templates & Planners (Design Assets)", "pricing"),
        ("Niche Templates & Planners (Design Assets)", "competition"),
        ("Expertise-Based Educational Products (eBooks/Cohort Courses)", "pricing"),
        ("Expertise-Based Educational Products (eBooks/Cohort Courses)", "competition"),
    ):
        query = build_external_research_query(candidate_label=label_key, category=category)
        print(f"  [{category:11s}] {query}")

    assert after_chars < before_chars
    assert reduction_pct > 30.0  # meaningful, measured reduction — not cosmetic
