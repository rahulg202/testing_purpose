"""Audit trail contracts — append-only, hash-chained decision records."""

from datetime import datetime

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """A single audit event — immutable once written.

    Hash-chained: each event's hash includes the previous event's hash,
    creating a tamper-evident log.
    """

    event_id: str = Field(description="ULID")
    tenant_id: str
    case_id: str | None = None
    source_record_id: str | None = None

    # What happened
    event_type: (
        str  # field_change | state_change | approval | signature | ai_invocation | rule_evaluation
    )
    field_path: str | None = None  # e.g. "reactions[0].coded_pt.value"
    old_value: str | None = None  # JSON-serialised
    new_value: str | None = None  # JSON-serialised

    # Who/what did it
    actor_type: str  # ai | rule | human | system
    actor_id: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    rule_id: str | None = None
    rule_set_version: str | None = None

    # Context
    reason_code: str | None = None
    rationale: str | None = None
    confidence: float | None = None

    # Integrity
    timestamp: datetime
    content_hash: str = Field(description="SHA-256 of this event's content fields")
    previous_hash: str = Field(description="Hash of the preceding event — chain integrity")

    # Trace
    trace_id: str | None = None
    request_id: str | None = None
