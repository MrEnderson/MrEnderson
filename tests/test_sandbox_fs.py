"""Sandboxed filesystem path security (v0.1.3.4, spec section 32). All
tests use pytest's `tmp_path` — never a real user directory."""
from __future__ import annotations

import pytest

from app.decision_intelligence.sandbox_fs import (
    MAX_CONTENT_BYTES,
    SandboxContentTooLargeError,
    SandboxExtensionNotAllowedError,
    SandboxPathAbsoluteError,
    SandboxPathEmptyError,
    SandboxPathEscapeError,
    SandboxPathNullByteError,
    SandboxPathSymlinkError,
    SandboxPathTraversalError,
    SandboxTargetExistsError,
    check_content_size,
    check_no_overwrite,
    resolve_sandbox_path,
)


@pytest.fixture
def sandbox_root(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    return root


# --- Normal / nested paths ----------------------------------------------------


def test_normal_relative_path_resolves_inside_sandbox(sandbox_root):
    target = resolve_sandbox_path(sandbox_root, "note.txt")
    assert target.parent == sandbox_root.resolve()
    assert target.name == "note.txt"


def test_nested_relative_path_resolves_inside_sandbox(sandbox_root):
    target = resolve_sandbox_path(sandbox_root, "a/b/c/note.md")
    assert target.is_relative_to(sandbox_root.resolve())
    assert target.name == "note.md"


def test_nested_directories_do_not_need_to_exist_yet(sandbox_root):
    # resolve_sandbox_path only validates the path; it never creates dirs.
    target = resolve_sandbox_path(sandbox_root, "new/nested/dir/file.txt")
    assert not target.parent.exists()


# --- Traversal ------------------------------------------------------------


def test_parent_traversal_rejected(sandbox_root):
    with pytest.raises(SandboxPathTraversalError):
        resolve_sandbox_path(sandbox_root, "../outside.txt")


def test_nested_parent_traversal_rejected(sandbox_root):
    with pytest.raises(SandboxPathTraversalError):
        resolve_sandbox_path(sandbox_root, "a/../../outside.txt")


def test_backslash_traversal_rejected(sandbox_root):
    with pytest.raises(SandboxPathTraversalError):
        resolve_sandbox_path(sandbox_root, "a\\..\\..\\outside.txt")


def test_dot_segment_rejected(sandbox_root):
    with pytest.raises(SandboxPathTraversalError):
        resolve_sandbox_path(sandbox_root, "./note.txt")


# --- Absolute / UNC / drive paths --------------------------------------------


def test_posix_absolute_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathAbsoluteError):
        resolve_sandbox_path(sandbox_root, "/etc/passwd.txt")


def test_windows_absolute_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathAbsoluteError):
        resolve_sandbox_path(sandbox_root, "C:\\Windows\\System32\\evil.txt")


def test_windows_drive_relative_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathAbsoluteError):
        resolve_sandbox_path(sandbox_root, "C:evil.txt")


def test_unc_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathAbsoluteError):
        resolve_sandbox_path(sandbox_root, "\\\\server\\share\\evil.txt")


def test_unc_forward_slash_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathAbsoluteError):
        resolve_sandbox_path(sandbox_root, "//server/share/evil.txt")


# --- Empty / null byte ------------------------------------------------------


def test_empty_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathEmptyError):
        resolve_sandbox_path(sandbox_root, "")


def test_whitespace_only_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathEmptyError):
        resolve_sandbox_path(sandbox_root, "   ")


def test_null_byte_path_rejected(sandbox_root):
    with pytest.raises(SandboxPathNullByteError):
        resolve_sandbox_path(sandbox_root, "note\x00.txt")


# --- Target outside sandbox (post-resolution) --------------------------------


def test_target_outside_sandbox_via_sibling_prefix_is_not_fooled(tmp_path):
    # Regression guard against a naive string-prefix check: "sandbox-evil"
    # shares a string prefix with "sandbox" but must never be treated as
    # inside it.
    root = tmp_path / "sandbox"
    root.mkdir()
    sibling = tmp_path / "sandbox-evil"
    sibling.mkdir()
    (sibling / "leak.txt").write_text("leaked")
    # Even though a naive prefix check on strings would match, our
    # resolve()+is_relative_to() check must not.
    target = resolve_sandbox_path(root, "leak.txt")
    assert target.is_relative_to(root.resolve())
    assert target != sibling / "leak.txt"


# --- Existing file / overwrite policy ----------------------------------------


def test_existing_file_blocks_overwrite(sandbox_root):
    existing = sandbox_root / "already-there.txt"
    existing.write_text("original")
    target = resolve_sandbox_path(sandbox_root, "already-there.txt")
    with pytest.raises(SandboxTargetExistsError):
        check_no_overwrite(target)


def test_nonexistent_file_passes_overwrite_check(sandbox_root):
    target = resolve_sandbox_path(sandbox_root, "brand-new.txt")
    check_no_overwrite(target)  # must not raise


# --- Size limit ---------------------------------------------------------------


def test_content_within_limit_passes():
    check_content_size(b"x" * 100)  # must not raise


def test_content_exactly_at_limit_passes():
    check_content_size(b"x" * MAX_CONTENT_BYTES)  # must not raise


def test_content_over_limit_rejected():
    with pytest.raises(SandboxContentTooLargeError):
        check_content_size(b"x" * (MAX_CONTENT_BYTES + 1))


# --- Extension allowlist -------------------------------------------------------


def test_disallowed_extension_rejected(sandbox_root):
    with pytest.raises(SandboxExtensionNotAllowedError):
        resolve_sandbox_path(sandbox_root, "evil.exe")


def test_disallowed_script_extension_rejected(sandbox_root):
    with pytest.raises(SandboxExtensionNotAllowedError):
        resolve_sandbox_path(sandbox_root, "run.ps1")


def test_no_extension_rejected(sandbox_root):
    with pytest.raises(SandboxExtensionNotAllowedError):
        resolve_sandbox_path(sandbox_root, "no_extension_at_all")


def test_allowed_extension_txt_passes(sandbox_root):
    resolve_sandbox_path(sandbox_root, "note.txt")  # must not raise


def test_allowed_extension_json_passes(sandbox_root):
    resolve_sandbox_path(sandbox_root, "data.json")  # must not raise


# --- Symlink escape / safe symlink policy ------------------------------------


def test_symlink_escape_rejected(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "escape_link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(SandboxPathEscapeError):
        resolve_sandbox_path(root, "escape_link/leak.txt")


def test_existing_symlink_at_leaf_pointing_outside_is_rejected_as_escape(tmp_path):
    root = tmp_path / "sandbox"
    root.mkdir()
    real_target = tmp_path / "real_target.txt"
    real_target.write_text("hello")
    link = root / "link.txt"
    try:
        link.symlink_to(real_target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    # Denied either way (escape takes priority when both apply) — the
    # important invariant is that it is never silently followed.
    with pytest.raises((SandboxPathEscapeError, SandboxPathSymlinkError)):
        resolve_sandbox_path(root, "link.txt")


def test_safe_symlink_inside_sandbox_pointing_to_another_sandbox_file_is_still_rejected_at_leaf(tmp_path):
    # Even a symlink that stays entirely within the sandbox is rejected at
    # the leaf — resolve_sandbox_path never follows an existing symlink,
    # regardless of where it points (conservative, fail-closed default).
    root = tmp_path / "sandbox"
    root.mkdir()
    real = root / "real.txt"
    real.write_text("hello")
    link = root / "alias.txt"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted in this environment")

    with pytest.raises(SandboxPathSymlinkError):
        resolve_sandbox_path(root, "alias.txt")
