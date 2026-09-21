"""v0.1.2.7: candidate/query identity integrity + gap/query identity, using
the exact three benchmark candidates from the checkpoint:

1. CMS Template & Component Marketplace
2. Digital Product Creation & Distribution Course
3. Headless CMS + E-commerce Integration Suite

Root cause (Phase 1/2/7): app/agents/research.py::_build_queries used to
return a bare list[str] — once a query became plain text, WHICH candidate/
requirement it was built for was discarded. Every VALIDATION EvidenceItem's
candidate_id was then decided from scratch by _tag_validation_evidence's
cross-candidate keyword-overlap scoring, with no memory of which candidate's
own query actually retrieved it. A search result that happens to read more
like a DIFFERENT candidate's business (an imperfect/adjacent real-world
search hit) would outscore the correct candidate and get reassigned to the
wrong candidate_id — exactly the corruption the live benchmark showed
(a "CMS Template Component Marketplace" query's own evidence tagged
candidate_id=headless-cms-e-commerce-integration-suite).

Fix: app/agents/research.py::QueryTarget/_build_query_targets carries
candidate_id/requirement_category alongside the query TEXT from
construction through to EvidenceItem creation (_gather_evidence), and
_tag_validation_evidence now treats a pre-stamped candidate_id as EXPLICIT
PROVENANCE that wins outright — never up for cross-candidate reassignment.

Offline only — fake providers, no network call.
"""
from __future__ import annotations

import pytest

from app.agents.research import (
    ResearchAgent,
    _build_query_targets,
    _tag_validation_evidence,
)
from app.database.models import PermissionLevel
from app.research_intelligence.query_builder import build_query_plan
from app.research_intelligence.requirements import generate_requirement_set
from app.research_intelligence.schemas import ResearchCandidate
from app.schemas.agents import AgentDescriptor, ResearchOutput
from app.schemas.evidence import EvidenceItem
from app.tools.research_tools import SearchResult

CMS_MARKETPLACE = ("cms-template-component-marketplace", "CMS Template & Component Marketplace")
DIGITAL_COURSE = ("digital-product-creation-distribution-course", "Digital Product Creation & Distribution Course")
HEADLESS_CMS = ("headless-cms-e-commerce-integration-suite", "Headless CMS + E-commerce Integration Suite")
CANDIDATES = [CMS_MARKETPLACE, DIGITAL_COURSE, HEADLESS_CMS]

CANDIDATES_INPUT = [{"id": cid, "label": label} for cid, label in CANDIDATES]


def _descriptor() -> AgentDescriptor:
    return AgentDescriptor(
        name="research", role="research", description="research", capabilities=[],
        permissions=[PermissionLevel.READ], model="mock-model",
    )


class _StubModelProvider:
    name = "stub"

    async def complete_structured(self, *, system_prompt, user_prompt, output_schema, model):
        return ResearchOutput(question="q", findings=[], summary="s", insufficient_evidence=False)


class _PerQueryResearchProvider:
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


def _agent(by_query: dict[str, list[SearchResult]]) -> ResearchAgent:
    return ResearchAgent(
        descriptor=_descriptor(), provider=_StubModelProvider(),
        research_provider=_PerQueryResearchProvider(by_query),
    )


# --- Phase 1/6: three candidates generate correctly paired queries ----------


def test_three_candidates_generate_distinct_correctly_paired_query_targets():
    targets = _build_query_targets(
        title="Validate discovered candidates",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT},
    )
    assert len(targets) == 3
    by_id = {t.candidate_id: t for t in targets}
    assert set(by_id) == {cid for cid, _ in CANDIDATES}
    for cid, label in CANDIDATES:
        query = by_id[cid].query.lower()
        # No orchestration vocabulary, and never another candidate's id.
        assert "candidate" not in query and "opportunit" not in query
    queries = {t.query for t in targets}
    assert len(queries) == 3, "each candidate's initial query must be distinct"


