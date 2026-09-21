"""Approval-gate heuristics. Defense-in-depth on top of the planner's own
requires_approval flag: any task whose text implies a consequential action is
force-flagged for human approval even if the planner missed it."""
from __future__ import annotations

import re

from app.database.models import RiskLevel

_APPROVAL_KEYWORDS = {
    RiskLevel.CRITICAL: [
        r"\bpurchase\b", r"\bbuy\b", r"\bpayment\b", r"\bpay\b", r"\btransfer funds\b",
        r"\bdelete\b.*\baccount\b", r"\bdelete\b.*\bdatabase\b", r"\bwire\b",
    ],
    RiskLevel.HIGH: [
        r"\bpublish\b", r"\bsend email\b", r"\bpost to\b", r"\bmessage\b.*\bcustomer\b",
        r"\bdelete\b", r"\baccount change\b", r"\birreversible\b",
    ],
    RiskLevel.MEDIUM: [
        r"\bexternal\b", r"\bsend\b", r"\bnotify\b", r"\bcontact\b",
    ],
}


def classify_risk(text: str) -> RiskLevel | None:
    lowered = text.lower()
    for level in (RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM):
        for pattern in _APPROVAL_KEYWORDS[level]:
            if re.search(pattern, lowered):
                return level
    return None


def requires_human_approval(text: str) -> bool:
    return classify_risk(text) is not None
