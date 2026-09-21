"""v0.1.2.6 Phase 11: diagnostic safety, re-verified after this
checkpoint's QA context compactor + split worker/QA diagnostic collection
(app/orchestration/evaluator.py now logs `worker_diagnostics +
qa_diagnostics` together). Must never log API keys, Anthropic workspace
IDs, authorization headers, full prompts, or full page extracts — only
counts, sizes, model identifiers, task identifiers, and safe bounded
metadata. Offline — no network call.
"""
from __future__ import annotations

import json

from app.agents.qa_context import compact_qa_context
from app.config.settings import Settings
from tests._qa_context_fixtures import realistic_output_for_attempt

_SECRET_MARKERS = ("sk-ant-", "api_key", "apikey", "authorization", "bearer ", "workspace_id", "anthropic-workspace-id")


def test_compacted_qa_view_never_contains_secret_markers():
    settings = Settings()
    output = realistic_output_for_attempt(3)
    compacted = compact_qa_context(output, settings=settings)
    serialized = json.dumps(compacted).lower()
    for marker in _SECRET_MARKERS:
        assert marker not in serialized


def test_compacted_qa_view_never_contains_full_page_extract_text():
    """Excerpts are dropped entirely from the QA-facing evidence view —
    only a short, bounded claim survives (Phase 4)."""
    settings = Settings()
    output = realistic_output_for_attempt(2)
    compacted = compact_qa_context(output, settings=settings)
    for item in compacted["evidence"]:
        assert "excerpt" not in item


async def test_worker_and_qa_diagnostics_logged_together_stay_secret_free():
    """End-to-end: app/orchestration/evaluator.py now logs
    worker_diagnostics + qa_diagnostics combined — confirms the combined
    log payload is still secret-free (mirrors
    tests/test_diagnostic_reporting.py's checks at the integration level)."""
    from app.agents.providers import AnthropicProvider
    from app.agents.usage import collect_request_diagnostics, with_diagnostic_context
    from app.orchestration.evaluator import _log_request_diagnostics
    from app.research_intelligence.prompt_diagnostics import format_diagnostic_summary
    import pydantic

    class _Dummy(pydantic.BaseModel):
        ok: bool = True

    async def fake_parse(**kwargs):
        class FakeUsage:
            input_tokens = 100
            output_tokens = 20

        class FakeResponse:
            parsed_output = _Dummy(ok=True)
            usage = FakeUsage()

        return FakeResponse()

    provider = AnthropicProvider(api_key="sk-ant-should-never-appear-in-logs")
    provider._client.messages.parse = fake_parse

    with collect_request_diagnostics() as worker_diag:
        with with_diagnostic_context({"agent_type": "research"}):
            await provider.complete_structured(
                system_prompt="sys", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001",
            )
    with collect_request_diagnostics() as qa_diag:
        with with_diagnostic_context({"agent_type": "qa"}):
            await provider.complete_structured(
                system_prompt="sys", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001",
            )

    summary = format_diagnostic_summary(worker_diag + qa_diag, title="t")
    assert "sk-ant-should-never-appear-in-logs" not in summary
    assert "authorization" not in summary.lower()
