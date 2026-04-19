"""Tests for manifest-only --analyze support in iceshelf-restore."""

import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from modules import restoreutils


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
RESTORE_BIN = os.path.join(REPO_ROOT, "iceshelf-restore")


def _run_restore(args, *, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, RESTORE_BIN] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def _write_manifest(path, *, modified=None, deleted=None, moved=None, previousbackup=None):
    payload = {
        "modified": modified or {},
        "deleted": deleted or [],
        "moved": moved or {},
    }
    if previousbackup is not None:
        payload["previousbackup"] = previousbackup
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _prepare_fake_gpg_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_gpg = bin_dir / "gpg"
    fake_gpg.write_text("""#!/usr/bin/python3
import sys


def read_input(path):
    if path == "-" or path is None:
        return sys.stdin.buffer.read()
    with open(path, "rb") as fp:
        return fp.read()


def write_output(path, data):
    if path in (None, "-"):
        sys.stdout.buffer.write(data)
        return
    with open(path, "wb") as fp:
        fp.write(data)


args = sys.argv[1:]
if "--version" in args:
    sys.stdout.write("gpg (fake) 1.0\\n")
    raise SystemExit(0)
if "--verify" in args or "--import" in args or "--import-ownertrust" in args:
    if "--import" in args or "--import-ownertrust" in args:
        sys.stdin.buffer.read()
    raise SystemExit(0)
if "--list-keys" in args or "--list-secret-keys" in args:
    raise SystemExit(0)

output_path = None
if "--output" in args:
    output_path = args[args.index("--output") + 1]

input_path = None
for value in reversed(args):
    if value == output_path:
        continue
    if value == "-" or not value.startswith("-"):
        input_path = value
        break

data = read_input(input_path)
write_output(output_path, data)
raise SystemExit(0)
""")
    fake_gpg.chmod(0o755)
    return {"PATH": str(bin_dir)}


def test_parse_analysis_threshold_supports_absolute_percent_and_clipping():
    absolute = restoreutils.parse_analysis_threshold("0", 9)
    percent = restoreutils.parse_analysis_threshold("10%", 6)
    clipped_percent = restoreutils.parse_analysis_threshold("0%", 500)

    assert absolute["threshold"] == 1
    assert percent["threshold"] == 1
    assert clipped_percent["value"] == 1
    assert clipped_percent["threshold"] == 5


def test_analyze_manifest_history_tracks_renamed_lifecycle_by_checksum():
    report = restoreutils.analyze_manifest_history({
        "b1": {
            "modified": {"/cache/a.tmp": {"checksum": "sha1:abc"}},
            "deleted": [],
            "moved": {},
        },
        "b2": {
            "modified": {"/cache/b.tmp": {"checksum": "sha1:abc"}},
            "deleted": [],
            "moved": {},
        },
        "b3": {
            "modified": {},
            "deleted": ["/cache/b.tmp"],
            "moved": {},
        },
    })

    assert report["total_actions"] == 3
    assert report["file_items"][0]["display_path"] == "/cache/b.tmp"
    assert report["file_items"][0]["action_count"] == 3
    assert report["file_items"][0]["modification_count"] == 2
    assert report["file_items"][0]["deletion_count"] == 1
    assert report["file_items"][0]["path_count"] == 2
    assert report["folder_items"][0]["display_path"] == "/cache"
    assert report["folder_items"][0]["action_count"] == 3


def test_analyze_manifest_history_uses_moved_entry_for_latest_delete_path():
    report = restoreutils.analyze_manifest_history({
        "b1": {
            "modified": {"/incoming/file.txt": {"checksum": "sha1:move"}},
            "deleted": [],
            "moved": {},
        },
        "b2": {
            "modified": {},
            "deleted": [],
            "moved": {"/transient/file.txt": "/incoming/file.txt"},
        },
        "b3": {
            "modified": {},
            "deleted": ["/transient/file.txt"],
            "moved": {},
        },
    })

    assert report["file_items"][0]["display_path"] == "/transient/file.txt"
    assert report["file_items"][0]["action_count"] == 2
    assert report["file_items"][0]["path_count"] == 2
    assert report["folder_items"][0]["display_path"] == "/transient"
    assert report["folder_items"][0]["action_count"] == 1
    assert report["folder_items"][0]["deletion_count"] == 1


def test_restore_analyze_rejects_incompatible_flags():
    result = _run_restore(["--analyze", "--validate", "dummy"])

    assert result.returncode == 2
    assert "--analyze cannot be combined" in result.stderr


def test_restore_analyze_rejects_invalid_threshold():
    result = _run_restore(["--analyze", "--analyze-activity", "abc", "dummy"])

    assert result.returncode == 2
    assert "activity threshold must be an integer or a percentage" in result.stderr


def test_restore_analyze_single_manifest_reports_lifecycle_and_exclude(tmp_path):
    manifest_path = _write_manifest(
        tmp_path / "backup-001.json",
        modified={
            "/var/cache/app.db": {"checksum": "sha1:db"},
            "/var/cache/app.log": {"checksum": "sha1:log"},
        },
        deleted=["/var/cache/app.log"],
    )

    result = _run_restore(["--analyze", str(manifest_path)])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Manifest analysis summary:" in result.stdout
    assert "Frequently changing file lifecycles:" in result.stdout
    assert "/var/cache/app.log | actions=2" in result.stdout
    assert "exclude=/var/cache/app.log" in result.stdout
    assert "Transient folders:" in result.stdout
    assert "/var/cache | actions=2" in result.stdout


def test_restore_analyze_directory_uses_all_manifests_in_order(tmp_path):
    _write_manifest(
        tmp_path / "backup-001.json",
        modified={
            "/cache/tmp1": {"checksum": "sha1:tmp1"},
            "/stable/data.txt": {"checksum": "sha1:stable"},
        },
    )
    _write_manifest(
        tmp_path / "backup-002.json",
        modified={
            "/cache/tmp2": {"checksum": "sha1:tmp2"},
            "/stable/data.txt": {"checksum": "sha1:stable"},
        },
        deleted=["/cache/tmp1"],
        previousbackup="backup-001",
    )
    _write_manifest(
        tmp_path / "backup-003.json",
        deleted=["/cache/tmp2"],
        previousbackup="backup-002",
    )

    result = _run_restore(["--analyze", "--analyze-activity", "2", str(tmp_path)])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "backups analyzed: 3" in result.stdout
    assert "/stable/data.txt | actions=2" in result.stdout
    assert "/cache | actions=4" in result.stdout
    assert "exclude=/cache/" in result.stdout


def test_restore_analyze_handles_signed_encrypted_manifest_with_fake_gpg(tmp_path):
    extra_env = _prepare_fake_gpg_env(tmp_path)
    manifest_path = _write_manifest(
        tmp_path / "backup-enc.json.gpg.asc",
        modified={"/volatile/file.txt": {"checksum": "sha1:enc"}},
    )

    result = _run_restore(["--analyze", str(manifest_path)], extra_env=extra_env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "/volatile/file.txt | actions=1" in result.stdout


@pytest.mark.parametrize(
    "value,total_actions,expected",
    [
        ("10", 8, 10),
        ("10%", 8, 1),
        ("25%", 8, 2),
    ],
)
def test_parse_analysis_threshold_resolves_expected_threshold(value, total_actions, expected):
    info = restoreutils.parse_analysis_threshold(value, total_actions)

    assert info["threshold"] == expected
