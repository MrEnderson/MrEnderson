"""Tool metadata contracts + deterministic Tool Registry (v0.1.3.2, spec
sections 2/3/4/14). DEFINITIONS ONLY: nothing in this module executes a
tool, stores an executable callable, or accepts model/agent-provided data as
a registration. See docs/decision_intelligence.md's v0.1.3.2 section.

A ToolDefinition is application-controlled configuration, the same trust
tier as app/agents/registry.py's AgentDescriptor registrations
(build_default_registry) — never something an LLM response can produce and
feed straight into ToolRegistry.register(). register() only accepts an
already-constructed ToolDefinition instance (isinstance-checked, not
duck-typed against a dict), and ToolDefinition has no field capable of
holding a Python callable, shell command, URL-as-code, or import path —
so there is no path from "model output" to "registered executable
capability" here, by construction, not by convention.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from app.database.models import PermissionLevel, RiskLevel

# Strict, deterministic name validation (spec section 3: "registry names
# must be normalized deterministically or validated strictly"). Lowercase
# dotted segments only (e.g. "research.read", "communication.send_email") —
# rejects anything that could create a case-insensitive collision (e.g.
# "Evil.Tool" vs "evil.tool") or embed whitespace/control characters.
_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# Same shape for the action_type strings a tool declares support for.
_ACTION_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ToolDefinition(BaseModel):
    """Application-controlled tool metadata. Immutable (frozen) — nothing
    downstream may mutate a registered definition in place; a replacement
    must go through ToolRegistry.register(..., replace=True) with a new
    instance, so every change to a tool's declared policy floor is an
    explicit, auditable registration event.

    default_permission_level / default_risk_level are a FLOOR (spec section
    7): the Permission Engine must never authorize an Action at a level
    below what the resolved tool declares here, regardless of what an
    agent-proposed Action claims.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""
    supported_action_types: frozenset[str]
    default_permission_level: PermissionLevel
    default_risk_level: RiskLevel
    has_side_effects: bool
    supports_dry_run: bool = False
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    verification_strategy: str = ""
    enabled: bool = True


class ToolRegistrationError(Exception):
    """Base class for all typed Tool Registry errors. Every failure mode in
    this module fails closed — there is no fallback registration path."""


class InvalidToolDefinitionError(ToolRegistrationError):
    pass


class DuplicateToolError(ToolRegistrationError):
    def __init__(self, name: str):
        super().__init__(f"Tool '{name}' is already registered (pass replace=True to replace it)")
        self.name = name


class UnknownToolError(ToolRegistrationError):
    def __init__(self, name: str):
        super().__init__(f"No tool registered with name '{name}'")
        self.name = name


class DisabledToolError(ToolRegistrationError):
    def __init__(self, name: str):
        super().__init__(f"Tool '{name}' is registered but disabled")
        self.name = name


class UnsupportedActionTypeError(ToolRegistrationError):
    def __init__(self, name: str, action_type: str):
        super().__init__(f"Tool '{name}' does not support action_type '{action_type}'")
        self.name = name
        self.action_type = action_type


def _validate_definition(tool: ToolDefinition) -> None:
    if not _NAME_PATTERN.match(tool.name):
        raise InvalidToolDefinitionError(
            f"Tool name '{tool.name}' must be lowercase, dotted (e.g. 'research.read'); "
            "no whitespace, uppercase, or single-segment names."
        )
    if not tool.supported_action_types:
        raise InvalidToolDefinitionError(f"Tool '{tool.name}' declares no supported_action_types")
    for action_type in tool.supported_action_types:
        if not _ACTION_TYPE_PATTERN.match(action_type):
            raise InvalidToolDefinitionError(
                f"Tool '{tool.name}' has malformed supported_action_types entry: '{action_type}'"
            )