def test_no_candidate_query_target_carries_a_different_candidates_id():
    targets = _build_query_targets(
        title="Validate discovered candidates",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT},
    )
    label_by_query = {t.query: t.candidate_id for t in targets}
    for t in targets:
        # The query text is built ONLY from this target's own candidate_id's
        # label — a naive substring check that another candidate's own
        # normalized-id fragments never leaked in.
        for other_cid, other_label in CANDIDATES:
            if other_cid == t.candidate_id:
                continue
            assert other_cid not in (t.query.lower().replace(" ", "-"))


# --- Phase 1/2/7: query -> EvidenceItem identity survives adversarial ------
#     content that reads more like a DIFFERENT candidate


def _query_for(label: str) -> str:
    """The exact query text _build_query_targets builds for a candidate's
    initial (no-gap) attempt — computed via the real query_builder machinery
    rather than hand-typed, so this test never drifts from the actual
    normalization rules (e.g. "+"/"&" handling)."""
    from app.research_intelligence.query_builder import build_external_research_query

    return build_external_research_query(candidate_label=label)


def _adversarial_by_query() -> dict[str, list[SearchResult]]:
    """Each candidate's OWN query returns a search result whose content is
    deliberately written to read like ANOTHER candidate's business — the
    exact shape of a real, imperfect Tavily hit. Proves identity is decided
    by which query retrieved the item, not by which candidate's keywords
    the returned text happens to match best."""
    return {
        _query_for(CMS_MARKETPLACE[1]): [
            SearchResult(
                title="Headless CMS e-commerce integration review",
                url="https://example.com/cms-marketplace-result",
                snippet=(
                    "Headless CMS e-commerce integration suite pricing plans and competitors "
                    "listed for major platforms."
                ),
            ),
        ],
        _query_for(DIGITAL_COURSE[1]): [
            SearchResult(
                title="CMS template marketplace listing",
                url="https://example.com/digital-course-result",
                snippet="CMS template component marketplace competitors and marketplace fees compared.",
            ),
        ],
        _query_for(HEADLESS_CMS[1]): [
            SearchResult(
                title="Digital product course platform demand",
                url="https://example.com/headless-cms-result",
                snippet="Digital product creation and distribution course demand and sales search trends.",
            ),
        ],
    }


async def test_candidate_a_query_evidence_never_gets_a_different_candidates_id():
    agent = _agent(_adversarial_by_query())
    result = await agent.run(
        title="Validate discovered candidates", description="",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT}, context={},
    )
    by_query_used: dict[str, str | None] = {e.query_used: e.candidate_id for e in result.evidence}
    assert by_query_used[_query_for(CMS_MARKETPLACE[1])] == CMS_MARKETPLACE[0]
    assert by_query_used[_query_for(DIGITAL_COURSE[1])] == DIGITAL_COURSE[0]
    assert by_query_used[_query_for(HEADLESS_CMS[1])] == HEADLESS_CMS[0]


async def test_rejected_evidence_still_preserves_its_originating_candidate_identity():
    """Phase 7: the adversarial items above are expected to be REJECTED
    (their content really is about a different candidate) — but rejection
    must never erase or reassign candidate_id; it must stay the candidate
    whose query actually produced the item."""
    agent = _agent(_adversarial_by_query())
    result = await agent.run(
        title="Validate discovered candidates", description="",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT}, context={},
    )
    cms_item = next(e for e in result.evidence if e.query_used == "CMS Template Component Marketplace")
    assert cms_item.candidate_id == CMS_MARKETPLACE[0]
    assert cms_item.relevance_label == "REJECT"
    assert cms_item.rejection_reason == "WRONG_CANDIDATE"
    assert cms_item.admission_status == "REJECTED"


