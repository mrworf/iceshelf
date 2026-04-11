"""Behavior tests for streamed archive assembly."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from modules import fileutils


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ICESHELF_BIN = os.path.join(REPO_ROOT, "iceshelf")
RESTORE_BIN = os.path.join(REPO_ROOT, "iceshelf-restore")
TEST_KEY_PUBLIC = os.path.join(REPO_ROOT, "extras", "testsuite", "test_key.public")
TEST_KEY_PRIVATE = os.path.join(REPO_ROOT, "extras", "testsuite", "test_key.private")


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


def _write_key_file(path):
    with open(TEST_KEY_PUBLIC, "rb") as public_fp:
        public_data = public_fp.read()
    with open(TEST_KEY_PRIVATE, "rb") as private_fp:
        private_data = private_fp.read()
    path.write_bytes(public_data + private_data)


def _write_config(path, source_dir, *, compress="no", encrypt=False, sign=False,
                  done_dir="default", create_filelist="no", use_key_file=False,
                  ignore_unavailable_files="no"):
    key_file_path = path.parent / "combined_test.key"
    if use_key_file and (encrypt or sign):
        _write_key_file(key_file_path)

    if done_dir == "default":
        done_dir_line = f"done dir = {path.parent / 'done'}"
    else:
        done_dir_line = "done dir ="

    security_lines = []
    if use_key_file and (encrypt or sign):
        security_lines.append("[security]")
        security_lines.append(f"key file = {key_file_path}")
    elif encrypt or sign:
        security_lines.append("[security]")
    if encrypt:
        security_lines.append("encrypt = test@test.test")
        security_lines.append("encrypt phrase = test")
    if sign:
        security_lines.append("sign = test@test.test")
        security_lines.append("sign phrase = test")

    path.write_text(f"""
[sources]
source = {source_dir}

[paths]
prep dir = {path.parent / "prep"}
data dir = {path.parent / "data"}
{done_dir_line}
create paths = yes

[options]
compress = {compress}
create filelist = {create_filelist}
ignore unavailable files = {ignore_unavailable_files}
""".strip() + "\n" + ("\n" + "\n".join(security_lines) + "\n" if security_lines else ""))


def _run_iceshelf(config_path, *, extra_env=None):
    stub_root = config_path.parent / "stubs"
    _write_stub_modules(stub_root)

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(stub_root) if not existing_pythonpath else str(stub_root) + os.pathsep + existing_pythonpath
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [sys.executable, ICESHELF_BIN, str(config_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


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


def _create_source_files(source_dir):
    source_dir.mkdir(parents=True)
    (source_dir / "a.txt").write_text("hello world\n")
    nested = source_dir / "nested"
    nested.mkdir()
    (nested / "b.txt").write_text("second file\n")


def _load_backup_id(tmp_path):
    with open(tmp_path / "data" / "checksum.json", "r", encoding="utf-8") as fp:
        return json.load(fp)["lastbackup"]


def _archive_files_for_backup(tmp_path, backup_id):
    backup_dir = tmp_path / "done" / backup_id
    return sorted(p.name for p in backup_dir.iterdir())


def _prepare_fake_tool_env(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_tar = bin_dir / "tar"
    fake_tar.write_text("""#!/usr/bin/python3
import os
import subprocess
import sys


to_remove = os.environ.get("ICESHELF_TEST_TAR_REMOVE")
if to_remove:
    for path in to_remove.split(os.pathsep):
        if not path:
            continue
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass

raise SystemExit(subprocess.run(["/usr/bin/tar"] + sys.argv[1:]).returncode)
""")
    fake_tar.chmod(0o755)
    os.symlink("/usr/bin/bzip2", bin_dir / "bzip2")
    fake_gpg = bin_dir / "gpg"
    fake_gpg.write_text("""#!/usr/bin/python3
import os
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
if "--list-keys" in args:
    raise SystemExit(0)

output_path = None
if "--output" in args:
    output_path = args[args.index("--output") + 1]

mode = None
if "--detach-sign" in args:
    mode = "detach-sign"
elif "--decrypt" in args:
    mode = "decrypt"
elif "--encrypt" in args:
    mode = "encrypt"
