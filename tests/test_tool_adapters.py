"""Trusted Tool Adapter registry + the one real adapter, file.create_sandboxed
(v0.1.3.4, spec sections 5/11/12/23/32/33). No live network, no shell."""
from __future__ import annotations

import hashlib

import pytest

from app.decision_intelligence.schemas import Action, ActionStatus
from app.decision_intelligence.tool_adapters import (
    DuplicateAdapterError,
    ExecutionContext,
    InvalidAdapterError,
    SandboxFileCreateAdapter,
    ToolAdapterRegistry,
    UnknownAdapterError,
    build_default_adapter_registry,
)


def _action(**overrides) -> Action:
    fields = dict(
        action_plan_id="plan-1",
        action_type="sandbox_create",
        tool_name="file.create_sandboxed",
        title="Write a note",
        inputs={"relative_path": "note.txt", "content": "hello"},
        expected_result="a sandbox file is created",
        status=ActionStatus.EXECUTING,
    )
    fields.update(overrides)
    return Action(**fields)


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


@pytest.fixture
def context(sandbox_root):
    return ExecutionContext(sandbox_root=sandbox_root)


# --- ToolAdapterRegistry ------------------------------------------------------


def test_register_and_get_round_trip():
    registry = ToolAdapterRegistry()
    adapter = SandboxFileCreateAdapter()
    registry.register("file.create_sandboxed", adapter)
    assert registry.get("file.create_sandboxed") is adapter


def test_contains_true_after_register():
    registry = ToolAdapterRegistry()
    registry.register("file.create_sandboxed", SandboxFileCreateAdapter())
    assert registry.contains("file.create_sandboxed") is True


def test_contains_false_for_unknown():
    registry = ToolAdapterRegistry()
    assert registry.contains("nope.tool") is False


def test_duplicate_registration_raises():
    registry = ToolAdapterRegistry()
    registry.register("file.create_sandboxed", SandboxFileCreateAdapter())
    with pytest.raises(DuplicateAdapterError):
        registry.register("file.create_sandboxed", SandboxFileCreateAdapter())


def test_duplicate_with_replace_true_succeeds():
    registry = ToolAdapterRegistry()
    registry.register("file.create_sandboxed", SandboxFileCreateAdapter())
    replacement = SandboxFileCreateAdapter()
    registry.register("file.create_sandboxed", replacement, replace=True)
    assert registry.get("file.create_sandboxed") is replacement


def test_unknown_adapter_lookup_raises():
    registry = ToolAdapterRegistry()
    with pytest.raises(UnknownAdapterError):
        registry.get("evil.magic_shell")


def test_register_rejects_object_without_execute_or_verify():
    registry = ToolAdapterRegistry()

    class NotAnAdapter:
        pass

    with pytest.raises(InvalidAdapterError):
        registry.register("broken.tool", NotAnAdapter())


def test_register_rejects_object_with_non_callable_execute():
    registry = ToolAdapterRegistry()

    class FakeAdapter:
        execute = "not callable"
        verify = "not callable either"

    with pytest.raises(InvalidAdapterError):
        registry.register("broken.tool", FakeAdapter())


def test_register_rejects_plain_dict_as_adapter():
    registry = ToolAdapterRegistry()
    with pytest.raises(InvalidAdapterError):
        registry.register("evil.tool", {"execute": "shell.exe", "verify": "noop"})  # type: ignore[arg-type]


def test_build_default_adapter_registry_has_exactly_one_real_adapter():
    registry = build_default_adapter_registry()
    assert registry.list_tool_names() == ["file.create_sandboxed"]


def test_build_default_adapter_registry_no_adapter_for_high_risk_tools():
    registry = build_default_adapter_registry()
    for tool_name in (
        "communication.send_email",
        "content.publish",
        "resource.delete_external",
        "finance.spend_money",
        "system.install_software",
        "system.privileged_shell",
    ):
        assert registry.contains(tool_name) is False


# --- SandboxFileCreateAdapter.execute() ---------------------------------------


