"""Model provider abstraction.

Core orchestration must be testable without a live LLM (see build spec section 35),
so every agent talks to a `ModelProvider`, never to a vendor SDK directly. Which
live provider backs that protocol (OpenAI, Anthropic) is chosen by the
`MODEL_PROVIDER` setting in `app.config.settings`, not hard-coded here. The
`MockProvider` is a deterministic, rule-based stand-in used for local development,
CI, and the offline demo path. It never fabricates facts — where it would need real
external knowledge (e.g. live web research) it clearly labels its output as
DEVELOPMENT / SAMPLE DATA rather than pretending to be real research.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.agents.usage import ModelUsage, record_request_diagnostic, record_usage, timer
from app.config.settings import get_settings
from app.schemas.agents import (
    ExecutionOutput,
    QAVerdict,
    ResearchFinding,
    ResearchOutput,
    StrategyOption,
    StrategyOutput,
)
from app.schemas.reports import ExecutiveReport
from app.schemas.research_dto import (
    DiscoveryCandidateProposal,
    DiscoveryModelOutput,
    GeneralResearchModelOutput,
    ValidationModelOutput,
)
from app.schemas.tasks import ExecutionPlan, TaskPlan
from app.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class ModelProviderError(Exception):
    pass


class ModelAuthenticationError(ModelProviderError):
    """Invalid/rejected API key or workspace credential (HTTP 401)."""


class ModelRateLimitError(ModelProviderError):
    """Rate limited (HTTP 429)."""


class ModelBillingError(ModelProviderError):
    """Insufficient credits or another billing-account issue."""


class ModelInvalidRequestError(ModelProviderError):
    """The request itself was rejected — invalid model id, malformed
    parameters, or similar (HTTP 400/404) — not auth/billing-specific."""


class ModelConnectionError(ModelProviderError):
    """Network/transient failure reaching the provider; no response received."""


class ModelOutputParsingError(ModelProviderError):
    """The provider accepted the request and returned a response, but it
    could not be parsed into the requested structured schema.

    `likely_truncated` is a best-effort guess (from the parse error's own
    text) that this was caused by hitting the output token limit mid-JSON,
    not a different kind of malformed response — the Anthropic SDK does not
    expose the raw stop_reason to us when its own JSON parsing fails (see
    docs/evidence.md for the underlying SDK behavior this works around).
    """

    def __init__(self, message: str, *, likely_truncated: bool = False):
        super().__init__(message)
        self.likely_truncated = likely_truncated


class ModelProvider(Protocol):
    async def complete_structured(
        self, *, system_prompt: str, user_prompt: str, output_schema: type[T], model: str
    ) -> T: ...


class MockProvider:
    """Deterministic offline provider. No network calls. Safe for tests and dev."""

    name = "mock"

    async def complete_structured(
        self, *, system_prompt: str, user_prompt: str, output_schema: type[T], model: str
    ) -> T:
        with timer() as elapsed:
            result = self._dispatch(output_schema, user_prompt)
        # MockProvider never returns real token counts — recording api_calls
        # only, with tokens left unset, keeps USAGE from being guessed.
        record_usage(ModelUsage(provider=self.name, model=model, elapsed_ms=elapsed()))
        return result

    def _dispatch(self, output_schema: type[T], user_prompt: str) -> T:
        try:
            context = json.loads(user_prompt)
        except (json.JSONDecodeError, TypeError):
            context = {"raw": user_prompt}

        if output_schema is ExecutionPlan:
            return self._plan(context)  # type: ignore[return-value]
        if output_schema is ResearchOutput:
            return self._research(context)  # type: ignore[return-value]
        if output_schema is GeneralResearchModelOutput:
            return self._general_research(context)  # type: ignore[return-value]
        if output_schema is DiscoveryModelOutput:
            return self._discovery_research(context)  # type: ignore[return-value]
        if output_schema is ValidationModelOutput:
            return self._validation_research(context)  # type: ignore[return-value]
        if output_schema is StrategyOutput:
            return self._strategy(context)  # type: ignore[return-value]
        if output_schema is ExecutionOutput:
            return self._execution(context)  # type: ignore[return-value]
        if output_schema is QAVerdict:
            return self._qa(context)  # type: ignore[return-value]
        if output_schema is ExecutiveReport:
            return self._report(context)  # type: ignore[return-value]
        raise ModelProviderError(f"MockProvider has no generator for schema {output_schema}")

    def _plan(self, context: dict) -> ExecutionPlan:
        objective = context.get("objective", "").strip() or "Unspecified objective"
        topics = _split_topics(objective)
        research_keys = []
        tasks: list[TaskPlan] = []
        for i, topic in enumerate(topics, start=1):
            key = f"research_{i}"
            research_keys.append(key)
            tasks.append(
                TaskPlan(
                    key=key,
                    title=f"Research: {topic}",
                    description=f"Investigate '{topic}' relevant to the objective: {objective}",
                    agent_type="research",
                    dependencies=[],
                    success_criteria="Findings are structured with evidence labeled FACT/ASSUMPTION/UNKNOWN.",
                )
            )
        tasks.append(
            TaskPlan(
                key="strategy_1",
                title="Synthesize strategy and recommendation",
                description=f"Compare findings and recommend the strongest option for: {objective}",
                agent_type="strategy",
                dependencies=research_keys,
                success_criteria="A single ranked recommendation with explicit reasoning and risks.",
            )
        )
        tasks.append(
            TaskPlan(
                key="qa_1",
                title="Quality-review the strategic recommendation",
                description="Validate the strategy output for unsupported claims and completeness.",
                agent_type="qa",
                dependencies=["strategy_1"],
                success_criteria="PASS, FAIL, or NEEDS_REVIEW verdict with actionable feedback.",
            )
        )
        return ExecutionPlan(
            objective=objective,
            tasks=tasks,
            estimated_complexity="medium" if len(topics) > 1 else "low",
            requires_approval=False,
            success_criteria="An evidence-based recommendation that passes QA review.",
        )

    def _research(self, context: dict) -> ResearchOutput:
        question = context.get("question") or context.get("title") or "Unspecified research question"
        topic = question.replace("Research:", "").strip()
        generated_at = datetime.now(timezone.utc).isoformat()
        findings = [
            ResearchFinding(
                claim=(
                    f"[DEVELOPMENT/SAMPLE DATA — no live web research is connected in this "
                    f"environment] '{topic}' is a plausible area of interest based on the "
                    f"objective text alone; no external sources were queried."
                ),
                evidence_type="ASSUMPTION",
                source=None,
                confidence=0.3,
            ),
            ResearchFinding(
                claim=(
                    f"Research request for '{topic}' was recorded at {generated_at}; a live "
                    f"search/browse provider is not configured (see ResearchProvider)."
                ),
                evidence_type="UNKNOWN",
                source=None,
                confidence=0.0,
            ),
        ]
        return ResearchOutput(
            question=topic,
            findings=findings,
            assumptions=[
                "Live web research is unavailable in this environment; findings above are "
                "placeholders and must not be treated as verified facts."
            ],
            insufficient_evidence=True,
            summary=(
                f"No live research capability is connected for '{topic}'. This output is "
                f"clearly-labeled development/sample data, not verified research."
            ),
        )

    # --- Compact Research DTOs (v0.1.2.1 grammar-size patch) ---------------
    #
    # Mirrors _research()'s exact dev-mode "no live research connected"
    # framing, but in the small DTO shape ResearchAgent's DISCOVERY/
    # VALIDATION/GENERAL modes actually request now — see
    # app/schemas/research_dto.py.

    def _general_research(self, context: dict) -> GeneralResearchModelOutput:
        question = context.get("question") or context.get("title") or "Unspecified research question"
        topic = question.replace("Research:", "").strip()
        generated_at = datetime.now(timezone.utc).isoformat()
        return GeneralResearchModelOutput(
            findings=[
                f"[DEVELOPMENT/SAMPLE DATA — no live web research is connected in this "
                f"environment] '{topic}' is a plausible area of interest based on the "
                f"objective text alone; no external sources were queried.",
                f"Research request for '{topic}' was recorded at {generated_at}; a live "
                f"search/browse provider is not configured (see ResearchProvider).",
            ],
            assumptions=[
                "Live web research is unavailable in this environment; findings above are "
                "placeholders and must not be treated as verified facts."
            ],
            insufficient_evidence=True,
            summary=(
                f"No live research capability is connected for '{topic}'. This output is "
                f"clearly-labeled development/sample data, not verified research."
            ),
        )

    def _discovery_research(self, context: dict) -> DiscoveryModelOutput:
        question = context.get("question") or context.get("title") or "Unspecified objective"
        topics = _split_topics(question)
        has_evidence = bool(context.get("evidence"))
        return DiscoveryModelOutput(
            candidates=[
                DiscoveryCandidateProposal(
                    label=topic, description=f"[MOCK/DEV DATA] Candidate proposal for: {topic}."
                )
                for topic in topics
            ],
            findings=[f"[DEVELOPMENT/SAMPLE DATA] Identified {len(topics)} candidate(s) for: {question}"],
            insufficient_evidence=not has_evidence,
            summary=f"Identified {len(topics)} candidate opportunity(ies) for: {question}.",
        )

    def _validation_research(self, context: dict) -> ValidationModelOutput:
        candidates = context.get("candidates") or []
        names = ", ".join(c.get("label", "?") for c in candidates if isinstance(c, dict)) or "(none)"
        has_evidence = bool(context.get("evidence"))
        return ValidationModelOutput(
            findings=[f"[DEVELOPMENT/SAMPLE DATA] Validation findings for: {names}"],
            insufficient_evidence=not has_evidence,
            summary=f"Validated candidate(s): {names}.",
        )

    def _strategy(self, context: dict) -> StrategyOutput:
        research_results = context.get("research_results", [])
        options = []
        for i, r in enumerate(research_results, start=1):
            options.append(
                StrategyOption(
                    name=r.get("question", f"Option {i}"),
                    advantages=["Aligned with stated objective (unverified — see assumptions)."],
                    risks=["Underlying research is sample/development data, not live evidence."],
                    supporting_evidence=[f.get("claim", "") for f in r.get("findings", [])[:1]],
                )
            )
        if not options:
            options.append(
                StrategyOption(
                    name="No researched options available",
                    advantages=[],
                    risks=["No research input was provided to strategy synthesis."],
                    supporting_evidence=[],
                )
            )
        top = options[0]
        return StrategyOutput(
            options_considered=options,
            recommendation=(
                f"Provisionally recommend '{top.name}', pending real research once a live "
                f"research provider is connected."
            ),
            reasoning=(
                "Recommendation is based on ordering of the provided research tasks only, "
                "since underlying research data is development/sample data, not verified evidence."
            ),
            assumptions=[
                "All supporting research is unverified sample data.",
                "No competitive or market data has been independently confirmed.",
            ],
            confidence=0.25,
        )

    def _execution(self, context: dict) -> ExecutionOutput:
        title = context.get("title", "task")
        return ExecutionOutput(
            actions_performed=[f"Recorded internal draft/state update for: {title}"],
            artifacts=[],
            notes="Execution Agent operated within READ+WRITE permissions; no external action taken.",
            blocked_on_approval=False,
        )

    def _qa(self, context: dict) -> QAVerdict:
        output = context.get("output", {})
        issues: list[str] = []
        unsupported: list[str] = []

        if isinstance(output, dict):
            if output.get("insufficient_evidence"):
                issues.append("Underlying research reports insufficient evidence.")
            recommendation = output.get("recommendation")
            assumptions = output.get("assumptions") or []
            if recommendation and not assumptions:
                unsupported.append(
                    "Recommendation given without any stated assumptions or evidence caveats."
                )
        else:
            issues.append("Output was not structured as expected.")

        if issues or unsupported:
            verdict = "NEEDS_REVIEW"
            score = 0.5
        else:
            verdict = "PASS"
            score = 0.85

        return QAVerdict(
            verdict=verdict,
            score=score,
            issues=issues,
            unsupported_claims=unsupported,
            feedback=(
                "Flag clearly that findings are development/sample data until a live research "
                "provider is connected."
                if issues or unsupported
                else "Output is internally consistent and properly labels assumptions."
            ),
        )

    def _report(self, context: dict) -> ExecutiveReport:
        return ExecutiveReport(
            objective=context.get("objective", ""),
            status=context.get("status", "COMPLETED"),
            what_was_done=context.get("what_was_done", []),
            key_findings=context.get("key_findings", []),
            evidence=context.get("evidence", []),
            recommendation=context.get("recommendation", "No recommendation available."),
            risks=context.get("risks", []),
            assumptions=context.get("assumptions", []),
            open_questions=context.get("open_questions", []),
            next_actions=context.get("next_actions", []),
            approvals_required=context.get("approvals_required", []),
        )


class OpenAIProvider:
    """Live provider backed by the OpenAI API's structured-output parsing."""

    name = "openai"

    def __init__(self, api_key: str):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)

    async def complete_structured(
        self, *, system_prompt: str, user_prompt: str, output_schema: type[T], model: str
    ) -> T:
        with timer() as elapsed:
            completion = await self._client.chat.completions.parse(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=output_schema,
            )
        elapsed_ms = elapsed()
        parsed = completion.choices[0].message.parsed
        if parsed is None:
            raise ModelProviderError("OpenAI response did not contain a parsed structured object.")

        usage = getattr(completion, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        record_usage(
            ModelUsage(
                provider=self.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                elapsed_ms=elapsed_ms,
            )
        )
        return parsed


class AnthropicProvider:
    """Live provider backed by the Anthropic API's structured-output parsing.

    Uses the official `anthropic` SDK's `messages.parse()` helper, which validates
    the response against the given Pydantic schema the same way OpenAIProvider does.
    """

    name = "anthropic"

    _MAX_TOKENS = 4096

    def __init__(self, api_key: str, *, workspace_id: str | None = None):
        from anthropic import AsyncAnthropic

        # Only added when configured: a workspace-scoped API key doesn't need
        # (and doesn't have) a workspace id, and must keep working exactly as
        # before. Only an unscoped key requires this header, per Anthropic's
        # "this API key is not scoped to a workspace" error.
        client_kwargs: dict = {"api_key": api_key}
        if workspace_id:
            client_kwargs["default_headers"] = {"anthropic-workspace-id": workspace_id}
        self._client = AsyncAnthropic(**client_kwargs)

    # A malformed/truncated structured response OR a response that simply
    # carries no parsed object at all gets exactly one repair attempt —
    # asking for a more concise, strictly-JSON answer, not the same huge one
    # again — before giving up. This lives entirely inside a single
    # complete_structured() call and never touches MAX_AGENT_RETRIES; from
    # the mission retry budget's point of view this whole thing is still
    # "one attempt" (see _retry_or_raise below, and
    # app/orchestration/evaluator.py::run_worker_with_qa's `attempt` counter,
    # which is never incremented by this).
    _REPAIR_HINT = (
        "\n\nIMPORTANT: Your previous response to this exact request could not be used — "
        "either it was not valid JSON matching the required schema, or no structured output "
        "was returned at all. On this attempt:\n"
        "- Return ONLY a single JSON object matching the required schema. No commentary, "
        "no markdown, no code fences, no text before or after the JSON.\n"
        "- Keep the same semantic task, the same underlying facts, and the same reasoning as "
        "before — do not change what you are answering, only how concisely you write it.\n"
        "- Preserve every evidence id exactly as given; never invent, drop, or alter one.\n"
        "- Return a SIGNIFICANTLY MORE CONCISE structured response: shorten optional prose "
        "fields aggressively and use fewer items in any list the schema allows to vary in "
        "length, so the response fits well within the token limit and cannot be cut off."
    )
    _MAX_DIAGNOSTIC_CHARS = 300

    async def complete_structured(
        self, *, system_prompt: str, user_prompt: str, output_schema: type[T], model: str
    ) -> T:
        return await self._complete_structured_once(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
            model=model,
            is_repair_attempt=False,
        )

    async def _complete_structured_once(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model: str,
        is_repair_attempt: bool,
    ) -> T:
        import anthropic
        import pydantic

        from app.agents.usage import current_diagnostic_context
        from app.research_intelligence.prompt_diagnostics import build_request_diagnostic

        # Defect 1 (v0.1.2.4): built IMMEDIATELY BEFORE the SDK call, from
        # the EXACT arguments about to be sent — never a separate,
        # possibly-divergent measurement path. Safe metadata only (see
        # ModelRequestDiagnostic) — no prompt content, no secrets.
        #
        # `diagnostic_context` is read from a ContextVar (see
        # app/agents/usage.py::with_diagnostic_context), not a
        # complete_structured() parameter — that keeps the ModelProvider
        # Protocol's signature (and every test double implementing it)
        # completely unchanged; only the caller (app/agents/research.py)
        # and this one real provider need to know about it.
        diagnostic = build_request_diagnostic(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_schema=output_schema,
            diagnostic_context=current_diagnostic_context(),
        )

        with timer() as elapsed:
            try:
                response = await self._client.messages.parse(
                    model=model,
                    max_tokens=self._MAX_TOKENS,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    output_format=output_schema,
                )
            except anthropic.AuthenticationError as exc:
                raise ModelAuthenticationError(
                    "Authentication failed: Anthropic rejected the API key (HTTP 401)."
                ) from exc
            except anthropic.RateLimitError as exc:
                raise ModelRateLimitError(
                    "Rate limited: Anthropic returned HTTP 429 for this request."
                ) from exc
            except anthropic.PermissionDeniedError as exc:
                message = _anthropic_error_message(exc)
                if _looks_like_billing_issue(message):
                    raise ModelBillingError(f"Billing/credit issue: {message}") from exc
                raise ModelInvalidRequestError(f"Permission denied (HTTP 403): {message}") from exc
            except anthropic.NotFoundError as exc:
                raise ModelInvalidRequestError(
                    f"Invalid model: Anthropic could not find model '{model}' (HTTP 404)."
                ) from exc
            except anthropic.BadRequestError as exc:
                message = _anthropic_error_message(exc)
                if _looks_like_billing_issue(message):
                    raise ModelBillingError(f"Billing/credit issue: {message}") from exc
                raise ModelInvalidRequestError(
                    f"Invalid request (HTTP 400): {message}"
                ) from exc
            except anthropic.APIConnectionError as exc:
                raise ModelConnectionError(
                    "Network/transient failure: could not connect to the Anthropic API."
                ) from exc
            except (pydantic.ValidationError, ValueError) as exc:
                # messages.parse() validates the model's JSON response against
                # output_schema internally (see anthropic/lib/_parse/_response.py);
                # on failure it raises this raw, with no access to the raw
                # Message (so no usage/stop_reason is recoverable for this
                # specific call) — a confirmed limitation of this SDK version,
                # not something worked around here. The API call still
                # happened, so it's still counted (tokens honestly left unset).
                # Malformed/truncated JSON and schema-validation failures both
                # land here (the SDK doesn't expose which) — both are
                # "structured output could not be parsed" and get the same
                # one repair attempt.
                record_usage(ModelUsage(provider=self.name, model=model, elapsed_ms=elapsed()))
                record_request_diagnostic(diagnostic)  # tokens unset — call failed before usage was reported
                return await self._retry_or_raise(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    output_schema=output_schema,
                    model=model,
                    is_repair_attempt=is_repair_attempt,
                    diagnostic_exc=exc,
                )
            except anthropic.APIStatusError as exc:
                raise ModelProviderError(
                    f"Anthropic API error (status {exc.status_code})."
                ) from exc

        elapsed_ms = elapsed()
        parsed = response.parsed_output
        if parsed is None:
            # Distinct failure mode from the exception branch above: the SDK
            # call itself succeeded (no exception), but carried no parsed
            # structured object at all — this used to raise immediately with
            # zero repair attempts (the confirmed live-benchmark bug: see
            # docs on Defect 2). It now gets exactly the same one repair
            # attempt as a validation failure, via the same _retry_or_raise.
            record_usage(ModelUsage(provider=self.name, model=model, elapsed_ms=elapsed_ms))
            record_request_diagnostic(diagnostic)  # tokens unset — no usable parsed response either
            return await self._retry_or_raise(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_schema=output_schema,
                model=model,
                is_repair_attempt=is_repair_attempt,
                diagnostic_exc=None,
            )

        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None) if usage else None
        output_tokens = getattr(usage, "output_tokens", None) if usage else None
        # Phase 1 (v0.1.2.4): provider-reported usage, recorded on the
        # diagnostic exactly as Anthropic reported it — never guessed. If a
        # future SDK version exposes additional usage categories (e.g.
        # cache-related token counts), they belong here too, read directly
        # off `usage`, never estimated.
        diagnostic.provider_input_tokens = input_tokens
        diagnostic.provider_output_tokens = output_tokens
        record_request_diagnostic(diagnostic)
        total_tokens = (
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None
        )
        record_usage(
            ModelUsage(
                provider=self.name,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                elapsed_ms=elapsed_ms,
            )
        )
        return parsed

    async def _retry_or_raise(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        output_schema: type[T],
        model: str,
        is_repair_attempt: bool,
        diagnostic_exc: Exception | None,
    ) -> T:
        """Single funnel for BOTH structured-output failure modes (a parse/
        validation exception, or a response with no parsed object at all) —
        exactly one repair attempt total, never two, regardless of which
        mode fired on the first attempt or which mode fires again on the
        repair attempt."""
        if not is_repair_attempt:
            return await self._complete_structured_once(
                system_prompt=system_prompt + self._REPAIR_HINT,
                user_prompt=user_prompt,
                output_schema=output_schema,
                model=model,
                is_repair_attempt=True,
            )
        if diagnostic_exc is not None:
            diagnostic = _bounded_diagnostic(diagnostic_exc, self._MAX_DIAGNOSTIC_CHARS)
            likely_truncated = _looks_like_truncation(str(diagnostic_exc))
            raise ModelOutputParsingError(
                f"Structured output could not be parsed: {diagnostic}",
                likely_truncated=likely_truncated,
            ) from diagnostic_exc
        raise ModelOutputParsingError(
            "Structured output could not be parsed: Anthropic response did not contain a "
            "parsed structured object, even after one repair attempt."
        )


