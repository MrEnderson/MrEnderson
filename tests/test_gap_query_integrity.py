"""v0.1.2.6 Phase 6: gap query integrity. The live v0.1.2.5 benchmark
showed a retry firing a generic, orchestration-flavored query even though
its EvidenceGap carried a real candidate_id/requirement_category:

    candidate_id: ai-powered-content-personalization-platform-for-e-commerce
    requirement_category: market_size
    query: "Validate and compare candidate opportunities market size"

Root cause: app/security/evidence_qa.py's own generic, candidate-agnostic
gap detector produces a gap for the SAME gap_type a candidate-scoped
VALIDATION gap already covers, built from the raw task title. After
v0.1.2.5's (candidate_id, gap_type)-keyed _merge_gaps fix, both gaps now
survive independently in accumulated_gaps, and app/agents/research.py::
_build_queries used to trust whichever gap's own `suggested_query` string
it found — including the generic one, even when a real candidate_id was
present on ANOTHER gap entirely, or (per the exact live bug) even on the
SAME gap object if it had been built from the wrong source.

Fixed by app/agents/research.py::_query_for_gap: whenever a gap carries
BOTH candidate_id and requirement_category, the external query is ALWAYS
rebuilt deterministically from candidate concept + requirement-specific
intent — the gap's own suggested_query is audit metadata only in that
case, never executed. Offline — no network call.
"""
from __future__ import annotations

from app.agents.research import _build_queries, _query_for_gap, _candidate_lookup

ECOMMERCE_CANDIDATE_ID = "ai-powered-content-personalization-platform-for-e-commerce"
ECOMMERCE_CANDIDATE_LABEL = "AI-Powered Content Personalization Platform for E-commerce"

BLUE_COLLAR_CANDIDATE_ID = "niche-video-course-marketplace-for-blue-collar-skills"
BLUE_COLLAR_CANDIDATE_LABEL = "Niche Video Course Marketplace for Blue-Collar Skills"

_ORCHESTRATION_MARKERS = (
    "validate and compare candidate opportunities",
    "candidate opportunities",
    "validation task",
    "compare candidates",
    "research task",
)


def _assert_query_is_clean(query: str, *, must_contain: tuple[str, ...] = ()) -> None:
    lowered = query.lower()
    for marker in _ORCHESTRATION_MARKERS:
        assert marker not in lowered, f"orchestration wording {marker!r} leaked into query: {query!r}"
    for token in must_contain:
        assert token.lower() in lowered, f"expected {token!r} in query, got: {query!r}"


# --- 14. exact e-commerce market-size live regression -----------------------


def test_ecommerce_market_size_gap_never_executes_the_generic_suggested_query():
    """Reproduces the exact live bug: a gap carrying a real candidate_id
    and requirement_category, but a generic (evidence_qa.py-style)
    suggested_query — the query actually issued must be rebuilt, not the
    stored generic string."""
    gap = {
        "candidate_id": ECOMMERCE_CANDIDATE_ID,
        "requirement_category": "market_size",
        "gap_type": "market_size",
        "importance": 3,
        "claim_or_question": "Missing market_size evidence",
        # The exact generic text the live benchmark showed being executed:
        "suggested_query": "Validate and compare candidate opportunities market size",
    }
    candidates_by_id = _candidate_lookup(
        [{"id": ECOMMERCE_CANDIDATE_ID, "label": ECOMMERCE_CANDIDATE_LABEL, "description": ""}]
    )
    query = _query_for_gap(gap, title="Validate and compare candidate opportunities", candidates_by_id=candidates_by_id)
    _assert_query_is_clean(query, must_contain=("market size",))
    assert query != gap["suggested_query"]


