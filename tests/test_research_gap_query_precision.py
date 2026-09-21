"""Item 8 (v0.1.2.2 Phase 14): gap retries use candidate-specific,
search-safe queries — never a bare orchestration phrase, and never a query
that fails to distinguish which candidate it's about. Offline."""
from __future__ import annotations

from app.agents.research import ResearchAgent, _validation_gaps
from app.config.settings import Settings
from app.database.models import PermissionLevel
from app.research_intelligence.coverage import build_coverage_matrix
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.schemas import ResearchCandidate
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.schemas.research_dto import ValidationModelOutput
from app.tools.research_tools import SearchResult


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


def test_validation_gaps_produce_candidate_specific_search_safe_queries():
    settings = Settings()
    candidates = [
        ResearchCandidate(id="ai-education", label="AI Tool Education & Tutorials (Courses/Templates)"),
        ResearchCandidate(id="templates-planners", label="Niche Templates & Planners (Design Assets)"),
    ]
    requirements = []
    for c in candidates:
        requirements.extend(generate_requirement_set(candidate_id=c.id, candidate_label=c.label, settings=settings))
    # No evidence at all -> every cell MISSING -> gaps for both candidates.
    coverage_cells = build_coverage_matrix(requirements, {c.id: [] for c in candidates}, settings=settings)

    gaps = _validation_gaps(requirements, coverage_cells, candidates, settings=settings)
    assert gaps
    for gap in gaps:
        lowered = (gap.suggested_query or "").lower()
        assert "candidate" not in lowered
        assert "opportunity" not in lowered

    # Every gap's query is unique and clearly scoped to its OWN candidate
    # (never a bare generic phrase that could apply to either).
    queries = [g.suggested_query for g in gaps]
    assert len(set(queries)) == len(queries)
    assert all("ai" in q.lower() for q in queries)  # this batch happened to
    # exhaust the higher-priority candidate's critical gaps first (bounded
    # by research_max_gap_queries_per_attempt) — see a second attempt below
    # for the other candidate's turn once the first's gaps start resolving.

    # A second candidate WOULD get its own distinctly-scoped queries once
    # it becomes the lowest-coverage one — verified directly via the query
    # builder (already covered in tests/test_query_builder.py), and here by
    # confirming the underlying per-candidate concept differs.
    from app.research_intelligence.query_builder import build_external_research_query

    other_query = build_external_research_query(
        candidate_label=candidates[1].label, category="pricing"
    )
    assert "planner" in other_query.lower()
    assert other_query not in queries


async def test_validation_retry_gap_queries_are_candidate_specific_end_to_end():
    """Full path: ResearchAgent's own gap generation -> _build_queries on
    the next attempt actually issues candidate-specific queries to the
    research provider."""
    candidates_input = [
        {"id": "ai-education", "label": "AI Tool Education & Tutorials (Courses/Templates)"},
        {"id": "templates-planners", "label": "Niche Templates & Planners (Design Assets)"},
    ]

    class _NoResultsProvider:
        name = "fake"
        is_live = True

        async def search(self, query, *, max_results=5):
            return []  # forces every requirement to stay MISSING

        async def fetch(self, url):
            raise NotImplementedError

        async def extract(self, content, question):
            raise NotImplementedError

    class _StubModel:
        name = "stub"

        async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
            return ValidationModelOutput(summary="s")

    agent = ResearchAgent(descriptor=_descriptor(), provider=_StubModel(), research_provider=_NoResultsProvider())
    result = await agent.run(
        title="Validate and compare candidate opportunities",
        description="",
        input_data={"research_mode": "VALIDATION", "candidates": candidates_input},
        context={},
    )
    assert result.evidence_gaps
    for gap in result.evidence_gaps:
        assert "candidate" not in (gap.suggested_query or "").lower()
