"""Static, non-destructive check of the v0.2.6 DESIGN FREEZE baseline
(docs/V0_2_6_DESIGN_FREEZE_RECORD.md / docs/v0.2.6_design_freeze_manifest.json).

v0.2.6 is DESIGN_FROZEN at design revision r10, exactly as reviewed by HR12.
There is no v0.2.6 production code, and this checker deliberately imports
none. It verifies, WITHOUT touching the database, `.env`, the network,
credentials, providers or any ToolAdapter:

  - each of the twelve frozen artifacts (the r10 design and HR2..HR12)
    exists and its canonical bytes hash to the SHA-256 pinned in THIS file.
    The hashes are pinned here, not read from the manifest, so editing the
    manifest cannot launder a changed artifact. Canonical = CRLF normalized
    to LF (core.autocrlf may rewrite endings on checkout); any other CR byte
    is a failure;
  - HR12's section 2 hash table names exactly the pinned design and HR2..HR11
    hashes, HR12 reports no design freeze blockers, 0 CRITICAL / HIGH /
    MEDIUM findings, and the final status READY FOR OWNER FREEZE DECISION;
  - the design is revision r10 and still declares implementation_authorized
    = false;
  - the manifest is valid JSON, status DESIGN_FROZEN, lists exactly the
    pinned artifacts, records HR12-01 / HR12-02 as ACCEPTED non-freeze-
    blocking residuals that remain implementation blockers, and keeps every
    non-authorized flag (implementation, integration, migration,
    dependencies, configuration, .env, providers/tools, OpenDex, deployment,
    frozen validators, v0.2.7) exactly false;
  - the freeze record carries the status lines, the Human Owner authorization,
    every pinned hash, the residual constraints and the checkpoint line;
  - relative to the v0.2.5.1 predecessor commit, the ONLY new or modified
    files anywhere in the working tree are the freeze file set (so no
    production code, migration, test, dependency, configuration or existing
    validator has changed), no `app/context*` path exists, and no module in
    `app/` defines a class the v0.2.6 design proposes;
  - the Alembic revision graph (parsed from files, no DB) has the single head
    `7f2c9a1e4b6d`; the v0.1.3 and v0.2.5.1 tags still peel to their frozen
    commits; the ToolAdapter inventory is exactly `['file.create_sandboxed']`;
  - if the annotated tag `v0.2.6-design-freeze` exists: it is an annotated tag
    whose commit's sole parent is the predecessor, that commit changes exactly
    the freeze file set, and its committed blobs hash to the pinned values.
    With --require-tag, a missing tag is a failure.

This checker is supplemental evidence, not a proof: it verifies identity,
structure and scope, not the correctness of the design argument.

This is a read-only validator. It does not modify files, the database or
Git; it does not call external APIs, access the network, execute providers
or invoke ToolAdapters; it requires no secrets and does not read `.env`.

Usage:
    python scripts/check_v026_design_freeze.py [--require-tag]

Exit code 0 = the freeze baseline matches. Exit code 1 = a discrepancy was
found (printed).
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

_RECORD_PATH = "docs/V0_2_6_DESIGN_FREEZE_RECORD.md"
_MANIFEST_PATH = "docs/v0.2.6_design_freeze_manifest.json"
_VALIDATOR_PATH = "scripts/check_v026_design_freeze.py"
_DESIGN_PATH = "docs/V0_2_6_CONTEXT_BROKER_PROVENANCE_AND_DATA_BOUNDARIES_SECURITY_DESIGN.md"
_HR12_PATH = "docs/V0_2_6_HR12_FINAL_FREEZE_VERIFICATION.md"

_FREEZE_TAG = "v0.2.6-design-freeze"
_PREDECESSOR_COMMIT = "13796dcd61015098429f343e2fb982a9c75698bb"  # v0.2.5.1
_EXPECTED_V013_COMMIT = "be667b177f27839f5a370939bca045b7fb06eb4c"
_EXPECTED_ALEMBIC_HEAD = "7f2c9a1e4b6d"
_EXPECTED_TOOL_ADAPTERS = ["file.create_sandboxed"]

# (path, role, line count, SHA-256 of the canonical LF bytes). The design and
# HR2..HR11 values are those HR12 recorded in its section 2; HR12's value is
# the file as the Human Owner received it with the freeze authorization.
_FROZEN_ARTIFACTS: tuple[tuple[str, str, int, str], ...] = (
    (_DESIGN_PATH, "DESIGN_R10", 8397, "f934f3ec91365a63c6e27a9dcf1d17d08083866ff704bda3d9def0918d38e0b4"),
    ("docs/V0_2_6_INDEPENDENT_HOSTILE_SECURITY_REVIEW.md", "HR2", 1357,
     "ec7d9f3174fd61ae512f4562a5d91285b41a26e3bf96b13fde0af9eec94b9b2e"),
    ("docs/V0_2_6_FRESH_INDEPENDENT_SECURITY_VERIFICATION.md", "HR3", 1352,
     "081c8993bb7573b2a54cee65da57a08ae45c167bd23ebb2785252a5b2e40ee58"),
    ("docs/V0_2_6_POST_CORRECTION_SECURITY_VERIFICATION.md", "HR4", 1474,
     "d6a761010337579636897b591eca825b254a18a49d301d468a7e24e6126f379c"),
    ("docs/V0_2_6_HR5_POST_CORRECTION_SECURITY_VERIFICATION.md", "HR5", 1384,
     "921f4e83d9bce3ecf6182162d8657407672ce3a38d8f30ac5a0d78c4ec5ed9cd"),
    ("docs/V0_2_6_HR6_FINAL_DESIGN_VERIFICATION.md", "HR6", 1372,
     "42b170a580dba800fa310735c4ca0267083aa2beab0fb033fbebeeb289b4f07e"),
    ("docs/V0_2_6_HR7_FINAL_FREEZE_VERIFICATION.md", "HR7", 1179,
     "91e8d19eec8e98f38e7203b1f58d5181c2f25329c094de32fef53575fcecad64"),
    ("docs/V0_2_6_HR8_FREEZE_VERIFICATION.md", "HR8", 1256,
     "9848284e796f548b0012aa509de3b7a4cc3480f9fa5bad437020abf3d1b9aee7"),
    ("docs/V0_2_6_HR9_FREEZE_VERIFICATION.md", "HR9", 1266,
     "e8fcf9a2eb2598910b08c4cb64bc2c9d87c02ead5304743f6fb1c05f6ed73d15"),
    ("docs/V0_2_6_HR10_FINAL_FREEZE_VERIFICATION.md", "HR10", 1227,
     "a29b3e505313bab315c2f97ef780237cd401c5b844a1fc45848fad7f192c31a8"),
    ("docs/V0_2_6_HR11_FINAL_FREEZE_VERIFICATION.md", "HR11", 1165,
     "1ba2b13a59bad759de0de5029c9cd8fc800d957c3cc981f9538fd2757ee553eb"),
    (_HR12_PATH, "HR12", 1101, "bf3d9c33e5a4b0c0a91908af2bae14e16562497358895169e0362d9eb1722b61"),
)

# The complete set of files the freeze commit may add; nothing else may differ
# from the predecessor.
_FREEZE_FILES = frozenset(
    {path for path, _, _, _ in _FROZEN_ARTIFACTS} | {_RECORD_PATH, _MANIFEST_PATH, _VALIDATOR_PATH}
)

_MUST_BE_FALSE = (
    "implementation_authorized", "production_code_created",
    "pipeline_integration_authorized", "runtime_integration_authorized",
    "migration_authorized", "dependency_changes_authorized",
    "configuration_changes_authorized", "env_changes_authorized",
    "provider_enablement_authorized", "tool_enablement_authorized",
    "opendex_changes_authorized", "deployment_authorized",
    "frozen_validator_changes_authorized", "v0_2_7_authorized",
    "design_modified_during_freeze",
)
_RECORD_STATUS_LINES = (
    "status                              = DESIGN_FROZEN",
    "design_revision                     = r10",
    "human_owner_freeze_authorization    = GRANTED",
    *(f"{flag:<35} = false" for flag in _MUST_BE_FALSE if flag != "production_code_created"),
)
_RECORD_REQUIRED_TEXT = (
    "I authorize the Jarvis OS v0.2.6 security design revision r10, exactly as",
    "I accept HR12-01 and HR12-02 as non-freeze-blocking residual findings",
    "No v0.2.6 production implementation is authorized by this decision.",
    "**This record is authoritative for the v0.2.6 freeze status.**",
    "`|chain_predecessor_esc_ids| = 1`",
    "`ForkAuthorization.created_at ≤ instant + δ`",
    "NO v0.2.6 PRODUCTION IMPLEMENTATION HAS BEEN AUTHORIZED OR CREATED.",
)
_RESIDUAL_IDS = ("HR12-01", "HR12-02")
_INFO_IDS = ("HR12-03", "HR12-04")
_EXPECTED_COUNTS = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 2, "INFO": 2}
_HR12_FINAL_STATUS = "R10 DESIGN READY FOR OWNER FREEZE DECISION"
_HR12_COUNTS_RE = re.compile(
    r"\*\*Counts:\*\* CRITICAL 0 · HIGH 0 · MEDIUM 0 · LOW 2 \(HR12-01, HR12-02\) ·\s+INFO 2 \(HR12-03, HR12-04\)"
)
_HR12_NO_BLOCKERS_RE = re.compile(r"^## 27\. Design freeze blockers\n\n`NONE`$", re.MULTILINE)
_DESIGN_REQUIRED_LINES = (
    re.compile(r"^design_revision += r10 ", re.MULTILINE),
    re.compile(r"^implementation_authorized += false$", re.MULTILINE),
    re.compile(r"^\*\*No v0\.2\.6 production implementation has been authorized or created\.\*\*$", re.MULTILINE),
)

# Components the v0.2.6 design proposes. None may exist as a class in app/.
_DESIGN_ONLY_CLASS_NAMES = frozenset({
    "ContextBroker", "ExecutionControlFacts", "ForkAuthorization", "LocalRenunciationRecord",
    "RevocationTargetHandle", "PendingModelRevocation", "RevocationRequestResult",
    "ChildIssuanceResult", "IntegrationActivation", "ActivationManifest", "LineagePair",
    "TaskProfile", "T7Policy", "InternalEndpointPolicy",
})


def canonical_bytes(raw: bytes) -> bytes | None:
    """CRLF -> LF. Returns None if any other CR byte remains."""
    lf = raw.replace(b"\r\n", b"\n")
    return None if b"\r" in lf else lf


def check_artifact_bytes(path: str, raw: bytes, where: str) -> list[str]:
    expected = {p: (lines, digest) for p, _, lines, digest in _FROZEN_ARTIFACTS}[path]
    lf = canonical_bytes(raw)
    if lf is None:
        return [f"{where} {path}: contains a CR byte outside a CRLF pair"]
    problems = []
    digest = hashlib.sha256(lf).hexdigest()
    if digest != expected[1]:
        problems.append(f"{where} {path}: sha256 {digest} != frozen {expected[1]}")
    lines = lf.count(b"\n")
    if lines != expected[0]:
        problems.append(f"{where} {path}: {lines} lines != frozen {expected[0]}")
    return problems


def check_frozen_artifacts(repo_root: Path) -> list[str]:
    problems: list[str] = []
    for path, _, _, _ in _FROZEN_ARTIFACTS:
        f = repo_root / path
        if not f.is_file():
            problems.append(f"missing frozen artifact: {path}")
            continue
        problems.extend(check_artifact_bytes(path, f.read_bytes(), "working tree"))
    return problems


def check_hr12(hr12_text: str) -> list[str]:
    """HR12 recorded the reviewed hashes and cleared the design for freeze."""
    problems: list[str] = []
    for path, role, _, digest in _FROZEN_ARTIFACTS:
        if role == "HR12":
            continue
        if not re.search(rf"^\| `{re.escape(path)}` \| [^|]+ \| `{digest}` \|$", hr12_text, flags=re.MULTILINE):
            problems.append(f"HR12 section 2 does not record {role} {path} with sha256 {digest}")
    if not re.search(rf"^final_status += {re.escape(_HR12_FINAL_STATUS)}$", hr12_text, flags=re.MULTILINE):
        problems.append(f"HR12 final_status is not {_HR12_FINAL_STATUS!r}")
    if not _HR12_NO_BLOCKERS_RE.search(hr12_text):
        problems.append("HR12 section 27 does not record design freeze blockers `NONE`")
    if not _HR12_COUNTS_RE.search(hr12_text):
        problems.append("HR12 finding counts are not CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 2 / INFO 2")
    for fid in (*_RESIDUAL_IDS, *_INFO_IDS):
        if not re.search(rf"^### {re.escape(fid)} — ", hr12_text, flags=re.MULTILINE):
            problems.append(f"HR12 does not define finding {fid}")
    for fid in _RESIDUAL_IDS:
        block = hr12_text.split(f"### {fid} — ", 1)[-1].split("\n### ", 1)[0]
        if "- **Freeze blocker:** NO" not in block:
            problems.append(f"HR12 does not classify {fid} as non-freeze-blocking")
    return problems


def check_design(design_text: str) -> list[str]:
    return [
        f"design does not state {pattern.pattern!r}"
        for pattern in _DESIGN_REQUIRED_LINES
        if not pattern.search(design_text)
    ]


def check_manifest(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["manifest top level is not an object"]
    problems: list[str] = []
    expected_scalars = {
        "version": "v0.2.6", "status": "DESIGN_FROZEN", "design_revision": "r10",
        "freeze_record": _RECORD_PATH, "freeze_validator": _VALIDATOR_PATH, "freeze_tag": _FREEZE_TAG,
        "predecessor_commit": _PREDECESSOR_COMMIT, "controlling_review": "HR12",
        "controlling_review_final_status": _HR12_FINAL_STATUS,
        "human_owner_freeze_authorization": "GRANTED", "hash_algorithm": "sha256",
        "alembic_head_expected": _EXPECTED_ALEMBIC_HEAD,
    }
    for key, value in expected_scalars.items():
        if data.get(key) != value:
            problems.append(f"manifest {key} is {data.get(key)!r}, expected {value!r}")
    if data.get("design_frozen") is not True:
        problems.append("manifest design_frozen must be exactly true")
    for flag in _MUST_BE_FALSE:
        if data.get(flag) is not False:
            problems.append(f"manifest {flag} must be exactly false")
    if data.get("tool_adapters_expected") != _EXPECTED_TOOL_ADAPTERS:
        problems.append("manifest tool_adapters_expected does not match the frozen inventory")
    if data.get("hr12_finding_counts") != _EXPECTED_COUNTS:
        problems.append(f"manifest hr12_finding_counts is {data.get('hr12_finding_counts')!r}")
    if data.get("design_freeze_blockers") != []:
        problems.append("manifest design_freeze_blockers must be empty")

    listed = [
        (a.get("path"), a.get("role"), a.get("lines"), a.get("sha256"))
        for a in data.get("frozen_artifacts") or [] if isinstance(a, dict)
    ]
    if listed != list(_FROZEN_ARTIFACTS):
        problems.append("manifest frozen_artifacts do not exactly match the pinned artifacts")

    residuals = [r for r in data.get("accepted_residual_findings") or [] if isinstance(r, dict)]
    if [r.get("id") for r in residuals] != list(_RESIDUAL_IDS):
        problems.append(f"manifest accepted_residual_findings must be exactly {list(_RESIDUAL_IDS)}")
    for r in residuals:
        if r.get("owner_disposition") != "ACCEPTED_NON_FREEZE_BLOCKING" or r.get("severity") != "LOW":
            problems.append(f"{r.get('id')} must be a LOW finding ACCEPTED_NON_FREEZE_BLOCKING")
        if r.get("freeze_blocker") is not False or r.get("implementation_blocker") is not True:
            problems.append(f"{r.get('id')} must be freeze_blocker=false and implementation_blocker=true")
        if r.get("folded_into_frozen_text") is not False:
            problems.append(f"{r.get('id')} must record folded_into_frozen_text=false")
        if not str(r.get("implementation_constraint", "")).strip():
            problems.append(f"{r.get('id')} lacks its implementation constraint")
    info = [r.get("id") for r in data.get("carried_info_findings") or [] if isinstance(r, dict)]
    if info != list(_INFO_IDS):
        problems.append(f"manifest carried_info_findings must be exactly {list(_INFO_IDS)}")
    return problems


def check_record(text: str) -> list[str]:
    problems: list[str] = []
    for line in _RECORD_STATUS_LINES:
        if not re.search(rf"^{re.escape(line)}$", text, flags=re.MULTILINE):
            problems.append(f"freeze record must state {line!r}")
    for snippet in _RECORD_REQUIRED_TEXT:
        if snippet not in text:
            problems.append(f"freeze record lacks {snippet!r}")
    for path, _, _, digest in _FROZEN_ARTIFACTS:
        if not re.search(rf"^\| `{re.escape(path)}` \|.*\| `{digest}` \|$", text, flags=re.MULTILINE):
            problems.append(f"freeze record does not list {path} with sha256 {digest}")
    for fid in _RESIDUAL_IDS:
        if f"### {fid} (LOW)" not in text:
            problems.append(f"freeze record does not record the accepted residual {fid}")
    return problems


def _git(*args: str, binary: bool = False) -> Any:
    try:
        out = subprocess.run(
            ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=not binary, check=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if binary else out.stdout.rstrip()


def _alembic_heads(versions_dir: Path) -> list[str]:
    """Heads of the revision graph, parsed from migration files (no DB)."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in versions_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        values: dict[str, Any] = {}
        for node in tree.body:
            targets = []
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            for t in targets:
                if isinstance(t, ast.Name) and t.id in ("revision", "down_revision"):
                    values[t.id] = ast.literal_eval(value)
        if "revision" not in values:
            continue
        revisions.add(values["revision"])
        down = values.get("down_revision")
        if isinstance(down, str):
            parents.add(down)
        elif isinstance(down, (tuple, list)):
            parents.update(down)
    return sorted(revisions - parents)


