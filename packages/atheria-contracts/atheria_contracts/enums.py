"""Shared enumerations for the Atheria platform."""

from enum import Enum


class Channel(str, Enum):
    """Source channel types — every connector emits one of these."""

    SOCIAL_INSTAGRAM = "social_instagram"
    SOCIAL_FACEBOOK = "social_facebook"
    SOCIAL_LINKEDIN = "social_linkedin"
    SOCIAL_X = "social_x"
    SOCIAL_YOUTUBE = "social_youtube"
    SOCIAL_TIKTOK = "social_tiktok"
    AGGREGATOR = "aggregator"
    FORUM = "forum"
    LITERATURE_PUBMED = "literature_pubmed"
    LITERATURE_EMBASE = "literature_embase"
    LITERATURE_FULLTEXT = "literature_fulltext"
    EMAIL = "email"
    WEB_FORM = "web_form"
    VOICE_CALL = "voice_call"
    MI_TICKET = "mi_ticket"
    PARTNER_FILE = "partner_file"
    E2B_INBOUND = "e2b_inbound"
    EDC_SAE = "edc_sae"
    REGULATOR_FEED = "regulator_feed"
    MANUAL_ENTRY = "manual_entry"


class ChannelClass(str, Enum):
    """Channel classification for regulatory obligation determination."""

    OWNED = "owned"
    EARNED = "earned"
    SOLICITED = "solicited"
    PARTNER = "partner"
    LITERATURE = "literature"
    CLINICAL = "clinical"
    REGULATOR = "regulator"


class ContentType(str, Enum):
    """Content type classification from triage."""

    AE = "ae"
    PQC = "pqc"
    MI_ENQUIRY = "mi_enquiry"
    OFF_LABEL = "off_label"
    PREGNANCY = "pregnancy"
    MISUSE = "misuse"
    ABUSE = "abuse"
    OVERDOSE = "overdose"
    MEDICATION_ERROR = "medication_error"
    LACK_OF_EFFECT = "lack_of_effect"
    OCCUPATIONAL_EXPOSURE = "occupational_exposure"
    COUNTERFEIT = "counterfeit"
    NONE = "none"


class ICSROutcome(str, Enum):
    """Three-way triage outcome."""

    VALID_ICSR = "valid_icsr"
    POTENTIAL_ICSR = "potential_icsr"
    NON_ICSR = "non_icsr"


class SourceStatus(str, Enum):
    """Source record processing status."""

    RECEIVED = "received"
    NORMALISING = "normalising"
    TRIAGING = "triaging"
    TRIAGED = "triaged"
    CASE_CREATED = "case_created"
    NON_ICSR = "non_icsr"
    NOISE = "noise"
    ERROR = "error"
    QUARANTINED = "quarantined"


class CaseState(str, Enum):
    """Case lifecycle states."""

    DRAFT = "draft"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    CODING = "coding"
    CODED = "coded"
    ASSESSING = "assessing"
    ASSESSED = "assessed"
    REVIEW_REQUIRED = "review_required"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    HANDED_OFF = "handed_off"
    CLOSED = "closed"
    ERROR = "error"


class LockState(str, Enum):
    """Case lock state."""

    OPEN = "open"
    LOCKED_FOR_REVIEW = "locked_for_review"
    LOCKED_SUBMITTED = "locked_submitted"


class VersionType(str, Enum):
    """Case version types."""

    INITIAL = "initial"
    FOLLOW_UP = "follow_up"
    AMENDMENT = "amendment"
    NULLIFICATION = "nullification"


class ReportType(str, Enum):
    """Safety report type."""

    SPONTANEOUS = "spontaneous"
    STUDY = "study"
    OTHER = "other"
    LITERATURE = "literature"


class Sex(str, Enum):
    """Patient sex."""

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class AgeGroup(str, Enum):
    """Age group categories."""

    NEONATE = "neonate"
    INFANT = "infant"
    CHILD = "child"
    ADOLESCENT = "adolescent"
    ADULT = "adult"
    ELDERLY = "elderly"
    UNKNOWN = "unknown"


class DrugCharacterisation(str, Enum):
    """Drug role in the case."""

    SUSPECT = "suspect"
    CONCOMITANT = "concomitant"
    INTERACTING = "interacting"
    DRUG_NOT_ADMINISTERED = "drug_not_administered"


class ActionTaken(str, Enum):
    """Drug action taken."""

    WITHDRAWN = "withdrawn"
    DOSE_REDUCED = "dose_reduced"
    DOSE_INCREASED = "dose_increased"
    DOSE_NOT_CHANGED = "dose_not_changed"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class Dechallenge(str, Enum):
    """Dechallenge result."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NOT_DONE = "not_done"
    UNKNOWN = "unknown"


class Rechallenge(str, Enum):
    """Rechallenge result."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NOT_DONE = "not_done"
    UNKNOWN = "unknown"


class Outcome(str, Enum):
    """Reaction outcome."""

    RECOVERED = "recovered"
    RECOVERING = "recovering"
    NOT_RECOVERED = "not_recovered"
    FATAL = "fatal"
    UNKNOWN = "unknown"
    RECOVERED_WITH_SEQUELAE = "recovered_with_sequelae"


class ProducedBy(str, Enum):
    """Who/what produced a value."""

    AI = "ai"
    RULE = "rule"
    HUMAN = "human"
    IMPORT = "import"
    DEFAULT = "default"


class ReviewState(str, Enum):
    """Field-level review state."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class ObligationType(str, Enum):
    """Reporting obligation type."""

    EXPEDITED = "expedited"
    PERIODIC = "periodic"
    NON_EXPEDITED = "non_expedited"
    NONE = "none"


class ObligationStatus(str, Enum):
    """Reporting obligation status."""

    PENDING = "pending"
    HANDED_OFF = "handed_off"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    REJECTED = "rejected"
    NOT_REQUIRED = "not_required"
    WAIVED = "waived"
