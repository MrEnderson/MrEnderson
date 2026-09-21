"""Executes READY tasks, respecting concurrency limits, permissions, and the
approval gate. Independent tasks run concurrently via asyncio.

Each concurrently-running task gets its OWN database session/transaction
(AsyncSession is not safe to share across concurrently-running coroutines) —
that is why this module takes a `session_factory`, not a single `session`.
Dependent tasks never run until the dispatcher has confirmed their dependencies
are COMPLETED in a committed transaction.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.registry import AgentRegistry
from app.agents.providers import classify_error_text
from app.agents.usage import collect_usage
from app.config.settings import Settings, get_settings
from app.database.connection import get_session_factory
from app.database.models import AgentRunStatus, PermissionLevel, RiskLevel, Task, TaskStatus
from app.database.repositories import AgentRunRepository
from app.memory.manager import MemoryManager
from app.orchestration import dispatcher
from app.orchestration.budget import check_budget
from app.orchestration.evaluator import WorkerExecutionError, run_worker_with_qa
from app.schemas.agents import QAVerdict
from app.schemas.evidence import EvidenceItem
from app.schemas.reports import AgentUsageBreakdown, ExecutiveReport, MissionUsage
from app.security.approvals import classify_risk
from app.security.evidence_qa import evaluate_evidence, merge_into_verdict
from app.security.permissions import PermissionDeniedError, check_permission
from app.services.approval_service import ApprovalService
from app.services.evidence_service import EvidenceService
from app.services.task_service import TaskService
from app.services.usage_service import UsageService
from app.utils.logging import get_logger

SessionFactory = Callable[[], AsyncSession]

logger = get_logger(__name__)


class AgentExecutor:
    def __init__(
        self,
        session_factory: SessionFactory,
        registry: AgentRegistry,
        provider,
        settings: Settings | None = None,
    ):
        self.session_factory = session_factory
        self.registry = registry
        self.provider = provider
        self.settings = settings or get_settings()
        self._semaphore = asyncio.Semaphore(self.settings.max_concurrent_agents)

    async def run_ready_tasks(self, *, workspace_id: str, project_id: str) -> list[Task]:
        async with self.session_factory() as session:
            ready = await dispatcher.get_ready_tasks(session, project_id=project_id)

        results = await asyncio.gather(
            *(self._run_one(workspace_id=workspace_id, task_id=t.id) for t in ready)
        )
        return [r for r in results if r is not None]

    async def _run_one(self, *, workspace_id: str, task_id: str) -> Task | None:
        async with self._semaphore:
            async with self.session_factory() as session:
                task_service = TaskService(session)
                approval_service = ApprovalService(session)
                run_repo = AgentRunRepository(session)
                memory = MemoryManager(session)

                task = await task_service.get(task_id)
                if task is None:
                    return None

                # Enter RUNNING first (matches the documented RUNNING -> NEEDS_APPROVAL /
                # RUNNING -> FAILED transitions) so both the permission check and the
                # approval gate below have a valid state to transition out of.
                await task_service.transition(task.id, TaskStatus.RUNNING, workspace_id=workspace_id)
                await session.commit()

                try:
                    check_permission(self.registry, task.agent_type, PermissionLevel.READ)
                except (PermissionDeniedError, KeyError) as exc:
                    result = await task_service.transition(
                        task.id, TaskStatus.FAILED, workspace_id=workspace_id, error=str(exc)
                    )
                    await session.commit()
                    return result

                gate_text = f"{task.title} {task.description or ''}"
                risk = classify_risk(gate_text)
                if task.requires_approval or risk is not None:
                    existing = await approval_service.approvals.get_for_task(task.id)
                    if existing is None:
                        await approval_service.request_approval(
                            workspace_id=workspace_id,
                            task_id=task.id,
                            requested_action=task.title,
                            risk_level=risk or RiskLevel.MEDIUM,
                            reason="Task matched an approval-required action pattern.",
                        )
                        await session.commit()
                        return None

                # Pre-call budget gate (v0.1.1 efficiency patch): re-checked
                # here, per task, not just once per dispatch batch in
                # run_objective — closes the gap where usage committed by
                # earlier tasks in the SAME concurrent batch pushed the
                # mission over budget before this task's turn. A task
                # deferred here goes to WAITING (resumable), never FAILED —
                # a budget stop is not a task failure. Mid-task retries are
                # additionally gated inside run_worker_with_qa via
                # `mission_usage` below, using a conservative reservation
                # for the next attempt rather than only already-committed
                # totals.
                usage_service = UsageService(session)
                mission_usage = await usage_service.totals_for_project(task.project_id)
                daily_cost = await usage_service.total_cost_for_workspace_today(workspace_id)
                pre_call_budget_reason = check_budget(
                    totals=mission_usage, daily_cost_usd=daily_cost, settings=self.settings
                )
                if pre_call_budget_reason:
                    result = await task_service.transition(
                        task.id, TaskStatus.WAITING, workspace_id=workspace_id
                    )
                    await session.commit()
                    logger.info(
                        "task_deferred_budget_limit", task_id=task.id, reason=pre_call_budget_reason
                    )
                    return result

                input_data = await self._build_input(task_service, task)

                known_evidence_ids: set[str] | None = None
                if task.agent_type in ("strategy", "qa"):
                    # Authoritative source for "does this evidence id actually
                    # exist" — the persisted Evidence table, which now shares
                    # ids with the EvidenceItems Strategy/QA actually saw (see
                    # app/database/repositories.py::EvidenceRepository.create).
                    # This is what closes the gap for the standalone `qa` task,
                    # whose input_data never carries research_results at all.
                    known_evidence_ids = {
                        e.id for e in await EvidenceService(session).list_for_project(task.project_id)
                    }

                run = await run_repo.create(
                    task_id=task.id,
                    agent_type=task.agent_type,
                    status=AgentRunStatus.RUNNING,
                    input_payload=input_data,
                )
                await session.commit()

                # Populated as soon as anything is known, in EITHER branch —
                # so if the try block below raises, whatever was already
                # accounted for is still available to the except handler
                # instead of being lost with the stack frame that raised.
                usage_events: list = []
                accumulated_evidence: list = []
                try:
                    if task.agent_type == "qa":
                        try:
                            with collect_usage() as events:
                                output = await self._run_qa_task(task, input_data)
                        finally:
                            usage_events = list(events)
                        evidence_check = evaluate_evidence(
                            input_data.get("output", {}),
                            input_data=input_data,
                            known_evidence_ids=known_evidence_ids,
                        )
                        output = merge_into_verdict(output, evidence_check)
                        output_data = output.model_dump(mode="json")
                        verdict = output.verdict
                        retries_used = 0
                    else:
                        agent = self.registry.create(task.agent_type, provider=self.provider)
                        qa_agent = self.registry.create("qa", provider=self.provider)
                        try:
                            eval_result = await run_worker_with_qa(
                                worker_agent=agent,
                                qa_agent=qa_agent,
                                title=task.title,
                                description=task.description or "",
                                input_data=input_data,
                                success_criteria=task.success_criteria,
                                max_retries=self.settings.max_agent_retries,
                                known_evidence_ids=known_evidence_ids,
                                mission_usage=mission_usage,
                            )
                        except WorkerExecutionError as exc:
                            usage_events = exc.usage_events
                            accumulated_evidence = exc.accumulated_evidence
                            raise
                        output_data = eval_result.output.model_dump(mode="json")
                        output_data["qa_verdict"] = eval_result.verdict.verdict
                        output_data["qa_score"] = eval_result.verdict.score
                        output_data["qa_feedback"] = eval_result.verdict.feedback
                        if eval_result.budget_stopped_reason:
                            output_data["budget_stopped_reason"] = eval_result.budget_stopped_reason
                        # v0.1.2.6 Phase 10: usage is still attributed to
                        # THIS task's agent_type in UsageService (unchanged,
                        # intentional — see app/orchestration/evaluator.py's
                        # ModelUsage.role docstring), but the actual
                        # worker-vs-QA call split is real, useful
                        # information that used to be invisible. Carried
                        # through Task.output_data (JSON, no migration —
                        # same pattern as every other provenance field in
                        # this project) so app/orchestration/executor.py::
                        # build_report can surface it per task.
                        # v0.1.2.7 Phase 8: is_model_call filters out
                        # non-LLM provider calls (e.g. Tavily search/extract,
                        # issued by the worker inside this same collect_usage
                        # block) that used to be counted as worker MODEL
                        # calls just because they shared role == "worker" —
                        # see app/agents/usage.py::ModelUsage.is_model_call.
                        output_data["worker_model_calls"] = sum(
                            e.api_calls
                            for e in eval_result.usage_events
                            if e.role == "worker" and e.is_model_call
                        )
                        output_data["qa_model_calls"] = sum(
                            e.api_calls for e in eval_result.usage_events if e.role == "qa" and e.is_model_call
                        )
                        retries_used = eval_result.attempts_used
                        verdict = eval_result.verdict.verdict
                        usage_events = eval_result.usage_events
                        accumulated_evidence = eval_result.accumulated_evidence
                        await self._maybe_promote_memory(memory, workspace_id, task, output_data)

                    await self._maybe_persist_evidence(session, workspace_id, task, accumulated_evidence)
                    await UsageService(session).record_many(
                        workspace_id=workspace_id,
                        project_id=task.project_id,
                        task_id=task.id,
                        agent_type=task.agent_type,
                        events=usage_events,
                    )

                    await run_repo.complete(run.id, AgentRunStatus.SUCCEEDED, output=output_data)
                    task_row = await task_service.get(task.id)
                    if task_row is not None:
                        task_row.retry_count = retries_used
                    updated = await task_service.transition(
                        task.id, TaskStatus.COMPLETED, workspace_id=workspace_id, output_data=output_data
                    )
                    await session.commit()
                    logger.info(
                        "task_completed", task_id=task.id, agent_type=task.agent_type, qa_verdict=verdict
                    )
                    return updated
                except Exception as exc:  # noqa: BLE001 - task failures must never crash the run
                    # Every completed provider call up to the point of
                    # failure — including ones from earlier, fully successful
                    # retry attempts within this same task — still happened
                    # and still gets accounted for. See
                    # app/orchestration/evaluator.py::WorkerExecutionError.
                    await self._maybe_persist_evidence(session, workspace_id, task, accumulated_evidence)
                    if usage_events:
                        await UsageService(session).record_many(
                            workspace_id=workspace_id,
                            project_id=task.project_id,
                            task_id=task.id,
                            agent_type=task.agent_type,
                            events=usage_events,
                        )
                    await run_repo.complete(run.id, AgentRunStatus.FAILED, error=str(exc))
                    logger.error(
                        "task_failed", task_id=task.id, agent_type=task.agent_type, error=str(exc)
                    )
                    result = await task_service.transition(
                        task.id, TaskStatus.FAILED, workspace_id=workspace_id, error=str(exc)
                    )
                    await session.commit()
                    return result

    async def _run_qa_task(self, task: Task, input_data: dict) -> QAVerdict:
        qa_agent = self.registry.create("qa", provider=self.provider)
        return await qa_agent.run(
            title=task.title, description=task.description or "", input_data=input_data, context={}
        )

    async def _build_input(self, task_service: TaskService, task: Task) -> dict:
        base = task_service.parse_input(task) or {}
        deps = await task_service.tasks.get_dependencies(task.id)
        dep_outputs = []
        for dep in deps:
            dep_task = await task_service.get(dep.depends_on_task_id)
            if dep_task is not None:
                dep_outputs.append(
                    {
                        "task_id": dep_task.id,
                        "title": dep_task.title,
                        "agent_type": dep_task.agent_type,
                        **(task_service.parse_output(dep_task) or {}),
                    }
                )

        if task.agent_type == "strategy":
            base["research_results"] = dep_outputs
        elif task.agent_type == "qa" and dep_outputs:
            base["output"] = {
                k: v for k, v in dep_outputs[0].items() if k not in ("task_id", "title", "agent_type")
            }
            base["success_criteria"] = task.success_criteria
        elif task.agent_type == "research":
            # Candidate Discovery -> Validation handoff (v0.1.2.1): a
            # VALIDATION research task depends on a DISCOVERY research task
            # through the existing Task dependency graph — no new
            # orchestration mechanism. Whatever candidates any dependency
            # discovered flow straight into this task's input; ResearchAgent
            # treats their presence as validation intent even if
            # research_mode itself wasn't explicitly set (see
            # app/agents/research.py::_resolve_research_mode).
            candidates: list = []
            seen_ids: set[str] = set()
            for dep in dep_outputs:
                for c in dep.get("candidates") or []:
                    cid = c.get("id") if isinstance(c, dict) else None
                    if cid and cid in seen_ids:
                        continue
                    if cid:
                        seen_ids.add(cid)
                    candidates.append(c)
            if candidates:
                base["candidates"] = candidates
            # Evidence provenance (v0.1.2.3): lets ResearchAgent stamp
            # every EvidenceItem it gathers with the Task that produced it
            # — see app/schemas/evidence.py::EvidenceItem.research_task_id.
            base["task_id"] = task.id
        base.setdefault("title", task.title)
        base.setdefault("question", task.title)
        return base

    async def _maybe_persist_evidence(
        self, session: AsyncSession, workspace_id: str, task: Task, items: list[EvidenceItem]
    ) -> None:
        if not items:
            return
        await EvidenceService(session).store_many(
            workspace_id=workspace_id, project_id=task.project_id, task_id=task.id, items=items
        )

    async def _maybe_promote_memory(
        self, memory: MemoryManager, workspace_id: str, task: Task, output_data: dict
    ) -> None:
        if task.agent_type == "research":
            await memory.promote_research(
                workspace_id,
                question=task.title,
                summary=output_data.get("summary", ""),
                insufficient_evidence=bool(output_data.get("insufficient_evidence")),
            )
        elif task.agent_type == "strategy" and output_data.get("qa_verdict") == "PASS":
            await memory.promote_decision(
                workspace_id,
                title=f"Recommendation: {task.title}",
                content=output_data.get("recommendation", ""),
            )


async def run_objective(
    session: AsyncSession,
    registry: AgentRegistry,
    provider,
    *,
    workspace_id: str,
    project_id: str,
    objective: str,
    settings: Settings | None = None,
) -> ExecutiveReport:
    """Full run: plan -> persist -> dispatch/execute loop -> executive report.

    `session` is used for the sequential planning/dispatch/report phases. The
    concurrent execution phase uses its own sessions (see AgentExecutor) and
    `session.expire_all()` is called afterwards so subsequent reads on `session`
    see what those other transactions committed.
    """
    from app.orchestration.planner import create_plan

    settings = settings or get_settings()
    jarvis = registry.create("jarvis", provider=provider)
    start_time = time.monotonic()

    with collect_usage() as planning_events:
        plan = await create_plan(jarvis, objective)
    await UsageService(session).record_many(
        workspace_id=workspace_id,
        project_id=project_id,
        task_id=None,
        agent_type="jarvis",
        events=planning_events,
    )
    await dispatcher.persist_plan(session, workspace_id=workspace_id, project_id=project_id, plan=plan)
    await session.commit()

    executor = AgentExecutor(get_session_factory(), registry, provider, settings)

    budget_stopped_reason: str | None = None
    iterations = 0
    while iterations < settings.max_tasks_per_run:
        budget_stopped_reason = await _check_mission_budget(
            session, workspace_id=workspace_id, project_id=project_id, settings=settings
        )
        if budget_stopped_reason:
            from app.security.audit import AuditEventType, record_event

            await record_event(
                session,
                workspace_id=workspace_id,
                actor_type="system",
                event_type=AuditEventType.BUDGET_LIMIT_REACHED,
                entity_type="project",
                entity_id=project_id,
                metadata={"reason": budget_stopped_reason},
            )
            await session.commit()
            break

        await dispatcher.promote_ready_tasks(session, workspace_id=workspace_id, project_id=project_id)
        await session.commit()
        ready = await dispatcher.get_ready_tasks(session, project_id=project_id)
        if not ready:
            break
        batch_results = await executor.run_ready_tasks(workspace_id=workspace_id, project_id=project_id)
        session.expire_all()
        iterations += len(ready)

        # Mid-batch budget stop (v0.1.1 efficiency patch): a task may have
        # been deferred to WAITING (couldn't even start) or completed with a
        # retry cut short (see AgentExecutor._run_one /
        # app/orchestration/evaluator.py::run_worker_with_qa) because the
        # mission budget was reached DURING this batch — don't wait for the
        # next iteration's coarser pre-batch check to notice.
        mid_batch_reason = _scan_batch_for_budget_stop(batch_results)
        if mid_batch_reason:
            from app.security.audit import AuditEventType, record_event

            budget_stopped_reason = mid_batch_reason
            await record_event(
                session,
                workspace_id=workspace_id,
                actor_type="system",
                event_type=AuditEventType.BUDGET_LIMIT_REACHED,
                entity_type="project",
                entity_id=project_id,
                metadata={"reason": budget_stopped_reason},
            )
            await session.commit()
            break

    elapsed_seconds = time.monotonic() - start_time

    return await build_report(
        session,
        jarvis,
        workspace_id=workspace_id,
        project_id=project_id,
        objective=objective,
        elapsed_seconds=elapsed_seconds,
        budget_stopped_reason=budget_stopped_reason,
    )


# Report cleanup (v0.1.2.3): a QA feedback string that ends up embedded
# into a report list item (OPEN QUESTIONS) is bounded to a short summary —
# evidence_qa.py::merge_into_verdict can concatenate several issues into
# one long paragraph, and that must never become a raw multi-paragraph
# essay in the report.
_REPORT_TEXT_MAX_CHARS = 300


def _bounded_report_text(text: str) -> str:
    import re as _re

    normalized = _re.sub(r"\s+", " ", text or "").strip()
    if len(normalized) <= _REPORT_TEXT_MAX_CHARS:
        return normalized
    return normalized[:_REPORT_TEXT_MAX_CHARS].rstrip() + " [truncated]"


def _scan_batch_for_budget_stop(batch_results: list[Task]) -> str | None:
    """Looks for either budget-stop signal a just-finished batch may carry:
    a task deferred to WAITING before it could even start, or a task that
    COMPLETED normally but had a retry cut short (see
    AgentExecutor._run_one and evaluator.run_worker_with_qa). Returns the
    first reason found, or None."""
    for task in batch_results:
        if task.status == TaskStatus.WAITING:
            return "Mission budget reached — a task was deferred before it could start."
        if task.status == TaskStatus.COMPLETED:
            output = TaskService.parse_output(task) or {}
            reason = output.get("budget_stopped_reason")
            if reason:
                return reason
    return None


async def _check_mission_budget(
    session: AsyncSession, *, workspace_id: str, project_id: str, settings: Settings
) -> str | None:
    usage_service = UsageService(session)
    totals = await usage_service.totals_for_project(project_id)
    daily_cost = await usage_service.total_cost_for_workspace_today(workspace_id)
    return check_budget(totals=totals, daily_cost_usd=daily_cost, settings=settings)


async def build_report(
    session: AsyncSession,
    jarvis,
    *,
    workspace_id: str,
    project_id: str,
    objective: str,
    elapsed_seconds: float | None = None,
    budget_stopped_reason: str | None = None,
) -> ExecutiveReport:
    from app.database.models import ApprovalStatus
    from app.security.audit import AuditEventType, record_event

    task_service = TaskService(session)
    approval_service = ApprovalService(session)
    usage_service = UsageService(session)

    tasks = await task_service.list_for_project(project_id)
    completed = [t for t in tasks if t.status == TaskStatus.COMPLETED]
    failed = [t for t in tasks if t.status == TaskStatus.FAILED]
    not_started = [
        t
        for t in tasks
        if t.status in (TaskStatus.PLANNED, TaskStatus.READY, TaskStatus.WAITING)
    ]
    pending_approvals = await approval_service.list_for_workspace(
        workspace_id, status=ApprovalStatus.PENDING
    )

    what_was_done, key_findings, evidence, risks, assumptions, open_questions = [], [], [], [], [], []
    recommendation = "No recommendation available yet."

    research_insufficient = False
    any_non_passing_verdict = False
    evidence_pool: dict[str, EvidenceItem] = {}
    rejected_evidence_count = 0
    rejected_evidence_reasons: dict[str, int] = {}
    cited_evidence_ids: set[str] = set()
    comparison_ready: bool | None = None
    evidence_coverage_lines: list[str] = []
    critical_gaps: list[str] = []
    other_material_gaps: list[str] = []
    next_research: list[str] = []
    # v0.1.2.6 Phase 9: OPEN QUESTIONS used to be a catch-all for actual
    # questions + unresolved evidence gaps + QA feedback + unsupported-claim
    # warnings. Split into their own report concepts — see
    # app/schemas/reports.py::ExecutiveReport.
    unresolved_evidence_gaps: list[str] = []
    qa_notes: list[str] = []
    unsupported_claims: list[str] = []
    usage_role_breakdown: list[str] = []

    for t in completed:
        output = task_service.parse_output(t) or {}
        what_was_done.append(f"[{t.agent_type}] {t.title} — COMPLETED")
        if "worker_model_calls" in output or "qa_model_calls" in output:
            usage_role_breakdown.append(
                f"{t.agent_type.capitalize()} '{t.title}': worker model calls: "
                f"{output.get('worker_model_calls', 0)}, QA evaluator calls: {output.get('qa_model_calls', 0)}"
            )
        if t.agent_type == "research":
            key_findings.extend(f.get("claim", "") for f in output.get("findings", []))
            unsupported_claims.extend(output.get("unsupported_claims", []) or [])
            if output.get("insufficient_evidence"):
                open_questions.append(f"Insufficient evidence for: {t.title}")
                research_insufficient = True
            assumptions.extend(output.get("assumptions", []))
            open_questions.extend(output.get("open_questions", []))
            for gap in output.get("evidence_gaps", []) or []:
                if not gap.get("resolved"):
                    unresolved_evidence_gaps.append(
                        f"{gap.get('candidate_id') + ': ' if gap.get('candidate_id') else ''}"
                        f"({gap.get('gap_type')}) {gap.get('claim_or_question')}"
                    )
            for e in output.get("evidence", []) or []:
                try:
                    item = EvidenceItem.model_validate(e)
                except Exception:  # noqa: BLE001 - a malformed record must never break the report
                    continue
                # Report cleanup (v0.1.2.3) + Evidence Admission Gate
                # (v0.1.2.4 Defect 3/Phase 7): an item is excluded from the
                # main evidence section — never deleted, still in the
                # persisted Evidence table / audit trail — if EITHER it was
                # explicitly REJECTED by the admission gate (VALIDATION-mode
                # evidence that passed keyword relevance but failed
                # candidate-overlap/suitability — see
                # app/research_intelligence/admission.py) OR it scored
                # REJECT relevance directly (the older, coarser check,
                # still the only signal available for DISCOVERY/GENERAL
                # evidence, which never goes through the admission gate).
                # Before this fix, only the second check ran, which is
                # exactly why an off-topic MEDIUM-relevance item could
                # still reach evidence_details.
                if item.admission_status == "REJECTED" or item.relevance_label == "REJECT":
                    rejected_evidence_count += 1
                    for reason in item.admission_rejection_reasons or [item.rejection_reason or "IRRELEVANT_TOPIC"]:
                        if reason:
                            rejected_evidence_reasons[reason] = rejected_evidence_reasons.get(reason, 0) + 1
                    continue
                evidence_pool[item.id] = item
        if t.agent_type == "strategy":
            recommendation = output.get("recommendation", recommendation)
            assumptions.extend(output.get("assumptions", []))
            for opt in output.get("options_considered", []):
                risks.extend(opt.get("risks", []))
                evidence.extend(opt.get("supporting_evidence", []))
            unsupported_claims.extend(output.get("unsupported_claims", []) or [])
            cited_evidence_ids.update(output.get("evidence_used", []) or [])
            if "comparison_ready" in output:
                comparison_ready = output.get("comparison_ready")
            for status in output.get("candidate_statuses", []) or []:
                pct = round((status.get("coverage_percentage") or 0) * 100)
                readiness_word = "ready" if status.get("ready_for_comparison") else "not ready"
                evidence_coverage_lines.append(
                    f"{status.get('candidate_label', status.get('candidate_id', '?'))}: "
                    f"{pct}% coverage ({readiness_word})"
                )
            critical_gaps.extend(output.get("missing_requirements", []) or [])
            other_material_gaps.extend(output.get("other_material_gaps", []) or [])
            next_research.extend(output.get("remediation_queries", []) or [])
        qa_verdict = output.get("qa_verdict")
        if qa_verdict and qa_verdict != "PASS":
            any_non_passing_verdict = True
            # v0.1.2.6 Phase 9: QA NOTES is its own report concept, not
            # mixed into OPEN QUESTIONS — evidence_qa.py's merge_into_verdict
            # can concatenate several issues into one long feedback string,
            # bounded here exactly as before, just in the right section.
            qa_notes.append(
                f"'{t.title}' flagged {qa_verdict}: {_bounded_report_text(output.get('qa_feedback', ''))}"
            )

    # Typed failure categories (see app/agents/providers.py::classify_error_text)
    # — never a hardcoded vendor-specific error string. INVALID_REQUEST
    # covers a rejected/oversized request (e.g. Anthropic's compiled-
    # grammar-too-large error); PARSING covers a response that couldn't be
    # parsed into the structured schema. Both mean the RESEARCH MODEL call
    # itself failed, not that no live research happened.
    research_model_call_failed = False
    authentication_failure = False
    for t in failed:
        what_was_done.append(f"[{t.agent_type}] {t.title} — FAILED: {t.error}")
        risks.append(f"Task failed and could not complete: {t.title}")
        category = classify_error_text(t.error)
        if t.agent_type == "research" and category in ("PARSING", "INVALID_REQUEST"):
            research_model_call_failed = True
        if category == "AUTHENTICATION":
            authentication_failure = True

    approvals_required = [
        f"{a.requested_action} (risk={a.risk_level.value})" for a in pending_approvals
    ]

    # Evidence collected survives even a task that ultimately FAILED (see
    # app/orchestration/evaluator.py::WorkerExecutionError and
    # AgentExecutor._maybe_persist_evidence) — the persisted Evidence table
    # is the robust source of truth for "did live research actually happen,"
    # independent of whether the task that produced it later failed.
    persisted_evidence = await EvidenceService(session).list_for_project(project_id)
    research_evidence_present = bool(persisted_evidence)

    # A LIVE research attempt can still leave research_evidence_present
    # False — e.g. Tavily's search succeeded (and its own usage event is
    # recorded regardless — see app/orchestration/evaluator.py's exception
    # handling) but the SAME worker attempt's Research model call then
    # failed before any EvidenceItem was ever attached to a returned
    # ResearchOutput, so nothing reached EvidenceService. Usage records
    # from a non-LLM provider (Tavily today) are the authoritative signal
    # that live research was actually attempted, independent of whether
    # evidence ended up persisted or the task ultimately failed.
    usage_records = await usage_service.usage.list_for_project(project_id)
    live_research_attempted = any(r.provider not in ("anthropic", "openai", "mock") for r in usage_records)

    # A research task that ultimately FAILED never reaches `completed`, so
    # evidence_pool above may be empty even though real evidence was
    # gathered and persisted before the failure — fall back to the DB.
    if not evidence_pool and persisted_evidence:
        for e in persisted_evidence:
            evidence_pool[e.id] = EvidenceItem(
                id=e.id,
                claim=e.claim,
                source_title=e.source_title,
                source_url=e.source_url,
                publisher=e.publisher,
                published_at=e.published_at,
                retrieved_at=e.retrieved_at,
                excerpt=e.excerpt,
                evidence_type=e.evidence_type,
                confidence=e.confidence,
                query_used=e.query_used,
                verification_status=e.verification_status,
                source_quality=e.source_quality,
                evidence_depth=e.evidence_depth,
            )

    if budget_stopped_reason:
        status = "STOPPED_BUDGET_LIMIT"
    elif failed:
        status = "COMPLETED_WITH_FAILURES"
    elif pending_approvals:
        status = "NEEDS_APPROVAL"
    elif any_non_passing_verdict:
        status = "COMPLETED_WITH_REVIEW"
    else:
        status = "COMPLETED"

    # Report quality (v0.1.1 efficiency patch): when the mission stopped on
    # budget before a final QA verdict was reached, the recommendation must
    # read as a preliminary candidate, never as an unconditional launch
    # instruction — see docs on this phase's example ("Preliminary candidate
    # pending validation" vs. "Launch X first").
    final_qa_ran = bool(completed) and not any_non_passing_verdict and not not_started
    if budget_stopped_reason and not final_qa_ran and recommendation != "No recommendation available yet.":
        recommendation = (
            "PRELIMINARY — pending final QA validation (mission stopped before it could "
            f"complete): {recommendation}"
        )
    if budget_stopped_reason:
        for t in not_started:
            what_was_done.append(f"[{t.agent_type}] {t.title} — NOT STARTED (mission stopped)")

    # The evidence actually cited by Strategy is the most useful thing to show
    # a human; if nothing was cited yet, fall back to everything collected
    # rather than showing nothing. Capped so the report stays readable.
    if cited_evidence_ids:
        evidence_details = [evidence_pool[i] for i in cited_evidence_ids if i in evidence_pool]
    else:
        evidence_details = list(evidence_pool.values())
    evidence_details = evidence_details[:20]

    next_actions = []
    if pending_approvals:
        next_actions.append("Resolve pending approvals to continue.")
    if budget_stopped_reason:
        # A token/API-call safety limit is a FEATURE, not an obstacle
        # (Phase 13, v0.1.2.2) — never automatically suggest raising it.
        # Cost-based limits (estimated cost / daily cost) are a different
        # axis and keep the existing "raise the limit" framing.
        if "MAX_TOKENS_PER_MISSION" in budget_stopped_reason or "MAX_API_CALLS_PER_MISSION" in budget_stopped_reason:
            next_actions.append(
                f"Mission stopped at the configured token safety limit ({budget_stopped_reason}). "
                "Reduce/target the research context (e.g. a narrower validation scope) or "
                "continue validation in a new bounded mission, rather than raising the limit."
            )
        else:
            next_actions.append(
                f"Mission stopped early: {budget_stopped_reason}. Raise the limit or start a "
                "new run to continue."
            )
    if not pending_approvals and not budget_stopped_reason:
        if authentication_failure:
            next_actions.append("Fix provider authentication (see the failed task's error) and retry.")
        elif research_model_call_failed:
            next_actions.append("Resolve the Research model structured-output failure, then rerun the mission.")
        elif not research_evidence_present and not live_research_attempted:
            next_actions.append("Connect a live ResearchProvider to replace development/sample research data.")
        elif research_insufficient:
            next_actions.append("Run targeted follow-up research for unresolved evidence gaps.")

    usage_totals = await usage_service.totals_for_project(project_id)
    by_agent_provider_totals = await usage_service.breakdown_by_agent_and_provider(project_id)
    mission_usage = MissionUsage(
        by_agent=[
            AgentUsageBreakdown(
                agent_type=agent_type,
                provider=provider,
                model=model,
                api_calls=totals.api_calls,
                initial_calls=totals.initial_calls,
                retry_calls=totals.retry_calls,
                input_tokens=totals.input_tokens,
                output_tokens=totals.output_tokens,
                total_tokens=totals.total_tokens,
            )
            for (agent_type, provider, model), totals in sorted(by_agent_provider_totals.items())
        ],
        total_api_calls=usage_totals.api_calls,
        total_input_tokens=usage_totals.input_tokens,
        total_output_tokens=usage_totals.output_tokens,
        total_tokens=usage_totals.total_tokens,
        total_retries=sum(t.retry_count for t in tasks),
        elapsed_seconds=elapsed_seconds,
        estimated_cost_usd=usage_totals.estimated_cost_usd,
        pricing_configured=UsageService.pricing_configured(),
        budget_stopped_reason=budget_stopped_reason,
    )

    report = ExecutiveReport(
        objective=objective,
        status=status,
        what_was_done=what_was_done,
        key_findings=list(dict.fromkeys(key_findings)),
        evidence=list(dict.fromkeys(e for e in evidence if e)),
        evidence_details=evidence_details,
        recommendation=recommendation,
        rejected_evidence_count=rejected_evidence_count,
        rejected_evidence_reasons=dict(sorted(rejected_evidence_reasons.items())),
        risks=list(dict.fromkeys(risks)),
        assumptions=list(dict.fromkeys(assumptions)),
        open_questions=list(dict.fromkeys(open_questions)),
        unresolved_evidence_gaps=list(dict.fromkeys(unresolved_evidence_gaps)),
        qa_notes=list(dict.fromkeys(qa_notes)),
        unsupported_claims=list(dict.fromkeys(unsupported_claims)),
        usage_role_breakdown=usage_role_breakdown,
        next_actions=next_actions,
        approvals_required=approvals_required,
        usage=mission_usage,
        comparison_ready=comparison_ready,
        evidence_coverage=evidence_coverage_lines,
        critical_gaps=list(dict.fromkeys(critical_gaps)),
        other_material_gaps=list(dict.fromkeys(other_material_gaps)),
        next_research=list(dict.fromkeys(next_research)),
    )

    await record_event(
        session,
        workspace_id=workspace_id,
        actor_type="jarvis",
        event_type=AuditEventType.REPORT_GENERATED,
        entity_type="project",
        entity_id=project_id,
        metadata={"status": status},
    )
    await session.commit()
    return report
