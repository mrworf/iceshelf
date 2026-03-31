"""Unit tests for modules/aws.py."""

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))


class DummySession:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def client(self, **kwargs):
        return {
            "session_kwargs": self.kwargs,
            "client_kwargs": kwargs,
        }


sys.modules.setdefault("boto3", types.SimpleNamespace(Session=DummySession))
botocore_exceptions = types.SimpleNamespace(
    ClientError=Exception,
    NoCredentialsError=Exception,
    NoRegionError=Exception,
)
sys.modules.setdefault("botocore", types.SimpleNamespace(exceptions=botocore_exceptions))
sys.modules.setdefault("botocore.exceptions", botocore_exceptions)

from modules import aws


@pytest.fixture(autouse=True)
def clear_aws_env(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)


def test_create_s3_client_accepts_explicit_credentials():
    client, err = aws.create_s3_client({
        "region": "us-east-1",
        "access_key_id": "key",
        "secret_access_key": "secret",
    })

    assert err is None
    assert client["session_kwargs"]["aws_access_key_id"] == "key"
    assert client["client_kwargs"]["service_name"] == "s3"


def test_create_glacier_client_accepts_profile():
    client, err = aws.create_glacier_client({
        "region": "us-east-1",
        "profile": "iceshelf",
    })

    assert err is None
    assert client["session_kwargs"]["profile_name"] == "iceshelf"
    assert client["client_kwargs"]["service_name"] == "glacier"


def test_create_s3_client_accepts_environment_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "env-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "env-secret")

    client, err = aws.create_s3_client({
        "region": "us-east-1",
    })

    assert err is None
    assert client["session_kwargs"] == {"region_name": "us-east-1"}
    assert client["client_kwargs"]["service_name"] == "s3"


def test_create_glacier_client_fails_without_config_or_env_credentials():
    client, err = aws.create_glacier_client({
        "region": "us-east-1",
    })

    assert client is None
    assert "AWS credentials required." in err
    assert "AWS_ACCESS_KEY_ID" in err
    assert "AWS_SECRET_ACCESS_KEY" in err