def test_ecommerce_market_size_via_build_queries_end_to_end():
    input_data = {
        "candidates": [{"id": ECOMMERCE_CANDIDATE_ID, "label": ECOMMERCE_CANDIDATE_LABEL, "description": ""}],
        "evidence_gaps": [
            {
                "candidate_id": ECOMMERCE_CANDIDATE_ID,
                "requirement_category": "market_size",
                "gap_type": "market_size",
                "importance": 5,
                "resolved": False,
                "suggested_query": "Validate and compare candidate opportunities market size",
            }
        ],
    }
    queries = _build_queries(title="Validate and compare candidate opportunities", input_data=input_data)
    assert len(queries) == 1
    _assert_query_is_clean(queries[0], must_contain=("market size",))


# --- 15. exact blue-collar growth/demand live regression --------------------


def test_blue_collar_courses_gap_never_executes_the_generic_suggested_query():
    gap = {
        "candidate_id": BLUE_COLLAR_CANDIDATE_ID,
        "requirement_category": "demand",
        "gap_type": "demand",
        "importance": 4,
        "claim_or_question": "Missing demand evidence",
        # The exact live example used "growth rate" phrasing; demand is
        # used here since generate_requirement_set's CORE_COMPARISON_CATEGORIES
        # includes demand, not growth (growth is not a core comparison
        # category — see app/research_intelligence/requirements.py).
        "suggested_query": "Validate and compare candidate opportunities growth rate",
    }
    candidates_by_id = _candidate_lookup(
        [{"id": BLUE_COLLAR_CANDIDATE_ID, "label": BLUE_COLLAR_CANDIDATE_LABEL, "description": ""}]
    )
    query = _query_for_gap(gap, title="Validate and compare candidate opportunities", candidates_by_id=candidates_by_id)
    _assert_query_is_clean(query, must_contain=("demand",))
    assert query != gap["suggested_query"]


# --- 16. no orchestration vocabulary in validation retry query --------------


def test_multiple_candidates_gaps_all_rebuilt_cleanly_in_one_retry():
    input_data = {
        "candidates": [
            {"id": ECOMMERCE_CANDIDATE_ID, "label": ECOMMERCE_CANDIDATE_LABEL, "description": ""},
            {"id": BLUE_COLLAR_CANDIDATE_ID, "label": BLUE_COLLAR_CANDIDATE_LABEL, "description": ""},
        ],
        "evidence_gaps": [
            {
                "candidate_id": ECOMMERCE_CANDIDATE_ID, "requirement_category": "market_size", "gap_type": "market_size",
                "importance": 5, "resolved": False,
                "suggested_query": "Validate and compare candidate opportunities market size",
            },
            {
                "candidate_id": BLUE_COLLAR_CANDIDATE_ID, "requirement_category": "demand", "gap_type": "demand",
                "importance": 4, "resolved": False,
                "suggested_query": "Validate and compare candidate opportunities demand",
            },
            # A genuinely candidate-agnostic gap (evidence_qa.py's own
            # generic detector, e.g. from a legacy/GENERAL context) — must
            # still fall back to its own suggested_query since there's no
            # candidate to rebuild from.
            {
                "candidate_id": None, "gap_type": "pricing", "importance": 3, "resolved": False,
                "suggested_query": "some other generic pricing query",
            },
        ],
    }
    queries = _build_queries(title="Validate and compare candidate opportunities", input_data=input_data)
    assert len(queries) == 3
    for query in queries[:2]:  # the two candidate-scoped ones
        _assert_query_is_clean(query)
    assert queries[2] == "some other generic pricing query"  # candidate-agnostic gap unaffected


def test_gap_without_matching_candidate_falls_back_safely():
    """A gap's candidate_id that doesn't match any known candidate (stale
    data, candidate dropped) must not crash — falls back to its own
    suggested_query rather than guessing."""
    gap = {
        "candidate_id": "unknown-candidate-id", "requirement_category": "pricing",
        "gap_type": "pricing", "suggested_query": "fallback query text",
    }
    query = _query_for_gap(gap, title="t", candidates_by_id={})
    assert query == "fallback query text"