def _check_no_design_classes(repo_root: Path) -> list[str]:
    problems: list[str] = []
    for path in (repo_root / "app").rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"could not parse {rel}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in _DESIGN_ONLY_CLASS_NAMES:
                problems.append(f"v0.2.6 design-only class {node.name!r} is defined in production code: {rel}")
    return problems


def check_tag(require: bool) -> list[str]:
    """The annotated freeze tag, if present, pins exactly the freeze commit."""
    if _git("rev-parse", "-q", "--verify", f"refs/tags/{_FREEZE_TAG}") is None:
        return [f"freeze tag {_FREEZE_TAG} does not exist"] if require else []
    problems: list[str] = []
    if _git("cat-file", "-t", f"refs/tags/{_FREEZE_TAG}") != "tag":
        problems.append(f"{_FREEZE_TAG} is not an annotated tag")
    commit = _git("rev-parse", f"{_FREEZE_TAG}^{{commit}}")
    parents = (_git("rev-list", "--parents", "-n", "1", str(commit)) or "").split()[1:]
    if parents != [_PREDECESSOR_COMMIT]:
        problems.append(f"{_FREEZE_TAG} commit parents are {parents}, expected [{_PREDECESSOR_COMMIT}]")
    changed = _git("diff", "--name-only", "--no-renames", _PREDECESSOR_COMMIT, str(commit))
    if changed is None or set(changed.splitlines()) != _FREEZE_FILES:
        problems.append(f"{_FREEZE_TAG} commit does not change exactly the freeze file set: {changed!r}")
    for path, _, _, _ in _FROZEN_ARTIFACTS:
        blob = _git("show", f"{commit}:{path}", binary=True)
        if blob is None:
            problems.append(f"{_FREEZE_TAG} lacks {path}")
        else:
            problems.extend(check_artifact_bytes(path, blob, f"tag {_FREEZE_TAG}"))
    return problems


