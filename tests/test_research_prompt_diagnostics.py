"""v0.1.2.3 Defect 2: offline prompt-size diagnostics (per-component
breakdown), and Research structured-output schema size measurement.
Offline, no network calls."""
from __future__ import annotations

import json

from app.research_intelligence.prompt_diagnostics import assert_no_secrets, diagnose_prompt_size
from app.schemas.agents import QAVerdict, StrategyOutput
from app.schemas.research_dto import DiscoveryModelOutput, GeneralResearchModelOutput, ValidationModelOutput
from app.schemas.tasks import ExecutionPlan


def _schema_size(model) -> int:
    return len(json.dumps(model.model_json_schema()))


# --- 10. Prompt diagnostics report per-component sizes ---------------------


def test_prompt_diagnostics_reports_per_component_sizes():
    prompt_context = {
        "question": "Validate and compare candidate opportunities",
        "description": "",
        "candidates": [{"label": "Notion Template Marketplace", "description": "d"}],
        "evidence": [{"id": "e1", "claim": "c", "excerpt": "x" * 500}],
        "qa_feedback": "y" * 100,
        "unresolved_gaps": [{"gap_type": "pricing", "claim_or_question": "q"}],
    }
    report = diagnose_prompt_size(system_prompt="SYS" * 100, prompt_context=prompt_context)

    assert report.system_prompt_chars == 300
    assert report.question_title_description_chars == len(prompt_context["question"])
    assert report.candidates_chars > 0
    assert report.evidence_chars > 500  # includes the 500-char excerpt plus JSON overhead
    assert report.qa_feedback_chars == 100
    assert report.unresolved_gaps_chars > 0
    assert report.evidence_item_count == 1
    assert report.total_request_chars > report.evidence_chars  # includes system prompt too

    text = report.to_text()
    assert "system_prompt" in text
    assert "evidence" in text
    assert "TOTAL" in text


def test_prompt_diagnostics_handles_missing_optional_components():
    report = diagnose_prompt_size(
        system_prompt="sys", prompt_context={"question": "q", "description": "d"}
    )
    assert report.candidates_chars == 0
    assert report.evidence_chars == 0
    assert report.qa_feedback_chars == 0
    assert report.unresolved_gaps_chars == 0
    assert report.evidence_item_count == 0


# --- 11. Diagnostics contain no secrets -------------------------------------


def test_diagnostics_never_contain_secret_like_markers():
    system_prompt = "You are the Research Agent inside Jarvis OS."
    prompt_context = {
        "question": "Validate candidates",
        "description": "",
        "candidates": [{"label": "Notion Template Marketplace"}],
        "evidence": [{"id": "e1", "claim": "Pricing info from a public page.", "source_url": "https://example.com/pricing"}],
    }
    report = diagnose_prompt_size(system_prompt=system_prompt, prompt_context=prompt_context)
    assert_no_secrets(report, system_prompt=system_prompt, prompt_context=prompt_context)  # must not raise


def test_diagnostics_secret_check_actually_detects_a_marker():
    """Proves the guard isn't a no-op — a system prompt that DID leak
    something secret-shaped is caught."""
    import pytest

    bad_system_prompt = "system prompt leaking api_key=sk-ant-not-a-real-key-but-shaped-like-one"
    with pytest.raises(AssertionError):
        assert_no_secrets(
            diagnose_prompt_size(system_prompt=bad_system_prompt, prompt_context={}),
            system_prompt=bad_system_prompt,
            prompt_context={},
        )


# --- 12. Research structured-output schema size is measured ---------------


def test_research_dto_schema_sizes_are_measured_and_small():
    discovery_size = _schema_size(DiscoveryModelOutput)
    validation_size = _schema_size(ValidationModelOutput)
    general_size = _schema_size(GeneralResearchModelOutput)

    # Confirms the v0.1.2.1 fix still holds: none of the three research
    # DTOs are anywhere near the size that triggered Anthropic's compiled-
    # grammar-too-large error (the old ResearchOutput was ~9,650 chars).
    for size in (discovery_size, validation_size, general_size):
        assert size < 2500

    # And Strategy/QA/planner (unrelated to this defect) stay comfortably
    # small too, confirming schema size is NOT what's driving Defect 2 —
    # the evidence/prompt-context payload is (see
    # tests/test_research_prompt_compaction.py).
    assert _schema_size(StrategyOutput) < 5000
    assert _schema_size(QAVerdict) < 5000
    assert _schema_size(ExecutionPlan) < 5000
