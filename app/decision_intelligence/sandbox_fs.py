"""Sandboxed filesystem path security (v0.1.3.4, spec sections 4/6/7/8/9/10).
The ONLY real side-effecting capability this checkpoint introduces routes
through `resolve_sandbox_path()` before ever touching a filesystem path —
nothing here executes anything; this module is pure path validation.

Threat model this defends against, deliberately not via string-prefix
checks (spec section 6 explicitly forbids those — e.g. a naive
`str(target).startswith(str(root))` is defeated by a sibling directory
that merely shares a prefix, such as root="/sandbox" matching
"/sandbox-evil"):

- absolute paths (POSIX `/etc/passwd`, Windows `C:\\...`, or `C:foo`
  drive-relative) — rejected by explicit string-level checks BEFORE any
  pathlib parsing, because `pathlib.Path.is_absolute()` is platform-
  dependent (on native Windows, `PureWindowsPath("/etc/passwd")` is NOT
  considered absolute — only a leading drive+root, or a UNC path, is — so
  relying on it alone would silently let a POSIX-style absolute path
  through on a Windows host).
- UNC paths (`\\\\server\\share`, `//server/share`) — caught by the same
  leading-slash/backslash check.
- `..` traversal, in either `/` or `\\`-separated form.
- null bytes, empty/whitespace-only input.
- symlink escapes — `Path.resolve()` dereferences every symlink in the
  parent chain that exists on disk; comparing the FULLY RESOLVED target
  against the FULLY RESOLVED sandbox root (via `Path.is_relative_to`,
  never a string prefix) means a symlink planted inside the sandbox that
  points outside it is caught here, not at write time.
- an existing symlink AT the leaf itself (`target.is_symlink()`) is
  rejected outright — never followed, even if it happens to resolve back
  inside the sandbox, since Windows junctions/reparse points are not
  uniformly introspectable at the pure-pathlib level and the conservative,
  fail-closed answer is to refuse rather than to try to classify it further.

This does not attempt any privileged OS-level trick (no ACL introspection,
no reparse-point-specific Win32 calls) — see the module's test file for the
explicit list of what is and is not covered, and
docs/decision_intelligence.md's v0.1.3.4 section for the honest limitation
this implies under true filesystem-level TOCTOU races.
"""
from __future__ import annotations

import re
from pathlib import Path

# spec section 9: 1 MiB, chosen as a conservative round number comfortably
# large enough for any inert text artifact this checkpoint's single adapter
# produces, small enough to bound worst-case sandbox disk usage per write.
# Not configurable via Action input — see SandboxContentTooLargeError.
MAX_CONTENT_BYTES = 1 * 1024 * 1024

# spec section 10: conservative allowlist of inert, non-executable text
# extensions. Deliberately excludes anything the OS could ever be induced
# to execute or interpret (.exe/.dll/.sh/.bat/.cmd/.ps1/.py/.js/.vbs/...),
# and excludes no-extension files too (a stricter default than strictly
# necessary, easy to loosen later, never silently widened by Action input).
ALLOWED_EXTENSIONS = frozenset({".txt", ".md", ".json", ".csv", ".log", ".yaml", ".yml"})

_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


class SandboxPathError(Exception):
    """Base class for every sandbox path-safety rejection. Fail-closed:
    raising one of these means NO write is ever attempted."""


class SandboxPathEmptyError(SandboxPathError):
    pass


class SandboxPathNullByteError(SandboxPathError):
    pass


class SandboxPathAbsoluteError(SandboxPathError):
    pass


class SandboxPathTraversalError(SandboxPathError):
    pass


class SandboxPathEscapeError(SandboxPathError):
    pass


class SandboxPathSymlinkError(SandboxPathError):
    pass


class SandboxExtensionNotAllowedError(SandboxPathError):
    pass


class SandboxContentTooLargeError(SandboxPathError):
    pass


class SandboxTargetExistsError(SandboxPathError):
    pass


def resolve_sandbox_path(sandbox_root: Path, relative_path: str) -> Path:
    """Validates `relative_path` and returns its fully resolved, guaranteed-
    inside-`sandbox_root` absolute Path. Never returns a path outside
    `sandbox_root`; always raises a typed SandboxPathError instead.

    `sandbox_root` is trusted application configuration (see
    app.config.settings.Settings.sandbox_root) — this function does not
    care where it came from, but callers must never let an Action/model
    input choose it.
    """
    if relative_path is None or not isinstance(relative_path, str) or relative_path.strip() == "":
        raise SandboxPathEmptyError("relative_path must be a non-empty string")
    if "\x00" in relative_path:
        raise SandboxPathNullByteError("relative_path must not contain a null byte")

    normalized = relative_path.replace("\\", "/")

    if normalized.startswith("/"):
        raise SandboxPathAbsoluteError(
            f"'{relative_path}' is an absolute or UNC path, not sandbox-relative"
        )
    if _DRIVE_PREFIX_RE.match(relative_path):
        raise SandboxPathAbsoluteError(f"'{relative_path}' is a Windows drive path, not sandbox-relative")

    segments = [seg for seg in normalized.split("/") if seg != ""]
    if not segments:
        raise SandboxPathEmptyError("relative_path must resolve to at least one path segment")
    if any(seg == ".." for seg in segments):
        raise SandboxPathTraversalError(f"'{relative_path}' contains a '..' traversal segment")
    if any(seg == "." for seg in segments):
        raise SandboxPathTraversalError(f"'{relative_path}' contains a '.' segment, which is not allowed")

    extension = Path(segments[-1]).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise SandboxExtensionNotAllowedError(
            f"'{segments[-1]}' has extension '{extension or '(none)'}', which is not in the allowed set "
            f"{sorted(ALLOWED_EXTENSIONS)}"
        )

    sandbox_root_resolved = sandbox_root.resolve()
    candidate = sandbox_root_resolved.joinpath(*segments)
    # Checked BEFORE resolve(): resolve() fully dereferences a symlink, so
    # by the time a path is resolved it never looks like a symlink anymore
    # (it IS its target) — the leaf's symlink-ness must be captured first.
    leaf_is_symlink = candidate.is_symlink()
    resolved_target = candidate.resolve()

    if not resolved_target.is_relative_to(sandbox_root_resolved):
        raise SandboxPathEscapeError(f"'{relative_path}' resolves outside the sandbox root")
    if leaf_is_symlink:
        raise SandboxPathSymlinkError(f"'{relative_path}' is an existing symlink, which is never followed")

    return resolved_target


def check_content_size(content: bytes) -> None:
    """Fail-closed size gate — checked BEFORE any write is attempted (spec
    section 9). Never adjustable by Action input."""
    if len(content) > MAX_CONTENT_BYTES:
        raise SandboxContentTooLargeError(
            f"content is {len(content)} bytes, exceeding the {MAX_CONTENT_BYTES}-byte sandbox limit"
        )


def check_no_overwrite(target: Path) -> None:
    """Default-deny overwrite policy (spec section 8). No `overwrite=True`
    escape hatch exists — a caller that needs to replace an existing file
    must use a separately permissioned future action, not this one."""
    if target.exists():
        raise SandboxTargetExistsError(f"'{target}' already exists; file.create_sandboxed never overwrites")
