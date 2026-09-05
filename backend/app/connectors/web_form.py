"""Web-form connector — solicited direct reports.

A web form is a *solicited* channel: the company asked for the information, so
its regulatory handling differs from an unsolicited social-media mention. That
distinction is carried by ``ChannelClass.SOLICITED`` and drives obligation
rules downstream.

The form gives us semi-structured fields. We keep them as labelled sections in
the ``raw_text`` (rather than pre-filling case fields) so that triage reads the
same shape of input for every channel, and every extracted value still has to
earn an evidence span pointing back at the submitted text.
"""

from __future__ import annotations

from dataclasses import dataclass

from atheria_contracts.enums import Channel, ChannelClass
from atheria_contracts.source_record import SourceRecord

from .base import build_source_record


@dataclass
class WebFormSubmission:
    """Fields captured by the public adverse-event reporting form.

    Everything is optional except the narrative: incomplete reports are exactly
    the ones the validity rule needs to see, so the connector must accept them
    rather than reject them at the door.
    """

    narrative: str
    reporter_name: str | None = None
    reporter_qualification: str | None = None
    reporter_email: str | None = None
    reporter_country: str | None = None
    patient_initials: str | None = None
    patient_age: str | None = None
    patient_sex: str | None = None
    product_name: str | None = None
    dose: str | None = None
    event_description: str | None = None
    onset_date: str | None = None
    language: str | None = "en"

    def to_source_text(self) -> str:
        """Render the submission as labelled text for triage.

        Only populated fields are emitted. Empty fields are omitted entirely
        rather than written as "unknown", so the model cannot mistake a blank
        form field for a positive assertion of absence.
        """
        sections: list[tuple[str, str | None]] = [
            ("Reporter name", self.reporter_name),
            ("Reporter qualification", self.reporter_qualification),
            ("Reporter email", self.reporter_email),
            ("Reporter country", self.reporter_country),
            ("Patient initials", self.patient_initials),
            ("Patient age", self.patient_age),
            ("Patient sex", self.patient_sex),
            ("Product", self.product_name),
            ("Dose", self.dose),
            ("Event", self.event_description),
            ("Onset date", self.onset_date),
        ]
        lines = [
            f"{label}: {value.strip()}" for label, value in sections if value and value.strip()
        ]
        lines.append("")
        lines.append("Narrative:")
        lines.append(self.narrative.strip())
        return "\n".join(lines)


def ingest_web_form(
    *,
    tenant_id: str,
    submission: WebFormSubmission,
    trace_id: str | None = None,
    external_id: str | None = None,
) -> SourceRecord:
    """Turn a web-form submission into a SourceRecord."""
    return build_source_record(
        tenant_id=tenant_id,
        channel=Channel.WEB_FORM,
        channel_class=ChannelClass.SOLICITED,
        raw_text=submission.to_source_text(),
        raw_language=submission.language,
        trace_id=trace_id,
        external_id=external_id,
    )
