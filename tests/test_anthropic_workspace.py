"""ANTHROPIC_WORKSPACE_ID support: optional anthropic-workspace-id header,
never leaked into logs, and the connectivity script's HTTP 400 error
classification (including the exact "not scoped to a workspace" message).
Fully offline — the AsyncAnthropic SDK client class itself is mocked at
construction time, so no test here ever reaches the network."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import anthropic
import pytest

from app.agents.providers import AnthropicProvider, get_default_provider
from app.config.settings import get_settings
from app.utils.logging import _redact_processor

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "test_anthropic_connection.py"


class _FakeAsyncAnthropic:
    """Stands in for anthropic.AsyncAnthropic — captures constructor kwargs
    without touching the network (construction alone never makes a request)."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _load_script_module():
    """Loads scripts/test_anthropic_connection.py as a module WITHOUT running
    its `if __name__ == "__main__":` guarded main() — exec_module() only runs
    top-level definitions, never main(), so this makes no network call."""
    spec = importlib.util.spec_from_file_location("_anthropic_connection_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _isolated_settings(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "")
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- AnthropicProvider: optional workspace header ----------------------------


def test_no_workspace_id_omits_default_headers(monkeypatch):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider = AnthropicProvider(api_key="sk-ant-fake")
    assert "default_headers" not in provider._client.kwargs


def test_empty_workspace_id_treated_as_not_configured(monkeypatch):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider = AnthropicProvider(api_key="sk-ant-fake", workspace_id="")
    assert "default_headers" not in provider._client.kwargs


def test_workspace_id_configured_sets_default_headers(monkeypatch):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider = AnthropicProvider(api_key="sk-ant-fake", workspace_id="wrkspc_123")
    assert provider._client.kwargs["default_headers"] == {"anthropic-workspace-id": "wrkspc_123"}


def test_correct_header_name_and_only_that_header(monkeypatch):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider = AnthropicProvider(api_key="sk-ant-fake", workspace_id="wrkspc_abc")
    headers = provider._client.kwargs["default_headers"]
    assert list(headers.keys()) == ["anthropic-workspace-id"]
    assert headers["anthropic-workspace-id"] == "wrkspc_abc"


def test_api_key_still_passed_through_unchanged(monkeypatch):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    provider = AnthropicProvider(api_key="sk-ant-fake-key", workspace_id="wrkspc_123")
    assert provider._client.kwargs["api_key"] == "sk-ant-fake-key"


def test_existing_construction_without_workspace_kwarg_still_works():
    """Backward compatibility: any existing call site that only passes
    api_key (no workspace_id at all) must keep working unchanged."""
    provider = AnthropicProvider(api_key="sk-ant-not-a-real-key")
    assert provider.name == "anthropic"


# --- get_default_provider() wiring -------------------------------------------


def test_get_default_provider_passes_configured_workspace_id(monkeypatch):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_from_settings")
    get_settings.cache_clear()

    provider = get_default_provider()

    assert isinstance(provider, AnthropicProvider)
    assert provider._client.kwargs["default_headers"] == {
        "anthropic-workspace-id": "wrkspc_from_settings"
    }


def test_get_default_provider_omits_header_when_unset(monkeypatch):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
    get_settings.cache_clear()

    provider = get_default_provider()

    assert isinstance(provider, AnthropicProvider)
    assert "default_headers" not in provider._client.kwargs


# --- Secrets never exposed ----------------------------------------------------


def test_redact_processor_redacts_workspace_id_field():
    redacted = _redact_processor(
        None, None, {"anthropic_workspace_id": "wrkspc_secret", "provider": "anthropic"}
    )
    assert redacted["anthropic_workspace_id"] == "***REDACTED***"
    assert redacted["provider"] == "anthropic"


def test_redact_processor_still_redacts_api_key_field():
    redacted = _redact_processor(None, None, {"anthropic_api_key": "sk-ant-secret"})
    assert redacted["anthropic_api_key"] == "***REDACTED***"


def test_get_default_provider_never_prints_key_or_workspace_id(monkeypatch, capsys):
    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeAsyncAnthropic)
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-SUPER-SECRET-VALUE")
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc-SUPER-SECRET-ID")
    get_settings.cache_clear()

    get_default_provider()

    captured = capsys.readouterr()
    assert "sk-ant-SUPER-SECRET-VALUE" not in captured.out
    assert "wrkspc-SUPER-SECRET-ID" not in captured.out
    assert "sk-ant-SUPER-SECRET-VALUE" not in captured.err
    assert "wrkspc-SUPER-SECRET-ID" not in captured.err


# --- Connectivity script: HTTP 400 classification, no live call -------------


def test_classify_bad_request_workspace_required():
    module = _load_script_module()
    category = module._classify_bad_request(
        "This API key is not scoped to a workspace, so this request must include "
        "the anthropic-workspace-id header with the ID of the workspace to use."
    )
    assert category == "workspace_required"


def test_classify_bad_request_insufficient_credits():
    module = _load_script_module()
    category = module._classify_bad_request(
        "Your credit balance is too low to access the Anthropic API."
    )
    assert category == "insufficient_credits"


def test_classify_bad_request_invalid_model():
    module = _load_script_module()
    category = module._classify_bad_request("The model `claude-does-not-exist` does not exist.")
    assert category == "invalid_model"


def test_classify_bad_request_other_falls_back():
    module = _load_script_module()
    category = module._classify_bad_request("Something else went wrong entirely.")
    assert category == "other"


class _FakeStatusError:
    def __init__(self, body=None):
        self.body = body

    def __str__(self):
        return "fallback string representation"


def test_error_message_extracts_message_from_body():
    module = _load_script_module()
    exc = _FakeStatusError({"error": {"message": "not scoped to a workspace"}})
    assert module._error_message(exc) == "not scoped to a workspace"


def test_error_message_falls_back_to_str_when_no_body():
    module = _load_script_module()
    exc = _FakeStatusError(None)
    assert module._error_message(exc) == "fallback string representation"


def test_script_reports_workspace_not_configured_by_default(monkeypatch):
    module = _load_script_module()
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "")
    module.get_settings.cache_clear()
    settings = module.get_settings()
    assert not settings.anthropic_workspace_id


def test_script_reports_workspace_configured_flag_only(monkeypatch):
    module = _load_script_module()
    monkeypatch.setenv("ANTHROPIC_WORKSPACE_ID", "wrkspc_real_value")
    module.get_settings.cache_clear()
    settings = module.get_settings()
    assert bool(settings.anthropic_workspace_id) is True
    # The script must only ever report the boolean presence, never the value —
    # verified structurally: main() prints the ternary string, never
    # `settings.anthropic_workspace_id` itself (see scripts/test_anthropic_connection.py).
    import inspect

    source = inspect.getsource(module.main)
    assert "settings.anthropic_workspace_id}" not in source
    assert "{settings.anthropic_workspace_id" not in source