def _anthropic_error_message(exc) -> str:
    """Pulls Anthropic's own human-readable message out of an error body —
    never secret, always safe to include in a raised exception's text."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        body_error = body.get("error")
        if isinstance(body_error, dict):
            message = body_error.get("message")
            if message:
                return str(message)
    return str(exc)


def _looks_like_billing_issue(message: str) -> bool:
    lowered = message.lower()
    return "credit balance" in lowered or ("insufficient" in lowered and "credit" in lowered)


def _looks_like_truncation(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in ("eof while parsing", "unterminated string", "unexpected end of")
    )


# Coarse, typed failure categories derived from each ModelProviderError
# subtype's own distinctive message prefix (defined right above/below —
# these are OUR OWN fixed templates, not the raw vendor error text). This
# lets callers like app/orchestration/executor.py::build_report react to
# *what kind* of provider failure occurred (from Task.error, the only place
# it survives once persisted — there is no separate typed-failure DB
# column) without ever hardcoding a specific vendor error string such as
# Anthropic's "compiled grammar is too large" message.
_ERROR_TEXT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("authentication failed", "AUTHENTICATION"),
    ("rate limited", "RATE_LIMIT"),
    ("billing/credit issue", "BILLING"),
    ("invalid request (http 400)", "INVALID_REQUEST"),
    ("invalid model", "INVALID_REQUEST"),
    ("permission denied", "INVALID_REQUEST"),
    ("network/transient failure", "CONNECTION"),
    ("structured output could not be parsed", "PARSING"),
)


def classify_error_text(error_text: str | None) -> str:
    """Maps a persisted Task.error string back to the coarse category of
    ModelProviderError that produced it — "AUTHENTICATION", "RATE_LIMIT",
    "BILLING", "INVALID_REQUEST" (covers a rejected/oversized request, e.g.
    Anthropic's compiled-grammar-too-large error), "CONNECTION", "PARSING",
    or "UNKNOWN" for anything else (including non-provider failures)."""
    lowered = (error_text or "").lower()
    for marker, category in _ERROR_TEXT_CATEGORIES:
        if marker in lowered:
            return category
    return "UNKNOWN"


def _bounded_diagnostic(exc: Exception, max_chars: int) -> str:
    """Never dumps a full model response into logs/exceptions — bounds
    whatever diagnostic text an underlying parsing exception carries."""
    text = str(exc)
    if len(text) > max_chars:
        return text[:max_chars] + "... [diagnostic truncated]"
    return text


def get_default_provider() -> ModelProvider:
    settings = get_settings()
    provider_name = settings.model_provider.strip().lower()

    if provider_name == "mock":
        logger.info("model_provider_selected", provider="mock", reason="explicit_mock_provider")
        return MockProvider()

    if provider_name == "openai":
        if settings.has_llm_credentials:
            logger.info("model_provider_selected", provider="openai")
            return OpenAIProvider(api_key=settings.openai_api_key)  # type: ignore[arg-type]
        logger.info("model_provider_selected", provider="mock", reason="no_openai_api_key")
        return MockProvider()

    if provider_name == "anthropic":
        if settings.has_llm_credentials:
            logger.info("model_provider_selected", provider="anthropic")
            return AnthropicProvider(
                api_key=settings.anthropic_api_key,  # type: ignore[arg-type]
                workspace_id=settings.anthropic_workspace_id,
            )
        logger.info("model_provider_selected", provider="mock", reason="no_anthropic_api_key")
        return MockProvider()

    raise ModelProviderError(
        f"Unknown MODEL_PROVIDER '{settings.model_provider}'. Expected 'openai', 'anthropic', or 'mock'."
    )


def _split_topics(objective: str, max_topics: int = 3) -> list[str]:
    import re

    lowered = objective.lower()
    match = re.search(r"\b(one|two|three|four|five|\d+)\b", lowered)
    count = _word_to_number(match.group(1)) if match else max_topics
    count = max(1, min(count, max_topics))

    parts = [p.strip() for p in re.split(r",| and ", objective) if p.strip()]
    if len(parts) >= count:
        return parts[:count]
    return [f"{objective} (angle {i + 1})" for i in range(count)]


def _word_to_number(word: str) -> int:
    mapping = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
    if word in mapping:
        return mapping[word]
    try:
        return int(word)
    except ValueError:
        return 3