def check_repository(repo_root: Path) -> list[str]:
    problems: list[str] = []
    if _git("merge-base", "--is-ancestor", _PREDECESSOR_COMMIT, "HEAD") is None:
        problems.append(f"predecessor {_PREDECESSOR_COMMIT} is not an ancestor of HEAD")

    tracked = _git("diff", "--name-only", "--no-renames", _PREDECESSOR_COMMIT)
    untracked = _git("ls-files", "--others", "--exclude-standard")
    if tracked is None or untracked is None:
        problems.append("git unavailable: cannot verify the changed-file allowlist")
    else:
        for path in sorted(set(tracked.splitlines()) | set(untracked.splitlines())):
            if path and path not in _FREEZE_FILES:
                problems.append(f"file outside the v0.2.6 freeze set differs from {_PREDECESSOR_COMMIT[:7]}: {path}")

    for path in (repo_root / "app").glob("context*"):
        problems.append(f"forbidden v0.2.6 implementation path exists: {path.relative_to(repo_root).as_posix()}")
    problems.extend(_check_no_design_classes(repo_root))

    heads = _alembic_heads(repo_root / "migrations" / "versions")
    if heads != [_EXPECTED_ALEMBIC_HEAD]:
        problems.append(f"Alembic heads are {heads!r}, expected [{_EXPECTED_ALEMBIC_HEAD!r}]")
    if _git("rev-parse", "v0.1.3^{}") != _EXPECTED_V013_COMMIT:
        problems.append(f"v0.1.3^{{}} does not resolve to {_EXPECTED_V013_COMMIT}")
    if _git("rev-parse", "v0.2.5.1^{}") != _PREDECESSOR_COMMIT:
        problems.append(f"v0.2.5.1^{{}} does not resolve to {_PREDECESSOR_COMMIT}")

    try:
        sys.path.insert(0, str(repo_root))
        from app.decision_intelligence.tool_adapters import build_default_adapter_registry

        adapters = sorted(build_default_adapter_registry().list_tool_names())
        if adapters != _EXPECTED_TOOL_ADAPTERS:
            problems.append(f"ToolAdapter inventory is {adapters!r}, expected {_EXPECTED_TOOL_ADAPTERS!r}")
    except ImportError as exc:
        problems.append(f"Could not import ToolAdapterRegistry to verify inventory: {exc}")
    return problems


