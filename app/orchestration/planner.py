"""Turns an objective into a validated, structured ExecutionPlan. Never accepts
free-text as a plan — the planner's raw model output must validate against
ExecutionPlan/TaskPlan or it is rejected outright."""
from __future__ import annotations

from app.agents.jarvis import JarvisAgent
from app.schemas.tasks import ExecutionPlan


class PlanValidationError(Exception):
    pass


async def create_plan(jarvis: JarvisAgent, objective: str) -> ExecutionPlan:
    if not objective or not objective.strip():
        raise PlanValidationError("Objective must not be empty")

    plan = await jarvis.plan(objective)
    _validate_plan(plan)
    return plan


def _validate_plan(plan: ExecutionPlan) -> None:
    if not plan.tasks:
        raise PlanValidationError("ExecutionPlan must contain at least one task")

    keys = [t.key for t in plan.tasks]
    if len(keys) != len(set(keys)):
        raise PlanValidationError("ExecutionPlan task keys must be unique")

    key_set = set(keys)
    for task in plan.tasks:
        for dep in task.dependencies:
            if dep not in key_set:
                raise PlanValidationError(
                    f"Task '{task.key}' depends on unknown task key '{dep}'"
                )
            if dep == task.key:
                raise PlanValidationError(f"Task '{task.key}' cannot depend on itself")

    _assert_no_cycles(plan)


def _assert_no_cycles(plan: ExecutionPlan) -> None:
    graph = {t.key: t.dependencies for t in plan.tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            raise PlanValidationError(f"Cyclic dependency detected involving task '{node}'")
        visiting.add(node)
        for dep in graph.get(node, []):
            visit(dep)
        visiting.discard(node)
        visited.add(node)

    for key in graph:
        visit(key)
