"""Behavior tests for max size slice looping in the iceshelf CLI."""

import json
import os
import subprocess
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ICESHELF_BIN = os.path.join(REPO_ROOT, "iceshelf")


def _write_stub_modules(stub_root):
    botocore_dir = stub_root / "botocore"
    botocore_dir.mkdir(parents=True, exist_ok=True)
    (stub_root / "paramiko.py").write_text("""
class PasswordRequiredException(Exception):
    pass


class AuthenticationException(Exception):
    pass


class SSHClient:
    pass


class AutoAddPolicy:
    pass
""".strip() + "\n")
    (stub_root / "boto3.py").write_text("""
class Session:
    def __init__(self, *args, **kwargs):
        pass
""".strip() + "\n")
    (botocore_dir / "__init__.py").write_text("")
    (botocore_dir / "exceptions.py").write_text("""
class ClientError(Exception):
    pass


class NoCredentialsError(Exception):
    pass


class NoRegionError(Exception):
    pass
""".strip() + "\n")


def _write_config(path, source_dir, *, max_size="", loop_slices=None):
    option_lines = [
        f"max size = {max_size}",
        "compress = no",
        "create filelist = no",
    ]
    if loop_slices is not None:
        option_lines.append(f"loop slices = {loop_slices}")

    path.write_text(f"""
[sources]
source = {source_dir}

[paths]
prep dir = {path.parent / "prep"}
data dir = {path.parent / "data"}
done dir = {path.parent / "done"}
create paths = yes

[options]
{chr(10).join(option_lines)}
""".strip() + "\n")


def _run_iceshelf(config_path):
    stub_root = config_path.parent / "stubs"
    _write_stub_modules(stub_root)

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(stub_root) if not existing_pythonpath else str(stub_root) + os.pathsep + existing_pythonpath

    return subprocess.run(
        [sys.executable, ICESHELF_BIN, str(config_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def _load_checksum(tmp_path):
    with open(tmp_path / "data" / "checksum.json", "r", encoding="utf-8") as fp:
        return json.load(fp)


def _create_source_files(source_dir):
    source_dir.mkdir()
    for name in ("a.txt", "b.txt", "c.txt"):
        (source_dir / name).write_text("123456")


def test_max_size_loops_through_all_slices_by_default(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, max_size="10")

    result = _run_iceshelf(config_path)

    assert result.returncode == 0
    data = _load_checksum(tmp_path)
    backup_ids = sorted(data["backups"])

    assert len(backup_ids) == 3
    assert backup_ids[0].endswith("-s0001")
    assert backup_ids[1].endswith("-s0002")
    assert backup_ids[2].endswith("-s0003")
    assert data["lastbackup"] == backup_ids[-1]
    assert sorted(os.listdir(tmp_path / "done")) == backup_ids


def test_max_size_can_keep_legacy_rerun_behavior(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, max_size="10", loop_slices="no")

    first = _run_iceshelf(config_path)
    second = _run_iceshelf(config_path)
    third = _run_iceshelf(config_path)

    assert first.returncode == 10
    assert second.returncode == 10
    assert third.returncode == 0

    data = _load_checksum(tmp_path)
    backup_ids = sorted(data["backups"])

    assert len(backup_ids) == 3
    assert all("-s" not in backup_id for backup_id in backup_ids)
    assert sorted(os.listdir(tmp_path / "done")) == backup_ids


def test_unlimited_backup_stays_single_archive(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, max_size="")

    result = _run_iceshelf(config_path)

    assert result.returncode == 0
    data = _load_checksum(tmp_path)
    backup_ids = sorted(data["backups"])

    assert len(backup_ids) == 1
    assert "-s" not in backup_ids[0]


def test_overlimit_run_does_not_mark_existing_files_deleted(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    initial_config = tmp_path / "initial.conf"
    _write_config(initial_config, source_dir, max_size="")
    initial = _run_iceshelf(initial_config)
    assert initial.returncode == 0

    overlimit_config = tmp_path / "overlimit.conf"
    _write_config(overlimit_config, source_dir, max_size="1")
    overlimit = _run_iceshelf(overlimit_config)

    assert overlimit.returncode == 3

    data = _load_checksum(tmp_path)
    assert data["dataset"][str(source_dir / "a.txt")]["checksum"] != ""
    assert len(data["backups"]) == 1
