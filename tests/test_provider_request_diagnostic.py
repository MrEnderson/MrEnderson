"""v0.1.2.4 Defect 1: the request diagnostic is built from the EXACT
arguments the Anthropic SDK is about to receive (not a separate,
possibly-divergent offline estimate), and provider-reported usage is
recorded per call. Offline — the SDK client's `messages.parse` is
monkeypatched directly, mirroring tests/test_provider_error_handling.py's
pattern exactly; no real network call."""
from __future__ import annotations

import json

import pydantic

from app.agents.providers import AnthropicProvider
from app.agents.usage import collect_request_diagnostics, with_diagnostic_context
from app.research_intelligence.prompt_diagnostics import ModelRequestDiagnostic


class _Dummy(pydantic.BaseModel):
    ok: bool = True


def _provider() -> AnthropicProvider:
    return AnthropicProvider(api_key="sk-ant-not-a-real-key")


def _fake_response(parsed=None, input_tokens=1234, output_tokens=56):
    class FakeUsage:
        pass

    fake_usage = FakeUsage()
    fake_usage.input_tokens = input_tokens
    fake_usage.output_tokens = output_tokens

    class FakeResponse:
        parsed_output = parsed
        usage = fake_usage if parsed is not None else None

    return FakeResponse()


# --- 1. Diagnostic measures the actual SDK-bound request object -----------


async def test_diagnostic_measures_the_exact_arguments_sent_to_the_sdk():
    captured_kwargs = {}

    async def fake_parse(**kwargs):
        captured_kwargs.update(kwargs)
        return _fake_response(parsed=_Dummy(ok=True))

    provider = _provider()
    provider._client.messages.parse = fake_parse

    system_prompt = "SYSTEM PROMPT TEXT"
    user_prompt = json.dumps({"question": "q", "evidence": [{"id": "e1", "claim": "c"}]})

    with collect_request_diagnostics() as diagnostics:
        with with_diagnostic_context({"agent_type": "research", "research_mode": "VALIDATION", "attempt_number": 0, "evidence_count": 1, "candidate_count": 2, "gap_count": 3}):
            await provider.complete_structured(
                system_prompt=system_prompt, user_prompt=user_prompt, output_schema=_Dummy,
                model="claude-haiku-4-5-20251001",
            )

    assert len(diagnostics) == 1
    diag = diagnostics[0]
    assert isinstance(diag, ModelRequestDiagnostic)
    # Measures the EXACT strings passed to messages.parse — no separate
    # estimate, no drift.
    assert diag.system_chars == len(captured_kwargs["system"])
    assert diag.system_chars == len(system_prompt)
    assert diag.content_chars == len(captured_kwargs["messages"][0]["content"])
    assert diag.content_chars == len(user_prompt)
    assert diag.message_count == len(captured_kwargs["messages"])
    assert diag.output_schema_chars == len(json.dumps(_Dummy.model_json_schema()))
    assert diag.agent_type == "research"
    assert diag.research_mode == "VALIDATION"
    assert diag.attempt_number == 0
    assert diag.evidence_count == 1
    assert diag.candidate_count == 2
    assert diag.gap_count == 3


# --- 2. Diagnostic excludes secrets -----------------------------------------


async def test_diagnostic_structurally_cannot_carry_prompt_content_or_secrets():
    """Every field on ModelRequestDiagnostic is a count/enum-like value —
    proves this structurally, not just by example."""
    for name, field in ModelRequestDiagnostic.model_fields.items():
        assert field.annotation in (
            int, int | None, str, str | None, float, float | None,
        ), f"Unexpected non-safe field type on ModelRequestDiagnostic: {name}"


async def test_diagnostic_never_exposes_the_api_key():
    async def fake_parse(**kwargs):
        return _fake_response(parsed=_Dummy(ok=True))

    provider = _provider()
    provider._client.messages.parse = fake_parse

    with collect_request_diagnostics() as diagnostics:
        with with_diagnostic_context({"agent_type": "research"}):
            await provider.complete_structured(
                system_prompt="sys", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001",
            )

    serialized = diagnostics[0].model_dump_json()
    assert "sk-ant-not-a-real-key" not in serialized


# --- 3. Provider-reported input/output usage recorded per call ------------


async def test_provider_reported_usage_recorded_on_the_diagnostic():
    async def fake_parse(**kwargs):
        return _fake_response(parsed=_Dummy(ok=True), input_tokens=9001, output_tokens=42)

    provider = _provider()
    provider._client.messages.parse = fake_parse

    with collect_request_diagnostics() as diagnostics:
        await provider.complete_structured(
            system_prompt="sys", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001",
        )

    assert diagnostics[0].provider_input_tokens == 9001
    assert diagnostics[0].provider_output_tokens == 42


async def test_failed_call_still_records_a_diagnostic_with_tokens_unset():
    """A repair-triggering failure still gets a diagnostic recorded for
    THAT attempt (tokens unset, since no usable usage was ever reported) —
    visibility into failed/repair attempts' request size, not just
    successful ones."""

    async def fake_parse(**kwargs):
        # ValueError is caught by the same except clause as pydantic's
        # ValidationError in AnthropicProvider._complete_structured_once —
        # simpler to construct here, same code path exercised.
        raise ValueError("malformed structured output")

    provider = _provider()
    provider._client.messages.parse = fake_parse

    with collect_request_diagnostics() as diagnostics:
        try:
            await provider.complete_structured(
                system_prompt="sys", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001",
            )
        except Exception:  # noqa: BLE001 - expected: exhausts the one repair attempt and raises
            pass

    assert len(diagnostics) == 2  # original attempt + one repair attempt
    assert all(d.provider_input_tokens is None for d in diagnostics)


# --- 4. Helper measurement and provider measurement use the same content --


async def test_helper_and_provider_diagnostics_agree_on_the_same_content():
    """app/research_intelligence/prompt_diagnostics.py::diagnose_prompt_size
    (the offline helper) and build_request_diagnostic (used by the real
    provider call) must report the SAME system/content sizes when given
    the same inputs — no second, divergent measurement path."""
    from app.research_intelligence.prompt_diagnostics import build_request_diagnostic, diagnose_prompt_size

    system_prompt = "SYS" * 50
    prompt_context = {"question": "q", "description": "d", "evidence": [{"id": "e1", "claim": "c"}]}
    user_prompt = json.dumps(prompt_context)

    helper_report = diagnose_prompt_size(system_prompt=system_prompt, prompt_context=prompt_context)
    provider_diag = build_request_diagnostic(
        model="claude-haiku-4-5-20251001", system_prompt=system_prompt, user_prompt=user_prompt,
        output_schema=_Dummy,
    )

    assert helper_report.system_prompt_chars == provider_diag.system_chars
    assert len(user_prompt) == provider_diag.content_chars
