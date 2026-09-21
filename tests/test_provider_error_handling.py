"""AnthropicProvider structured-output failure handling: typed exceptions,
usage recorded even when parsing fails, truncation detection, the bounded
one-shot repair retry, and no raw model output ever dumped into logs.
Fully offline — the SDK client's `messages.parse` method is monkeypatched
directly; no test here makes a real network call."""
from __future__ import annotations

import pydantic
import pytest

from app.agents.providers import (
    AnthropicProvider,
    ModelAuthenticationError,
    ModelBillingError,
    ModelConnectionError,
    ModelInvalidRequestError,
    ModelOutputParsingError,
    ModelProviderError,
    ModelRateLimitError,
)
from app.agents.usage import collect_usage


class _Dummy(pydantic.BaseModel):
    ok: bool = True


def _provider() -> AnthropicProvider:
    return AnthropicProvider(api_key="sk-ant-not-a-real-key")


async def _run(provider, fake_parse):
    provider._client.messages.parse = fake_parse
    return await provider.complete_structured(
        system_prompt="sys", user_prompt="{}", output_schema=_Dummy, model="claude-haiku-4-5-20251001"
    )


# --- Typed exception classification -------------------------------------


async def test_authentication_error_is_typed_and_no_usage_recorded():
    import anthropic

    async def fake_parse(**kwargs):
        raise anthropic.AuthenticationError(
            message="invalid api key", response=_fake_httpx_response(401), body=None
        )

    provider = _provider()
    with collect_usage() as events:
        with pytest.raises(ModelAuthenticationError):
            await _run(provider, fake_parse)
    assert events == []  # no response was ever received


async def test_rate_limit_error_is_typed():
    import anthropic

    async def fake_parse(**kwargs):
        raise anthropic.RateLimitError(message="rate limited", response=_fake_httpx_response(429), body=None)

    with pytest.raises(ModelRateLimitError):
        await _run(_provider(), fake_parse)


async def test_billing_issue_detected_from_bad_request_message():
    import anthropic

    async def fake_parse(**kwargs):
        raise anthropic.BadRequestError(
            message="bad request",
            response=_fake_httpx_response(400),
            body={"error": {"message": "Your credit balance is too low to access the API."}},
        )

    with pytest.raises(ModelBillingError):
        await _run(_provider(), fake_parse)


async def test_invalid_model_maps_to_invalid_request_error():
    import anthropic

    async def fake_parse(**kwargs):
        raise anthropic.NotFoundError(message="not found", response=_fake_httpx_response(404), body=None)

    with pytest.raises(ModelInvalidRequestError):
        await _run(_provider(), fake_parse)


async def test_generic_bad_request_maps_to_invalid_request_error():
    import anthropic

    async def fake_parse(**kwargs):
        raise anthropic.BadRequestError(
            message="bad request",
            response=_fake_httpx_response(400),
            body={"error": {"message": "some other malformed request"}},
        )

    with pytest.raises(ModelInvalidRequestError):
        await _run(_provider(), fake_parse)


async def test_connection_error_is_typed():
    import anthropic
    import httpx

    async def fake_parse(**kwargs):
        raise anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))

    with pytest.raises(ModelConnectionError):
        await _run(_provider(), fake_parse)


async def test_unrecognized_status_error_falls_back_to_base_error():
    import anthropic

    async def fake_parse(**kwargs):
        raise anthropic.InternalServerError(
            message="internal error", response=_fake_httpx_response(500), body=None
        )

    with pytest.raises(ModelProviderError):
        await _run(_provider(), fake_parse)


# --- Malformed/truncated structured output: usage survives, typed error ----


async def test_malformed_structured_output_raises_typed_parsing_error_and_records_usage():
    call_count = {"n": 0}

    async def fake_parse(**kwargs):
        call_count["n"] += 1
        raise pydantic.ValidationError.from_exception_data(
            "ResearchOutput",
            [{"type": "json_invalid", "loc": (), "input": "", "ctx": {"error": "EOF while parsing a string"}}],
        )

    provider = _provider()
    with collect_usage() as events:
        with pytest.raises(ModelOutputParsingError):
            await _run(provider, fake_parse)

    # One initial attempt + one bounded repair attempt = 2 calls, 2 usage events.
    assert call_count["n"] == 2
    assert len(events) == 2
    assert all(e.provider == "anthropic" for e in events)
    assert all(e.input_tokens is None and e.output_tokens is None for e in events)  # never guessed