async def test_admitted_evidence_preserves_its_originating_candidate_target():
    """A search result that DOES genuinely match the candidate its own
    query targeted must be admitted under that SAME candidate_id."""

    def _on_topic_by_query() -> dict[str, list[SearchResult]]:
        return {
            "CMS Template Component Marketplace": [
                SearchResult(
                    title="CMS template marketplace competitors",
                    url="https://example.com/cms-ontopic",
                    snippet="CMS template component marketplace has several named competitors and marketplace fees.",
                ),
            ],
        }

    agent = _agent(_on_topic_by_query())
    result = await agent.run(
        title="Validate discovered candidates", description="",
        input_data={"research_mode": "VALIDATION", "candidates": CANDIDATES_INPUT}, context={},
    )
    item = next(e for e in result.evidence if e.query_used == "CMS Template Component Marketplace")
    assert item.candidate_id == CMS_MARKETPLACE[0]
    assert item.admission_status == "ACCEPTED"


# --- Unit-level: _tag_validation_evidence pinning ----------------------------


def test_tag_validation_evidence_pins_explicit_candidate_id_over_semantic_reassignment():
    from app.config.settings import Settings

    settings = Settings()
    candidates = [ResearchCandidate(id=cid, label=label) for cid, label in CANDIDATES]
    reqs_by_candidate = {
        c.id: generate_requirement_set(candidate_id=c.id, candidate_label=c.label, settings=settings)
        for c in candidates
    }
    item = EvidenceItem(
        claim="Headless CMS e-commerce integration suite pricing plans and competitors listed.",
        source_url="https://example.com/headless-cms-review",
        excerpt="Headless CMS e-commerce integration suite pricing plans and competitors listed for major platforms.",
        query_used="CMS Template Component Marketplace",
        research_mode="VALIDATION",
        candidate_id=CMS_MARKETPLACE[0],  # stamped by _gather_evidence from explicit query provenance
    )
    tagged = _tag_validation_evidence([item], candidates, reqs_by_candidate)
    assert tagged[0].candidate_id == CMS_MARKETPLACE[0]
    assert tagged[0].candidate_id != HEADLESS_CMS[0]


def test_tag_validation_evidence_still_uses_semantic_match_when_no_explicit_target():
    """Untargeted evidence (candidate_id unset — e.g. a broad GENERAL-shaped
    search folded into validation) still falls through to the pre-existing
    best-match behavior; this is the ONLY case semantic reassignment may
    ever decide identity."""
    from app.config.settings import Settings

    settings = Settings()
    candidates = [ResearchCandidate(id=cid, label=label) for cid, label in CANDIDATES]
    reqs_by_candidate = {
        c.id: generate_requirement_set(candidate_id=c.id, candidate_label=c.label, settings=settings)
        for c in candidates
    }
    item = EvidenceItem(
        claim="Headless CMS e-commerce integration suite pricing plans and competitors listed.",
        source_url="https://example.com/headless-cms-review",
        excerpt="Headless CMS e-commerce integration suite pricing plans and competitors listed for major platforms.",
        research_mode="VALIDATION",
        candidate_id=None,
    )
    tagged = _tag_validation_evidence([item], candidates, reqs_by_candidate)
    assert tagged[0].candidate_id == HEADLESS_CMS[0]


# --- Phase 5/11: gap/query identity across all 8 requirement categories -----

_CATEGORIES_UNDER_TEST = (
    "market_size", "growth", "competition", "pricing", "demand",
    "customer_pain", "feasibility", "unit_economics",
)


@pytest.mark.parametrize("category", _CATEGORIES_UNDER_TEST)
def test_candidate_scoped_query_plan_matches_canonical_requirement_for_every_category(category):
    from app.config.settings import Settings
    from app.research_intelligence.schemas import ResearchRequirement

    settings = Settings()
    cid, label = CMS_MARKETPLACE
    requirement = ResearchRequirement(candidate_id=cid, category=category, question=f"Q about {category}")
    plan = build_query_plan(
        candidate_id=cid, candidate_label=label, requirement=requirement,
        max_results=settings.research_max_results,
    )
    assert plan.candidate_id == cid
    assert plan.requirement_category == category
    lowered = plan.query.lower()
    assert "candidate" not in lowered and "opportunit" not in lowered
    assert "validate" not in lowered and "research task" not in lowered
    for other_cid, _ in CANDIDATES:
        if other_cid != cid:
            assert other_cid not in lowered.replace(" ", "-")


