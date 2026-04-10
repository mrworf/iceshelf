"""Unit and regression tests for restore parity handling."""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from modules import gpg as gpg_module
from modules import restoreutils


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ICESHELF_BIN = os.path.join(REPO_ROOT, "iceshelf")
RESTORE_BIN = os.path.join(REPO_ROOT, "iceshelf-restore")


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


def _run_restore(args):
    return subprocess.run(
        [sys.executable, RESTORE_BIN] + args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _write_backup_config(path, source_dir):
    path.write_text(f"""
[sources]
source = {source_dir}

[paths]
prep dir = {path.parent / "prep"}
data dir = {path.parent / "data"}
done dir = {path.parent / "done"}
create paths = yes

[options]
compress = no

[security]
add parity = 5
""".strip() + "\n")


def test_get_parity_files_finds_signed_and_volume_files(tmp_path):
    archive_name = "backup.tar"
    base = tmp_path
    for name in (
        "backup.tar.par2",
        "backup.tar.par2.sig",
        "backup.tar.vol000+001.par2",
        "backup.tar.vol001+002.par2.sig",
        "backup.tar.txt",
        "other.tar.par2",
    ):
        (base / name).write_text("x")

    found = restoreutils.get_parity_files(str(base), archive_name)

    assert found == sorted([
        str(base / "backup.tar.par2"),
        str(base / "backup.tar.par2.sig"),
        str(base / "backup.tar.vol000+001.par2"),
        str(base / "backup.tar.vol001+002.par2.sig"),
    ])


def test_get_files_for_basename_includes_parity_sidecars(tmp_path):
    basename = "backup"
    backup_dir = tmp_path
    for name in (
        "backup.json",
        "backup.tar",
        "backup.tar.par2",
        "backup.tar.vol000+001.par2.sig",
        "backup.lst",
    ):
        (backup_dir / name).write_text("x")

    found = restoreutils.get_files_for_basename(str(backup_dir), basename)

    assert found == [
        "backup.json",
        "backup.tar",
        "backup.tar.par2",
        "backup.tar.vol000+001.par2.sig",
        "backup.lst",
    ]


def test_get_files_for_basename_supports_signed_archive_and_signed_parity(tmp_path):
    basename = "backup"
    backup_dir = tmp_path
    for name in (
        "backup.json.asc",
        "backup.tar.sig",
        "backup.tar.sig.par2.sig",
        "backup.tar.sig.vol000+001.par2.sig",
        "backup.lst.asc",
    ):
        (backup_dir / name).write_text("x")

    found = restoreutils.get_files_for_basename(str(backup_dir), basename)

    assert found == [
        "backup.json.asc",
        "backup.tar.sig",
        "backup.tar.sig.par2.sig",
        "backup.tar.sig.vol000+001.par2.sig",
        "backup.lst.asc",
    ]


def test_valid_archive_treats_corrupt_archive_with_parity_as_repairable(tmp_path, caplog):
    manifest = tmp_path / "backup.json"
    archive = tmp_path / "backup.tar"
    parity = tmp_path / "backup.tar.par2"
    manifest.write_text("{}")
    archive.write_text("broken archive")
    parity.write_text("parity data")

    filelist = tmp_path / "backup.lst"
    filelist.write_text(
        f"{_sha1(manifest)}  backup.json\n"
        f"{'0'*40}  backup.tar\n"
        f"{_sha1(parity)}  backup.tar.par2\n"
    )

    corrupt = []
    found = []
    caplog.set_level(logging.WARNING)

    ok = restoreutils.valid_archive(str(tmp_path), str(filelist), corrupt, found)

    assert ok is False
    assert corrupt == ["backup.tar"]
    assert "backup.tar.par2" in found
    assert "parity is available making repair a possibility" in caplog.text


def test_prepare_parity_for_repair_uses_unsigned_main_file_directly(tmp_path):
    archive_name = "backup.tar"
    archive = tmp_path / archive_name
    main_par2 = tmp_path / (archive_name + ".par2")
    archive.write_text("archive")
    main_par2.write_text("parity")

    info, err = restoreutils.prepare_parity_for_repair(
        str(tmp_path),
        archive_name,
        [str(main_par2)],
        validate_file_fn=lambda *_args, **_kwargs: True,
    )

    assert err is None
    assert info["repair_dir"] is None
    assert info["main_par2"] == str(main_par2)
    assert info["archive_path"] == str(archive)


def test_prepare_parity_for_repair_stages_signed_files(tmp_path):
    archive_name = "backup.tar"
    archive = tmp_path / archive_name
    signed_main = tmp_path / (archive_name + ".par2.sig")
    signed_volume = tmp_path / (archive_name + ".vol000+001.par2.sig")
    archive.write_text("archive")
    signed_main.write_text("signed-main")
    signed_volume.write_text("signed-vol")

    strip_calls = []

    def fake_strip_file(path, _keyring_dir=None, output_path=None, work_dir=None):
        strip_calls.append((path, output_path, work_dir))
        with open(output_path, "wb") as fp:
            fp.write(b"plain parity")
        return output_path, None

    info, err = restoreutils.prepare_parity_for_repair(
        str(tmp_path),
        archive_name,
        [str(signed_main), str(signed_volume)],
        keyring_dir="dummy",
        work_dir=str(tmp_path),
        validate_file_fn=lambda *_args, **_kwargs: True,
        strip_file_fn=fake_strip_file,
    )

    try:
        assert err is None
        assert info["repair_dir"] is not None
        assert os.path.isfile(info["main_par2"])
        assert os.path.isfile(info["archive_path"])
        assert os.path.isfile(os.path.join(info["repair_dir"], archive_name + ".vol000+001.par2"))
        assert strip_calls
    finally:
        if info and info["repair_dir"]:
            shutil.rmtree(info["repair_dir"])


def test_gpg_key_capabilities_uses_imported_keyring_state(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if '--list-secret-keys' in args:
            return subprocess.CompletedProcess(args, 0, stdout='sec:u:255:1:ABC\n', stderr='')
        if '--list-keys' in args:
            return subprocess.CompletedProcess(args, 0, stdout='pub:u:255:1:ABC\n', stderr='')
        raise AssertionError(args)

    monkeypatch.setattr(subprocess, 'run', fake_run)

    has_public, has_private = gpg_module.gpg_key_capabilities('/tmp/test-keyring')

    assert has_public is True
    assert has_private is True
    assert any('--list-keys' in call for call in calls)
    assert any('--list-secret-keys' in call for call in calls)


@pytest.mark.skipif(shutil.which("par2") is None, reason="par2 not installed")
def test_restore_repair_validate_uses_parity(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "file.txt").write_text("hello parity restore\n")

    config_path = tmp_path / "iceshelf.conf"
    _write_backup_config(config_path, source_dir)

    result = _run_iceshelf(config_path)
    assert result.returncode == 0, result.stdout + result.stderr

    with open(tmp_path / "data" / "checksum.json", "r", encoding="utf-8") as fp:
        backup_id = json.load(fp)["lastbackup"]

    backup_dir = tmp_path / "done" / backup_id
    manifest_path = str(next(backup_dir.glob(backup_id + ".json*")))
    archive_path = next(backup_dir.glob(backup_id + ".tar"))
    parity_files = restoreutils.get_parity_files(str(backup_dir), archive_path.name)
    assert parity_files

    with open(archive_path, "r+b") as fp:
        fp.seek(10)
        fp.write(b"broken-data")

    validate = _run_restore(["--validate", manifest_path])
    assert validate.returncode != 0
    assert "Archive is corrupt" in validate.stdout

    repair = _run_restore(["--repair", "--validate", manifest_path])
    assert repair.returncode == 0, repair.stdout + repair.stderr
    assert "Attempting repair" in repair.stdout
    assert "File was repaired successfully" in repair.stdout
