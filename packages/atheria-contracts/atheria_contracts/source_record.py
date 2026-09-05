"""Source Record contract (C7) — the channel-agnostic envelope.

One record per unit of inbound content. This is what makes the platform
channel-extensible: adding a new source means writing a connector that
emits SourceRecord, and nothing downstream changes.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from .enums import (
    Channel,
    ChannelClass,
    ContentType,
    ICSROutcome,
    SourceStatus,
)
from .provenance import EvidenceSpan


class MediaRef(BaseModel):
    """Reference to a media attachment."""

    media_type: str  # image/png, video/mp4, audio/wav, application/pdf
    s3_key: str
    sha256: str
    size_bytes: int
    filename: str | None = None


class EvidenceRef(BaseModel):
    """Reference to an evidence object in S3."""

    s3_key: str
    sha256: str
    object_type: str  # raw, rendered, canonical_document, manifest


class ProductMention(BaseModel):
    """A product mentioned in the source content."""

    verbatim: str
    resolved_product_id: str | None = None
    resolved_product_name: str | None = None
    confidence: float
    span: EvidenceSpan | None = None


class EventMention(BaseModel):
    """An adverse event candidate detected in the source content."""

    verbatim: str
    coded_pt: str | None = None
    confidence: float
    span: EvidenceSpan | None = None


class ICSRElement(BaseModel):
    """One of the four minimum ICSR validity criteria."""

    present: bool
    evidence_span: EvidenceSpan | None = None


class ICSRElements(BaseModel):
    """The four minimum criteria for a valid ICSR."""

    identifiable_patient: ICSRElement
    identifiable_reporter: ICSRElement
    suspect_product: ICSRElement
    adverse_event: ICSRElement


class SecurityReport(BaseModel):
    """Security findings from intake scanning."""

    malware_detected: bool = False
    prompt_injection_detected: bool = False
    pii_findings: list[str] = Field(default_factory=list)
    xss_detected: bool = False
    sqli_detected: bool = False


class TriageResult(BaseModel):
    """Triage outcome — attached to a SourceRecord after the triage pipeline runs."""

    is_noise: bool = False
    noise_reason: str | None = None
    products_mentioned: list[ProductMention] = Field(default_factory=list)
    content_types: list[ContentType] = Field(default_factory=list)
    ae_candidates: list[EventMention] = Field(default_factory=list)
    patient_count: int = 1
    icsr_elements: ICSRElements | None = None
    icsr_outcome: ICSROutcome | None = None
    outcome_rule_id: str | None = None
    outcome_rule_version: str | None = None
    priority_score: float = 0.0
    seriousness_signal: bool = False
    confidence: float = 0.0
    model_id: str | None = None
    prompt_version: str | None = None
    rationale: str | None = None


class SourceRecord(BaseModel):
    """The channel-agnostic envelope for all inbound content.

    Contract C7 — the single most important intake type.
    """

    schema_version: str = "1.0"

    # Identity
    source_record_id: str = Field(description="ULID")
    tenant_id: str
    trace_id: str
    sweep_id: str | None = None

    # Provenance
    channel: Channel
    channel_class: ChannelClass
    external_id: str | None = None
    external_url: str | None = None
    parent_external_id: str | None = None
    author_handle_token: str | None = None
    platform_published_at: datetime | None = None
    retrieved_at: datetime
    awareness_datetime: datetime = Field(description="DAY 0 CANDIDATE — immutable once written")

    # Content
    raw_language: str | None = None
    raw_text: str | None = None
    translated_text: str | None = None
    translation_engine: str | None = None
    media: list[MediaRef] = Field(default_factory=list)
    transcript_ref: str | None = None
    canonical_document_ref: str | None = None
    content_hash: str = Field(description="SHA-256 of normalised text + media hashes")

    # Evidence
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    manifest_ref: str | None = None

    # Triage outcome
    triage: TriageResult | None = None

    # Lineage
    duplicate_of_source_record_id: str | None = None
    derived_case_ids: list[str] = Field(default_factory=list)
    security: SecurityReport | None = None
    status: SourceStatus = SourceStatus.RECEIVED
    error_type: str | None = None
    error_message: str | None = None
