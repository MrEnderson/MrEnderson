"""Offline Research prompt-size diagnostics (v0.1.2.3, Defect 2). Reports
estimated serialized character size by component for a given Research
model call, without ever making a live provider call. Never includes
secrets — operates purely on the already-built system_prompt/prompt_context
(a plain dict of question/description/candidates/evidence/qa_feedback/
unresolved_gaps), which never carries API keys or credentials.
"""
from __future__ import annotations

import json

from pydantic import BaseModel


class PromptSizeReport(BaseModel):
    system_prompt_chars: int = 0
    question_title_description_chars: int = 0
    candidates_chars: int = 0
    evidence_chars: int = 0
    qa_feedback_chars: int = 0
    unresolved_gaps_chars: int = 0
    other_chars: int = 0
    total_request_chars: int = 0
    evidence_item_count: int = 0

    def to_text(self) -> str:
        lines = [
            f"system_prompt:              {self.system_prompt_chars:>8} chars",
            f"question/title/description: {self.question_title_description_chars:>8} chars",
            f"candidates:                 {self.candidates_chars:>8} chars",
            f"evidence ({self.evidence_item_count} items):        {self.evidence_chars:>8} chars",
            f"qa_feedback:                 {self.qa_feedback_chars:>8} chars",
            f"unresolved_gaps:             {self.unresolved_gaps_chars:>8} chars",
            f"other:                       {self.other_chars:>8} chars",
            f"TOTAL:                       {self.total_request_chars:>8} chars",
        ]
        return "\n".join(lines)


_KNOWN_COMPONENTS = ("question", "description", "candidates", "evidence", "qa_feedback", "unresolved_gaps")


def diagnose_prompt_size(*, system_prompt: str, prompt_context: dict) -> PromptSizeReport:
    """Deterministic, offline breakdown of what a Research model call's
    request is actually spending characters on — never makes a network
    call, never touches secrets (prompt_context is already the plain,
    model-facing dict built by app/agents/research.py; it never carries an
    API key). Use before a provider call to catch a regression before it
    ever reaches Anthropic."""
    question = prompt_context.get("question", "")
    description = prompt_context.get("description", "")
    candidates = prompt_context.get("candidates")
    evidence = prompt_context.get("evidence")
    qa_feedback = prompt_context.get("qa_feedback")
    unresolved_gaps = prompt_context.get("unresolved_gaps")

    other = {k: v for k, v in prompt_context.items() if k not in _KNOWN_COMPONENTS}

    report = PromptSizeReport(
        system_prompt_chars=len(system_prompt or ""),
        question_title_description_chars=len(str(question)) + len(str(description)),
        candidates_chars=len(json.dumps(candidates)) if candidates is not None else 0,
        evidence_chars=len(json.dumps(evidence)) if evidence is not None else 0,
        qa_feedback_chars=len(str(qa_feedback)) if qa_feedback is not None else 0,
        unresolved_gaps_chars=len(json.dumps(unresolved_gaps)) if unresolved_gaps is not None else 0,
        other_chars=len(json.dumps(other)) if other else 0,
        evidence_item_count=len(evidence) if isinstance(evidence, list) else 0,
    )
    report.total_request_chars = report.system_prompt_chars + len(json.dumps(prompt_context))
    return report


class ModelRequestDiagnostic(BaseModel):
    """v0.1.2.4 (Defect 1): captures SAFE metadata about the EXACT request
    about to be sent to the Anthropic SDK — built immediately before
    `messages.parse()`/`messages.create()`, never guessed, never
    containing prompt content or secrets. `output_schema_chars`/
    `tool_schema_chars` are the same measurement: for this project's
    structured-output usage, Anthropic compiles the Pydantic output
    schema into a strict tool definition, so the schema's own serialized
    size IS the tool-schema overhead. `message_count` is always 1 in this
    architecture (a single user message per call, never multi-turn).
    `provider_input_tokens`/`provider_output_tokens` are filled in AFTER
    the call, from Anthropic's own reported `usage` — never estimated."""

    agent_type: str | None = None
    model: str
    research_mode: str | None = None
    attempt_number: int | None = None
    system_chars: int = 0
    content_chars: int = 0
    output_schema_chars: int = 0
    tool_schema_chars: int = 0
    message_count: int = 1
    evidence_count: int = 0
    candidate_count: int = 0
    gap_count: int = 0
    provider_input_tokens: int | None = None
    provider_output_tokens: int | None = None
    total_request_chars_estimate: int = 0

    def to_text(self) -> str:
        lines = [
            f"agent_type={self.agent_type} research_mode={self.research_mode} attempt={self.attempt_number} model={self.model}",
            f"system_chars={self.system_chars} content_chars={self.content_chars} "
            f"output_schema_chars={self.output_schema_chars} tool_schema_chars={self.tool_schema_chars} "
            f"message_count={self.message_count}",
            f"evidence_count={self.evidence_count} candidate_count={self.candidate_count} gap_count={self.gap_count}",
            f"total_request_chars_estimate={self.total_request_chars_estimate}",
            f"provider_input_tokens={self.provider_input_tokens} provider_output_tokens={self.provider_output_tokens}",
        ]
        return "\n".join(lines)


