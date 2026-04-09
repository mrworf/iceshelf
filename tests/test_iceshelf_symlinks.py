"""Behavior tests for broken symlink handling in the iceshelf CLI."""

import os
import subprocess
import sys


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ICESHELF_BIN = os.path.join(REPO_ROOT, "iceshelf")


def _write_config(path, source_dir, skip_broken_links="no"):
    path.write_text(f"""
[sources]
source = {source_dir}

[paths]
prep dir = {path.parent / "prep"}
data dir = {path.parent / "data"}
done dir = {path.parent / "done"}
create paths = yes

[options]
skip broken links = {skip_broken_links}
""".strip() + "\n")


def _run_iceshelf(config_path):
    stub_root = config_path.parent / "stubs"
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

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(stub_root) if not existing_pythonpath else str(stub_root) + os.pathsep + existing_pythonpath

    return subprocess.run(
        [sys.executable, ICESHELF_BIN, "--changes", str(config_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_broken_symlink_fails_cleanly(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    os.symlink("missing-target", source_dir / "broken-link")

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, skip_broken_links="no")

    result = _run_iceshelf(config_path)

    assert result.returncode == 1
    assert "Broken symbolic link" in result.stdout
    assert "broken-link" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def test_broken_symlink_can_be_skipped(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    os.symlink("missing-target", source_dir / "broken-link")

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, skip_broken_links="yes")

    result = _run_iceshelf(config_path)

    assert result.returncode == 0
    assert "Broken symbolic link" in result.stdout
    assert "skipping" in result.stdout
    assert "No file(s) changed or added since last backup" in result.stdout


def test_valid_symlink_still_works(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    target = source_dir / "target.txt"
    target.write_text("hello")
    os.symlink("target.txt", source_dir / "valid-link")

    config_path = tmp_path / "iceshelf.conf"
    _write_config(config_path, source_dir, skip_broken_links="yes")

    result = _run_iceshelf(config_path)

    assert result.returncode == 1
    assert "Broken symbolic link" not in result.stdout
    assert "\"%s\" is new" % (source_dir / "valid-link") in result.stdout
