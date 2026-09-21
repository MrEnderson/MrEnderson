"""API keys and other secrets must never reach the log output. See
app/utils/logging.py::_redact_processor."""
from __future__ import annotations

from app.utils.logging import _redact_processor


def test_redacts_known_secret_fields():
    event = {
        "event": "provider_selected",
        "openai_api_key": "sk-super-secret",
        "anthropic_api_key": "sk-ant-super-secret",
        "api_key": "another-secret",
        "authorization": "Bearer secret-token",
        "password": "hunter2",
        "token": "abc123",
        "provider": "anthropic",
    }
    redacted = _redact_processor(None, None, dict(event))

    for key in ("openai_api_key", "anthropic_api_key", "api_key", "authorization", "password", "token"):
        assert redacted[key] == "***REDACTED***"
    assert redacted["provider"] == "anthropic"  # non-secret fields pass through untouched


def test_redaction_is_case_insensitive_on_key_name():
    redacted = _redact_processor(None, None, {"API_KEY": "sk-secret", "Token": "t"})
    assert redacted["API_KEY"] == "***REDACTED***"
    assert redacted["Token"] == "***REDACTED***"
