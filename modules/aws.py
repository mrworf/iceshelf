# pylint: disable=invalid-name
"""Shared AWS helpers using boto3.

Provides session/client creation for S3 and Glacier, a YAML config
loader, and the Glacier tree-hash helper used during upload and
download verification.
"""

from . import helper
import logging
import os
import io
import hashlib
import math

import boto3
import yaml
from botocore.exceptions import ClientError, NoCredentialsError, NoRegionError

AWS_CONFIG_KEYS = (
    "region",
    "access_key_id",
    "secret_access_key",
    "session_token",
    "profile",
    "endpoint_url",
)

PROVIDER_CONFIG_KEYS = (
    "region",
    "access key id",
    "secret access key",
    "session token",
    "profile",
    "endpoint url",
    "aws config",
)

_PROVIDER_KEY_MAP = {
    'region': 'region',
    'access key id': 'access_key_id',
    'secret access key': 'secret_access_key',
    'session token': 'session_token',
    'profile': 'profile',
    'endpoint url': 'endpoint_url',
    'aws config': 'aws_config',
}


def load_aws_config_file(path):
    """Load AWS config from a YAML file.  Returns a dict with only known keys."""
    if not path or not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {k: data[k] for k in AWS_CONFIG_KEYS if k in data and data[k] is not None}


def extract_aws_config(provider_cfg):
    """Extract AWS settings from a provider config dict (INI key names).

    Supports an optional ``aws config`` key pointing to a YAML file whose
    values are used as defaults (explicit keys in the provider section win).
    """
    file_cfg = {}
    aws_config_path = None
    for ini_key, dict_key in _PROVIDER_KEY_MAP.items():
        val = provider_cfg.get(ini_key)
        if val:
            if dict_key == 'aws_config':
                aws_config_path = val
            else:
                file_cfg[dict_key] = val
    if aws_config_path:
        base = load_aws_config_file(aws_config_path)
        base.update(file_cfg)
        return base
    return file_cfg


def create_session(aws_config):
    """Create a boto3 Session from a config dict.  Returns the Session."""
    region = aws_config.get("region")
    access_key_id = aws_config.get("access_key_id")
    secret_access_key = aws_config.get("secret_access_key")
    session_token = aws_config.get("session_token")
    profile = aws_config.get("profile")

    has_explicit = access_key_id and secret_access_key
    if has_explicit:
        return boto3.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=session_token,
            region_name=region,
        )
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def create_glacier_client(aws_config):
    """Create a boto3 Glacier client.  Returns (client, None) or (None, error_msg)."""
    region = aws_config.get("region")
    endpoint_url = aws_config.get("endpoint_url")

    if not region:
        return None, "AWS region is required (set 'region' in provider section or aws config file)."

    has_explicit = aws_config.get("access_key_id") and aws_config.get("secret_access_key")
    if not has_explicit and not aws_config.get("profile"):
        return None, ("AWS credentials required. Set 'access key id' and "
                      "'secret access key' in provider section, or use 'profile'.")

    try:
        session = create_session(aws_config)
        kwargs = {"service_name": "glacier", "region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        return session.client(**kwargs), None
    except (NoRegionError, NoCredentialsError, ClientError) as e:
        return None, str(e)
    except Exception as e:  # pylint: disable=broad-except
        return None, str(e)


def create_s3_client(aws_config):
    """Create a boto3 S3 client.  Returns (client, None) or (None, error_msg)."""
    region = aws_config.get("region")
    endpoint_url = aws_config.get("endpoint_url")

    if not region:
        return None, "AWS region is required (set 'region' in provider section or aws config file)."

    has_explicit = aws_config.get("access_key_id") and aws_config.get("secret_access_key")
    if not has_explicit and not aws_config.get("profile"):
        return None, ("AWS credentials required. Set 'access key id' and "
                      "'secret access key' in provider section, or use 'profile'.")

    try:
        session = create_session(aws_config)
        kwargs = {"service_name": "s3", "region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        return session.client(**kwargs), None
    except (NoRegionError, NoCredentialsError, ClientError) as e:
        return None, str(e)
    except Exception as e:  # pylint: disable=broad-except
        return None, str(e)


# ---------------------------------------------------------------------------
# Glacier tree-hash helpers (pure Python, no AWS CLI)
# ---------------------------------------------------------------------------

def hashFile(file, chunkSize):
    """Compute Glacier SHA-256 tree hash for *file*.

    Returns ``{'blocks': [...], 'final': hash_obj}`` or ``None``.
    """
    if not os.path.exists(file):
        return None

    h = hashlib.sha256
    blocks = []
    final = []
    with io.open(file, 'rb') as f:
        while True:
            data = f.read(1024 ** 2)
            if len(data) == 0:
                break
            v = h(data)
            blocks.append(v)

    def recurse(hashlist, size):
        if size == chunkSize:
            for o in hashlist:
                final.append(o)

        output = [h(h1.digest() + h2.digest())
                  for h1, h2 in zip(hashlist[::2], hashlist[1::2])]
        if len(hashlist) % 2:
            output.append(hashlist[-1])

        if len(output) > 1:
            return recurse(output, size * 2)
        return output[0]

    result = {'blocks': final, 'final': recurse(blocks or [h(b"")], 1024 ** 2)}
    return result


def compute_chunk_size(file_size):
    """Return a power-of-two chunk size suitable for Glacier multipart upload."""
    chunk = file_size / 10000
    if chunk <= 1024 ** 2:
        return 1024 ** 2
    factor = math.ceil(float(chunk) / float(1024 ** 2))
    chunk = int((1024 ** 2) * factor)
    chunk -= 1
    chunk |= chunk >> 1
    chunk |= chunk >> 2
    chunk |= chunk >> 4
    chunk |= chunk >> 8
    chunk |= chunk >> 16
    chunk += 1
    return chunk
