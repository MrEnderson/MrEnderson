"""ToolRegistry / ToolDefinition contracts (v0.1.3.2, spec sections 2/3/4/14
/21). DEFINITIONS ONLY — nothing here executes a tool."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.database.models import PermissionLevel, RiskLevel
from app.decision_intelligence.tool_registry import (
    DisabledToolError,
    DuplicateToolError,
    InvalidToolDefinitionError,
    ToolDefinition,
    ToolRegistry,
    UnknownToolError,
    UnsupportedActionTypeError,
    build_default_tool_registry,
)


def _tool(**overrides) -> ToolDefinition:
    fields = dict(
        name="test.sample",
        description="a sample tool",
        supported_action_types=frozenset({"read"}),
        default_permission_level=PermissionLevel.READ,
        default_risk_level=RiskLevel.LOW,
        has_side_effects=False,
    )
    fields.update(overrides)
    return ToolDefinition(**fields)


# --- ToolDefinition ---------------------------------------------------------


def test_tool_definition_constructs_with_minimum_fields():
    tool = _tool()
    assert tool.enabled is True
    assert tool.supports_dry_run is False
    assert tool.input_schema == {}
    assert tool.output_schema == {}


def test_tool_definition_is_frozen_immutable():
    tool = _tool()
    with pytest.raises(ValidationError):
        tool.name = "changed"


def test_tool_definition_serialization_round_trips():
    tool = _tool(description="round trips")
    dumped = tool.model_dump(mode="json")
    restored = ToolDefinition.model_validate(dumped)
    assert restored == tool


def test_tool_definition_rejects_unknown_permission_level():
    with pytest.raises(ValidationError):
        _tool(default_permission_level="SUPERUSER")


def test_tool_definition_rejects_unknown_risk_level():
    with pytest.raises(ValidationError):
        _tool(default_risk_level="APOCALYPTIC")


# --- Registration -----------------------------------------------------------


def test_register_and_get_round_trip():
    registry = ToolRegistry()
    tool = _tool()
    registry.register(tool)
    assert registry.get("test.sample") == tool


def test_contains_true_for_registered_tool():
    registry = ToolRegistry()
    registry.register(_tool())
    assert registry.contains("test.sample") is True


def test_contains_false_for_unknown_tool():
    registry = ToolRegistry()
    assert registry.contains("nope.nothing") is False


def test_duplicate_registration_raises():
    registry = ToolRegistry()
    registry.register(_tool())
    with pytest.raises(DuplicateToolError):
        registry.register(_tool())


def test_duplicate_registration_with_replace_true_succeeds():
    registry = ToolRegistry()
    registry.register(_tool())
    replacement = _tool(description="replaced")
    registry.register(replacement, replace=True)
    assert registry.get("test.sample").description == "replaced"


def test_unregister_removes_tool():
    registry = ToolRegistry()
    registry.register(_tool())
    registry.unregister("test.sample")
    assert registry.contains("test.sample") is False


def test_unregister_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(UnknownToolError):
        registry.unregister("nope.nothing")


def test_get_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(UnknownToolError):
        registry.get("nope.nothing")


def test_list_definitions_returns_all_registered():
    registry = ToolRegistry()
    registry.register(_tool(name="test.one"))
    registry.register(_tool(name="test.two"))
    names = {t.name for t in registry.list_definitions()}
    assert names == {"test.one", "test.two"}


# --- Trusted-registration boundary (spec section 14) ------------------------


def test_register_rejects_plain_dict_from_model_output():
    registry = ToolRegistry()
    model_output = {
        "name": "evil.magic_shell",
        "supported_action_types": ["privileged"],
        "default_permission_level": "ADMIN",
        "default_risk_level": "CRITICAL",
        "has_side_effects": True,
    }
    with pytest.raises(TypeError):
        registry.register(model_output)  # type: ignore[arg-type]
    assert registry.contains("evil.magic_shell") is False


def test_register_rejects_arbitrary_object_masquerading_as_tool():
    class FakeTool:
        name = "fake.tool"
        supported_action_types = frozenset({"read"})

    registry = ToolRegistry()
    with pytest.raises(TypeError):
        registry.register(FakeTool())  # type: ignore[arg-type]


def test_tool_definition_has_no_callable_or_import_path_field():
    tool = _tool()
    dumped = tool.model_dump()
    for value in dumped.values():
        assert not callable(value)
    assert "callable" not in ToolDefinition.model_fields
    assert "import_path" not in ToolDefinition.model_fields
    assert "shell_command" not in ToolDefinition.model_fields


# --- Malformed definitions fail closed --------------------------------------


def test_register_rejects_uppercase_name():
    registry = ToolRegistry()
    with pytest.raises(InvalidToolDefinitionError):
        registry.register(_tool(name="Evil.Tool"))


def test_register_rejects_single_segment_name():
    registry = ToolRegistry()
    with pytest.raises(InvalidToolDefinitionError):
        registry.register(_tool(name="noDot"))


def test_register_rejects_empty_supported_action_types():
    registry = ToolRegistry()
    with pytest.raises(InvalidToolDefinitionError):
        registry.register(_tool(supported_action_types=frozenset()))


def test_register_rejects_malformed_action_type_entry():
    registry = ToolRegistry()
    with pytest.raises(InvalidToolDefinitionError):
        registry.register(_tool(supported_action_types=frozenset({"Not Valid!"})))


def test_name_collision_across_case_is_rejected_not_merged():
    registry = ToolRegistry()
    registry.register(_tool(name="test.sample"))
    with pytest.raises(InvalidToolDefinitionError):
        registry.register(_tool(name="Test.Sample"))


# --- resolve(): the fail-closed compatibility entry point --------------------


def test_resolve_unknown_tool_raises():
    registry = ToolRegistry()
    with pytest.raises(UnknownToolError):
        registry.resolve("evil.magic_shell", "privileged")


def test_resolve_disabled_tool_raises():
    registry = ToolRegistry()
    registry.register(_tool(enabled=False))
    with pytest.raises(DisabledToolError):
        registry.resolve("test.sample", "read")


def test_resolve_unsupported_action_type_raises():
    registry = ToolRegistry()
    registry.register(_tool(supported_action_types=frozenset({"read"})))
    with pytest.raises(UnsupportedActionTypeError):
        registry.resolve("test.sample", "delete")


def test_resolve_success_returns_tool_definition():
    registry = ToolRegistry()
    tool = _tool()
    registry.register(tool)
    assert registry.resolve("test.sample", "read") == tool


# --- Default tool catalog (spec section 4) -----------------------------------


def test_default_tool_registry_covers_p1_through_p5():
    registry = build_default_tool_registry()
    by_permission = {t.default_permission_level for t in registry.list_definitions()}
    assert PermissionLevel.READ in by_permission  # P1
    assert PermissionLevel.WRITE in by_permission  # P2
    assert PermissionLevel.EXTERNAL_ACTION in by_permission  # P3/P4
    assert PermissionLevel.FINANCIAL_ACTION in by_permission  # P5 (financial)
    assert PermissionLevel.ADMIN in by_permission  # P5 (privileged)


def test_default_tool_registry_p4_p5_tools_are_enabled_but_non_executing():
    registry = build_default_tool_registry()
    for name in (
        "communication.send_email",
        "content.publish",
        "resource.delete_external",
        "finance.spend_money",
        "system.install_software",
        "system.privileged_shell",
    ):
        tool = registry.get(name)
        assert tool.enabled is True
        assert tool.has_side_effects is True


def test_default_tool_registry_research_read_is_low_risk():
    registry = build_default_tool_registry()
    tool = registry.get("research.read")
    assert tool.default_permission_level == PermissionLevel.READ
    assert tool.default_risk_level == RiskLevel.LOW
    assert tool.has_side_effects is False


def test_default_tool_registry_has_no_duplicate_names():
    registry = build_default_tool_registry()
    names = [t.name for t in registry.list_definitions()]
    assert len(names) == len(set(names))