async def test_execute_creates_file_with_expected_content(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    result = await adapter.execute(_action(), context)
    assert result.success is True
    assert result.side_effect_occurred is True
    written = sandbox_root / "note.txt"
    assert written.read_text(encoding="utf-8") == "hello"


async def test_execute_result_reports_correct_hash_and_size(context):
    adapter = SandboxFileCreateAdapter()
    result = await adapter.execute(_action(), context)
    expected_hash = hashlib.sha256(b"hello").hexdigest()
    assert result.output["content_hash"] == expected_hash
    assert result.output["bytes_written"] == len(b"hello")


async def test_execute_missing_relative_path_input_fails_validation(context):
    adapter = SandboxFileCreateAdapter()
    action = _action(inputs={"content": "hello"})
    result = await adapter.execute(action, context)
    assert result.success is False
    assert result.error_code == "VALIDATION_FAILURE"
    assert result.side_effect_occurred is False


async def test_execute_non_string_content_fails_validation(context):
    adapter = SandboxFileCreateAdapter()
    action = _action(inputs={"relative_path": "note.txt", "content": 12345})
    result = await adapter.execute(action, context)
    assert result.success is False
    assert result.error_code == "VALIDATION_FAILURE"


async def test_execute_path_traversal_fails_as_sandbox_violation(context):
    adapter = SandboxFileCreateAdapter()
    action = _action(inputs={"relative_path": "../escape.txt", "content": "x"})
    result = await adapter.execute(action, context)
    assert result.success is False
    assert result.error_code == "SANDBOX_VIOLATION"
    assert result.side_effect_occurred is False


async def test_execute_oversized_content_blocked_before_write(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    from app.decision_intelligence.sandbox_fs import MAX_CONTENT_BYTES

    action = _action(inputs={"relative_path": "big.txt", "content": "x" * (MAX_CONTENT_BYTES + 1)})
    result = await adapter.execute(action, context)
    assert result.success is False
    assert result.error_code == "SANDBOX_VIOLATION"
    assert not (sandbox_root / "big.txt").exists()


async def test_execute_existing_target_not_overwritten(context, sandbox_root):
    (sandbox_root / "note.txt").write_text("original")
    adapter = SandboxFileCreateAdapter()
    result = await adapter.execute(_action(inputs={"relative_path": "note.txt", "content": "new"}), context)
    assert result.success is False
    assert result.error_code == "SANDBOX_VIOLATION"
    assert (sandbox_root / "note.txt").read_text() == "original"


async def test_execute_nested_directory_creation(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    action = _action(inputs={"relative_path": "a/b/c/note.txt", "content": "deep"})
    result = await adapter.execute(action, context)
    assert result.success is True
    assert (sandbox_root / "a" / "b" / "c" / "note.txt").read_text() == "deep"


async def test_execute_utf8_content_written_correctly(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    action = _action(inputs={"relative_path": "unicode.txt", "content": "héllo wörld 日本語"})
    result = await adapter.execute(action, context)
    assert result.success is True
    assert (sandbox_root / "unicode.txt").read_text(encoding="utf-8") == "héllo wörld 日本語"


async def test_execute_records_attempt_id_and_adapter_version(context):
    adapter = SandboxFileCreateAdapter()
    result = await adapter.execute(_action(), context)
    assert result.execution_attempt_id == context.attempt_id
    assert result.adapter_version == adapter.version


# --- SandboxFileCreateAdapter.verify() ----------------------------------------


async def test_verify_passes_for_a_correct_write(context):
    adapter = SandboxFileCreateAdapter()
    exec_result = await adapter.execute(_action(), context)
    verification = await adapter.verify(_action(), exec_result, context)
    assert verification.passed is True
    assert verification.issues == []
    assert verification.confidence == 1.0


async def test_verify_fails_if_target_missing(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    exec_result = await adapter.execute(_action(), context)
    (sandbox_root / "note.txt").unlink()  # simulate deletion between execute and verify
    verification = await adapter.verify(_action(), exec_result, context)
    assert verification.passed is False
    assert any("does not exist" in issue for issue in verification.issues)


async def test_verify_fails_on_content_hash_mismatch(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    exec_result = await adapter.execute(_action(), context)
    (sandbox_root / "note.txt").write_bytes(b"tampered content")  # bypass adapter, mutate directly
    verification = await adapter.verify(_action(), exec_result, context)
    assert verification.passed is False
    assert any("hash mismatch" in issue for issue in verification.issues)


async def test_verify_fails_on_byte_length_mismatch(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    exec_result = await adapter.execute(_action(), context)
    # Tamper with the reported output directly to simulate a byte-length claim mismatch.
    tampered_output = dict(exec_result.output)
    tampered_output["bytes_written"] = 999
    tampered_result = exec_result.model_copy(update={"output": tampered_output})
    verification = await adapter.verify(_action(), tampered_result, context)
    assert verification.passed is False
    assert any("byte length mismatch" in issue for issue in verification.issues)


async def test_verify_fails_if_execution_did_not_succeed(context):
    adapter = SandboxFileCreateAdapter()
    action = _action(inputs={"relative_path": "../escape.txt", "content": "x"})
    exec_result = await adapter.execute(action, context)
    assert exec_result.success is False
    verification = await adapter.verify(action, exec_result, context)
    assert verification.passed is False


async def test_verify_fails_if_target_is_not_a_regular_file(context, sandbox_root):
    adapter = SandboxFileCreateAdapter()
    exec_result = await adapter.execute(_action(), context)
    # Replace the file with a directory of the same name to simulate a
    # non-regular-file target at verification time.
    target = sandbox_root / "note.txt"
    target.unlink()
    target.mkdir()
    verification = await adapter.verify(_action(), exec_result, context)
    assert verification.passed is False
    assert any("not a regular file" in issue for issue in verification.issues)
