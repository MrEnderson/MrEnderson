"""Issue 2: the deterministic Candidate Completeness Gate must use the
AUTHORITATIVE accumulated research/evidence, never the bounded/compacted
view built for the Strategy model prompt.

    AUTHORITATIVE EVIDENCE -> GATE
    AUTHORITATIVE EVIDENCE -> COMPACTOR -> STRATEGY MODEL

Never COMPACTOR -> GATE. Also proves the separate "gate_evidence_ids" vs
"visible_strategy_evidence_ids" concepts: Strategy may only ever cite
evidence ids actually visible in its bounded prompt, even though the gate
may see (and use) evidence Strategy was never shown. Offline."""
from __future__ import annotations

import uuid

from app.agents.strategy_context import compact_research_results
from app.config.settings import Settings, get_settings
from app.orchestration.evaluator import run_worker_with_qa
from app.schemas.agents import QAVerdict, StrategyOutput
from app.security.evidence_qa import evaluate_evidence


def _item(url: str, claim: str) -> dict:
    return {"id": str(uuid.uuid4()), "claim": claim, "source_url": url, "excerpt": claim}


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


def _research_result(title: str, evidence: list[dict]) -> dict:
    return {
        "task_id": title, "title": title, "agent_type": "research", "question": title, "summary": "s",
        "insufficient_evidence": False, "findings": [], "assumptions": [], "open_questions": [],
        "evidence_gaps": [], "evidence": evidence,
    }


# --- 8/9. Gate uses authoritative full evidence; the Strategy prompt ------
#          itself stays bounded


async def test_completeness_gate_uses_authoritative_evidence_not_compacted_context(monkeypatch):
    monkeypatch.setenv("STRATEGY_MAX_EVIDENCE_ITEMS", "3")
    get_settings.cache_clear()
    try:
        research_results = [
            _research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace")),
            _research_result("Coda template hub", _full_coverage_evidence("Coda template hub")),
        ]
        captured_inputs: list[dict] = []

        class _RecordingStrategyWorker:
            async def run(self, *, title, description, input_data, context):
                captured_inputs.append(input_data)
                return StrategyOutput(
                    options_considered=[], recommendation="Pursue Notion.", reasoning="r",
                    assumptions=["a"], evidence_used=[], confidence=0.5,
                )

        class _QASequence:
            def __init__(self):
                self.calls = 0

            async def run(self, **kwargs):
                self.calls += 1
                verdict = "PASS" if self.calls >= 2 else "NEEDS_REVIEW"
                return QAVerdict(verdict=verdict, score=0.9 if verdict == "PASS" else 0.4, feedback="try again")

        await run_worker_with_qa(
            worker_agent=_RecordingStrategyWorker(), qa_agent=_QASequence(), title="t", description="",
            input_data={"research_results": research_results}, success_criteria=None, max_retries=3,
        )

        assert len(captured_inputs) >= 2  # at least one retry actually happened

        settings = get_settings()
        for inp in captured_inputs:
            # 9. The Strategy MODEL PROMPT stays bounded by compaction...
            total_visible_evidence = sum(len(r["evidence"]) for r in inp["research_results"])
            assert total_visible_evidence <= settings.strategy_max_evidence_items
            # 8. ...but the gate injected alongside it reflects the FULL,
            # authoritative 11-items-per-candidate evidence pool, not the
            # handful actually shown — both candidates are fully covered.
            assert inp["comparison_readiness"]["ready"] is True
    finally:
        get_settings.cache_clear()


async def test_completeness_gate_stays_correct_when_full_evidence_is_imbalanced(monkeypatch):
    """The flip side: even though Strategy's bounded prompt might show a
    similarly-sized handful of evidence for both candidates, the
    AUTHORITATIVE gate must still see that one candidate's full evidence
    pool is actually far weaker, and refuse readiness. Uses the real
    StrategyAgent (via run_worker_with_qa, exactly as production does) so
    the deterministic gate-enforcement in app/agents/strategy.py actually
    runs."""
    from app.agents.strategy import StrategyAgent
    from app.agents.providers import MockProvider
    from app.database.models import PermissionLevel
    from app.schemas.agents import AgentDescriptor

    monkeypatch.setenv("STRATEGY_MAX_EVIDENCE_ITEMS", "3")
    get_settings.cache_clear()
    try:
        research_results = [
            _research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace")),
            _research_result(
                "Coda template hub",
                [_item("https://random-blog.example.com/top10", "Top 10 best ways to make money online with digital products.")],
            ),
        ]

        descriptor = AgentDescriptor(
            name="strategy", role="strategy", description="strategy", capabilities=[],
            permissions=[PermissionLevel.READ], model="mock-model",
        )
        worker = StrategyAgent(descriptor=descriptor, provider=MockProvider())

        class _QA:
            async def run(self, **kwargs):
                return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

        result = await run_worker_with_qa(
            worker_agent=worker, qa_agent=_QA(), title="t", description="",
            input_data={"research_results": research_results}, success_criteria=None, max_retries=1,
        )
        assert result.output.comparison_ready is False
        assert result.output.recommendation.upper().startswith("DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE")
    finally:
        get_settings.cache_clear()


# --- 10/11. Strategy may only cite visible evidence ids; hidden evidence --
#            may still feed deterministic coverage


def test_hidden_evidence_contributes_to_coverage_but_strategy_cannot_cite_it():
    research_results = [_research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace"))]
    settings = Settings(strategy_max_evidence_items=2)

    compacted, visible_ids, _ = compact_research_results(
        research_results, qa_feedback=None, previous_output=None, settings=settings
    )
    all_ids = {e["id"] for r in research_results for e in r["evidence"]}
    hidden_ids = all_ids - visible_ids
    assert hidden_ids  # compaction actually hid something

    hidden_id = next(iter(hidden_ids))
    output = {
        "recommendation": "Pursue it.",
        "reasoning": "r",
        "options_considered": [],
        "evidence_used": [hidden_id],  # cites evidence it was never shown
        "unsupported_claims": [],
        "assumptions": ["a"],
    }
    run_input = {"research_results": compacted}
    check = evaluate_evidence(output, input_data=run_input, known_evidence_ids=None)
    assert check.needs_review
    assert any("unknown evidence id" in i for i in check.issues)


def test_visible_evidence_can_still_be_cited():
    research_results = [_research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace"))]
    settings = Settings(strategy_max_evidence_items=2)

    compacted, visible_ids, _ = compact_research_results(
        research_results, qa_feedback=None, previous_output=None, settings=settings
    )
    visible_id = next(iter(visible_ids))
    output = {
        "recommendation": "Pursue it.",
        "reasoning": "r",
        "options_considered": [],
        "evidence_used": [visible_id],
        "unsupported_claims": [],
        "assumptions": ["a"],
    }
    run_input = {"research_results": compacted}
    check = evaluate_evidence(output, input_data=run_input, known_evidence_ids=None)
    assert not any("unknown evidence id" in i for i in check.issues)
