"""Permission enforcement. No agent acts outside its registered permission set.

READ / WRITE / EXTERNAL_ACTION / FINANCIAL_ACTION / ADMIN. No agent is granted
EXTERNAL_ACTION, FINANCIAL_ACTION, or ADMIN by default — those require explicit
human approval, enforced by the approval workflow, not by an agent's own claim.
"""
from __future__ import annotations

from app.agents.registry import AgentRegistry
from app.database.models import PermissionLevel

ELEVATED_PERMISSIONS = {
    PermissionLevel.EXTERNAL_ACTION,
    PermissionLevel.FINANCIAL_ACTION,
    PermissionLevel.ADMIN,
}


class PermissionDeniedError(Exception):
    def __init__(self, agent_type: str, permission: PermissionLevel):
        super().__init__(f"Agent '{agent_type}' does not hold permission {permission.value}")
        self.agent_type = agent_type
        self.permission = permission


def check_permission(
    registry: AgentRegistry, agent_type: str, permission: PermissionLevel
) -> None:
    if not registry.has_permission(agent_type, permission):
        raise PermissionDeniedError(agent_type, permission)


def requires_elevated_permission(registry: AgentRegistry, agent_type: str) -> bool:
    descriptor = registry.get_descriptor(agent_type)
    return any(p in ELEVATED_PERMISSIONS for p in descriptor.permissions)
