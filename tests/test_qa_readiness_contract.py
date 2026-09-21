"""Defect 3 / Phases 10-12 (v0.1.2.2): QA must not penalize Strategy merely
for correctly refusing to declare a winner under comparison_ready=false,
and must not let Strategy declare a winner under it either. Offline."""
from __future__ import annotations

from app.agents.qa import SYSTEM_PROMPT as QA_SYSTEM_PROMPT
from app.security.evidence_qa import evaluate_evidence, merge_into_verdict
from app.schemas.agents import QAVerdict


def _strategy_output(**overrides) -> dict:
    base = {
        "recommendation": "X is the strongest option.",
        "reasoning": "r",
        "options_considered": [],
        "evidence_used": [],
        "unsupported_claims": [],
        "assumptions": ["a"],
        "comparison_ready": False,
        "missing_requirements": [],
    }
    base.update(overrides)
    return base


def _model_verdict(verdict: str, score: float, feedback: str = "model feedback") -> QAVerdict:
    return QAVerdict(verdict=verdict, score=score, feedback=feedback)


# --- 19. comparison_ready=false + refusal to rank can PASS -----------------


def test_correct_refusal_under_incomplete_evidence_can_pass_even_if_model_qa_said_fail():
    output = _strategy_output(
        recommendation=(
            "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE\n"
            "MOST PROMISING VALIDATION CANDIDATE: X (provisional)\n"
            "MISSING INFORMATION: Candidate Y: pricing; Candidate Y: competition\n"
            "NEXT VALIDATION: Run targeted follow-up research."
        ),
        comparison_ready=False,
        missing_requirements=["Candidate Y: pricing"],
    )
    input_data = {"comparison_readiness": {"ready": False}}
    check = evaluate_evidence(output, input_data=input_data)
    assert check.verdict_override == "PASS"

    # Even a model QA that (incorrectly) said FAIL gets overridden to PASS.
    model_verdict = _model_verdict("FAIL", 0.2, "Strategy failed to name a single strongest opportunity.")
    merged = merge_into_verdict(model_verdict, check)
    assert merged.verdict == "PASS"
    assert "correct handling of insufficient evidence" in merged.feedback.lower()


# --- 20. comparison_ready=false + unsupported winner fails ----------------


def test_unqualified_winner_under_incomplete_evidence_fails_even_if_model_qa_said_pass():
    output = _strategy_output(
        recommendation="X is the strongest opportunity — pursue it now.",
        comparison_ready=False,
    )
    input_data = {"comparison_readiness": {"ready": False}}
    check = evaluate_evidence(output, input_data=input_data)
    assert check.verdict_override == "NEEDS_REVIEW"

    model_verdict = _model_verdict("PASS", 0.9, "Looks good.")
    merged = merge_into_verdict(model_verdict, check)
    assert merged.verdict == "NEEDS_REVIEW"
    assert merged.score <= 0.4


def test_mixed_disclaimer_and_unqualified_winner_language_still_flagged():
    """A recommendation that carries BOTH the required marker AND
    unqualified winner language is not let through just because the
    marker is present somewhere in the text."""
    output = _strategy_output(
        recommendation=(
            "DECISION STATUS: INSUFFICIENT COMPARABLE EVIDENCE, but X is clearly the winner "
            "and we should pursue it immediately."
        ),
        comparison_ready=False,
    )
    input_data = {"comparison_readiness": {"ready": False}}
    check = evaluate_evidence(output, input_data=input_data)
    assert check.verdict_override == "NEEDS_REVIEW"
    assert check.needs_review


# --- 21. comparison_ready=true + evidence-supported ranking may PASS ------


def test_ready_comparison_with_normal_ranking_is_not_overridden():
    output = _strategy_output(recommendation="Pursue X.", comparison_ready=True)
    input_data = {"comparison_readiness": {"ready": True}}
    check = evaluate_evidence(output, input_data=input_data)
    assert check.verdict_override is None

    model_verdict = _model_verdict("PASS", 0.9, "Well supported.")
    merged = merge_into_verdict(model_verdict, check)
    assert merged.verdict == "PASS"
    assert merged.score == 0.9  # untouched by the readiness contract


# --- 22. QA prompt explicitly contains readiness state ---------------------


def test_qa_system_prompt_explicitly_mentions_comparison_ready():
    assert "comparison_ready" in QA_SYSTEM_PROMPT


# --- 23. QA does not instruct Strategy to override false readiness --------


def test_qa_system_prompt_forbids_overriding_the_gate():
    # Whitespace-normalized: the source string wraps across lines, so a
    # phrase spanning a line break would otherwise contain a literal
    # newline instead of a single space.
    normalized = " ".join(QA_SYSTEM_PROMPT.lower().split())
    assert "never instruct strategy to override the gate" in normalized
    assert "do not fail or penalize strategy merely because it refused" in normalized
