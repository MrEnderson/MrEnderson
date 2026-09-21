"""Static, non-destructive check of the v0.1.3 freeze baseline
(docs/V0_1_3_FREEZE_MANIFEST.md / docs/v0.1.3_freeze_manifest.json).

Verifies, WITHOUT touching the database, `.env`, the network, or any
application state:

  - the required freeze documents exist;
  - the JSON manifest is valid and internally consistent with itself;
  - the actual Alembic migration chain has exactly one head, matching the
    manifest's recorded head;
  - the actual default ToolAdapter registry contains exactly the adapters
    the manifest claims (today: `file.create_sandboxed` only).

This does NOT run pytest, does NOT run the hostile benchmark, does NOT
open a live database connection, and does NOT replace either. It is a
cheap regression tripwire a future change can run to notice it drifted
from the frozen baseline BEFORE running the real verification suite.

Usage:
    python scripts/check_v013_freeze_baseline.py

Exit code 0 = baseline matches. Exit code 1 = a discrepancy was found
(printed).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _fail(problems: list[str], message: str) -> None:
    problems.append(message)


def main() -> int:
    problems: list[str] = []

    manifest_md = _REPO_ROOT / "docs" / "V0_1_3_FREEZE_MANIFEST.md"
    manifest_json = _REPO_ROOT / "docs" / "v0.1.3_freeze_manifest.json"

    if not manifest_md.exists():
        _fail(problems, f"Missing required freeze document: {manifest_md}")
    if not manifest_json.exists():
        _fail(problems, f"Missing required freeze document: {manifest_json}")
        print("\n".join(problems))
        return 1

    try:
        data = json.loads(manifest_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(problems, f"{manifest_json} is not valid JSON: {exc}")
        print("\n".join(problems))
        return 1

    if data.get("status") != "FROZEN":
        _fail(problems, f"Manifest status is {data.get('status')!r}, expected 'FROZEN'")
    if data.get("version") != "v0.1.3":
        _fail(problems, f"Manifest version is {data.get('version')!r}, expected 'v0.1.3'")
    if data.get("test_failures") != 0:
        _fail(problems, f"Manifest records {data.get('test_failures')} test failures, expected 0")

    # --- Alembic: exactly one head, matching the manifest ---
    versions_dir = _REPO_ROOT / "migrations" / "versions"
    revisions: dict[str, str | None] = {}
    if versions_dir.exists():
        for f in versions_dir.glob("*.py"):
            text = f.read_text(encoding="utf-8")
            rev = down_rev = None
            for line in text.splitlines():
                if line.startswith("revision:") or line.startswith("revision ="):
                    rev = line.split("=", 1)[-1].strip().strip("\"'")
                elif line.startswith("down_revision:") or line.startswith("down_revision ="):
                    raw = line.split("=", 1)[-1].strip()
                    down_rev = None if raw.startswith("None") else raw.strip("\"'")
            if rev:
                revisions[rev] = down_rev
        parents = {d for d in revisions.values() if d is not None}
        heads = [r for r in revisions if r not in parents]
        if len(heads) != 1:
            _fail(problems, f"Expected exactly 1 Alembic head, found {len(heads)}: {heads}")
        else:
            expected_head = data.get("alembic_head")
            if heads[0] != expected_head:
                _fail(problems, f"Alembic head is {heads[0]!r}, manifest expects {expected_head!r}")
    else:
        _fail(problems, f"Migrations directory not found: {versions_dir}")

    # --- Adapter inventory: exactly what the manifest claims ---
    try:
        from app.decision_intelligence.tool_adapters import build_default_adapter_registry

        registry = build_default_adapter_registry()
        actual_adapters = sorted(registry.list_tool_names())
        expected_adapters = sorted(data.get("genuine_tool_adapters", []))
        if actual_adapters != expected_adapters:
            _fail(
                problems,
                f"Adapter registry is {actual_adapters}, manifest expects {expected_adapters}",
            )
    except Exception as exc:  # pragma: no cover - diagnostic path only
        _fail(problems, f"Could not inspect the default adapter registry: {exc}")

    if problems:
        print("v0.1.3 FREEZE BASELINE CHECK: DISCREPANCY FOUND")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("v0.1.3 FREEZE BASELINE CHECK: OK")
    print(f"  Alembic head: {data.get('alembic_head')}")
    print(f"  Genuine ToolAdapters: {data.get('genuine_tool_adapters')}")
    print(f"  Recorded test baseline: {data.get('test_count')} passed, {data.get('test_failures')} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
