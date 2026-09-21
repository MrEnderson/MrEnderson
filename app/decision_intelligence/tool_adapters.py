"""Trusted Tool Adapter abstraction (v0.1.3.4, spec sections 11/12) and the
ONE real, side-effecting adapter this checkpoint introduces:
`SandboxFileCreateAdapter` (file.create_sandboxed).

ToolDefinition (v0.1.3.2) says "what this tool is ALLOWED to represent" —
pure metadata, no executable capability. A ToolAdapter here says "TRUSTED
CODE capable of actually performing it." A registered ToolDefinition with
no matching adapter in ToolAdapterRegistry cannot execute — see
action_executor.py's ADAPTER_NOT_FOUND path. This separation is
deliberate: registering a tool's metadata (v0.1.3.2, already
model-input-proof) is a materially smaller trust boundary than registering
code capable of a real side effect, and this checkpoint keeps that second,
larger boundary to exactly one adapter, hand-written in this file.

Adapters are Python objects registered by application code only — see
ToolAdapterRegistry.register()'s isinstance/callable-shape checks. An
Action can supply a `tool_name` STRING to request routing to an adapter by
name; it can never supply a callable, an import path, a class name, a
module path, or a shell/subprocess command that becomes executable. There
is no code path anywhere in this module that imports, evals, or otherwise
turns Action/model-supplied data into executable capability.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field

from app.decision_intelligence.sandbox_fs import (
    SandboxPathError,
    check_content_size,
    check_no_overwrite,
    resolve_sandbox_path,
)
from app.decision_intelligence.schemas import (
    Action,
    EXECUTOR_FAILURE_CATEGORY,
    ExecutorFailureCode,
    ExecutionResult,
    VerificationResult,
)


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ExecutionContext:
    """Minimal trusted execution context (spec section 29). Every field is
    application-controlled; nothing here is ever set from Action/model
    input. `sandbox_root` is the ONLY filesystem root any adapter may write
    under — see app.config.settings.Settings.sandbox_root and
    action_executor.py, which is the only place this is constructed."""

    sandbox_root: Path
    now: Callable[[], datetime] = field(default=_default_now)
    attempt_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class EffectInspection(BaseModel):
    """v0.1.3.5, spec section 17 — the READ-ONLY report an adapter's
    optional `inspect_effect()` returns for reconciliation. Never implies
    a write/delete/modify happened or will happen."""

    exists: bool
    is_regular_file: bool | None = None
    inside_sandbox: bool | None = None
    is_symlink: bool | None = None
    size: int | None = None
    sha256: str | None = None
    relative_path: str | None = None
    # True/False when an expectation was available to compare against;
    # None when there was nothing to compare against (e.g. no fingerprint
    # on file, or the target doesn't exist at all).
    matches_expected: bool | None = None
    issues: list[str] = Field(default_factory=list)


class ToolAdapter(Protocol):
    """Every registered adapter implements this shape (duck-typed, matching
    app.agents.registry.AgentProtocol's convention — no forced base class).
    `inspect_effect` is OPTIONAL (spec section 17) — ToolAdapterRegistry
    does not require it, and reconciliation.py falls back to a safe,
    fail-closed AMBIGUOUS_STATE classification when an adapter lacks it."""

    name: str
    version: str

    async def execute(self, action: Action, context: ExecutionContext) -> ExecutionResult: ...

    async def verify(
        self, action: Action, execution_result: ExecutionResult, context: ExecutionContext
    ) -> VerificationResult: ...


class ToolAdapterRegistrationError(Exception):
    """Base class for all typed ToolAdapterRegistry errors."""


class DuplicateAdapterError(ToolAdapterRegistrationError):
    def __init__(self, tool_name: str):
        super().__init__(f"An adapter is already registered for '{tool_name}' (pass replace=True to replace it)")
        self.tool_name = tool_name


class UnknownAdapterError(ToolAdapterRegistrationError):
    def __init__(self, tool_name: str):
        super().__init__(f"No trusted adapter registered for '{tool_name}'")
        self.tool_name = tool_name


class InvalidAdapterError(ToolAdapterRegistrationError):
    pass


class ToolAdapterRegistry:
    """Deterministic, application-controlled adapter catalog — the trusted-
    capability counterpart to ToolRegistry's metadata catalog (v0.1.3.2).
    Unknown lookup fails closed; nothing here ever falls back to a default
    adapter."""

    def __init__(self) -> None:
        self._adapters: dict[str, ToolAdapter] = {}

    def register(self, tool_name: str, adapter: Any, *, replace: bool = False) -> None:
        if not hasattr(adapter, "execute") or not hasattr(adapter, "verify"):
            raise InvalidAdapterError(
                f"Object registered for '{tool_name}' does not implement execute()/verify() — "
                f"got {type(adapter).__name__}"
            )
        if not callable(getattr(adapter, "execute")) or not callable(getattr(adapter, "verify")):
            raise InvalidAdapterError(f"'{tool_name}' adapter's execute/verify attributes are not callable")
        if tool_name in self._adapters and not replace:
            raise DuplicateAdapterError(tool_name)
        self._adapters[tool_name] = adapter

    def get(self, tool_name: str) -> ToolAdapter:
        adapter = self._adapters.get(tool_name)
        if adapter is None:
            raise UnknownAdapterError(tool_name)
        return adapter

    def contains(self, tool_name: str) -> bool:
        return tool_name in self._adapters

    def list_tool_names(self) -> list[str]:
        return list(self._adapters.keys())


class SandboxFileCreateAdapter:
    """The ONE real, side-effecting adapter this checkpoint introduces.
    Writes exactly one UTF-8 text file, strictly inside `context.sandbox_root`
    (see sandbox_fs.py for the full path-safety contract), never overwriting
    an existing target, never exceeding the size limit, never following a
    symlink. `verify()` re-derives every claim from the actual filesystem —
    no trust is placed in what `execute()` merely reported.
    """

    name = "file.create_sandboxed"
    version = "1.0.0"

    async def execute(self, action: Action, context: ExecutionContext) -> ExecutionResult:
        started_at = context.now()
        relative_path = action.inputs.get("relative_path")
        content = action.inputs.get("content")

        if not isinstance(relative_path, str) or not isinstance(content, str):
            return self._failure(
                action,
                started_at,
                context.now(),
                ExecutorFailureCode.VALIDATION_FAILURE,
                "inputs.relative_path and inputs.content must both be strings",
                context.attempt_id,
            )

        try:
            target = resolve_sandbox_path(context.sandbox_root, relative_path)
            content_bytes = content.encode("utf-8")
            check_content_size(content_bytes)
            check_no_overwrite(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content_bytes)
        except SandboxPathError as exc:
            return self._failure(
                action,
                started_at,
                context.now(),
                ExecutorFailureCode.SANDBOX_VIOLATION,
                str(exc),
                context.attempt_id,
            )
        except OSError as exc:
            return self._failure(
                action,
                started_at,
                context.now(),
                ExecutorFailureCode.TOOL_EXECUTION_FAILURE,
                f"filesystem write failed: {exc}",
                context.attempt_id,
            )

        completed_at = context.now()
        digest = hashlib.sha256(content_bytes).hexdigest()
        sandbox_relative = target.relative_to(context.sandbox_root.resolve()).as_posix()
        return ExecutionResult(
            action_id=action.id,
            tool_name=self.name,
            started_at=started_at,
            completed_at=completed_at,
            success=True,
            output={
                "resolved_relative_path": sandbox_relative,
                "bytes_written": len(content_bytes),
                "content_hash": digest,
                "written_at": completed_at.isoformat(),
            },
            side_effects=[f"created:{sandbox_relative}"],
            cost=0.0,
            side_effect_occurred=True,
            execution_attempt_id=context.attempt_id,
            adapter_version=self.version,
        )

    async def verify(
        self, action: Action, execution_result: ExecutionResult, context: ExecutionContext
    ) -> VerificationResult:
        """Real, deterministic verification (spec section 23) — every claim
        is re-derived from the actual filesystem, never trusted from
        `execution_result.output` alone."""
        verified_at = context.now()
        issues: list[str] = []

        if not execution_result.success or not execution_result.output:
            return VerificationResult(
                action_id=action.id,
                method="sandbox_file_verification",
                expected="a successful prior execution result",
                observed="execution did not succeed",
                passed=False,
                confidence=0.0,
                issues=["execution_result.success is False; nothing to verify"],
                verified_at=verified_at,
            )

        sandbox_root_resolved = context.sandbox_root.resolve()
        relative_path = execution_result.output.get("resolved_relative_path")
        expected_hash = execution_result.output.get("content_hash")
        expected_bytes = execution_result.output.get("bytes_written")

        target = sandbox_root_resolved / relative_path if relative_path else None

        if target is None or not target.exists():
            issues.append("target file does not exist")
        else:
            resolved_target = target.resolve()
            if not resolved_target.is_relative_to(sandbox_root_resolved):
                issues.append("target no longer resolves inside the sandbox root")
            if not resolved_target.is_file() or resolved_target.is_symlink():
                issues.append("target is not a regular file")
            else:
                actual_bytes = resolved_target.read_bytes()
                if expected_bytes is not None and len(actual_bytes) != expected_bytes:
                    issues.append(
                        f"byte length mismatch: expected {expected_bytes}, got {len(actual_bytes)}"
                    )
                actual_hash = hashlib.sha256(actual_bytes).hexdigest()
                if expected_hash is not None and actual_hash != expected_hash:
                    issues.append(f"content hash mismatch: expected {expected_hash}, got {actual_hash}")
                try:
                    actual_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    issues.append("content does not round-trip as UTF-8")

        passed = not issues
        return VerificationResult(
            action_id=action.id,
            method="sandbox_file_verification",
            expected=f"file at '{relative_path}' matching hash {expected_hash}",
            observed="verified" if passed else "; ".join(issues),
            passed=passed,
            confidence=1.0 if passed else 0.0,
            issues=issues,
            verified_at=verified_at,
        )

    async def inspect_effect(self, action: Action, context: ExecutionContext) -> EffectInspection:
        """v0.1.3.5, spec section 17 — READ-ONLY reconciliation inspection.
        Never writes, deletes, or modifies anything. Recomputes the
        EXPECTED effect directly from `action.inputs` (the same
        authoritative payload `execute()` would have written from) and
        compares it against whatever actually exists on disk right now."""
        relative_path = action.inputs.get("relative_path")
        content = action.inputs.get("content")
        if not isinstance(relative_path, str) or not isinstance(content, str):
            return EffectInspection(exists=False, issues=["action.inputs missing relative_path/content; cannot inspect"])

        try:
            target = resolve_sandbox_path(context.sandbox_root, relative_path)
        except SandboxPathError as exc:
            return EffectInspection(exists=False, issues=[f"cannot resolve expected path: {exc}"])

        sandbox_root_resolved = context.sandbox_root.resolve()
        rel = target.relative_to(sandbox_root_resolved).as_posix()

        if not target.exists():
            return EffectInspection(exists=False, relative_path=rel, matches_expected=None)

        expected_bytes = content.encode("utf-8")
        expected_hash = hashlib.sha256(expected_bytes).hexdigest()

        issues: list[str] = []
        inside = target.is_relative_to(sandbox_root_resolved)
        if not inside:
            issues.append("target no longer resolves inside the sandbox")
        is_symlink = target.is_symlink()
        is_regular = target.is_file() and not is_symlink
        if not is_regular:
            issues.append("target is not a regular file")

        size = None
        actual_hash = None
        matches: bool | None = False
        if is_regular and inside:
            actual_bytes = target.read_bytes()
            size = len(actual_bytes)
            actual_hash = hashlib.sha256(actual_bytes).hexdigest()
            matches = actual_hash == expected_hash and size == len(expected_bytes)
            if not matches:
                issues.append("on-disk content does not match the expected content from action.inputs")

        return EffectInspection(
            exists=True,
            is_regular_file=is_regular,
            inside_sandbox=inside,
            is_symlink=is_symlink,
            size=size,
            sha256=actual_hash,
            relative_path=rel,
            matches_expected=matches,
            issues=issues,
        )

    def _failure(
        self,
        action: Action,
        started_at: datetime,
        completed_at: datetime,
        code: ExecutorFailureCode,
        message: str,
        attempt_id: str,
    ) -> ExecutionResult:
        return ExecutionResult(
            action_id=action.id,
            tool_name=self.name,
            started_at=started_at,
            completed_at=completed_at,
            success=False,
            error_type=EXECUTOR_FAILURE_CATEGORY[code],
            error_code=code.value,
            error_message=message,
            side_effect_occurred=False,
            execution_attempt_id=attempt_id,
            adapter_version=self.version,
        )


def build_default_adapter_registry() -> ToolAdapterRegistry:
    """The checkpoint's trusted adapter catalog: exactly one real adapter.
    Every other registered ToolDefinition (v0.1.3.2's
    build_default_tool_registry()) deliberately has NO matching adapter
    here — attempting to execute any of them fails closed with
    ADAPTER_NOT_FOUND (see action_executor.py)."""
    registry = ToolAdapterRegistry()
    registry.register(SandboxFileCreateAdapter.name, SandboxFileCreateAdapter())
    return registry
