"""FastAPI app factory + development CLI.

Run the API:      uvicorn app.main:app --reload
Run the CLI:       python -m app.main
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.providers import get_default_provider
from app.agents.registry import build_default_registry
from app.config.settings import get_settings
from app.database.connection import get_session_factory, init_db
from app.database.repositories import UserRepository, WorkspaceRepository
from app.utils.logging import configure_logging, get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    from app.api.routes import router

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await init_db()
        logger.info("jarvis_api_started", environment=settings.jarvis_env)
        yield

    app = FastAPI(
        title="Jarvis OS",
        version="0.1.0",
        description="Personal AI CEO / business operating system — orchestration foundation.",
        lifespan=lifespan,
    )
    app.include_router(router)

    return app


app = create_app()


async def _run_cli() -> None:
    from app.orchestration import dispatcher
    from app.orchestration.executor import AgentExecutor, build_report
    from app.orchestration.planner import create_plan
    from app.services.project_service import ProjectService

    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db()

    registry = build_default_registry(settings)
    provider = get_default_provider()
    session_factory = get_session_factory()

    print("=" * 60)
    print("Jarvis OS v0.1 — development CLI")
    print(f"Model provider: {provider.name}" + ("" if provider.name == "openai" else " (offline/dev mode)"))
    print("Type an objective, or 'exit' to quit.")
    print("=" * 60)

    email = input("Your email [cli-user@example.com]: ").strip() or "cli-user@example.com"

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email(email)
        workspace = await WorkspaceRepository(session).create(user.id, "CLI Workspace")
        await session.commit()
        workspace_id = workspace.id

    while True:
        objective = input("\nYou: ").strip()
        if not objective:
            continue
        if objective.lower() in {"exit", "quit"}:
            print("Jarvis: Goodbye.")
            break

        async with session_factory() as session:
            project_service = ProjectService(session)
            project = await project_service.create_project(workspace_id, objective[:80])
            await project_service.set_objective(workspace_id, project.id, objective)
            await session.commit()
            project_id = project.id

        print("\nJarvis: Planning...")
        async with session_factory() as session:
            jarvis = registry.create("jarvis", provider=provider)
            plan = await create_plan(jarvis, objective)
            await dispatcher.persist_plan(
                session, workspace_id=workspace_id, project_id=project_id, plan=plan
            )
            await session.commit()
        print(f"Jarvis: Plan created with {len(plan.tasks)} tasks.")

        executor = AgentExecutor(session_factory, registry, provider, settings)
        iterations = 0
        while iterations < settings.max_tasks_per_run:
            async with session_factory() as session:
                await dispatcher.promote_ready_tasks(
                    session, workspace_id=workspace_id, project_id=project_id
                )
                await session.commit()
                ready = await dispatcher.get_ready_tasks(session, project_id=project_id)
                if not ready:
                    finished = await dispatcher.is_project_finished(session, project_id=project_id)
                    if not finished:
                        print("Jarvis: Waiting on human approval to continue.")
                    break
                for t in ready:
                    print(f"Jarvis: Running {t.agent_type} task — {t.title}")

            completed = await executor.run_ready_tasks(
                workspace_id=workspace_id, project_id=project_id
            )
            for t in completed:
                print(f"Jarvis: {t.status.value} — {t.title}")
            iterations += len(ready)

        async with session_factory() as session:
            jarvis = registry.create("jarvis", provider=provider)
            report = await build_report(
                session, jarvis, workspace_id=workspace_id, project_id=project_id, objective=objective
            )
            await session.commit()

        print("\nJarvis: Recommendation ready.\n")
        print(report.to_text())


def main() -> None:
    asyncio.run(_run_cli())


if __name__ == "__main__":
    main()
