"""VALIDATION mode (v0.1.2.1, Issue 1): candidates already exist (from a
prior DISCOVERY task, via the existing Task dependency graph) — Research
gathers candidate-specific evidence against a common requirement set for
every candidate in ONE bounded task. Offline."""
from __future__ import annotations

from app.agents.research import ResearchAgent, _resolve_research_mode
from app.config.settings import Settings
from app.database.models import PermissionLevel
from app.research_intelligence.requirements import CORE_COMPARISON_CATEGORIES
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.tools.research_tools import SearchResult

CANDIDATES_INPUT = [
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
    """A fake ResearchProvider that returns candidate-specific results keyed
    by the exact query string — lets tests deterministically control which
    evidence "belongs" to which candidate's search."""

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


def _by_query_results() -> dict[str, list[SearchResult]]:
    return {
        "Notion template marketplace": [
            SearchResult(
                title="Notion template marketplace pricing",
                url="https://gumroad.com/l/notion-templates",
                snippet="Notion template marketplace pricing plans start at $9 per template on Gumroad.",
            ),
        ],
        "Coda template hub": [
            SearchResult(
                title="Coda template hub demand",
                url="https://www.producthunt.com/posts/coda-templates",
                snippet="Coda template hub shows strong demand and growing traction on Product Hunt.",
            ),
        ],
        "Airtable template pack": [
            SearchResult(
                title="Airtable template pack competitors",
                url="https://www.g2.com/products/airtable-templates",
                snippet="Airtable template pack has several named competitors listed on G2.",
            ),
        ],
    }


def _validation_agent(by_query=None) -> ResearchAgent:
    return ResearchAgent(
        descriptor=_descriptor(),
        provider=_StubModelProvider(),
        research_provider=_PerCandidateResearchProvider(by_query or _by_query_results()),
    )


def test_validation_mode_resolved_from_candidates_key_without_explicit_tag():
    input_data = {"candidates": CANDIDATES_INPUT}
    assert _resolve_research_mode(input_data) == "VALIDATION"


# --- 5. Validation generates the same common requirement categories for ----
#        all three candidates


async def test_validation_generates_common_requirement_categories_for_all_candidates():
    agent = _validation_agent()
    result = await agent.run(
        title="Validate discovered candidates",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT},
        context={},
    )
    assert result.research_mode == "VALIDATION"
    assert len(result.candidates) == 3

    categories_by_candidate: dict[str, set] = {}
    for req in result.requirements:
        categories_by_candidate.setdefault(req.candidate_id, set()).add(req.category)

    assert len(categories_by_candidate) == 3
    for categories in categories_by_candidate.values():
        assert categories == set(CORE_COMPARISON_CATEGORIES)


async def test_validation_requirement_count_bounded_per_candidate():
    agent = _validation_agent()
    result = await agent.run(
        title="Validate discovered candidates",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT},
        context={},
    )
    settings = Settings()
    counts: dict[str, int] = {}
    for req in result.requirements:
        counts[req.candidate_id] = counts.get(req.candidate_id, 0) + 1
    assert all(c <= settings.research_max_requirements_per_candidate for c in counts.values())


# --- 6. Evidence is assigned to the correct candidate -----------------------


async def test_evidence_assigned_to_correct_candidate():
    agent = _validation_agent()
    result = await agent.run(
        title="Validate discovered candidates",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT},
        context={},
    )
    by_candidate = {e.candidate_id: e for e in result.evidence}
    assert "notion-template-marketplace" in by_candidate
    assert "coda-template-hub" in by_candidate
    assert "airtable-template-pack" in by_candidate
    assert "notion" in by_candidate["notion-template-marketplace"].claim.lower()
    assert "coda" in by_candidate["coda-template-hub"].claim.lower()
    assert "airtable" in by_candidate["airtable-template-pack"].claim.lower()


# --- 7. Evidence for Candidate A cannot satisfy Candidate B's requirement --


async def test_candidate_a_evidence_cannot_satisfy_candidate_b_requirement():
    agent = _validation_agent()
    result = await agent.run(
        title="Validate discovered candidates",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT},
        context={},
    )
    # Notion's pricing evidence must not be attributed to Coda or Airtable.
    notion_pricing_evidence = [
        e for e in result.evidence
        if e.candidate_id == "notion-template-marketplace" and e.requirement_category == "pricing"
    ]
    assert notion_pricing_evidence
    for e in result.evidence:
        if e.id in {x.id for x in notion_pricing_evidence}:
            assert e.candidate_id == "notion-template-marketplace"
            assert e.candidate_id != "coda-template-hub"
            assert e.candidate_id != "airtable-template-pack"


# --- 16. No unbounded candidate/task creation -------------------------------


async def test_validation_candidate_count_bounded_even_with_excess_input():
    excess = CANDIDATES_INPUT + [
        {"id": "extra-1", "label": "Extra candidate 1"},
        {"id": "extra-2", "label": "Extra candidate 2"},
    ]
    agent = _validation_agent()
    result = await agent.run(
        title="Validate discovered candidates",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": excess},
        context={},
    )
    assert len(result.candidates) == Settings().research_max_candidates_per_mission


async def test_validation_falls_back_to_general_when_no_candidates_present():
    """Defensive: a VALIDATION-tagged task with an empty candidate list must
    never crash — it degrades to GENERAL rather than doing nothing useful."""
    agent = _validation_agent()
    result = await agent.run(
        title="Validate discovered candidates",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": []},
        context={},
    )
    assert result.research_mode == "GENERAL"
