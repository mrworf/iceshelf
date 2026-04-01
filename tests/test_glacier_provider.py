"""Unit tests for modules/providers/glacier.py."""

import logging
import os
import sys
import types

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))
sys.modules.setdefault("paramiko", types.SimpleNamespace())
sys.modules.setdefault("boto3", types.SimpleNamespace(Session=object))
botocore_exceptions = types.SimpleNamespace(
    ClientError=Exception,
    NoCredentialsError=Exception,
    NoRegionError=Exception,
)
sys.modules.setdefault("botocore", types.SimpleNamespace(exceptions=botocore_exceptions))
sys.modules.setdefault("botocore.exceptions", botocore_exceptions)

from modules.providers.glacier import GlacierProvider


class DummyClient:
    def __init__(self, vault_exists=True, describe_error=None, create_error=None):
        self.vault_exists = vault_exists
        self.describe_error = describe_error
        self.create_error = create_error
        self.calls = []

    def describe_vault(self, vaultName):
        self.calls.append(("describe_vault", vaultName))
        if self.describe_error is not None:
            raise self.describe_error
        if not self.vault_exists:
            raise FakeClientError("ResourceNotFoundException")
        return {"VaultName": vaultName}

    def create_vault(self, vaultName):
        self.calls.append(("create_vault", vaultName))
        if self.create_error is not None:
            raise self.create_error
        self.vault_exists = True
        return {}


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


def test_verify_rejects_invalid_create_value(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)

    monkeypatch.setattr(
        "modules.providers.glacier.aws.create_glacier_client",
        lambda aws_config: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    provider = GlacierProvider(vault="myvault", create="true")

    assert provider.verify() is False
    assert 'glacier provider: create must be "yes" or "no"' in caplog.text


def test_upload_files_succeeds_when_vault_exists(tmp_path, monkeypatch):
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(vault_exists=True)

    monkeypatch.setattr(
        "modules.providers.glacier.aws.create_glacier_client",
        lambda aws_config: (client, None),
    )
    monkeypatch.setattr(
        GlacierProvider,
        "_upload_one",
        lambda self, filepath, prefix, bytes_done, bytes_total: True,
    )

    provider = GlacierProvider(vault="myvault")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is True
    assert ("describe_vault", "myvault") in client.calls
    assert ("create_vault", "myvault") not in client.calls


def test_upload_files_fails_when_vault_missing_and_create_disabled(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(vault_exists=False)

    monkeypatch.setattr(
        "modules.providers.glacier.aws.create_glacier_client",
        lambda aws_config: (client, None),
    )
    monkeypatch.setattr(
        GlacierProvider,
        "_upload_one",
        lambda self, filepath, prefix, bytes_done, bytes_total: (_ for _ in ()).throw(
            AssertionError("upload should not start")
        ),
    )

    provider = GlacierProvider(vault="myvault", create="no")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is False
    assert ("create_vault", "myvault") not in client.calls
    assert "vault myvault does not exist and create is disabled" in caplog.text


def test_upload_files_creates_missing_vault_when_enabled(tmp_path, monkeypatch):
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(vault_exists=False)

    monkeypatch.setattr(
        "modules.providers.glacier.aws.create_glacier_client",
        lambda aws_config: (client, None),
    )
    monkeypatch.setattr(
        GlacierProvider,
        "_upload_one",
        lambda self, filepath, prefix, bytes_done, bytes_total: True,
    )

    provider = GlacierProvider(vault="myvault", create="yes")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is True
    assert ("create_vault", "myvault") in client.calls


def test_upload_files_fails_when_vault_creation_fails(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(vault_exists=False, create_error=RuntimeError("boom"))

    monkeypatch.setattr(
        "modules.providers.glacier.aws.create_glacier_client",
        lambda aws_config: (client, None),
    )
    monkeypatch.setattr(
        GlacierProvider,
        "_upload_one",
        lambda self, filepath, prefix, bytes_done, bytes_total: (_ for _ in ()).throw(
            AssertionError("upload should not start")
        ),
    )

    provider = GlacierProvider(vault="myvault", create="yes")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is False
    assert ("create_vault", "myvault") in client.calls
    assert "Failed to create vault myvault" in caplog.text
