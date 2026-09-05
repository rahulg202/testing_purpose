"""Canonical Case contract (C8) — the working ICSR, versioned.

MVP subset: ~25 fields covering identification, reporter, patient,
1..n drugs, 1..n reactions, and narrative. Full model per doc 02 §4.
"""

from datetime import date, datetime

from pydantic import BaseModel, Field

from .enums import (
    ActionTaken,
    AgeGroup,
    CaseState,
    Dechallenge,
    DrugCharacterisation,
    LockState,
    Outcome,
    Rechallenge,
    ReportType,
    Sex,
    VersionType,
)
from .provenance import Provenanced

# --- Sub-structures ---


class CodedTerm(BaseModel):
    """A MedDRA or other coded term."""

    code: str
    term: str
    dictionary: str = "MedDRA"
    dictionary_version: str | None = None


class AgeValue(BaseModel):
    """Age with unit."""

    value: float
    unit: str = "year"  # year | month | week | day | hour


class DoseInfo(BaseModel):
    """Drug dosage information."""

    amount: float | None = None
    unit: str | None = None
    frequency: str | None = None
    route: str | None = None
    cumulative_amount: float | None = None
    cumulative_unit: str | None = None


class PartialDate(BaseModel):
    """E2B(R3) partial date — year is always present, month and day are optional."""

    year: int
    month: int | None = None
    day: int | None = None


class Duration(BaseModel):
    """Duration with unit."""

    value: float
    unit: str  # second | minute | hour | day | week | month | year


class LiteratureRef(BaseModel):
    """Literature reference."""

    pmid: str | None = None
    doi: str | None = None
    title: str | None = None
    authors: str | None = None
    journal: str | None = None
    publication_date: str | None = None


class StudyIdentification(BaseModel):
    """Clinical study identification."""

    study_number: str | None = None
    study_name: str | None = None
    sponsor_study_number: str | None = None


class Reporter(BaseModel):
    """Reporter information (pseudonymised in the case body)."""

    reporter_id: str | None = None
    qualification: str | None = None  # physician | pharmacist | other_hp | lawyer | consumer
    country: str | None = None  # ISO 3166-1 alpha-2
    is_primary: bool = False


class SenderIdentification(BaseModel):
    """Sender identification for E2B."""

    sender_organisation: str | None = None
    sender_department: str | None = None
    sender_type: str | None = None


class ReceiverProfile(BaseModel):
    """Per-authority receiver profile."""

    authority: str
    receiver_organisation: str | None = None
    jurisdiction: str | None = None


# --- Patient block ---


class MedicalHistoryItem(BaseModel):
    """Patient medical history entry."""

    condition: str
    coded_term: CodedTerm | None = None
    start_date: PartialDate | None = None
    end_date: PartialDate | None = None
    continuing: bool | None = None


class PatientBlock(BaseModel):
    """Patient demographic and medical history data."""

    patient_pii_token: str | None = None
    age_at_onset: Provenanced[AgeValue] | None = None
    age_group: Provenanced[AgeGroup] | None = None
    sex: Provenanced[Sex] | None = None
    weight_kg: Provenanced[float] | None = None
    height_cm: Provenanced[float] | None = None


# --- Drug block ---


class DrugBlock(BaseModel):
    """Drug information — suspect, concomitant, or interacting."""

    drug_id: str
    characterisation: Provenanced[DrugCharacterisation]
    product_name_verbatim: Provenanced[str]
    active_substances: list[Provenanced[str]] = Field(default_factory=list)
    dose: Provenanced[DoseInfo] | None = None
    route: Provenanced[str] | None = None
    indications: list[Provenanced[CodedTerm]] = Field(default_factory=list)
    therapy_start: Provenanced[PartialDate] | None = None
    therapy_end: Provenanced[PartialDate] | None = None
    action_taken: Provenanced[ActionTaken] | None = None
    dechallenge: Provenanced[Dechallenge] | None = None
    rechallenge: Provenanced[Rechallenge] | None = None


# --- Reaction block ---


class SeriousnessFacts(BaseModel):
    """Seriousness criteria — these are FACTS extracted, not determinations."""

    resulted_in_death: Provenanced[bool] | None = None
    life_threatening: Provenanced[bool] | None = None
    required_hospitalisation: Provenanced[bool] | None = None
    prolonged_hospitalisation: Provenanced[bool] | None = None
    persistent_disability: Provenanced[bool] | None = None
    congenital_anomaly: Provenanced[bool] | None = None
    other_medically_important: Provenanced[bool] | None = None


class RuleEvaluation(BaseModel):
    """Record of a rule engine evaluation — the deterministic decision trace."""

    rule_id: str
    rule_set_version: str
    inputs: dict[str, object] = Field(default_factory=dict)
    input_provenance: dict[str, str] = Field(default_factory=dict)
    fired_rules: list[str] = Field(default_factory=list)
    explanation: str | None = None
    outcome: str | None = None


