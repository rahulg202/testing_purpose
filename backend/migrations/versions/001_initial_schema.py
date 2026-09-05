"""Initial schema — all Sprint 2 tables.

Revision ID: 001
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cases table
    op.create_table(
        "cases",
        sa.Column("case_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("case_number", sa.String(128), nullable=False),
        sa.Column("current_version", sa.Integer(), default=1),
        sa.Column("lifecycle_state", sa.String(32), default="draft"),
        sa.Column("lock_state", sa.String(32), default="open"),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "case_number", name="uq_tenant_case_number"),
    )

    # Case versions table
    op.create_table(
        "case_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "case_id", sa.String(64), sa.ForeignKey("cases.case_id"), nullable=False, index=True
        ),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("version_type", sa.String(32), default="initial"),
        sa.Column("supersedes_version", sa.Integer(), nullable=True),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("case_id", "version", name="uq_case_version"),
    )

    # Source records table
    op.create_table(
        "source_records",
        sa.Column("source_record_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("sweep_id", sa.String(64), nullable=True),
        sa.Column("channel", sa.String(64), nullable=False),
        sa.Column("channel_class", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(512), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "awareness_datetime",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="DAY 0 — immutable after first write",
        ),
        sa.Column("platform_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("raw_language", sa.String(16), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("manifest_ref", sa.Text(), nullable=True),
        sa.Column("triage_result", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(32), default="received"),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("derived_case_ids", sa.JSON(), default=[]),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Evidence refs table
    op.create_table(
        "evidence_refs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "source_record_id",
            sa.String(64),
            sa.ForeignKey("source_records.source_record_id"),
            nullable=False,
            index=True,
        ),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Audit events table (append-only, hash-chained)
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("case_id", sa.String(64), nullable=True, index=True),
        sa.Column("source_record_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("field_path", sa.String(256), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(128), nullable=True),
        sa.Column("model_id", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("rule_id", sa.String(128), nullable=True),
        sa.Column("rule_set_version", sa.String(32), nullable=True),
        sa.Column("reason_code", sa.String(64), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
    )

    # Pipeline runs table
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column("source_record_id", sa.String(64), nullable=False, index=True),
        sa.Column("case_id", sa.String(64), nullable=True),
        sa.Column("pipeline_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Pipeline stages table
    op.create_table(
        "pipeline_stages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, index=True),
        sa.Column(
            "run_id",
            sa.String(64),
            sa.ForeignKey("pipeline_runs.run_id"),
            nullable=False,
            index=True,
        ),
        sa.Column("stage_name", sa.String(64), nullable=False),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("error_type", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
    )

    # Indexes for common query patterns
    op.create_index("ix_audit_events_case_timestamp", "audit_events", ["case_id", "timestamp"])
    op.create_index("ix_source_records_status", "source_records", ["tenant_id", "status"])
    op.create_index("ix_cases_lifecycle", "cases", ["tenant_id", "lifecycle_state"])


def downgrade() -> None:
    op.drop_index("ix_cases_lifecycle")
    op.drop_index("ix_source_records_status")
    op.drop_index("ix_audit_events_case_timestamp")
    op.drop_table("pipeline_stages")
    op.drop_table("pipeline_runs")
    op.drop_table("audit_events")
    op.drop_table("evidence_refs")
    op.drop_table("source_records")
    op.drop_table("case_versions")
    op.drop_table("cases")
