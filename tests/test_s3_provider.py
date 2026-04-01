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
    def __init__(self, bucket_exists=True, head_error=None, create_error=None):
        self.bucket_exists = bucket_exists
        self.head_error = head_error
        self.create_error = create_error
        self.calls = []

    def head_bucket(self, Bucket):
        self.calls.append({
            "op": "head_bucket",
            "bucket": Bucket,
        })
        if self.head_error is not None:
            raise self.head_error
        if not self.bucket_exists:
            raise FakeClientError("404")

    def create_bucket(self, **kwargs):
        self.calls.append({
            "op": "create_bucket",
            "kwargs": kwargs,
        })
        if self.create_error is not None:
            raise self.create_error
        self.bucket_exists = True

    def upload_file(self, filename, bucket, key, **kwargs):
        self.calls.append({
            "op": "upload_file",
            "filename": filename,
            "bucket": bucket,
            "key": key,
            "kwargs": kwargs,
        })


class FakeClientError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


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
        "op": "head_bucket",
        "bucket": "mybucket",
    }, {
        "op": "upload_file",
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
        "op": "head_bucket",
        "bucket": "mybucket",
    }, {
        "op": "upload_file",
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


def test_verify_rejects_invalid_create_value(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    provider = S3Provider(bucket="mybucket", create="true")

    assert provider.verify() is False
    assert 's3 provider: create must be "yes" or "no"' in caplog.text


def test_upload_files_fails_when_bucket_missing_and_create_disabled(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(bucket_exists=False)

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (client, None),
    )

    provider = S3Provider(bucket="mybucket", create="no")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is False
    assert client.calls == [{
        "op": "head_bucket",
        "bucket": "mybucket",
    }]
    assert "bucket mybucket does not exist and create is disabled" in caplog.text


def test_upload_files_creates_missing_bucket_when_enabled(tmp_path, monkeypatch):
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(bucket_exists=False)

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (client, None),
    )

    provider = S3Provider(bucket="mybucket", create="yes", region="us-west-2")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is True
    assert client.calls == [{
        "op": "head_bucket",
        "bucket": "mybucket",
    }, {
        "op": "create_bucket",
        "kwargs": {
            "Bucket": "mybucket",
            "CreateBucketConfiguration": {"LocationConstraint": "us-west-2"},
        },
    }, {
        "op": "upload_file",
        "filename": str(archive),
        "bucket": "mybucket",
        "key": "backup.tar",
        "kwargs": {},
    }]


def test_upload_files_fails_when_bucket_creation_fails(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(bucket_exists=False, create_error=RuntimeError("boom"))

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (client, None),
    )

    provider = S3Provider(bucket="mybucket", create="yes", region="us-east-1")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is False
    assert "failed to create bucket mybucket" in caplog.text


def test_upload_files_fails_for_unrelated_bucket_check_error(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    archive = tmp_path / "backup.tar"
    archive.write_text("backup-data")
    client = DummyClient(head_error=FakeClientError("403"))

    monkeypatch.setattr(
        "modules.providers.s3.aws.create_s3_client",
        lambda aws_config: (client, None),
    )

    provider = S3Provider(bucket="mybucket")

    assert provider.verify() is True
    assert provider.upload_files([str(archive)]) is False
    assert "unable to check bucket mybucket" in caplog.text
