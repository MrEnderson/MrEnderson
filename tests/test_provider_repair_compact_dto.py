"""Phase 3/9: the existing Anthropic structured-output repair mechanism is
generic over `output_schema` and needs zero changes to work with the new
compact Research DTOs — this proves it. Offline; the SDK client's
`messages.parse` is monkeypatched directly, mirroring
tests/test_provider_error_handling.py's pattern exactly."""
from __future__ import annotations

import pydantic
import pytest

from app.agents.providers import AnthropicProvider, ModelOutputParsingError
from app.agents.usage import collect_usage
from app.schemas.research_dto import DiscoveryModelOutput


def _provider() -> AnthropicProvider:
    return AnthropicProvider(api_key="sk-ant-not-a-real-key")


# --- 18/19. Repair works with the compact DTO, using the SAME schema on ---
#            both calls


async def test_repair_succeeds_with_compact_dto_and_uses_it_on_both_calls():
    call_count = {"n": 0}
    captured_schemas: list = []

    async def fake_parse(**kwargs):
        call_count["n"] += 1
        captured_schemas.append(kwargs.get("output_format"))
        if call_count["n"] == 1:
            raise pydantic.ValidationError.from_exception_data(
                "DiscoveryModelOutput",
                [{"type": "json_invalid", "loc": (), "input": "", "ctx": {"error": "EOF while parsing"}}],
            )

        class FakeResponse:
            parsed_output = DiscoveryModelOutput(summary="s")
            usage = None

        return FakeResponse()

    provider = _provider()
    provider._client.messages.parse = fake_parse
    with collect_usage() as events:
        result = await provider.complete_structured(
            system_prompt="sys", user_prompt="{}", output_schema=DiscoveryModelOutput,
            model="claude-haiku-4-5-20251001",
        )

    assert call_count["n"] == 2  # exactly one repair attempt, not more
    assert isinstance(result, DiscoveryModelOutput)
    assert len(events) == 2
    # The repair NEVER falls back to a different (e.g. the giant
    # ResearchOutput) schema — same compact DTO both times.
    assert captured_schemas == [DiscoveryModelOutput, DiscoveryModelOutput]


async def test_repair_exhausted_raises_typed_error_never_falls_back_to_research_output():
    async def fake_parse(**kwargs):
        raise pydantic.ValidationError.from_exception_data(
            "DiscoveryModelOutput",
            [{"type": "json_invalid", "loc": (), "input": "", "ctx": {"error": "EOF"}}],
        )

    provider = _provider()
    provider._client.messages.parse = fake_parse
    with pytest.raises(ModelOutputParsingError):
        await provider.complete_structured(
            system_prompt="sys", user_prompt="{}", output_schema=DiscoveryModelOutput,
            model="claude-haiku-4-5-20251001",
        )


# --- 20. Repair does not consume a mission-level retry ---------------------


async def test_compact_dto_repair_does_not_consume_mission_retry():
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
            parsed_output = DiscoveryModelOutput(summary="s")
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
                system_prompt="sys", user_prompt="{}", output_schema=DiscoveryModelOutput,
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

    assert call_count["n"] == 2  # SDK called twice (original + internal repair)
    assert worker.calls == 1  # but the WORKER was only invoked once
    assert result.attempts_used == 0  # mission-level attempt counter unaffected
    assert result.verdict.verdict == "PASS"