# --- Phase 4: malformed candidate-scoped gaps are rejected, never a --------
#     generic fallback, and never consume a retry slot


def test_malformed_candidate_scoped_gap_produces_no_query_and_consumes_no_slot():
    """A gap that CLAIMS a candidate_id but that id no longer resolves
    (stale/dropped candidate) must be skipped entirely — never fall back to
    its own suggested_query (which could carry orchestration wording or a
    stale target) and never eat one of the bounded retry slots that a
    genuinely resolvable gap could have used instead."""
    input_data = {
        "candidates": CANDIDATES_INPUT,
        "evidence_gaps": [
            {
                "candidate_id": "some-dropped-candidate-id", "requirement_category": "pricing",
                "gap_type": "pricing", "importance": 5, "resolved": False,
                "suggested_query": "Validate and compare candidate opportunities pricing",
            },
            {
                "candidate_id": CMS_MARKETPLACE[0], "requirement_category": "demand", "gap_type": "demand",
                "importance": 3, "resolved": False, "suggested_query": "irrelevant stale text",
            },
        ],
    }
    targets = _build_query_targets(title="Validate discovered candidates", input_data=input_data)
    assert len(targets) == 1
    assert targets[0].candidate_id == CMS_MARKETPLACE[0]
    assert targets[0].requirement_category == "demand"
    for t in targets:
        assert "some-dropped-candidate-id" not in t.query.lower().replace(" ", "-")


def test_candidate_scoped_gap_missing_requirement_category_is_rejected_not_generic():
    """A gap with a real, resolvable candidate_id but NO requirement
    category is still malformed for query-construction purposes — it must
    not silently execute a generic fallback query under that candidate's
    identity."""
    input_data = {
        "candidates": CANDIDATES_INPUT,
        "evidence_gaps": [
            {
                "candidate_id": CMS_MARKETPLACE[0], "requirement_category": None, "gap_type": "other",
                "importance": 5, "resolved": False, "suggested_query": "some generic fallback text",
            },
        ],
    }
    targets = _build_query_targets(title="Validate discovered candidates", input_data=input_data)
    # No valid candidate-scoped target and no genuinely candidate-agnostic
    # gap either -> falls back to the broad title query, never the
    # malformed gap's own suggested_query.
    assert len(targets) == 1
    assert targets[0].candidate_id is None
    assert targets[0].query != "some generic fallback text"


def test_freed_slot_from_malformed_gap_goes_to_a_lower_ranked_valid_gap():
    """The malformed gap must not consume a slot even when it ranks ABOVE
    other valid gaps by importance — a lower-importance but resolvable gap
    must still get its query built once the malformed one is skipped."""
    from app.config.settings import Settings

    max_queries = Settings().research_max_gap_queries_per_attempt
    gaps = [
        {
            "candidate_id": "unknown-id", "requirement_category": "pricing", "gap_type": "pricing",
            "importance": 5, "resolved": False, "suggested_query": "x",
        },
    ]
    # Fill the rest with genuinely valid, lower-importance candidate-scoped gaps.
    for i, (cid, _label) in enumerate(CANDIDATES):
        gaps.append(
            {
                "candidate_id": cid, "requirement_category": "demand", "gap_type": "demand",
                "importance": 1, "resolved": False, "suggested_query": "x",
            }
        )
    input_data = {"candidates": CANDIDATES_INPUT, "evidence_gaps": gaps}
    targets = _build_query_targets(title="Validate discovered candidates", input_data=input_data)
    assert len(targets) == min(max_queries, 3)
    assert all(t.candidate_id in {cid for cid, _ in CANDIDATES} for t in targets)
