"""Unit tests for modules/providers/s3.py."""

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

from modules.providers.s3 import S3Provider


class DummyClient:
    def __init__(self):
        self.calls = []

    def upload_file(self, filename, bucket, key, **kwargs):
        self.calls.append({
            "filename": filename,
            "bucket": bucket,
            "key": key,
            "kwargs": kwargs,
        })


def test_upload_files_without_storage_class_omits_extra_args(tmp_path, monkeypatch):
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient()

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (client, None),
    )

    provider = S3Provider(bucket="mybucket")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is True
    assert client.calls == [{
        "filename": str(archive),
        "bucket": "mybucket",
        "key": "backup.tar",
        "kwargs": {},
    }]


def test_upload_files_with_storage_class_passes_normalized_extra_args(tmp_path, monkeypatch):
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient()

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (client, None),
    )

    provider = S3Provider(bucket="mybucket", **{"storage class": "deep-archive"})

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is True
    assert client.calls == [{
        "filename": str(archive),
        "bucket": "mybucket",
        "key": "backup.tar",
        "kwargs": {"ExtraArgs": {"StorageClass": "DEEP_ARCHIVE"}},
    }]


def test_normalize_storage_class_accepts_common_spellings():
    assert S3Provider.normalize_storage_class("glacier") == "GLACIER"
    assert S3Provider.normalize_storage_class("deep archive") == "DEEP_ARCHIVE"
    assert S3Provider.normalize_storage_class("GLACIER_IR") == "GLACIER_IR"


def test_verify_fails_for_unsupported_storage_class(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    provider = S3Provider(
        bucket="mybucket",
        **{"storage class": "frozen-lake"},
    )

    assert provider.verify() is False
    assert 'storage class "frozen-lake" is not supported' in caplog.text


def test_upload_files_logs_success(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient()

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (client, None),
    )

    provider = S3Provider(bucket="mybucket")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is True
    assert "Stored 1 file(s) successfully via s3:mybucket" in caplog.text