def _read_text(rel: str, problems: list[str]) -> str:
    f = _REPO_ROOT / rel
    if not f.is_file():
        problems.append(f"missing freeze document: {rel}")
        return ""
    return f.read_text(encoding="utf-8")


def main(argv: list[str]) -> int:
    require_tag = "--require-tag" in argv
    problems = check_frozen_artifacts(_REPO_ROOT)
    problems.extend(check_hr12(_read_text(_HR12_PATH, problems)))
    problems.extend(check_design(_read_text(_DESIGN_PATH, problems)))
    problems.extend(check_record(_read_text(_RECORD_PATH, problems)))
    manifest_text = _read_text(_MANIFEST_PATH, problems)
    if manifest_text:
        try:
            problems.extend(check_manifest(json.loads(manifest_text)))
        except json.JSONDecodeError as exc:
            problems.append(f"manifest JSON is invalid: {exc}")
    problems.extend(check_repository(_REPO_ROOT))
    problems.extend(check_tag(require_tag))

    if problems:
        print("v0.2.6 DESIGN FREEZE CHECK: DISCREPANCY FOUND")
        for p in problems:
            print(f"  - {p}")
        return 1

    tag_present = _git("rev-parse", "-q", "--verify", f"refs/tags/{_FREEZE_TAG}") is not None
    print("v0.2.6 DESIGN FREEZE CHECK: OK")
    print("  Status: DESIGN_FROZEN at r10 (as reviewed by HR12); implementation NOT authorized")
    print(f"  Frozen artifacts: {len(_FROZEN_ARTIFACTS)} (r10 design + HR2..HR12), sha256 pinned")
    print("  Accepted residuals: HR12-01, HR12-02 (non-freeze-blocking; implementation blockers)")
    print(f"  Changes since v0.2.5.1 ({_PREDECESSOR_COMMIT[:7]}): freeze file set only")
    print(f"  Freeze tag {_FREEZE_TAG}: {'verified' if tag_present else 'not yet created'}")
    print(f"  Alembic head: {_EXPECTED_ALEMBIC_HEAD}")
    print(f"  ToolAdapters: {_EXPECTED_TOOL_ADAPTERS}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
