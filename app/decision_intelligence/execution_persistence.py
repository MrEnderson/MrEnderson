"""Persistence bridge for durable execution state (v0.1.3.5, spec sections
4/5/9/10/11/23/32). Deliberately separate from both ends it connects, same
pattern as approval_persistence.py: app.database.repositories stays
domain-agnostic (plain ORM rows/kwargs), app.decision_intelligence's
pure-domain modules stay persistence-agnostic. This module is the only
place that knows about both, plus the handful of small deterministic
derivations (idempotency key, side-effect fingerprint, bounded
serialization) that don't belong in either.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.database.models import (
    ActionRecord,
    ExecutionResultRecord,
    PersistedActionStatus,
    ResultProvenance,
    VerificationResultRecord,
)
from app.decision_intelligence.action_hash import compute_action_hash
from app.decision_intelligence.schemas import Action, ActionStatus, ExecutionResult, VerificationResult

# --------------------------------------------------------------------------
# Bounded serialization (spec section 32)
# --------------------------------------------------------------------------

# Non-security-relevant free-text fields (output/observed/issues/error
# messages/etc.) are safely truncated with a visible marker if oversized —
# losing some diagnostic detail is acceptable; losing the fact that
# truncation happened is not.
MAX_TEXT_FIELD_CHARS = 4000
_TRUNCATION_MARKER = "...[truncated]"

# Security-relevant payloads (Action.inputs — part of action_hash) are
# NEVER truncated: truncating would silently change what a persisted
# row claims the authorized payload was, without changing the hash it's
# compared against, which could look like tampering either way. Persisting
# something that large fails closed instead.
MAX_INPUTS_JSON_CHARS = 200_000


class PayloadTooLargeForPersistenceError(Exception):
    """Fail-closed: a security-relevant payload (Action.inputs) exceeded
    the persistence bound and was NOT truncated or silently dropped."""


def bounded_text(value: str | None, *, max_chars: int = MAX_TEXT_FIELD_CHARS) -> str | None:
    if value is None:
        return None
    if len(value) <= max_chars:
        return value
    keep = max_chars - len(_TRUNCATION_MARKER)
    return value[: max(keep, 0)] + _TRUNCATION_MARKER


def bounded_json(value, *, max_chars: int = MAX_TEXT_FIELD_CHARS) -> str | None:
    if value is None:
        return None
    dumped = json.dumps(value, sort_keys=True, default=str)
    if len(dumped) <= max_chars:
        return dumped
    # A collection (list/dict) is safely re-serialized as a marker string
    # rather than sliced mid-JSON (which would produce invalid JSON) —
    # this path is only ever used for non-security-relevant fields.
    return json.dumps({"_truncated": True, "_original_chars": len(dumped)})


def safe_inputs_json(inputs: dict) -> str:
    """Security-relevant — fails closed rather than truncating (spec
    section 32)."""
    dumped = json.dumps(inputs, sort_keys=True, default=str)
    if len(dumped) > MAX_INPUTS_JSON_CHARS:
        raise PayloadTooLargeForPersistenceError(
            f"Action.inputs serializes to {len(dumped)} chars, exceeding the "
            f"{MAX_INPUTS_JSON_CHARS}-char persistence bound"
        )
    return dumped


# --------------------------------------------------------------------------
# Idempotency key / side-effect fingerprint (spec sections 11/23)
# --------------------------------------------------------------------------


def compute_idempotency_key(action_id: str, action_hash: str, attempt_number: int = 0) -> str:
    """Deterministic, never model-chosen (spec section 23) — the same
    Action, at the same authoritative action_hash, always derives the same
    key, which the database's UNIQUE constraint on
    ExecutionAttemptRecord.idempotency_key turns into the atomic execution
    claim (see ExecutionAttemptRepository.claim()).

    `attempt_number` (v0.1.3.7, spec sections 10/13): a bounded, authorized
    RETRY of the exact same Action deliberately keeps the SAME action_hash
    (spec section 13 — "same Action, same security-relevant payload...
    that is a retry; a changed hash is a REPLAN, not a retry"), so without
    this parameter every retry attempt would collide on the very
    idempotency-key uniqueness constraint that exists to PREVENT duplicate
    execution — the first (failed) attempt would forever "already own"
    the claim. Left at its default of 0, this produces the BYTE-IDENTICAL
    digest v0.1.3.5 always computed (`retry_controller.py` is the only
    caller that ever passes a nonzero value, using `Action.retry_count` —
    see its module docstring), so every pre-v0.1.3.7 caller and test is
    unaffected."""
    suffix = f":{attempt_number}" if attempt_number else ""
    return hashlib.sha256(f"{action_id}:{action_hash}{suffix}".encode("utf-8")).hexdigest()


def compute_side_effect_fingerprint(
    *, tool_name: str, relative_path: str, content_hash: str, expected_bytes: int
) -> str:
    """Deterministic reconciliation fingerprint for a sandbox file write
    (spec section 11) — NOT an approval hash; kept conceptually and
    algorithmically separate from action_hash.py::compute_action_hash().
    Canonical (fixed-order, explicit-delimiter) serialization so the same
    logical effect always fingerprints identically."""
    canonical = f"{tool_name}\n{relative_path}\n{content_hash}\n{expected_bytes}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Action <-> ActionRecord (spec sections 4/5/6)
# --------------------------------------------------------------------------


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def action_to_record_fields(action: Action) -> dict:
    """The exact fields persist_new_action()/ActionRecordRepository.create()
    needs, derived from a pydantic Action. `action_hash` reuses
    action_hash.py::compute_action_hash() EXACTLY — see this module's
    docstring and docs/decision_intelligence.md's v0.1.3.5 "Payload/hash
    integrity" section for why no second, competing hash was invented."""
    return dict(
        id=action.id,
        action_plan_id=action.action_plan_id,
        sequence=action.sequence,
        action_type=action.action_type,
        title=action.title,
        description=action.description or None,
        agent_type=action.agent_type,
        tool_name=action.tool_name,
        inputs_json=safe_inputs_json(action.inputs),
        action_hash=compute_action_hash(action),
        risk_level=action.risk_level,
        permission_level=action.permission_level,
        approval_required=action.approval_required,
        approval_id=action.approval_id,
        estimated_cost=action.estimated_cost,
        dependencies_json=bounded_json(action.dependencies),
        expected_result=bounded_text(action.expected_result),
        success_criteria=bounded_text(action.success_criteria),
        verification_method=bounded_text(action.verification_method),
        status=PersistedActionStatus(action.status.value),
        retry_count=action.retry_count,
        max_retries=action.max_retries,
        started_at=action.started_at,
        completed_at=action.completed_at,
        last_error=bounded_text(action.error),
        superseded_by_action_id=action.superseded_by,
    )


def record_to_action(row: ActionRecord) -> Action:
    """Reconstructs the pydantic Action from its durable row. `version` is
    NOT part of the domain object (it is a pure persistence/concurrency
    concept) — callers that need it read `row.version` directly."""
    return Action(
        id=row.id,
        action_plan_id=row.action_plan_id,
        sequence=row.sequence,
        action_type=row.action_type,
        title=row.title,
        description=row.description or "",
        agent_type=row.agent_type,
        tool_name=row.tool_name,
        inputs=json.loads(row.inputs_json) if row.inputs_json else {},
        risk_level=row.risk_level,
        permission_level=row.permission_level,
        approval_required=row.approval_required,
        approval_id=row.approval_id,
        estimated_cost=row.estimated_cost,
        dependencies=json.loads(row.dependencies_json) if row.dependencies_json else [],
        expected_result=row.expected_result or "",
        success_criteria=row.success_criteria or "",
        verification_method=row.verification_method or "",
        status=ActionStatus(row.status.value),
        started_at=_ensure_utc(row.started_at),
        completed_at=_ensure_utc(row.completed_at),
        retry_count=row.retry_count,
        max_retries=row.max_retries,
        error=row.last_error,
        superseded_by=row.superseded_by_action_id,
    )


# --------------------------------------------------------------------------
# ExecutionResult <-> ExecutionResultRecord (spec section 9)
# --------------------------------------------------------------------------


def execution_result_to_record_fields(
    attempt_id: str, result: ExecutionResult, *, provenance: ResultProvenance = ResultProvenance.ORIGINAL
) -> dict:
    output_json = bounded_json(result.output)
    output_hash = (
        hashlib.sha256(output_json.encode("utf-8")).hexdigest() if output_json is not None else None
    )
    return dict(
        attempt_id=attempt_id,
        action_id=result.action_id,
        tool_name=result.tool_name,
        success=result.success,
        provider_status=result.provider_status,
        structured_output_json=output_json,
        output_hash=output_hash,
        side_effect_occurred=result.side_effect_occurred,
        side_effects_json=bounded_json(result.side_effects),
        cost=result.cost,
        error_type=result.error_type.value if result.error_type else None,
        error_code=result.error_code,
        error_message=bounded_text(result.error_message),
        adapter_version=result.adapter_version,
        provenance=provenance,
        started_at=result.started_at,
        completed_at=result.completed_at,
    )


def record_to_execution_result(row: ExecutionResultRecord) -> ExecutionResult:
    from app.decision_intelligence.schemas import FailureCategory

    return ExecutionResult(
        action_id=row.action_id,
        tool_name=row.tool_name,
        started_at=_ensure_utc(row.started_at),
        completed_at=_ensure_utc(row.completed_at),
        success=row.success,
        provider_status=row.provider_status,
        output=json.loads(row.structured_output_json) if row.structured_output_json else None,
        side_effects=json.loads(row.side_effects_json) if row.side_effects_json else [],
        cost=row.cost,
        error_type=FailureCategory(row.error_type) if row.error_type else None,
        error_message=row.error_message,
        execution_attempt_id=row.attempt_id,
        error_code=row.error_code,
        side_effect_occurred=row.side_effect_occurred,
        adapter_version=row.adapter_version,
    )


# --------------------------------------------------------------------------
# VerificationResult <-> VerificationResultRecord (spec section 10)
# --------------------------------------------------------------------------


def verification_result_to_record_fields(
    attempt_id: str, result: VerificationResult, *, provenance: ResultProvenance = ResultProvenance.ORIGINAL
) -> dict:
    return dict(
        attempt_id=attempt_id,
        action_id=result.action_id,
        method=result.method,
        expected=bounded_text(result.expected),
        observed=bounded_text(result.observed),
        passed=result.passed,
        confidence=result.confidence,
        issues_json=bounded_json(result.issues),
        provenance=provenance,
        verified_at=result.verified_at,
    )


def record_to_verification_result(row: VerificationResultRecord) -> VerificationResult:
    return VerificationResult(
        action_id=row.action_id,
        method=row.method,
        expected=row.expected,
        observed=row.observed,
        passed=row.passed,
        confidence=row.confidence,
        issues=json.loads(row.issues_json) if row.issues_json else [],
        verified_at=_ensure_utc(row.verified_at),
    )
