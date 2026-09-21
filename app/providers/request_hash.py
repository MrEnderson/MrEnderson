"""Canonical ProviderRequest/ProviderResponse fingerprinting (contract §13,
§17). Same allowlist-hash pattern as
`app/decision_intelligence/action_hash.py` — an explicit allowlist, not a
denylist, so a newly-added field defaults to NOT affecting the hash until
someone deliberately decides it should.

This does not build the durable `ModelInvocation` record (v0.2.7); it only
proves the request/response shapes are hashable in a way a future
`ModelInvocation.request_hash`/`response_hash` can rely on without a
redesign (contract §57).
"""
from __future__ import annotations

import hashlib
import json

from app.providers.contracts import ProviderRequest, ProviderResponse

# Fields included: the semantic content of what was asked. Fields
# deliberately EXCLUDED: request_id (the identifier itself, not part of
# "what was asked"), created_at (a timestamp), metadata (caller-supplied,
# non-semantic annotations).
_REQUEST_HASHED_FIELDS = (
    "provider_id",
    "model_id",
    "input",
    "system_instructions",
    "task_class",
    "required_capabilities",
    "structured_output_schema_name",
    "generation_parameters",
)

# Fields included: the semantic content of what was answered, plus the
# identifiers needed to correlate it back to a request. Fields deliberately
# EXCLUDED: created_at (a timestamp), usage (telemetry, not content),
# provider_metadata (opaque, untrusted, caller-supplied).
_RESPONSE_HASHED_FIELDS = (
    "request_id",
    "provider_id",
    "model_id",
    "content",
    "structured_output",
    "finish_reason",
)


def canonical_request_payload(request: ProviderRequest) -> dict:
    dumped = request.model_dump(mode="json")
    return {field: dumped[field] for field in _REQUEST_HASHED_FIELDS}


def compute_request_hash(request: ProviderRequest) -> str:
    payload = canonical_request_payload(request)
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def canonical_response_payload(response: ProviderResponse) -> dict:
    dumped = response.model_dump(mode="json")
    return {field: dumped[field] for field in _RESPONSE_HASHED_FIELDS}


def compute_response_hash(response: ProviderResponse) -> str:
    payload = canonical_response_payload(response)
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
