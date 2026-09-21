"""Strategy prompt/context compaction (v0.1.1 efficiency patch): bounds what
the Strategy Agent is shown on each attempt without ever touching persisted
evidence or the research task's own stored output. All offline, deterministic
— no network, no live API key. See app/agents/strategy_context.py."""
from __future__ import annotations

from app.agents.strategy_context import compact_research_results
from app.config.settings import Settings, get_settings


def _settings(**overrides) -> Settings:
    base = dict(
        strategy_max_evidence_items=3,
        strategy_max_evidence_excerpt_chars=20,
        strategy_max_findings=2,
        strategy_max_open_questions=2,
        strategy_max_assumptions=2,
        strategy_max_qa_feedback_chars=15,
    )
    base.update(overrides)
    return Settings(**base)


def _evidence(id_: str, *, depth="SEARCH_SNIPPET", quality="UNKNOWN", excerpt="x" * 50) -> dict:
    return {
        "id": id_,
        "claim": f"claim {id_}",
        "excerpt": excerpt,
        "evidence_depth": depth,
        "source_quality": quality,
    }


def _research_result(task_id: str, evidence: list[dict], **overrides) -> dict:
    base = dict(
        task_id=task_id,
        title=f"Research {task_id}",
        agent_type="research",
        question="q",
        summary="s",
        insufficient_evidence=True,
        findings=[{"claim": f"f{i}"} for i in range(5)],
        assumptions=[f"a{i}" for i in range(5)],
        open_questions=[f"oq{i}" for i in range(5)],
        evidence_gaps=[],
        evidence=evidence,
    )
    base.update(overrides)
    return base


# --- Bounding ----------------------------------------------------------------


def test_evidence_count_is_bounded_across_all_research_results():
    research_results = [
        _research_result("r1", [_evidence("e1"), _evidence("e2")]),
        _research_result("r2", [_evidence("e3"), _evidence("e4"), _evidence("e5")]),
    ]
    compacted, visible_ids, _ = compact_research_results(
        research_results, qa_feedback=None, previous_output=None, settings=_settings()
    )
    total_shown = sum(len(r["evidence"]) for r in compacted)
    assert total_shown == 3  # strategy_max_evidence_items
    assert len(visible_ids) == 3


def test_excerpts_are_bounded():
    research_results = [_research_result("r1", [_evidence("e1", excerpt="x" * 500)])]
    compacted, _, _ = compact_research_results(
        research_results, qa_feedback=None, previous_output=None, settings=_settings()
    )
    excerpt = compacted[0]["evidence"][0]["excerpt"]
    assert len(excerpt) <= 20 + len(" [truncated]")


def test_findings_assumptions_open_questions_are_bounded():
    research_results = [_research_result("r1", [])]
    compacted, _, _ = compact_research_results(
        research_results, qa_feedback=None, previous_output=None, settings=_settings()
    )
    assert len(compacted[0]["findings"]) == 2
    assert len(compacted[0]["assumptions"]) == 2
    assert len(compacted[0]["open_questions"]) == 2


def test_qa_feedback_is_bounded():
    long_feedback = "y" * 100
    _, _, extra = compact_research_results(
        [], qa_feedback=long_feedback, previous_output=None, settings=_settings()
    )
    assert len(extra["previous_qa_feedback"]) <= 15 + len(" [truncated]")


def test_retry_context_does_not_grow_without_bound():
    """Simulates several retries' worth of accumulated evidence (as
    app/orchestration/evaluator.py would pass in) — the compacted output
    stays the same bounded size regardless of how much has piled up."""
    settings = _settings()
    small = [_research_result("r1", [_evidence(f"e{i}") for i in range(4)])]
    large = [_research_result("r1", [_evidence(f"e{i}") for i in range(50)])]

    compacted_small, ids_small, _ = compact_research_results(
        small, qa_feedback=None, previous_output=None, settings=settings
    )
    compacted_large, ids_large, _ = compact_research_results(
        large, qa_feedback=None, previous_output=None, settings=settings
    )
    assert sum(len(r["evidence"]) for r in compacted_small) <= settings.strategy_max_evidence_items
    assert sum(len(r["evidence"]) for r in compacted_large) <= settings.strategy_max_evidence_items
    assert len(ids_large) == settings.strategy_max_evidence_items


# --- Prioritization ------------------------------------------------------------


def test_highest_value_evidence_is_prioritized_deterministically():
    research_results = [
        _research_result(
            "r1",
            [
                _evidence("weak", depth="SEARCH_SNIPPET", quality="UNKNOWN"),
                _evidence("strong", depth="PAGE_EXTRACT", quality="AUTHORITATIVE"),
            ],
        )
    ]
    compacted, visible_ids, _ = compact_research_results(
        research_results,
        qa_feedback=None,
        previous_output=None,
        settings=_settings(strategy_max_evidence_items=1),
    )
    assert visible_ids == {"strong"}
    assert compacted[0]["evidence"][0]["id"] == "strong"