class ToolRegistry:
    """Deterministic, application-controlled tool catalog. Every lookup
    fails closed: unknown/disabled/incompatible always raise a typed error,
    never silently degrade to a default tool or permission level."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition, *, replace: bool = False) -> None:
        if not isinstance(tool, ToolDefinition):
            raise TypeError(
                f"ToolRegistry.register() requires a ToolDefinition instance, got {type(tool).__name__}. "
                "Tool definitions are trusted, application-constructed objects, never raw "
                "dicts/JSON — model or user-provided data can never be registered directly."
            )
        _validate_definition(tool)
        if tool.name in self._tools and not replace:
            raise DuplicateToolError(tool.name)
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        if name not in self._tools:
            raise UnknownToolError(name)
        del self._tools[name]

    def contains(self, name: str) -> bool:
        return name in self._tools

    def get(self, name: str) -> ToolDefinition:
        """Raw lookup: returns the definition regardless of enabled state.
        Most callers should use resolve() instead, which enforces the full
        fail-closed compatibility contract."""
        tool = self._tools.get(name)
        if tool is None:
            raise UnknownToolError(name)
        return tool

    def list_definitions(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def resolve(self, name: str, action_type: str) -> ToolDefinition:
        """The single entry point the Permission Engine uses. Fail-closed,
        in order: unknown tool -> UnknownToolError; disabled tool ->
        DisabledToolError; tool/action_type incompatible ->
        UnsupportedActionTypeError. Returns the ToolDefinition only when all
        three checks pass."""
        tool = self.get(name)
        if not tool.enabled:
            raise DisabledToolError(name)
        if action_type not in tool.supported_action_types:
            raise UnsupportedActionTypeError(name, action_type)
        return tool


def build_default_tool_registry() -> ToolRegistry:
    """The checkpoint's safe, non-executing tool catalog (spec section 4).
    Every definition here is a DEFINITION ONLY — none is wired to a real
    execution function. Covers the full P1-P5 ladder documented in
    permission_engine.py:

    research.read              P1  read-only
    plan.create                P2  internal creation
    artifact.draft             P2  internal creation
    file.create_sandboxed      P2  internal/sandboxed creation
    mock.external_action       P3  reversible external change (policy-sensitive)
    communication.send_email   P4  consequential external action
    content.publish            P4  consequential external action
    resource.delete_external   P4  consequential external action
    finance.spend_money        P5  financial (REQUIRE_APPROVAL under policy)
    system.install_software    P5  privileged/system (BLOCK under policy)
    system.privileged_shell    P5  privileged/system (BLOCK under policy)
    """
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="research.read",
            description="Read previously-gathered research/evidence. No network call, no mutation.",
            supported_action_types=frozenset({"read"}),
            default_permission_level=PermissionLevel.READ,
            default_risk_level=RiskLevel.LOW,
            has_side_effects=False,
            supports_dry_run=False,
            verification_strategy="none",
        )
    )
    registry.register(
        ToolDefinition(
            name="plan.create",
            description="Create an internal ActionPlan/Decision artifact. No external effect.",
            supported_action_types=frozenset({"internal_create"}),
            default_permission_level=PermissionLevel.WRITE,
            default_risk_level=RiskLevel.LOW,
            has_side_effects=True,
            supports_dry_run=True,
            verification_strategy="automated",
        )
    )
    registry.register(
        ToolDefinition(
            name="artifact.draft",
            description="Draft an internal artifact (e.g. a document body) with no external delivery.",
            supported_action_types=frozenset({"internal_create"}),
            default_permission_level=PermissionLevel.WRITE,
            default_risk_level=RiskLevel.LOW,
            has_side_effects=True,
            supports_dry_run=True,
            verification_strategy="automated",
        )
    )
    registry.register(
        ToolDefinition(
            name="file.create_sandboxed",
            description="Create a file inside an application-controlled sandbox directory.",
            supported_action_types=frozenset({"sandbox_create"}),
            default_permission_level=PermissionLevel.WRITE,
            default_risk_level=RiskLevel.LOW,
            has_side_effects=True,
            supports_dry_run=True,
            verification_strategy="automated",
        )
    )
    registry.register(
        ToolDefinition(
            name="mock.external_action",
            description=(
                "Placeholder for a reversible external mutation (e.g. an update to an "
                "external record that could be rolled back). No real external system is "
                "ever contacted by this definition."
            ),
            supported_action_types=frozenset({"external_modify"}),
            default_permission_level=PermissionLevel.EXTERNAL_ACTION,
            default_risk_level=RiskLevel.MEDIUM,
            has_side_effects=True,
            supports_dry_run=True,
            verification_strategy="manual",
        )
    )
    registry.register(
        ToolDefinition(
            name="communication.send_email",
            description="DEFINITION ONLY — never wired to a real mail transport.",
            supported_action_types=frozenset({"send"}),
            default_permission_level=PermissionLevel.EXTERNAL_ACTION,
            default_risk_level=RiskLevel.HIGH,
            has_side_effects=True,
            supports_dry_run=True,
            verification_strategy="manual",
        )
    )
    registry.register(
        ToolDefinition(
            name="content.publish",
            description="DEFINITION ONLY — never wired to a real publishing target.",
            supported_action_types=frozenset({"publish"}),
            default_permission_level=PermissionLevel.EXTERNAL_ACTION,
            default_risk_level=RiskLevel.HIGH,
            has_side_effects=True,
            supports_dry_run=True,
            verification_strategy="manual",
        )
    )
    registry.register(
        ToolDefinition(
            name="resource.delete_external",
            description="DEFINITION ONLY — never wired to a real deletion API.",
            supported_action_types=frozenset({"delete"}),
            default_permission_level=PermissionLevel.EXTERNAL_ACTION,
            default_risk_level=RiskLevel.HIGH,
            has_side_effects=True,
            supports_dry_run=False,
            verification_strategy="manual",
        )
    )
    registry.register(
        ToolDefinition(
            name="finance.spend_money",
            description="DEFINITION ONLY — never wired to a real payment processor.",
            supported_action_types=frozenset({"financial"}),
            default_permission_level=PermissionLevel.FINANCIAL_ACTION,
            default_risk_level=RiskLevel.CRITICAL,
            has_side_effects=True,
            supports_dry_run=False,
            verification_strategy="manual",
        )
    )
    registry.register(
        ToolDefinition(
            name="system.install_software",
            description="DEFINITION ONLY — never wired to a real installer; blocked by policy.",
            supported_action_types=frozenset({"install"}),
            default_permission_level=PermissionLevel.ADMIN,
            default_risk_level=RiskLevel.CRITICAL,
            has_side_effects=True,
            supports_dry_run=False,
            verification_strategy="none",
        )
    )
    registry.register(
        ToolDefinition(
            name="system.privileged_shell",
            description="DEFINITION ONLY — never wired to a real shell; blocked by policy.",
            supported_action_types=frozenset({"privileged"}),
            default_permission_level=PermissionLevel.ADMIN,
            default_risk_level=RiskLevel.CRITICAL,
            has_side_effects=True,
            supports_dry_run=False,
            verification_strategy="none",
        )
    )

    return registry
