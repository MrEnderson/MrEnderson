"""v0.1.2.5 Phases 2/3: ResearchQueryPlan + candidate concept
normalization. External validation queries must be built primarily from
CANDIDATE CONCEPT + REQUIREMENT-SPECIFIC INTENT, never from Jarvis's own
task/orchestration wording. Offline — no network call, no LLM call for
concept generation (pure deterministic string manipulation)."""
from __future__ import annotations

from app.research_intelligence.query_builder import build_candidate_concepts, build_query_plan
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.schemas import ResearchQueryPlan
from app.config.settings import Settings

CANDIDATE_LABEL = "AI-Powered Content Creation Tools & Templates"
CANDIDATE_DESCRIPTION = (
    "A marketplace of prompt templates and workflow automation templates for small "
    "business content creation."
)


def _requirement(category: str):
    reqs = generate_requirement_set(candidate_id="c", candidate_label=CANDIDATE_LABEL, settings=Settings())
    return next(r for r in reqs if r.category == category)


# --- 1/2. query plan contains candidate_id / requirement_category ---------


def test_query_plan_contains_candidate_id_and_requirement_category():
    plan = build_query_plan(
        candidate_id="candidate-a", candidate_label=CANDIDATE_LABEL, candidate_description=CANDIDATE_DESCRIPTION,
        requirement=_requirement("pricing"), max_results=5,
    )
    assert isinstance(plan, ResearchQueryPlan)
    assert plan.candidate_id == "candidate-a"
    assert plan.requirement_category == "pricing"
    assert plan.max_results == 5


# --- 3. external query excludes orchestration wording ----------------------


def test_external_query_excludes_orchestration_wording():
    plan = build_query_plan(
        candidate_id="candidate-a", candidate_label="Candidate Opportunity: " + CANDIDATE_LABEL,
        candidate_description=CANDIDATE_DESCRIPTION, requirement=_requirement("pricing"), max_results=5,
    )
    lowered = plan.query.lower()
    for banned in ("candidate", "opportunity", "validation task", "research task", "discovery task"):
        assert banned not in lowered, f"orchestration wording '{banned}' leaked into query: {plan.query!r}"


# --- 4. candidate concept normalization bounded -----------------------------


def test_candidate_concept_normalization_is_bounded():
    concepts = build_candidate_concepts(CANDIDATE_LABEL, CANDIDATE_DESCRIPTION, max_concepts=4)
    assert 1 <= len(concepts) <= 4
    assert all(isinstance(c, str) and c for c in concepts)
    # No duplicates (case-insensitive) — a bounded SET, not a bag.
    assert len({c.lower() for c in concepts}) == len(concepts)
    # Never contains Jarvis's own orchestration vocabulary.
    for concept in concepts:
        assert "candidate" not in concept.lower()
        assert "opportunity" not in concept.lower()


def test_candidate_concept_normalization_never_calls_a_model():
    """Purely deterministic — same input always produces the same output,
    with no provider/model argument anywhere in the call signature."""
    import inspect

    sig = inspect.signature(build_candidate_concepts)
    assert "provider" not in sig.parameters
    assert "model" not in sig.parameters
    first = build_candidate_concepts(CANDIDATE_LABEL, CANDIDATE_DESCRIPTION)
    second = build_candidate_concepts(CANDIDATE_LABEL, CANDIDATE_DESCRIPTION)
    assert first == second


# --- 5-9. category-specific queries -----------------------------------------


def test_pricing_query_is_pricing_specific():
    plan = build_query_plan(
        candidate_id="c", candidate_label=CANDIDATE_LABEL, candidate_description=CANDIDATE_DESCRIPTION,
        requirement=_requirement("pricing"), max_results=5,
    )
    assert "pricing" in plan.query.lower()
    assert plan.search_intent == "pricing"


def test_competition_query_is_competition_specific():
    plan = build_query_plan(
        candidate_id="c", candidate_label=CANDIDATE_LABEL, candidate_description=CANDIDATE_DESCRIPTION,
        requirement=_requirement("competition"), max_results=5,
    )
    assert "competitor" in plan.query.lower()
    assert plan.search_intent == "competition"


def test_demand_query_is_demand_specific():
    plan = build_query_plan(
        candidate_id="c", candidate_label=CANDIDATE_LABEL, candidate_description=CANDIDATE_DESCRIPTION,
        requirement=_requirement("demand"), max_results=5,
    )
    assert "demand" in plan.query.lower()
    assert plan.search_intent == "demand"


def test_market_size_query_is_market_size_specific():
    plan = build_query_plan(
        candidate_id="c", candidate_label=CANDIDATE_LABEL, candidate_description=CANDIDATE_DESCRIPTION,
        requirement=_requirement("market_size"), max_results=5,
    )
    assert "market size" in plan.query.lower()
    assert plan.search_intent == "market_size"


def test_feasibility_query_is_feasibility_specific():
    plan = build_query_plan(
        candidate_id="c", candidate_label=CANDIDATE_LABEL, candidate_description=CANDIDATE_DESCRIPTION,
        requirement=_requirement("feasibility"), max_results=5,
    )
    assert plan.search_intent == "feasibility"
    # feasibility's template talks about setup/requirements, not pricing/competitors.
    assert "pricing" not in plan.query.lower()
    assert "competitor" not in plan.query.lower()


# --- Phase 4: preferred source roles are ranking guidance, never evidence --


def test_preferred_source_roles_carried_but_never_fabricate_evidence():
    plan = build_query_plan(
        candidate_id="c", candidate_label=CANDIDATE_LABEL, candidate_description=CANDIDATE_DESCRIPTION,
        requirement=_requirement("pricing"), max_results=5,
    )
    assert plan.preferred_source_roles  # pricing has a real preferred-role list
    assert all(isinstance(r, str) for r in plan.preferred_source_roles)
    # A ResearchQueryPlan is pure metadata for search/ranking — it has no
    # field that could carry a fabricated claim or evidence item at all.
    assert not hasattr(plan, "evidence")
    assert not hasattr(plan, "claim")
