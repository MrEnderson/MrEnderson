"""Phase 8: reproduces the exact live-benchmark report bug — Tavily
succeeded (HTTP 200), then the Research model call failed (compiled
grammar too large), and the report incorrectly recommended "Connect a live
ResearchProvider" even though one was already live. Offline — mirrors the
style of tests/test_report_lifecycle.py."""
from __future__ import annotations


async def test_live_tavily_usage_with_research_model_failure_does_not_suggest_connecting_provider(session_factory):
    from app.agents.usage import ModelUsage
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService
    from app.services.usage_service import UsageService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("liveresearch@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id,
            title="Discover candidate digital-product opportunities", agent_type="research",
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        # Tavily's own usage event is recorded (and persisted) regardless of
        # the LATER Anthropic failure in the same worker attempt — see
        # app/orchestration/evaluator.py's exception handling, which never
        # drops usage already captured before the failure.
        await UsageService(session).record_many(
            workspace_id=workspace_id, project_id=project_id, task_id=task_id, agent_type="research",
            events=[ModelUsage(provider="tavily", model="search", api_calls=1)],
        )
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.FAILED,
            workspace_id=workspace_id,
            error=(
                "Invalid request (HTTP 400): The compiled grammar is too large, which would "
                "cause performance issues. Simplify your tool schemas or reduce the number of "
                "strict tools."
            ),
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    assert not any("Connect a live ResearchProvider" in a for a in report.next_actions)
    assert any("structured-output" in a.lower() for a in report.next_actions)
    assert report.status == "COMPLETED_WITH_FAILURES"


async def test_no_live_research_and_research_model_failure_still_not_stale(session_factory):
    """Without any research-provider usage at all, the SAME typed failure
    category still wins over the generic 'connect a provider' fallback —
    the fix isn't just about the Tavily-usage signal, it's about
    recognizing the research-model failure category at all."""
    from app.database.models import TaskStatus
    from app.database.repositories import UserRepository, WorkspaceRepository
    from app.orchestration.executor import build_report
    from app.services.project_service import ProjectService
    from app.services.task_service import TaskService

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("noliveresearch@example.com")
        workspace = await WorkspaceRepository(session).create(user.id, "WS")
        project = await ProjectService(session).create_project(workspace.id, "Proj")
        ts = TaskService(session)
        task = await ts.create_task(
            workspace_id=workspace.id, project_id=project.id, title="Discover candidates", agent_type="research"
        )
        await session.commit()
        workspace_id, project_id, task_id = workspace.id, project.id, task.id

    async with session_factory() as session:
        ts = TaskService(session)
        await ts.transition(task_id, TaskStatus.READY, workspace_id=workspace_id)
        await ts.transition(task_id, TaskStatus.RUNNING, workspace_id=workspace_id)
        await ts.transition(
            task_id,
            TaskStatus.FAILED,
            workspace_id=workspace_id,
            error="Invalid request (HTTP 400): The compiled grammar is too large.",
        )
        await session.commit()

    async with session_factory() as session:
        report = await build_report(
            session, jarvis=None, workspace_id=workspace_id, project_id=project_id, objective="obj"
        )

    assert not any("Connect a live ResearchProvider" in a for a in report.next_actions)
    assert any("structured-output" in a.lower() for a in report.next_actions)


async def test_classify_error_text_recognizes_invalid_request_category():
    from app.agents.providers import classify_error_text

    assert classify_error_text(
        "Invalid request (HTTP 400): The compiled grammar is too large, which would cause "
        "performance issues. Simplify your tool schemas or reduce the number of strict tools."
    ) == "INVALID_REQUEST"
    assert classify_error_text("Structured output could not be parsed: EOF while parsing") == "PARSING"
    assert classify_error_text("Authentication failed: Anthropic rejected the API key (HTTP 401).") == "AUTHENTICATION"
    assert classify_error_text("some unrelated task error") == "UNKNOWN"
    assert classify_error_text(None) == "UNKNOWN"