def test_previously_cited_evidence_is_pinned_even_if_lower_quality():
    """A retry must not lose the ability to re-cite what it already cited
    validly, even if a higher-quality item now competes for the bounded
    slots — otherwise a legitimate re-citation would spuriously fail
    evidence-id validation on retry."""
    research_results = [
        _research_result(
            "r1",
            [
                _evidence("cited-weak", depth="SEARCH_SNIPPET", quality="UNKNOWN"),
                _evidence("new-strong-1", depth="PAGE_EXTRACT", quality="AUTHORITATIVE"),
                _evidence("new-strong-2", depth="PAGE_EXTRACT", quality="AUTHORITATIVE"),
            ],
        )
    ]
    previous_output = {"recommendation": "r", "confidence": 0.5, "evidence_used": ["cited-weak"]}
    compacted, visible_ids, _ = compact_research_results(
        research_results,
        qa_feedback=None,
        previous_output=previous_output,
        settings=_settings(strategy_max_evidence_items=2),
    )
    assert "cited-weak" in visible_ids


# --- IDs and persisted evidence never touched ---------------------------------


def test_evidence_ids_survive_compaction_unchanged():
    research_results = [_research_result("r1", [_evidence("stable-id")])]
    compacted, visible_ids, _ = compact_research_results(
        research_results, qa_feedback=None, previous_output=None, settings=_settings()
    )
    assert visible_ids == {"stable-id"}
    assert compacted[0]["evidence"][0]["id"] == "stable-id"


def test_compaction_never_mutates_the_input_research_results():
    """Full persisted evidence (the caller's own copy) must be unchanged —
    compaction only ever builds a NEW, separate structure."""
    original = _research_result("r1", [_evidence("e1", excerpt="x" * 500)])
    research_results = [original]
    compact_research_results(research_results, qa_feedback=None, previous_output=None, settings=_settings())
    assert original["evidence"][0]["excerpt"] == "x" * 500  # untouched
    assert len(original["findings"]) == 5  # untouched


# --- Retry-input-size regression: repeated retries stay bounded --------------
# See app/orchestration/evaluator.py::run_worker_with_qa and
# app/agents/strategy.py — previous_conclusion/previous_qa_feedback/
# research_results/valid_evidence_ids must never accumulate across retries
# (each attempt replaces, never appends to, the previous one's context).


async def test_strategy_retry_prompt_stays_bounded_across_many_retries():
    import json

    from app.orchestration.evaluator import run_worker_with_qa
    from app.schemas.agents import QAVerdict, StrategyOutput

    research_results = [
        _research_result(
            "r1",
            [_evidence(f"e{i}", excerpt="y" * 200) for i in range(30)],
            findings=[{"claim": f"f{i}" * 20} for i in range(20)],
            assumptions=[f"a{i}" * 20 for i in range(20)],
            open_questions=[f"oq{i}" * 20 for i in range(20)],
        )
    ]

    captured_inputs: list[dict] = []

    class _RecordingStrategyWorker:
        async def run(self, *, title, description, input_data, context):
            captured_inputs.append(input_data)
            return StrategyOutput(
                options_considered=[],
                # A long reasoning/recommendation on every attempt — if the
                # PREVIOUS attempt's full output were ever re-embedded
                # wholesale (rather than the small, bounded
                # previous_conclusion extract), this would compound.
                recommendation="Recommend option A. " + ("detail " * 50),
                reasoning="Because of the evidence. " + ("detail " * 50),
                assumptions=["a"],
                evidence_used=[],
                confidence=0.5,
            )

    class _QASequence:
        def __init__(self):
            self.calls = 0

        async def run(self, **kwargs):
            self.calls += 1
            return QAVerdict(verdict="NEEDS_REVIEW", score=0.4, feedback="try again " * 30)

    worker = _RecordingStrategyWorker()
    await run_worker_with_qa(
        worker_agent=worker, qa_agent=_QASequence(), title="t", description="",
        input_data={"research_results": research_results}, success_criteria=None, max_retries=4,
    )

    settings = get_settings()
    sizes = [len(json.dumps(inp, default=str)) for inp in captured_inputs]

    assert len(captured_inputs) == 5  # initial + 4 retries

    for inp in captured_inputs:
        total_evidence = sum(len(r["evidence"]) for r in inp["research_results"])
        assert total_evidence <= settings.strategy_max_evidence_items
        assert len(inp["research_results"][0]["findings"]) <= settings.strategy_max_findings
        # previous_conclusion/previous_qa_feedback are single bounded values,
        # never a growing list of every prior attempt's feedback.
        if "previous_qa_feedback" in inp:
            assert isinstance(inp["previous_qa_feedback"], str)
            assert len(inp["previous_qa_feedback"]) <= settings.strategy_max_qa_feedback_chars + len(" [truncated]")
        if "previous_conclusion" in inp:
            assert isinstance(inp["previous_conclusion"], dict)
            assert len(inp["previous_conclusion"]["recommendation"]) <= (
                settings.strategy_max_qa_feedback_chars + len(" [truncated]")
            )

    # The input size must not grow attempt-over-attempt — same bounded
    # research_results/evidence, and previous_conclusion/previous_qa_feedback
    # are always a single replaced value, never an accumulating history.
    max_size, min_size = max(sizes[1:]), min(sizes[1:])  # compare across retries only (attempt 0 has no "previous_*")
    assert max_size - min_size < 200  # near-constant; no unbounded growth across retries