def build_request_diagnostic(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    output_schema: type[BaseModel],
    diagnostic_context: dict | None = None,
) -> ModelRequestDiagnostic:
    """Built immediately before the Anthropic SDK call (see
    app/agents/providers.py::AnthropicProvider._complete_structured_once).
    `diagnostic_context` is the caller-supplied, agent-agnostic metadata
    dict (agent_type/research_mode/attempt_number/evidence_count/
    candidate_count/gap_count) — plain safe values only, never prompt
    content."""
    ctx = diagnostic_context or {}
    try:
        schema_chars = len(json.dumps(output_schema.model_json_schema()))
    except Exception:  # noqa: BLE001 - a diagnostic must never break the real call
        schema_chars = 0

    diagnostic = ModelRequestDiagnostic(
        agent_type=ctx.get("agent_type"),
        model=model,
        research_mode=ctx.get("research_mode"),
        attempt_number=ctx.get("attempt_number"),
        system_chars=len(system_prompt or ""),
        content_chars=len(user_prompt or ""),
        output_schema_chars=schema_chars,
        tool_schema_chars=schema_chars,
        message_count=1,
        evidence_count=ctx.get("evidence_count", 0),
        candidate_count=ctx.get("candidate_count", 0),
        gap_count=ctx.get("gap_count", 0),
    )
    diagnostic.total_request_chars_estimate = (
        diagnostic.system_chars + diagnostic.content_chars + diagnostic.output_schema_chars
    )
    return diagnostic


def format_diagnostic_summary(diagnostics: list[ModelRequestDiagnostic], *, title: str | None = None) -> str:
    """v0.1.2.5 Phase 11: a bounded, secret-free DEBUG summary — counts and
    sizes only, one block per attempt/retry. Never includes an API key,
    an Authorization header, a workspace id, a full prompt body, a full
    page extract, or any other prompt content — every field on
    ModelRequestDiagnostic is structurally a count/id/enum-like value (see
    test_provider_request_diagnostic.py), so there is nothing sensitive
    TO print here in the first place."""
    if not diagnostics:
        return "RESEARCH REQUEST DIAGNOSTICS\n(no diagnostics recorded for this attempt)"

    lines = ["RESEARCH REQUEST DIAGNOSTICS" + (f" — {title}" if title else "")]
    for diag in diagnostics:
        label = "attempt" if (diag.attempt_number or 0) == 0 else "retry"
        lines.append("")
        lines.append(f"{label} {diag.attempt_number if diag.attempt_number is not None else '?'}")
        lines.append(f"  agent_type: {diag.agent_type}")
        lines.append(f"  research_mode: {diag.research_mode}")
        lines.append(f"  model: {diag.model}")
        lines.append(f"  system_chars: {diag.system_chars}")
        lines.append(f"  content_chars: {diag.content_chars}")
        lines.append(f"  schema_chars: {diag.output_schema_chars}")
        lines.append(f"  message_count: {diag.message_count}")
        lines.append(f"  evidence_items: {diag.evidence_count}")
        lines.append(f"  candidate_count: {diag.candidate_count}")
        lines.append(f"  gap_count: {diag.gap_count}")
        lines.append(f"  request_chars (estimate): {diag.total_request_chars_estimate}")
        lines.append(f"  provider_input_tokens: {diag.provider_input_tokens}")
        lines.append(f"  provider_output_tokens: {diag.provider_output_tokens}")
    return "\n".join(lines)


_SECRET_MARKERS = ("api_key", "apikey", "secret", "token", "anthropic-workspace-id", "sk-ant-", "sk-")


def assert_no_secrets(report: PromptSizeReport, *, system_prompt: str, prompt_context: dict) -> None:
    """Defensive check for tests/diagnostics: the diagnostic report itself
    is just counts, but this verifies the underlying inputs it was built
    from don't contain anything that LOOKS like a credential — belt and
    suspenders, since prompt_context/system_prompt should never carry one
    in the first place (see app/agents/providers.py, which sends the API
    key only via the SDK client's own auth header, never in prompt text)."""
    haystacks = [system_prompt or "", json.dumps(prompt_context)]
    for haystack in haystacks:
        lowered = haystack.lower()
        for marker in _SECRET_MARKERS:
            if marker in lowered:
                raise AssertionError(f"Diagnostic input unexpectedly contains a secret-like marker: {marker!r}")
