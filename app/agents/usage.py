"""Model-usage accounting side channel (v0.1.1).

`ModelProvider.complete_structured()` must keep returning the parsed schema
object directly (every agent call site depends on that) — so usage can't ride
back as part of the return value. Instead each provider calls `record_usage()`
after its own API call, and callers wrap the calls they want to measure in
`collect_usage()`. This is a `contextvars.ContextVar`, so it is safe across the
concurrent `asyncio.gather` task execution in `app/orchestration/executor.py`:
each asyncio Task gets its own copy of the context, so concurrent tasks never
see each other's usage events.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from pydantic import BaseModel


class ModelUsage(BaseModel):
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    api_calls: int = 1
    elapsed_ms: float | None = None
    retry_number: int = 0
    # v0.1.2.6 Phase 10: which ACTUAL model-call role produced this event —
    # "worker" (the task's own agent, e.g. ResearchAgent/StrategyAgent) or
    # "qa" (the QA evaluator called from inside app/orchestration/
    # evaluator.py::run_worker_with_qa). Task-level attribution (a
    # Research task's usage rows are still recorded under agent_type=
    # "research" — see app/orchestration/executor.py) is UNCHANGED and
    # intentional; this is an ADDITIONAL, finer-grained dimension, never a
    # replacement. None for usage collected outside run_worker_with_qa
    # (e.g. the standalone "qa" task type, which has no separate worker
    # call to distinguish from).
    role: str | None = None
    # v0.1.2.7 Phase 8: whether this event is an actual LLM/model-provider
    # completion call — root cause of the "worker model calls: 16" defect,
    # where `role == "worker"` alone was treated as sufficient to count
    # toward worker_model_calls. `role` only tags WHO issued the call
    # (worker agent vs. QA evaluator, see above); it says nothing about
    # WHAT was called. A ResearchAgent's own Tavily search()/fetch() calls
    # happen INSIDE the same collect_usage() block as its one real
    # Anthropic complete_structured() call (see app/orchestration/
    # evaluator.py::run_worker_with_qa) and get tagged role="worker" right
    # alongside it — every Tavily call was being counted as a worker MODEL
    # call. Defaults True so every existing model-provider call site
    # (AnthropicProvider/OpenAIProvider/MockProvider) is unaffected; only
    # app/tools/research_tools.py's Tavily provider sets this False. See
    # app/orchestration/executor.py's worker_model_calls/qa_model_calls
    # computation, the only place this is read.
    is_model_call: bool = True


_collector: ContextVar[list[ModelUsage] | None] = ContextVar("_usage_collector", default=None)


def record_usage(usage: ModelUsage) -> None:
    events = _collector.get()
    if events is not None:
        events.append(usage)


@contextmanager
def collect_usage() -> Iterator[list[ModelUsage]]:
    events: list[ModelUsage] = []
    token = _collector.set(events)
    try:
        yield events
    finally:
        _collector.reset(token)


# v0.1.2.4: per-call request-size diagnostics (see
# app/research_intelligence/prompt_diagnostics.py::ModelRequestDiagnostic).
# Mirrors the collect_usage()/record_usage() side-channel pattern exactly —
# same ContextVar-per-asyncio-Task isolation, same "provider calls
# record(), caller wraps with collect()" shape. Logging/telemetry-only by
# design (Phase 2): never persisted to the database, never contains prompt
# content or secrets — see prompt_diagnostics.py for what's actually
# captured.
_diagnostic_collector: ContextVar[list | None] = ContextVar("_diagnostic_collector", default=None)


def record_request_diagnostic(diagnostic) -> None:
    events = _diagnostic_collector.get()
    if events is not None:
        events.append(diagnostic)


@contextmanager
def collect_request_diagnostics() -> Iterator[list]:
    events: list = []
    token = _diagnostic_collector.set(events)
    try:
        yield events
    finally:
        _diagnostic_collector.reset(token)


# Carries the CALLER-supplied safe metadata (agent_type/research_mode/
# attempt_number/evidence_count/candidate_count/gap_count — see
# app/research_intelligence/prompt_diagnostics.py::build_request_diagnostic)
# from app/agents/research.py down into AnthropicProvider's own call, one
# level below `complete_structured()`, WITHOUT adding a parameter to the
# ModelProvider Protocol — every existing test double implementing that
# Protocol's plain 4-argument signature keeps working unchanged; only the
# one real provider that cares reads this.
_diagnostic_context_var: ContextVar[dict | None] = ContextVar("_diagnostic_context", default=None)


def current_diagnostic_context() -> dict | None:
    return _diagnostic_context_var.get()


@contextmanager
def with_diagnostic_context(context: dict) -> Iterator[None]:
    token = _diagnostic_context_var.set(context)
    try:
        yield
    finally:
        _diagnostic_context_var.reset(token)


@contextmanager
def timer() -> Iterator[Callable[[], float]]:
    """Yields a function returning elapsed milliseconds since entry, on demand."""
    start = time.perf_counter()
    yield lambda: (time.perf_counter() - start) * 1000
