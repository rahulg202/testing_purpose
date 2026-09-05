"""Evidence vault — immutable storage for everything we received.

Provenance is only credible if the original artefact still exists byte-for-byte.
Every intake writes its raw payload here under a tenant-scoped key, and the
returned SHA-256 lets any later reader prove the bytes are unchanged.

Backends are open source by design:

* ``filesystem`` — the default, requires nothing installed.
* ``s3``         — points at self-hosted MinIO via ``evidence_endpoint_url``.

Keys are always ``{tenant_id}/{channel}/{yyyy}/{mm}/{dd}/{source_record_id}/raw.txt``
so tenant isolation holds in the storage layer, not just in the database.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

import structlog

logger = structlog.get_logger("evidence")


def build_evidence_key(
    *,
    tenant_id: str,
    channel: str,
    source_record_id: str,
    received_at: datetime,
    filename: str = "raw.txt",
) -> str:
    """Compose the tenant-scoped, date-partitioned object key."""
    return f"{tenant_id}/{channel}/{received_at:%Y/%m/%d}/{source_record_id}/{filename}"


@runtime_checkable
class EvidenceStore(Protocol):
    """Minimal write/read contract for the evidence vault."""

    def put_text(self, key: str, text: str) -> str:
        """Store text, returning its SHA-256."""
        ...

    def get_text(self, key: str) -> str | None:
        """Retrieve stored text, or None if absent."""
        ...


class FilesystemEvidenceStore:
    """Local-disk evidence vault.

    Writes are treated as write-once: an existing key is not overwritten, which
    preserves the "immutable evidence" guarantee during development just as
    object-lock would in production.
    """

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, key: str) -> Path:
        return self._root / key

    def put_text(self, key: str, text: str) -> str:
        payload = text.encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        path = self._path(key)
        if path.exists():
            logger.info("evidence_already_stored", key=key, sha256=digest[:16])
            return digest
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        logger.info("evidence_stored", key=key, sha256=digest[:16], bytes=len(payload))
        return digest

    def get_text(self, key: str) -> str | None:
        path = self._path(key)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")


class S3EvidenceStore:
    """S3-compatible evidence vault, targeting self-hosted MinIO.

    Deliberately not AWS-specific: any S3 API implementation works via
    ``endpoint_url``.
    """

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        import boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def put_text(self, key: str, text: str) -> str:
        payload = text.encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=payload, ContentType="text/plain; charset=utf-8"
        )
        logger.info("evidence_stored", key=key, sha256=digest[:16], bytes=len(payload))
        return digest

    def get_text(self, key: str) -> str | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception:
            return None
        body: bytes = response["Body"].read()
        return body.decode("utf-8")


def get_evidence_store() -> EvidenceStore:
    """Build the configured evidence store."""
    from .config import get_settings

    settings = get_settings()
    if settings.evidence_backend == "s3":
        return S3EvidenceStore(
            bucket=settings.evidence_bucket,
            endpoint_url=settings.evidence_endpoint_url,
            access_key=settings.evidence_access_key,
            secret_key=settings.evidence_secret_key,
            region=settings.aws_region,
        )
    return FilesystemEvidenceStore(settings.evidence_root)
