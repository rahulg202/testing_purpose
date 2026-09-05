"""Intake connectors — one per inbound channel.

Every connector's only job is to turn channel-specific input into a
channel-agnostic :class:`atheria_contracts.source_record.SourceRecord`. Nothing
downstream (triage, rules, review) knows or cares where a record came from, so
adding a channel means adding a connector and changing nothing else.
"""

from .base import ConnectorResult, build_source_record, compute_content_hash

__all__ = ["ConnectorResult", "build_source_record", "compute_content_hash"]
