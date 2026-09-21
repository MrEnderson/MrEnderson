"""End-to-end Candidate Completeness Gate over the DISCOVERY -> VALIDATION
shape (v0.1.2.1): a single VALIDATION research task's output carries
multiple candidates via its own `candidates` field, with evidence tagged
per candidate/requirement_category. Offline."""
from __future__ import annotations

from app.agents.research import ResearchAgent
from app.config.settings import Settings
from app.database.models import PermissionLevel
from app.research_intelligence.gate import evaluate_comparison_readiness
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.tools.research_tools import SearchResult

_CANDIDATES = [
    {"id": "notion-template-marketplace", "label": "Notion template marketplace"},
    {"id": "coda-template-hub", "label": "Coda template hub"},
    {"id": "airtable-template-pack", "label": "Airtable template pack"},
]


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _StubModelProvider:
    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        return ResearchOutput(question="q", findings=[], summary="s", insufficient_evidence=False)


class _PerCandidateResearchProvider:
    name = "fake"
    is_live = True

    def __init__(self, by_query: dict[str, list[SearchResult]]):
        self._by_query = by_query

    async def search(self, query, *, max_results=5):
        return self._by_query.get(query, [])

    async def fetch(self, url):
        raise NotImplementedError

    async def extract(self, content, question):
        raise NotImplementedError


def _full_coverage_results(label: str) -> list[SearchResult]:
    # Same-domain-per-category on purpose (to exercise source-role
    # suitability), but the PATH always embeds the candidate's own slug —
    # app/agents/research.py::_gather_evidence dedups by canonical URL
    # across every query in one attempt, so reusing an identical URL across
    # different candidates would silently collapse them into one item.
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
        descriptor=_descriptor(), provider=_StubModelProvider(),
        research_provider=_PerCandidateResearchProvider(by_query),
    )
    return await agent.run(
        title="Validate discovered candidates",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": _CANDIDATES},
        context={},
    )


def _as_research_result(validation_output: ResearchOutput) -> dict:
    return {
        "task_id": "validation-1",
        "title": "Validate discovered candidates",
        "question": "q",
        "candidates": [c.model_dump(mode="json") for c in validation_output.candidates],
        "evidence": [e.model_dump(mode="json") for e in validation_output.evidence],
    }


# --- 12. One incomplete candidate makes comparison_ready=false -------------


async def test_one_incomplete_candidate_blocks_readiness():
    by_query = {
        "Notion template marketplace": _full_coverage_results("Notion template marketplace"),
        "Coda template hub": _full_coverage_results("Coda template hub"),
        "Airtable template pack": _weak_results(),
    }
    validation_output = await _run_validation(by_query)
    research_results = [_as_research_result(validation_output)]
    readiness = evaluate_comparison_readiness(research_results, settings=Settings())
    assert readiness.ready is False
    statuses = {s.candidate_label: s.ready_for_comparison for s in readiness.candidate_statuses}
    assert statuses["Notion template marketplace"] is True
    assert statuses["Coda template hub"] is True
    assert statuses["Airtable template pack"] is False


# --- 13. Three sufficiently validated candidates make comparison_ready=true


async def test_three_sufficiently_validated_candidates_are_ready():
    by_query = {
        "Notion template marketplace": _full_coverage_results("Notion template marketplace"),
        "Coda template hub": _full_coverage_results("Coda template hub"),
        "Airtable template pack": _full_coverage_results("Airtable template pack"),
    }
    validation_output = await _run_validation(by_query)
    research_results = [_as_research_result(validation_output)]
    readiness = evaluate_comparison_readiness(research_results, settings=Settings())
    assert readiness.ready is True
    assert len(readiness.candidate_statuses) == 3
    assert all(s.ready_for_comparison for s in readiness.candidate_statuses)
