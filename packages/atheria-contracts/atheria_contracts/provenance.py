"""Provenance wrapper — the core trust primitive of Atheria.

Every clinically or regulatorily meaningful value is wrapped in Provenanced[T]
so that a reviewer can see *why* the field says what it says, and an inspector
can trace every value to its origin.
"""

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from .enums import ProducedBy, ReviewState

T = TypeVar("T")


class Locator(BaseModel):
    """Where in a source document the evidence lives."""

    # For PDFs: page + bounding box
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None  # x0, y0, x1, y1

    # For text: character offsets
    char_start: int | None = None
    char_end: int | None = None

    # For audio/video: timecodes
    time_start_ms: int | None = None
    time_end_ms: int | None = None


class EvidenceSpan(BaseModel):
    """A pointer to the exact location in a source that supports a field value."""

    source_record_id: str
    evidence_ref: str = Field(description="S3 key to the evidence object")
    locator: Locator
    quote: str = Field(description="Verbatim text, as-received language")
    quote_translated: str | None = None


class Provenanced(BaseModel, Generic[T]):
    """Wrapper that carries full provenance for any field value.

    This is the single most important type in Atheria: it is what makes
    the system inspectable, trustworthy, and regulatorily defensible.
    """

    value: T | None = None

    # Who/what produced the value
    produced_by: ProducedBy

    # AI attribution
    model_id: str | None = None
    prompt_version: str | None = None
    confidence: float | None = None

    # Rule attribution
    rule_id: str | None = None
    rule_set_version: str | None = None

    # Dictionary attribution
    dictionary: str | None = None
    dictionary_version: str | None = None

    # Evidence
    evidence: list[EvidenceSpan] = Field(default_factory=list)

    # Human attribution
    actor_id: str | None = None
    actor_action: str | None = None
    reason_code: str | None = None

    # Lifecycle
    first_set_at: datetime
    last_changed_at: datetime
    review_state: ReviewState = ReviewState.PROPOSED