async def test_truncation_is_detected_from_eof_error_text():
    async def fake_parse(**kwargs):
        raise pydantic.ValidationError.from_exception_data(
            "ResearchOutput",
            [{"type": "json_invalid", "loc": (), "input": "", "ctx": {"error": "EOF while parsing a string at line 1 column 15253"}}],
        )

    try:
        await _run(_provider(), fake_parse)
        assert False, "expected ModelOutputParsingError"
    except ModelOutputParsingError as exc:
        assert exc.likely_truncated is True


async def test_non_truncation_parse_error_not_flagged_as_truncated():
    async def fake_parse(**kwargs):
        raise pydantic.ValidationError.from_exception_data(
            "ResearchOutput",
            [{"type": "missing", "loc": ("ok",), "input": {}}],
        )

    try:
        await _run(_provider(), fake_parse)
        assert False, "expected ModelOutputParsingError"
    except ModelOutputParsingError as exc:
        assert exc.likely_truncated is False


# --- Bounded ONE repair retry, not infinite -----------------------------


async def test_repair_retry_succeeds_on_second_attempt():
    call_count = {"n": 0}

    async def fake_parse(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise pydantic.ValidationError.from_exception_data(
                "ResearchOutput",
                [{"type": "json_invalid", "loc": (), "input": "", "ctx": {"error": "EOF while parsing"}}],
            )

        class FakeResponse:
            parsed_output = _Dummy(ok=True)
            usage = None

        return FakeResponse()

    provider = _provider()
    with collect_usage() as events:
        result = await _run(provider, fake_parse)

    assert call_count["n"] == 2  # exactly one repair attempt, not more
    assert isinstance(result, _Dummy)
    assert len(events) == 2  # the failed attempt's usage + the successful repair's usage


async def test_valid_first_response_returns_immediately_no_repair():
    call_count = {"n": 0}

    async def fake_parse(**kwargs):
        call_count["n"] += 1

        class FakeResponse:
            parsed_output = _Dummy(ok=True)
            usage = None

        return FakeResponse()

    provider = _provider()
    with collect_usage() as events:
        result = await _run(provider, fake_parse)

    assert call_count["n"] == 1
    assert isinstance(result, _Dummy)
    assert len(events) == 1


# --- Defect 2: parsed_output is None (no exception raised) -----------------
#
# Distinct failure mode from a parse/validation exception: the SDK call
# succeeds, but response.parsed_output is None. Before this patch this
# raised ModelOutputParsingError immediately with ZERO repair attempts —
# the confirmed live-benchmark bug. It now goes through the exact same
# one-repair mechanism as a validation exception.


async def test_none_parsed_output_triggers_a_repair_attempt_and_succeeds():
    call_count = {"n": 0}

    async def fake_parse(**kwargs):
        call_count["n"] += 1

        class FakeResponse:
            usage = None
            parsed_output = None if call_count["n"] == 1 else _Dummy(ok=True)

        return FakeResponse()

    provider = _provider()
    with collect_usage() as events:
        result = await _run(provider, fake_parse)

    assert call_count["n"] == 2  # first attempt (None) + exactly one repair
    assert isinstance(result, _Dummy)
    assert len(events) == 2  # usage recorded for BOTH calls


async def test_none_parsed_output_on_repair_too_raises_typed_error():
    call_count = {"n": 0}

    async def fake_parse(**kwargs):
        call_count["n"] += 1

        class FakeResponse:
            usage = None
            parsed_output = None

        return FakeResponse()

    provider = _provider()
    with collect_usage() as events:
        with pytest.raises(ModelOutputParsingError):
            await _run(provider, fake_parse)

    assert call_count["n"] == 2  # exactly one repair attempt, never more
    assert len(events) == 2


async def test_none_parsed_output_repair_prompt_matches_validation_error_repair_prompt():
    """Both failure modes funnel through the same repair hint — restates the
    schema-only requirement, prohibits commentary/markdown, and asks for
    conciseness, regardless of which failure mode triggered it."""
    captured = {}

    async def fake_parse(**kwargs):
        captured["system"] = kwargs.get("system")
        if "IMPORTANT" not in (captured.get("system") or ""):

            class FirstResponse:
                usage = None
                parsed_output = None

            return FirstResponse()

        class FakeResponse:
            parsed_output = _Dummy(ok=True)
            usage = None

        return FakeResponse()

    await _run(_provider(), fake_parse)
    system = captured["system"].lower()
    assert "more concise" in system
    assert "no commentary" in system or "no markdown" in system
    assert "evidence id" in system


async def test_exception_then_none_parsed_output_still_only_one_repair():
    """The two failure modes can even differ between the original attempt
    and the repair attempt — the cap is still exactly one repair total."""
    call_count = {"n": 0}

    async def fake_parse(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise pydantic.ValidationError.from_exception_data(
                "ResearchOutput",
                [{"type": "json_invalid", "loc": (), "input": "", "ctx": {"error": "EOF"}}],
            )

        class FakeResponse:
            usage = None
            parsed_output = None

        return FakeResponse()

    provider = _provider()
    with collect_usage() as events:
        with pytest.raises(ModelOutputParsingError):
            await _run(provider, fake_parse)

    assert call_count["n"] == 2
    assert len(events) == 2


# --- Internal repair never consumes a mission-level retry -------------------


async def test_internal_repair_does_not_increment_mission_retry_attempt():
    """The provider's one internal repair attempt is invisible to
    app/orchestration/evaluator.py::run_worker_with_qa's own `attempt`
    counter — from the mission retry budget's point of view, a
    provider-level repair-then-success is still exactly one worker attempt."""
    from app.orchestration.evaluator import run_worker_with_qa
    from app.schemas.agents import QAVerdict

    call_count = {"n": 0}

    async def fake_parse(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:

            class FirstResponse:
                usage = None
                parsed_output = None

            return FirstResponse()

        class FakeResponse:
            parsed_output = _Dummy(ok=True)
            usage = None

        return FakeResponse()

    provider = _provider()
    provider._client.messages.parse = fake_parse

    class _ProviderBackedWorker:
        def __init__(self):
            self.calls = 0

        async def run(self, *, title, description, input_data, context):
            self.calls += 1
            return await provider.complete_structured(
                system_prompt="sys", user_prompt="{}", output_schema=_Dummy,
                model="claude-haiku-4-5-20251001",
            )

    class _AlwaysPassQA:
        async def run(self, **kwargs):
            return QAVerdict(verdict="PASS", score=0.9, feedback="ok")

    worker = _ProviderBackedWorker()
    result = await run_worker_with_qa(
        worker_agent=worker, qa_agent=_AlwaysPassQA(), title="t", description="",
        input_data={}, success_criteria=None, max_retries=3,
    )

    # The Anthropic SDK was called twice (original + internal repair), but
    # the WORKER (agent-level) was only invoked once, and the mission-level
    # attempt counter reflects a single, immediately-successful attempt.
    assert call_count["n"] == 2
    assert worker.calls == 1
    assert result.attempts_used == 0
    assert result.verdict.verdict == "PASS"


async def test_repair_prompt_asks_for_more_concise_output():
    captured = {}

    async def fake_parse(**kwargs):
        captured["system"] = kwargs.get("system")
        if "IMPORTANT" not in (captured.get("system") or ""):
            raise pydantic.ValidationError.from_exception_data(
                "ResearchOutput",
                [{"type": "json_invalid", "loc": (), "input": "", "ctx": {"error": "EOF"}}],
            )

        class FakeResponse:
            parsed_output = _Dummy(ok=True)
            usage = None

        return FakeResponse()

    await _run(_provider(), fake_parse)
    assert "more concise" in captured["system"].lower()


# --- No response body dumped into logs/exceptions ----------------------


async def test_diagnostic_text_is_bounded_length():
    huge_error_text = "x" * 50_000

    async def fake_parse(**kwargs):
        exc = ValueError(huge_error_text)
        raise exc

    try:
        await _run(_provider(), fake_parse)
        assert False, "expected ModelOutputParsingError"
    except ModelOutputParsingError as exc:
        assert len(str(exc)) < 1000  # nowhere near the 50,000-char raw text


async def test_auth_error_message_never_contains_the_api_key():
    import anthropic

    async def fake_parse(**kwargs):
        raise anthropic.AuthenticationError(
            message="invalid api key", response=_fake_httpx_response(401), body=None
        )

    provider = AnthropicProvider(api_key="sk-ant-SUPER-SECRET-KEY-VALUE")
    try:
        await _run(provider, fake_parse)
        assert False
    except ModelAuthenticationError as exc:
        assert "sk-ant-SUPER-SECRET-KEY-VALUE" not in str(exc)


def _fake_httpx_response(status_code: int):
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return httpx.Response(status_code, request=request, json={"error": {"message": "error"}})
