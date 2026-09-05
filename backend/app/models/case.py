"""Case database models — SQLAlchemy ORM for the canonical case store."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TenantMixin, TimestampMixin


class CaseModel(Base, TenantMixin, TimestampMixin):
    """The case header — one row per case, tracks the latest version."""

    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("tenant_id", "case_number", name="uq_tenant_case_number"),)

    case_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_number: Mapped[str] = mapped_column(String(128), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    lifecycle_state: Mapped[str] = mapped_column(String(32), default="draft")
    lock_state: Mapped[str] = mapped_column(String(32), default="open")
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Relationships
    versions: Mapped[list["CaseVersionModel"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseVersionModel.version"
    )


class CaseVersionModel(Base, TenantMixin, TimestampMixin):
    """Immutable case version — full snapshot of the case at a point in time."""

    __tablename__ = "case_versions"
    __table_args__ = (UniqueConstraint("case_id", "version", name="uq_case_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cases.case_id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    version_type: Mapped[str] = mapped_column(String(32), default="initial")
    supersedes_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The full case data as JSON — typed by CanonicalCase contract
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Content hash for integrity verification and signatures
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    case: Mapped["CaseModel"] = relationship(back_populates="versions")


class SourceRecordModel(Base, TenantMixin, TimestampMixin):
    """Source record database model — one per inbound content unit."""

    __tablename__ = "source_records"

    source_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sweep_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Channel info
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_class: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps — awareness_datetime is IMMUTABLE after first write
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    awareness_datetime: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="DAY 0 — immutable after first write"
    )
    platform_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Content
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Evidence
    manifest_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Triage outcome (JSON)
    triage_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(32), default="received")
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lineage
    derived_case_ids: Mapped[list[str]] = mapped_column(JSON, default=list)


class EvidenceRefModel(Base, TenantMixin, TimestampMixin):
    """Evidence reference — pointers to objects in the S3 evidence vault."""

    __tablename__ = "evidence_refs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("source_records.source_record_id"), nullable=False, index=True
    )
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AuditEventModel(Base, TenantMixin):
    """Audit trail — append-only, hash-chained events."""

    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    source_record_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Event
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    field_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Attribution
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rule_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_set_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Context
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    # Integrity
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Trace
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class PipelineRunModel(Base, TenantMixin, TimestampMixin):
    """Pipeline execution tracking — durable orchestration without Step Functions."""

    __tablename__ = "pipeline_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_record_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pipeline_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PipelineStageModel(Base, TenantMixin):
    """Pipeline stage execution — one row per stage in a run."""

    __tablename__ = "pipeline_stages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("pipeline_runs.run_id"), nullable=False, index=True
    )
    stage_name: Mapped[str] = mapped_column(String(64), nullable=False)
    stage_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(nullable=True)
