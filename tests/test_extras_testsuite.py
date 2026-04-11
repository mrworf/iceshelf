"""Integration coverage for the legacy shell suites under extras/testsuite."""

import os
import subprocess
from glob import glob


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
TESTSUITE_DIR = os.path.join(REPO_ROOT, "extras", "testsuite")
E2E_VENV_BIN = os.path.join(REPO_ROOT, ".venv-e2e", "bin")
SCRIPT_TIMEOUTS = {
    "test_backup.sh": 3600,
    "test_restore.sh": 1800,
}
ARTIFACT_PATHS = (
    "compare",
    "content",
    "data",
    "done",
    "restore",
    "restore2",
    "tmp",
    "combined_test.key",
    "config_restore",
    "diff.out",
)


def _cleanup_testsuite_artifacts():
    for name in ARTIFACT_PATHS:
        path = os.path.join(TESTSUITE_DIR, name)
        if os.path.isdir(path):
            subprocess.run(["rm", "-rf", path], check=False)
        elif os.path.exists(path):
            os.remove(path)

    for path in glob(os.path.join(TESTSUITE_DIR, "config_*")):
        if os.path.isfile(path):
            os.remove(path)


def _run_testsuite(script_name, tmp_path):
    gnupg_home = tmp_path / (script_name + ".gnupg")
    restore_log = "/tmp/iceshelf-restore-suite.log"
    if script_name == "test_restore.sh" and os.path.isfile(restore_log):
        os.unlink(restore_log)

    env = os.environ.copy()
    env["LC_ALL"] = env.get("LC_ALL", "C.UTF-8")
    env["LANG"] = env.get("LANG", "C.UTF-8")
    env["PATH"] = E2E_VENV_BIN + os.pathsep + env.get("PATH", "")

    command = (
        f'tmp_gnupg="{gnupg_home}" && '
        'mkdir -p "$tmp_gnupg" && '
        'chmod 700 "$tmp_gnupg" && '
        f'GNUPGHOME="$tmp_gnupg" bash ./{script_name}'
    )

    result = subprocess.run(
        ["/usr/bin/bash", "-lc", command],
        cwd=TESTSUITE_DIR,
        capture_output=True,
        text=True,
        timeout=SCRIPT_TIMEOUTS[script_name],
        env=env,
    )

    if script_name == "test_restore.sh" and os.path.isfile(restore_log):
        with open(restore_log, "r", encoding="utf-8", errors="replace") as fp:
            tail = fp.readlines()[-200:]
        result = subprocess.CompletedProcess(
            result.args,
            result.returncode,
            stdout=result.stdout + "\n--- restore log tail ---\n" + "".join(tail),
            stderr=result.stderr,
        )

    return result


def test_shell_suites(tmp_path):
    _cleanup_testsuite_artifacts()

    backup = _run_testsuite("test_backup.sh", tmp_path)
    assert backup.returncode == 0, backup.stdout + backup.stderr
    _cleanup_testsuite_artifacts()

    restore = _run_testsuite("test_restore.sh", tmp_path)
    assert restore.returncode == 0, restore.stdout + restore.stderr
    _cleanup_testsuite_artifacts()