class ListednessAssessment(BaseModel):
    """Expectedness assessment per reference document and region."""

    region: str
    reference_document_id: str
    reference_document_version: str
    matched_term: CodedTerm | None = None
    match_method: str | None = None  # exact_pt | llt_under_pt | soc_group | manual
    outcome: str | None = None  # listed | unlisted | unassessable
    rule_trace: RuleEvaluation | None = None


class ReactionBlock(BaseModel):
    """Reaction/event information."""

    reaction_id: str
    verbatim: Provenanced[str]
    verbatim_translated: Provenanced[str] | None = None
    coded_llt: Provenanced[CodedTerm] | None = None
    coded_pt: Provenanced[CodedTerm] | None = None
    derived_hlt: CodedTerm | None = None
    derived_soc: CodedTerm | None = None
    onset_date: Provenanced[PartialDate] | None = None
    end_date: Provenanced[PartialDate] | None = None
    outcome: Provenanced[Outcome] | None = None
    serious_criteria_facts: SeriousnessFacts | None = None
    is_serious: Provenanced[bool] | None = None
    seriousness_rule_trace: RuleEvaluation | None = None
    listedness: list[ListednessAssessment] = Field(default_factory=list)


# --- Narrative block ---


class NarrativeBlock(BaseModel):
    """Case narrative — generated from approved fields only."""

    text: Provenanced[str] | None = None
    coverage_check_passed: bool | None = None
    coverage_gaps: list[str] = Field(default_factory=list)


# --- Assessment block ---


class AssessmentBlock(BaseModel):
    """Atheria assessment layer — rule-derived, not in E2B verbatim."""

    case_seriousness: Provenanced[bool] | None = None
    case_seriousness_trace: RuleEvaluation | None = None
    is_valid_icsr: Provenanced[bool] | None = None
    validity_trace: RuleEvaluation | None = None


# --- Completeness ---


class CompletenessReport(BaseModel):
    """Case completeness assessment."""

    overall_score: float = 0.0
    missing_mandatory: list[str] = Field(default_factory=list)
    missing_recommended: list[str] = Field(default_factory=list)
    rule_trace: RuleEvaluation | None = None


class MissingDataItem(BaseModel):
    """A specific piece of missing data that requires follow-up."""

    field_path: str
    description: str
    is_mandatory: bool = False
    follow_up_question: str | None = None


# --- Electronic signature ---


class ElectronicSignature(BaseModel):
    """21 CFR Part 11 compliant electronic signature record."""

    actor_id: str
    meaning: str  # "Approval of case data", "Medical review complete"
    reason: str | None = None
    timestamp: datetime
    content_hash: str = Field(description="SHA-256 of the case version content at signing")
    mfa_method: str | None = None


# --- The canonical case ---


class CanonicalCase(BaseModel):
    """The canonical ICSR — Atheria's source of truth for case processing.

    MVP subset covers ~25 fields across identification, reporter, patient,
    drugs, reactions, and narrative. Full model adds medical history,
    concomitant conditions, lab results, and causality assessment.
    """

    schema_version: str = "1.0"

    # Identity & lifecycle
    case_id: str = Field(description="Atheria internal ULID")
    tenant_id: str
    case_number: str = Field(description="Human-facing, tenant-configurable pattern")
    version: int = 1
    version_type: VersionType = VersionType.INITIAL
    supersedes_version: int | None = None
    lifecycle_state: CaseState = CaseState.DRAFT
    lock_state: LockState = LockState.OPEN

    # C.1 Identification of the safety report
    report_type: Provenanced[ReportType] | None = None
    first_awareness_date: Provenanced[date] | None = None
    most_recent_information_date: Provenanced[date] | None = None
    source_records: list[str] = Field(default_factory=list, description="SourceRecord IDs")
    literature_references: list[Provenanced[LiteratureRef]] = Field(default_factory=list)

    # C.2 Primary source / reporter
    reporters: list[Provenanced[Reporter]] = Field(default_factory=list)
    reporter_pii_token: str | None = None

    # C.3 Sender
    sender: SenderIdentification | None = None
    receiver_profiles: list[ReceiverProfile] = Field(default_factory=list)

    # D Patient
    patient: PatientBlock | None = None

    # G Drug information
    drugs: list[DrugBlock] = Field(default_factory=list)

    # E Reactions/events
    reactions: list[ReactionBlock] = Field(default_factory=list)

    # H Narrative
    narrative: NarrativeBlock | None = None

    # Assessment
    assessment: AssessmentBlock | None = None

    # Completeness
    completeness: CompletenessReport | None = None
    missing_data: list[MissingDataItem] = Field(default_factory=list)

    # Signatures
    signatures: list[ElectronicSignature] = Field(default_factory=list)

    # Timestamps
    created_at: datetime
    created_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
