"""Deterministic retry/error-category classification (v0.1.3.1, spec
sections 7/17). No retry is ever executed here — classification only."""
from __future__ import annotations

import pytest

from app.decision_intelligence.retry_policy import is_potentially_retryable, is_replannable
from app.decision_intelligence.schemas import FailureCategory


@pytest.mark.parametrize(
    "category",
    [FailureCategory.TRANSIENT, FailureCategory.TOOL, FailureCategory.VERIFICATION],
)
def test_categories_that_are_potentially_retryable(category):
    assert is_potentially_retryable(category) is True


@pytest.mark.parametrize(
    "category",
    [
        FailureCategory.APPROVAL,
        FailureCategory.PERMISSION,
        FailureCategory.BUDGET,
        FailureCategory.SECURITY,
    ],
)
def test_categories_that_are_never_auto_retryable(category):
    assert is_potentially_retryable(category) is False


def test_security_failure_is_never_auto_retryable():
    assert is_potentially_retryable(FailureCategory.SECURITY) is False


def test_unknown_and_validation_are_conservatively_not_retryable():
    assert is_potentially_retryable(FailureCategory.UNKNOWN) is False
    assert is_potentially_retryable(FailureCategory.VALIDATION) is False


def test_only_verification_is_replannable():
    for category in FailureCategory:
        expected = category == FailureCategory.VERIFICATION
        assert is_replannable(category) is expected
