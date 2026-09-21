"""QA integration (Phase 12): deterministic checks complementing the model
QA verdict — candidate ranked despite comparison_ready=false,
comparison_ready mismatched against the recomputed gate, and a properly
qualified provisional result accepted. Offline."""
from __future__ import annotations

import uuid

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


def _weak_evidence() -> list[dict]:
    return [_item("https://random-blog.example.com/top10", "Top 10 best ways to make money online with digital products.")]


def _research_result(title: str, evidence: list[dict]) -> dict:
    return {"task_id": title, "title": title, "question": title, "evidence": evidence}


def _not_ready_research_results() -> list[dict]:
    return [
        _research_result("Notion template marketplace", _full_coverage_evidence("Notion template marketplace")),
        _research_result("Coda template hub", _weak_evidence()),
    ]


def test_qa_rejects_ranking_with_incomplete_comparison():
    output = {
        "recommendation": "Notion template marketplace is the strongest option — launch it first.",
        "reasoning": "r",
        "options_considered": [],
        "comparison_ready": False,
        "evidence_used": [],
        "unsupported_claims": [],
        "assumptions": ["a"],
    }
    check = evaluate_evidence(output, input_data={"research_results": _not_ready_research_results()})
    assert check.needs_review
    assert any("despite incomplete" in i for i in check.issues)


def test_qa_rejects_mismatched_comparison_ready_claim():
    output = {
        "recommendation": "Notion template marketplace is the strongest option.",
        "reasoning": "r",
        "options_considered": [],
        "comparison_ready": True,  # incorrectly claims ready — gate says otherwise
        "evidence_used": [],
        "unsupported_claims": [],
        "assumptions": ["a"],
    }
    check = evaluate_evidence(output, input_data={"research_results": _not_ready_research_results()})
    assert check.needs_review
    assert any("does not match" in i for i in check.issues)


def test_qa_accepts_appropriately_qualified_provisional_result():
    output = {
        "recommendation": (
            "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE\n"
            "MOST PROMISING VALIDATION CANDIDATE: Notion template marketplace (provisional)\n"
            "MISSING INFORMATION: Coda template hub: demand; Coda template hub: competition\n"
            "NEXT VALIDATION: Run targeted follow-up research."
        ),
        "reasoning": "r",
        "options_considered": [],
        "comparison_ready": False,
        "evidence_used": [],
        "unsupported_claims": [],
        "assumptions": ["a"],
    }
    check = evaluate_evidence(output, input_data={"research_results": _not_ready_research_results()})
    assert not any("despite incomplete" in i for i in check.issues)
    assert not any("does not match" in i for i in check.issues)


def test_qa_is_a_noop_without_research_results_in_input():
    output = {
        "recommendation": "X is the strongest option.",
        "reasoning": "r",
        "options_considered": [],
        "comparison_ready": True,
        "evidence_used": [],
        "unsupported_claims": [],
        "assumptions": ["a"],
    }
    check = evaluate_evidence(output, input_data={})
    assert not any("comparison" in i.lower() for i in check.issues)
