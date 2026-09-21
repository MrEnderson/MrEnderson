"""Request/response/failure correlation checking (contract §27, hostile-
review §16). A provider (especially a hostile or buggy one) can return a
response — or raise a failure — whose `request_id`/`provider_id`/
`model_id` don't match what was actually requested. This module is the
minimal check that neither a mismatched response nor a mismatched failure
can silently masquerade as belonging to the request that was actually
made — a full correlation ledger belongs to the future durable
`ModelInvocation` record (v0.2.7), not here."""
from __future__ import annotations

from app.providers.contracts import ProviderRequest, ProviderResponse
from app.providers.failures import ProviderFailure, ProviderFailureCategory, ProviderFailureError


def validate_response_correlation(request: ProviderRequest, response: ProviderResponse) -> None:
    """Raises `ProviderFailureError` (category `INVALID_RESPONSE`) if
    `response` does not correlate to `request` on `request_id`,
    `provider_id`, or `model_id`. Fails closed: an ambiguous/mismatched
    response is a failure, never a best-effort success."""
    mismatches: list[str] = []
    if response.request_id != request.request_id:
        mismatches.append(
            f"request_id mismatch: requested {request.request_id!r}, got {response.request_id!r}"
        )
    if response.provider_id != request.provider_id:
        mismatches.append(
            f"provider_id mismatch: requested {request.provider_id!r}, got {response.provider_id!r}"
        )
    if response.model_id != request.model_id:
        mismatches.append(
            f"model_id mismatch: requested {request.model_id!r}, got {response.model_id!r}"
        )
    if mismatches:
        raise ProviderFailureError(
            ProviderFailure(
                category=ProviderFailureCategory.INVALID_RESPONSE,
                message="Response does not correlate to the request: " + "; ".join(mismatches),
                provider_id=request.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )
        )


def validate_failure_correlation(request: ProviderRequest, error: ProviderFailureError) -> None:
    """The failure-path counterpart to `validate_response_correlation`
    (hostile-review §16): raises a NEW `ProviderFailureError` (category
    `INVALID_RESPONSE`) if `error.failure` claims a `provider_id`,
    `model_id`, or `request_id` that contradicts what was actually
    requested — a `None` on the failure is "not asserted" and never
    counts as a mismatch, but an explicit, DIFFERENT value does. This
    stops a malicious/buggy provider from making its failure for request A
    appear to belong to request B."""
    failure = error.failure
    mismatches: list[str] = []
    if failure.request_id is not None and failure.request_id != request.request_id:
        mismatches.append(
            f"request_id mismatch: requested {request.request_id!r}, failure claims {failure.request_id!r}"
        )
    if failure.provider_id != request.provider_id:
        mismatches.append(
            f"provider_id mismatch: requested {request.provider_id!r}, failure claims {failure.provider_id!r}"
        )
    if failure.model_id is not None and failure.model_id != request.model_id:
        mismatches.append(
            f"model_id mismatch: requested {request.model_id!r}, failure claims {failure.model_id!r}"
        )
    if mismatches:
        raise ProviderFailureError(
            ProviderFailure(
                category=ProviderFailureCategory.INVALID_RESPONSE,
                message="Failure does not correlate to the request: " + "; ".join(mismatches),
                provider_id=request.provider_id,
                model_id=request.model_id,
                request_id=request.request_id,
            )
        ) from error
