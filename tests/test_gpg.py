"""Unit tests for modules/gpg.py helpers."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
from modules import gpg


def test_gpg_result_output_falls_back_to_stdout():
    result = subprocess.CompletedProcess(["gpg"], 2, stdout="stdout-only failure", stderr="")

    assert gpg._gpg_result_output(result) == "stdout-only failure"


def test_should_retry_gpg_failure_for_agent_error():
    result = subprocess.CompletedProcess(
        ["gpg"],
        2,
        stdout="",
        stderr="gpg: failed to start gpg-agent '/usr/bin/gpg-agent': General error",
    )

    assert gpg._should_retry_gpg_failure(result) is True
