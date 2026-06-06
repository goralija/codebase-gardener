"""S3-compatible object storage client (MinIO locally, Cloudflare R2 in prod).

Pure functions over boto3 so they are reusable and easy to mock/test. Large
analysis blobs are stored gzip-compressed JSON under a per-tenant key prefix.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from functools import lru_cache
from typing import Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings


JsonValue = Any


@lru_cache(maxsize=1)
def client():
    """Cached boto3 S3 client built from settings."""
    return boto3.client(
        "s3",
        endpoint_url=settings.OBJECT_STORAGE_ENDPOINT_URL,
        aws_access_key_id=settings.OBJECT_STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.OBJECT_STORAGE_SECRET_KEY,
        region_name=settings.OBJECT_STORAGE_REGION,
        config=Config(signature_version="s3v4"),
    )


def bucket() -> str:
    return settings.OBJECT_STORAGE_BUCKET


def reset_client_cache() -> None:
    """Drop the cached client (tests that swap settings/endpoints)."""
    client.cache_clear()


def tenant_key(organization_id: str, repository_id: str, commit_sha: str, artifact: str) -> str:
    """Per-tenant object key. Prefix isolation: org_/repo_/<commit>/<artifact>.json.gz."""
    return f"org_{organization_id}/repo_{repository_id}/{commit_sha}/{artifact}.json.gz"


def ensure_bucket() -> None:
    """Create the bucket if it does not exist (idempotent; covers local MinIO)."""
    s3 = client()
    try:
        s3.head_bucket(Bucket=bucket())
    except ClientError:
        s3.create_bucket(Bucket=bucket())


def put_json(key: str, value: JsonValue) -> str:
    """Store *value* as gzip-compressed JSON at *key*. Returns the sha256 checksum."""
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    compressed = gzip.compress(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    client().put_object(
        Bucket=bucket(),
        Key=key,
        Body=compressed,
        ContentType="application/json",
        ContentEncoding="gzip",
        Metadata={"sha256": checksum},
    )
    return checksum


def get_json(key: str) -> JsonValue:
    """Fetch + gunzip + parse the JSON object stored at *key*."""
    response = client().get_object(Bucket=bucket(), Key=key)
    compressed = response["Body"].read()
    raw = gzip.decompress(compressed)
    return json.loads(raw)


def delete_prefix(prefix: str) -> int:
    """Delete every object under *prefix* (tenant purge). Returns count deleted."""
    s3 = client()
    paginator = s3.get_paginator("list_objects_v2")
    deleted = 0
    for page in paginator.paginate(Bucket=bucket(), Prefix=prefix):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if not objects:
            continue
        s3.delete_objects(Bucket=bucket(), Delete={"Objects": objects})
        deleted += len(objects)
    return deleted
