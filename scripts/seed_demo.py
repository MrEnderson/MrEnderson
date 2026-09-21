"""Run the Jarvis OS end-to-end demo objective non-interactively.

Usage:
    python scripts/seed_demo.py
    python scripts/seed_demo.py "Research the children's colouring-book market and identify three possible product opportunities."
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.providers import get_default_provider  # noqa: E402
from app.agents.registry import build_default_registry  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.database.connection import get_session_factory, init_db  # noqa: E402
from app.database.repositories import UserRepository, WorkspaceRepository  # noqa: E402
from app.orchestration.executor import run_objective  # noqa: E402
from app.services.project_service import ProjectService  # noqa: E402
from app.utils.logging import configure_logging  # noqa: E402

DEFAULT_OBJECTIVE = "Find three potential digital-product opportunities and recommend the strongest one."


async def main() -> None:
    objective = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OBJECTIVE

    settings = get_settings()
    configure_logging(settings.log_level)
    await init_db()

    registry = build_default_registry(settings)
    provider = get_default_provider()
    session_factory = get_session_factory()

    print(f"Model provider: {provider.name}")
    print(f"Objective: {objective}\n")

    async with session_factory() as session:
        user = await UserRepository(session).get_or_create_by_email("demo@jarvis-os.local")
        workspace = await WorkspaceRepository(session).create(user.id, "Demo Workspace")
        project = await ProjectService(session).create_project(workspace.id, objective[:80])
        await ProjectService(session).set_objective(workspace.id, project.id, objective)
        await session.commit()
        workspace_id, project_id = workspace.id, project.id

    async with session_factory() as session:
        report = await run_objective(
            session,
            registry,
            provider,
            workspace_id=workspace_id,
            project_id=project_id,
            objective=objective,
        )
        await session.commit()

    print(report.to_text())

    async with session_factory() as session:
        from app.services.task_service import TaskService

        tasks = await TaskService(session).list_for_project(project_id)
        print("\n--- Task states ---")
        for t in tasks:
            print(f"  [{t.status.value:16s}] ({t.agent_type:9s}) {t.title}")


if __name__ == "__main__":
    asyncio.run(main())
