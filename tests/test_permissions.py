"""Permission enforcement — no agent may act outside its registered permission set."""
from __future__ import annotations

import pytest

from app.database.models import PermissionLevel
from app.security.approvals import classify_risk, requires_human_approval
from app.security.permissions import (
    PermissionDeniedError,
    check_permission,
    requires_elevated_permission,
)


def test_check_permission_passes_for_granted_permission(registry):
    check_permission(registry, "execution", PermissionLevel.WRITE)  # should not raise


def test_check_permission_denies_ungranted_permission(registry):
    with pytest.raises(PermissionDeniedError):
        check_permission(registry, "research", PermissionLevel.WRITE)


def test_no_agent_has_elevated_permissions_by_default(registry):
    for agent_type in ("jarvis", "research", "strategy", "execution", "qa"):
        assert requires_elevated_permission(registry, agent_type) is False


def test_risk_classification_flags_consequential_actions():
    assert classify_risk("Please purchase the annual plan") is not None
    assert classify_risk("Publish the blog post") is not None
    assert classify_risk("Summarize the research findings") is None


def test_requires_human_approval_matches_risk_classification():
    assert requires_human_approval("Send a payment to the vendor") is True
    assert requires_human_approval("Draft an internal outline") is False
