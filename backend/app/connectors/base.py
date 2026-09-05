"""Shared connector plumbing.

Two things every channel needs and must do identically:

* **Content hashing** — a SHA-256 over the normalised text, used for
  deduplication and to prove the evidence has not been altered since intake.
* **Day 0 (``awareness_datetime``)** — the regulatory clock start. It is set
  once, at intake, and is immutable thereafter. Reporting deadlines are counted
  from it, so a connector must never backdate or recompute it.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime

from atheria_contracts.enums import Channel, ChannelClass, SourceStatus
from atheria_contracts.source_record import SourceRecord
from ulid import ULID


def normalise_text(text: str) -> str:
    """Canonicalise text before hashing.

    Unicode NFC plus whitespace/newline normalisation so that cosmetically
    different but semantically identical payloads hash the same and therefore
    deduplicate correctly.
    """
    normalised = unicodedata.normalize("NFC", text)
    normalised = normalised.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalised.split("\n")]
    return "\n".join(lines).strip()


def compute_content_hash(text: str) -> str:
    """SHA-256 of the normalised text — the evidence integrity anchor."""
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


@dataclass
class ConnectorResult:
    """What a connector returns: records plus a summary of the sweep."""

    records: list[SourceRecord] = field(default_factory=list)
    #: Records skipped because an identical content hash already exists.
    duplicates_skipped: int = 0
    #: Human-readable description of what the connector did, for the UI.
    summary: str = ""


def build_source_record(
    *,
    tenant_id: str,
    channel: Channel,
    channel_class: ChannelClass,
    raw_text: str,
    trace_id: str | None = None,
    external_id: str | None = None,
    external_url: str | None = None,
    raw_language: str | None = None,
    platform_published_at: datetime | None = None,
    awareness_datetime: datetime | None = None,
    sweep_id: str | None = None,
) -> SourceRecord:
    """Assemble a SourceRecord with identity, hashing, and Day 0 set.

    Args:
        awareness_datetime: Override only when replaying historical intake.
            Defaults to now, which is correct for live intake.
    """
    now = datetime.now(UTC)
    return SourceRecord(
        source_record_id=str(ULID()),
        tenant_id=tenant_id,
        trace_id=trace_id or str(ULID()),
        sweep_id=sweep_id,
        channel=channel,
        channel_class=channel_class,
        external_id=external_id,
        external_url=external_url,
        platform_published_at=platform_published_at,
        retrieved_at=now,
        # DAY 0 — immutable once written.
        awareness_datetime=awareness_datetime or now,
        raw_language=raw_language,
        raw_text=normalise_text(raw_text),
        content_hash=compute_content_hash(raw_text),
        status=SourceStatus.RECEIVED,
    )
