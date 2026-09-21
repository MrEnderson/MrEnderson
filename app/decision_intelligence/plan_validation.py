"""Deterministic ActionPlan structural validation (spec sections 12/13).
No LLM is ever consulted here. Cycle detection reuses the same
visiting/visited DFS approach as
app/orchestration/planner.py::_assert_no_cycles, adapted from TaskPlan
keys to Action ids.
"""
from __future__ import annotations

from app.decision_intelligence.schemas import Action, ActionPlan, ActionStatus, PlanReadinessResult

# Action types that never require a declared tool (nothing external to
# call) — anything else must declare Action.tool_name before a plan
# containing it can become READY. Deliberately small and conservative: an
# unrecognized action_type is treated as tool-requiring, not exempt.
_NO_TOOL_ACTION_TYPES = frozenset({"internal", "no_op", "manual", "decision_only"})

# An action already in one of these statuses cannot be part of a plan that
# is about to become READY — the plan would be inconsistent (some work
# already failed/stopped while the plan as a whole claims to be freshly
# ready to execute).
_IMPOSSIBLE_FOR_READY = frozenset(
    {
        ActionStatus.FAILED,
        ActionStatus.CANCELLED,
        ActionStatus.REJECTED,
        ActionStatus.BLOCKED,
        ActionStatus.VERIFICATION_FAILED,
    }
)


class ActionPlanValidationError(Exception):
    """Raised by the strict, construction-time helpers below. The main
    entry point for a caller that just wants a report of what's wrong is
    evaluate_plan_readiness(), which never raises."""


def duplicate_action_ids(actions: list[Action]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for action in actions:
        if action.id in seen and action.id not in duplicates:
            duplicates.append(action.id)
        seen.add(action.id)
    return duplicates


def unknown_dependency_ids(actions: list[Action]) -> list[tuple[str, str]]:
    """Returns (action_id, missing_dependency_id) pairs for every
    dependency that does not reference another action in the same plan."""
    known_ids = {a.id for a in actions}
    missing: list[tuple[str, str]] = []
    for action in actions:
        for dep in action.dependencies:
            if dep not in known_ids:
                missing.append((action.id, dep))
    return missing


def self_dependencies(actions: list[Action]) -> list[str]:
    return [a.id for a in actions if a.id in a.dependencies]


def detect_dependency_cycle(actions: list[Action]) -> list[str] | None:
    """Returns the ids forming a cycle (in traversal order) if one exists,
    else None. Ignores dependency ids that don't resolve to a known action
    (see unknown_dependency_ids) so a dangling reference can't be mistaken
    for/mask a cycle."""
    graph = {a.id: [d for d in a.dependencies if d != a.id] for a in actions}
    known_ids = set(graph)
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visited:
            return None
        if node in visiting:
            return path[path.index(node):] + [node]
        visiting.add(node)
        path.append(node)
        for dep in graph.get(node, []):
            if dep not in known_ids:
                continue
            cycle = visit(dep)
            if cycle:
                return cycle
        path.pop()
        visiting.discard(node)
        visited.add(node)
        return None

    for action_id in graph:
        cycle = visit(action_id)
        if cycle:
            return cycle
    return None


def forward_only_dependency_violations(actions: list[Action]) -> list[tuple[str, str]]:
    """Detects an action depending on another action with a STRICTLY LATER
    sequence number — i.e. depending on something that (by declared
    sequence) hasn't run yet. Returns (action_id, dependency_id) pairs.
    Only meaningful when the plan actually uses distinct sequence numbers;
    a plan that leaves every `sequence` at the default (0) has nothing
    ordered to violate, so it never flags anything."""
    by_id = {a.id: a for a in actions}
    violations: list[tuple[str, str]] = []
    for action in actions:
        for dep_id in action.dependencies:
            dep = by_id.get(dep_id)
            if dep is not None and dep.sequence > action.sequence:
                violations.append((action.id, dep_id))
    return violations


def requires_tool(action_type: str) -> bool:
    return action_type not in _NO_TOOL_ACTION_TYPES


def validate_dependencies(actions: list[Action]) -> None:
    """Strict, raising variant for callers that want a hard failure rather
    than a structured report (mirrors
    app/orchestration/planner.py::_validate_plan's style)."""
    duplicates = duplicate_action_ids(actions)
    if duplicates:
        raise ActionPlanValidationError(f"Duplicate action ids: {duplicates}")

    self_deps = self_dependencies(actions)
    if self_deps:
        raise ActionPlanValidationError(f"Actions cannot depend on themselves: {self_deps}")

    missing = unknown_dependency_ids(actions)
    if missing:
        raise ActionPlanValidationError(f"Unknown dependency references: {missing}")

    cycle = detect_dependency_cycle(actions)
    if cycle:
        raise ActionPlanValidationError(f"Cyclic dependency detected: {' -> '.join(cycle)}")


def evaluate_plan_readiness(plan: ActionPlan) -> PlanReadinessResult:
    """The deterministic ActionPlan readiness evaluator (spec section 13).
    Never raises, never consults an LLM — always returns a structured
    report. `ready` is True only when `blockers` is empty; `warnings` never
    affect `ready`.
    """
    blockers: list[str] = []
    warnings: list[str] = []
    actions = plan.actions

    if not actions:
        blockers.append("ActionPlan has no actions")
        return PlanReadinessResult(ready=False, blockers=blockers, warnings=warnings)

    duplicates = duplicate_action_ids(actions)
    if duplicates:
        blockers.append(f"Duplicate action ids: {duplicates}")

    self_deps = self_dependencies(actions)
    if self_deps:
        blockers.append(f"Actions cannot depend on themselves: {self_deps}")

    missing = unknown_dependency_ids(actions)
    if missing:
        blockers.append(
            "Actions depend on unknown action ids: "
            + ", ".join(f"{aid}->{dep}" for aid, dep in missing)
        )

    # Cycle detection is skipped if ids are already duplicated/dangling —
    # the graph isn't well-formed enough to traverse meaningfully, and
    # would otherwise risk producing a confusing secondary error.
    if not duplicates and not missing:
        cycle = detect_dependency_cycle(actions)
        if cycle:
            blockers.append(f"Cyclic dependency detected: {' -> '.join(cycle)}")

    forward_violations = forward_only_dependency_violations(actions)
    if forward_violations:
        blockers.append(
            "Actions depend on a later-sequenced action: "
            + ", ".join(f"{aid} depends on {dep}" for aid, dep in forward_violations)
        )

    for action in actions:
        label = f"Action '{action.id}' ({action.title or action.action_type})"
        if action.status in _IMPOSSIBLE_FOR_READY:
            blockers.append(f"{label} is in an impossible state for a READY plan: {action.status.value}")
        if not action.expected_result.strip():
            blockers.append(f"{label} has no expected_result")
        if not action.success_criteria.strip():
            blockers.append(f"{label} has no success_criteria")
        if not action.verification_method.strip():
            blockers.append(f"{label} has no verification_method")
        if requires_tool(action.action_type) and not action.tool_name:
            blockers.append(f"{label} requires a declared tool_name for action_type '{action.action_type}'")
        if action.approval_required and action.risk_level.value == "LOW":
            warnings.append(f"{label} is marked approval_required with risk_level LOW")
        if action.retry_count > action.max_retries:
            warnings.append(f"{label} has retry_count ({action.retry_count}) exceeding max_retries ({action.max_retries})")

    return PlanReadinessResult(ready=not blockers, blockers=blockers, warnings=warnings)
