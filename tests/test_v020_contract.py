"""Tests for the read-only v0.2.0 architecture/security contract validator
(scripts/check_v020_contract.py). These only exercise the static validator
itself -- they do not touch the database, network, or any ToolAdapter.

The mutation tests below exist because a hostile review of v0.2.0 found that
several fields the JSON contract already declared (e.g. no-authority-union
across delegations, credential isolation, fallback privacy-weakening,
preserved v0.1.3 components) were never actually checked by the validator --
a mutation flipping them would have passed silently. These tests pin that
those specific mutations are now caught."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_v020_contract.py"
_REAL_JSON_PATH = _REPO_ROOT / "docs" / "v0.2_architecture_security_contract.json"


def _load_validator_module():
    spec = importlib.util.spec_from_file_location("check_v020_contract", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_mutated_contract(tmp_path: Path, mutate) -> Path:
    """Copies the real, currently-passing contract into tmp_path, applies
    `mutate` to the parsed JSON in place, and writes both required files
    (the .md content is irrelevant to these tests) so the validator's
    file-existence check passes and only the mutation is under test."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md").write_text("stub", encoding="utf-8")

    data = json.loads(_REAL_JSON_PATH.read_text(encoding="utf-8"))
    mutate(data)
    (docs_dir / "v0.2_architecture_security_contract.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    return tmp_path


def test_validator_passes_against_real_contract() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "v0.2.0 CONTRACT CHECK: OK" in result.stdout


def test_validator_fails_closed_when_contract_files_missing(tmp_path, monkeypatch, capsys) -> None:
    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Missing required contract document" in captured.out


def test_validator_flags_missing_required_keys(tmp_path, monkeypatch, capsys) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "V0_2_ARCHITECTURE_AND_SECURITY_CONTRACT.md").write_text("stub", encoding="utf-8")
    (docs_dir / "v0.2_architecture_security_contract.json").write_text("{}", encoding="utf-8")

    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "missing required top-level key" in captured.out


def test_validator_catches_cross_delegation_authority_union(tmp_path, monkeypatch, capsys) -> None:
    def mutate(data: dict) -> None:
        data["authority_rules"]["cross_delegation_union_allowed"] = True

    _write_mutated_contract(tmp_path, mutate)
    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "cross_delegation_union_allowed" in captured.out


def test_validator_catches_credential_disclosure_to_models(tmp_path, monkeypatch, capsys) -> None:
    def mutate(data: dict) -> None:
        data["credential_rules"]["models_receive_raw_secrets"] = True

    _write_mutated_contract(tmp_path, mutate)
    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "models_receive_raw_secrets" in captured.out


def test_validator_catches_privacy_weakening_fallback(tmp_path, monkeypatch, capsys) -> None:
    def mutate(data: dict) -> None:
        data["provider_rules"]["fallback_may_weaken_privacy_or_permission_or_budget_policy"] = True

    _write_mutated_contract(tmp_path, mutate)
    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "fallback_may_weaken_privacy_or_permission_or_budget_policy" in captured.out


def test_validator_catches_removed_v013_compatibility_component(tmp_path, monkeypatch, capsys) -> None:
    def mutate(data: dict) -> None:
        data["permission_compatibility"]["preserved_v0_1_3_components"].remove("approval_engine")

    _write_mutated_contract(tmp_path, mutate)
    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "preserved_v0_1_3_components" in captured.out


def test_validator_catches_denial_evasion_allowed(tmp_path, monkeypatch, capsys) -> None:
    def mutate(data: dict) -> None:
        data["denial_persistence_rules"]["evasion_bypasses_denial"] = True

    _write_mutated_contract(tmp_path, mutate)
    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "evasion_bypasses_denial" in captured.out


def test_validator_catches_coding_agent_self_modification_allowed(tmp_path, monkeypatch, capsys) -> None:
    def mutate(data: dict) -> None:
        data["coding_agent_rules"]["agent_may_modify_protected_targets_as_ordinary_change"] = True

    _write_mutated_contract(tmp_path, mutate)
    module = _load_validator_module()
    monkeypatch.setattr(module, "_REPO_ROOT", tmp_path)

    exit_code = module.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "agent_may_modify_protected_targets_as_ordinary_change" in captured.out