elif "--sign" in args:
    mode = "sign"

input_path = None
for value in reversed(args):
    if value == output_path:
        continue
    if value == "-" or not value.startswith("-"):
        input_path = value
        break

if mode == "detach-sign":
    write_output(output_path, b"fake-signature")
    raise SystemExit(0)

data = read_input(input_path)
write_output(output_path, data)
raise SystemExit(0)
""")
    fake_gpg.chmod(0o755)
    return {"PATH": str(bin_dir)}


def _load_manifest(path):
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def test_archive_filenames_cover_streamed_variants(tmp_path):
    cases = [
        ("no", False, False, ".tar"),
        ("force", False, False, ".tar.bz2"),
        ("no", True, False, ".tar.gpg"),
        ("force", True, True, ".tar.bz2.gpg.sig"),
    ]

    for index, (compress, encrypt, sign, suffix) in enumerate(cases, start=1):
        case_dir = tmp_path / ("case_%d" % index)
        source_dir = case_dir / "source"
        _create_source_files(source_dir)

        config_path = case_dir / "iceshelf.conf"
        _write_config(config_path, source_dir, compress=compress, encrypt=encrypt, sign=sign)
        extra_env = _prepare_fake_tool_env(case_dir) if encrypt or sign else None

        result = _run_iceshelf(config_path, extra_env=extra_env)

        assert result.returncode == 0, result.stdout + result.stderr
        backup_id = _load_backup_id(case_dir)
        files = _archive_files_for_backup(case_dir, backup_id)

        archive_files = [name for name in files if name.startswith(backup_id + ".tar")]
        assert archive_files == [backup_id + suffix]


def test_streamed_archive_leaves_only_final_artifacts_in_prepdir(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    config_path = tmp_path / "iceshelf.conf"
    _write_config(
        config_path,
        source_dir,
        compress="force",
        encrypt=True,
        sign=True,
        done_dir=None,
    )
    extra_env = _prepare_fake_tool_env(tmp_path)

    result = _run_iceshelf(config_path, extra_env=extra_env)

    assert result.returncode == 0, result.stdout + result.stderr
    backup_id = _load_backup_id(tmp_path)
    prep_dir = tmp_path / "prep" / "iceshelf"
    assert sorted(p.name for p in prep_dir.iterdir()) == [
        backup_id + ".json.gpg.asc",
        backup_id + ".tar.bz2.gpg.sig",
    ]


def test_forced_compression_fails_when_no_compressor_is_available(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, compress="force", done_dir=None)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    os.symlink("/usr/bin/tar", bin_dir / "tar")

    result = _run_iceshelf(config_path, extra_env={"PATH": str(bin_dir)})

    assert result.returncode == 2
    assert "no bzip2-compatible compressor was found" in result.stdout


def test_pipeline_failure_removes_partial_archive(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, compress="force", done_dir=None)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    os.symlink("/usr/bin/tar", bin_dir / "tar")
    failing_compressor = bin_dir / "pbzip2"
    failing_compressor.write_text("#!/bin/sh\n/usr/bin/head -c 16\nexit 1\n")
    failing_compressor.chmod(0o755)

    result = _run_iceshelf(config_path, extra_env={"PATH": str(bin_dir)})

    assert result.returncode == 2
    assert "Archive pipeline stage" in result.stdout
    prep_dir = tmp_path / "prep" / "iceshelf"
    assert list(prep_dir.iterdir()) == []


def test_restore_handles_streamed_compressed_encrypted_signed_archive(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, compress="force", encrypt=True, sign=True)
    extra_env = _prepare_fake_tool_env(tmp_path)

    result = _run_iceshelf(config_path, extra_env=extra_env)

    assert result.returncode == 0, result.stdout + result.stderr
    backup_id = _load_backup_id(tmp_path)
    backup_dir = tmp_path / "done" / backup_id
    manifest_path = str(next(backup_dir.glob(backup_id + ".json*")))
    restore_dir = tmp_path / "restore"

    validate = _run_restore([
        "--passphrase", "test",
        "--validate",
        manifest_path,
    ], extra_env=extra_env)
    assert validate.returncode == 0, validate.stdout + validate.stderr

    restore = _run_restore([
        "--passphrase", "test",
        "--restore", str(restore_dir),
        manifest_path,
    ], extra_env=extra_env)
    assert restore.returncode == 0, restore.stdout + restore.stderr
    assert (restore_dir / str(source_dir).lstrip(os.sep) / "a.txt").read_text() == "hello world\n"
    assert (restore_dir / str(source_dir).lstrip(os.sep) / "nested" / "b.txt").read_text() == "second file\n"


def test_unavailable_file_fails_backup_by_default(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)
    disappearing = source_dir / "a.txt"

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir)
    extra_env = _prepare_fake_tool_env(tmp_path)
    extra_env["ICESHELF_TEST_TAR_REMOVE"] = str(disappearing)

    result = _run_iceshelf(config_path, extra_env=extra_env)

    assert result.returncode == 2
    assert "Archive creation encountered 1 unavailable file(s)" in result.stdout
    assert not (tmp_path / "data" / "checksum.json").exists()
    done_dir = tmp_path / "done"
    assert not done_dir.exists() or list(done_dir.iterdir()) == []


def test_ignore_unavailable_files_prunes_manifest_and_state(tmp_path):
    source_dir = tmp_path / "source"
    _create_source_files(source_dir)
    disappearing = source_dir / "a.txt"

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, ignore_unavailable_files="yes")
    extra_env = _prepare_fake_tool_env(tmp_path)
    extra_env["ICESHELF_TEST_TAR_REMOVE"] = str(disappearing)

    result = _run_iceshelf(config_path, extra_env=extra_env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Skipping 1 unavailable file(s) during archive creation" in result.stdout

    backup_id = _load_backup_id(tmp_path)
    backup_dir = tmp_path / "done" / backup_id
    manifest_path = next(backup_dir.glob(backup_id + ".json*"))
    manifest = _load_manifest(manifest_path)
    dataset = _load_manifest(tmp_path / "data" / "checksum.json")["dataset"]

    vanished_key = "/" + str(disappearing).lstrip(os.sep)
    kept_key = "/" + str(source_dir / "nested" / "b.txt").lstrip(os.sep)
    assert vanished_key not in manifest["modified"]
    assert kept_key in manifest["modified"]
    assert vanished_key not in dataset
    assert kept_key in dataset

    validate = _run_restore(["--validate", str(manifest_path)], extra_env=extra_env)
    assert validate.returncode == 0, validate.stdout + validate.stderr

    restore_dir = tmp_path / "restore"
    restore = _run_restore(["--restore", str(restore_dir), str(manifest_path)], extra_env=extra_env)
    assert restore.returncode == 0, restore.stdout + restore.stderr
    assert not (restore_dir / str(disappearing).lstrip(os.sep)).exists()
    assert (restore_dir / str(source_dir / "nested" / "b.txt").lstrip(os.sep)).read_text() == "second file\n"


def test_all_unavailable_files_becomes_noop(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    disappearing = source_dir / "only.txt"
    disappearing.write_text("bye\n")

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, ignore_unavailable_files="yes")
    extra_env = _prepare_fake_tool_env(tmp_path)
    extra_env["ICESHELF_TEST_TAR_REMOVE"] = str(disappearing)

    result = _run_iceshelf(config_path, extra_env=extra_env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "All archive candidates became unavailable, skipping backup" in result.stdout
    assert not (tmp_path / "data" / "checksum.json").exists()
    done_dir = tmp_path / "done"
    assert not done_dir.exists() or list(done_dir.iterdir()) == []


def test_select_bzip2_compressor_prefers_parallel_variants():
    mapping = {
        "pbzip2": "/bin/pbzip2",
        "lbzip2": "/bin/lbzip2",
        "bzip2": "/bin/bzip2",
    }

    assert fileutils.select_bzip2_compressor(mapping.get) == "/bin/pbzip2"
    assert fileutils.select_bzip2_compressor({"lbzip2": "/bin/lbzip2", "bzip2": "/bin/bzip2"}.get) == "/bin/lbzip2"
    assert fileutils.select_bzip2_compressor({"bzip2": "/bin/bzip2"}.get) == "/bin/bzip2"
    assert fileutils.select_bzip2_compressor({}.get) is None
