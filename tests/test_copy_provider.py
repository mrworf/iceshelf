"""Unit tests for modules/providers/copy.py."""

import logging
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
sys.modules.setdefault("paramiko", types.SimpleNamespace())

from modules.providers.copy import CopyProvider


def test_upload_files_logs_success(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    source = tmp_path / "backup.tar"
    source.write_text("backup-data")
    dest = tmp_path / "dest"
    dest.mkdir()

    monkeypatch.setattr("modules.providers.copy._which", lambda program: "/bin/cp")

    provider = CopyProvider(dest=str(dest))

    assert provider.verify() is True
    assert provider.upload_files([str(source)]) is True
    assert (dest / "backup.tar").exists()
    assert f"Stored 1 file(s) successfully via cp:{dest}" in caplog.text
