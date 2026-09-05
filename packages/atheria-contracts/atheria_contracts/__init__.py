"""Atheria Contracts — shared Pydantic models and JSON Schema definitions."""

__version__ = "0.1.0"

from .audit import AuditEvent
from .canonical_case import (
    AssessmentBlock,
    CanonicalCase,
    CodedTerm,
    CompletenessReport,
    DrugBlock,
    ElectronicSignature,
    MissingDataItem,
    NarrativeBlock,
    PatientBlock,
    ReactionBlock,
    RuleEvaluation,
    SeriousnessFacts,
)
from .enums import (
    CaseState,
    Channel,
    ChannelClass,
    ContentType,
    ICSROutcome,
    LockState,
    ProducedBy,
    ReviewState,
    SourceStatus,
    VersionType,
)
from .provenance import EvidenceSpan, Locator, Provenanced
from .source_record import (
    ICSRElement,
    ICSRElements,
    SourceRecord,
    TriageResult,
)

__all__ = [
    "AssessmentBlock",
    "AuditEvent",
    "CanonicalCase",
    "CaseState",
    "Channel",
    "ChannelClass",
    "CodedTerm",
    "CompletenessReport",
    "ContentType",
    "DrugBlock",
    "ElectronicSignature",
    "EvidenceSpan",
    "ICSRElement",
    "ICSRElements",
    "ICSROutcome",
    "Locator",
    "LockState",
    "MissingDataItem",
    "NarrativeBlock",
    "PatientBlock",
    "ProducedBy",
    "Provenanced",
    "ReactionBlock",
    "ReviewState",
    "RuleEvaluation",
    "SeriousnessFacts",
    "SourceRecord",
    "SourceStatus",
    "TriageResult",
    "VersionType",
]
