"""v0.1.2.5 Phase 11: the bounded DEBUG/diagnostic summary
(format_diagnostic_summary) — never dumps full prompts, never leaks
secrets, and correctly labels attempt/retry numbers. Offline — no network
call."""
from __future__ import annotations

from app.research_intelligence.prompt_diagnostics import ModelRequestDiagnostic, format_diagnostic_summary


def _diag(attempt: int, **overrides) -> ModelRequestDiagnostic:
    base = dict(
        agent_type="research", model="claude-haiku-4-5-20251001", research_mode="VALIDATION",
        attempt_number=attempt, system_chars=2600, content_chars=8000, output_schema_chars=800,
        tool_schema_chars=800, message_count=1, evidence_count=12, candidate_count=3, gap_count=2,
        provider_input_tokens=15300, provider_output_tokens=900, total_request_chars_estimate=11400,
    )
    base.update(overrides)
    return ModelRequestDiagnostic(**base)


def test_summary_contains_exact_raw_request_chars():
    summary = format_diagnostic_summary([_diag(0)])
    assert "system_chars: 2600" in summary
    assert "content_chars: 8000" in summary
    assert "schema_chars: 800" in summary
    assert "request_chars (estimate): 11400" in summary


def test_summary_records_provider_reported_input_tokens():
    summary = format_diagnostic_summary([_diag(0, provider_input_tokens=15307, provider_output_tokens=612)])
    assert "provider_input_tokens: 15307" in summary
    assert "provider_output_tokens: 612" in summary


def test_summary_never_contains_an_api_key():
    summary = format_diagnostic_summary([_diag(0)])
    for marker in ("sk-ant-", "sk-", "api_key", "apikey"):
        assert marker not in summary.lower()


def test_summary_never_contains_an_authorization_header():
    summary = format_diagnostic_summary([_diag(0)])
    assert "authorization" not in summary.lower()
    assert "bearer" not in summary.lower()


def test_summary_output_is_bounded():
    """A pathological number of attempts must not produce an unbounded
    string — each attempt contributes a small, fixed number of lines."""
    diagnostics = [_diag(i) for i in range(50)]
    summary = format_diagnostic_summary(diagnostics)
    lines_per_attempt = len(summary.splitlines()) / 50
    assert lines_per_attempt < 20  # a small, fixed block per attempt, not unbounded growth


def test_summary_identifies_attempt_vs_retry_number():
    summary = format_diagnostic_summary([_diag(0), _diag(1), _diag(2)])
    assert "attempt 0" in summary
    assert "retry 1" in summary
    assert "retry 2" in summary


def test_empty_diagnostics_says_so_explicitly_never_fabricated():
    summary = format_diagnostic_summary([])
    assert "no diagnostics recorded" in summary.lower()
