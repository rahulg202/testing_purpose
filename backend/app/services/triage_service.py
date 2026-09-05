"""Triage service — ICSR identification.

This is where Atheria's central claim becomes executable:

1. **The AI proposes.** A model reads the source text and reports, with verbatim
   evidence quotes, whether each of the four ICSR minimum criteria is present.
   It is explicitly forbidden (by prompt and by code path) from deciding
   validity.
2. **The rules decide.** ``val_001`` — deterministic, versioned, replayable —
   converts those four observations into a ``valid_icsr`` /
   ``potential_icsr`` / ``non_icsr`` outcome and emits a decision trace.
3. **The human approves.** Anything the rule escalates lands in the inbox as a
   work item rather than being silently resolved.

Everything is recorded so the result is defensible: the model and prompt
version behind each proposal, the rule ID and rule-set version behind the
decision, the evidence span behind each element, and a hash-chained audit event
for the rule evaluation itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from atheria_contracts.enums import ContentType, ICSROutcome, SourceStatus
from atheria_contracts.provenance import EvidenceSpan, Locator
from atheria_contracts.source_record import (
    EventMention,
    ICSRElement,
    ICSRElements,
    ProductMention,
    SourceRecord,
    TriageResult,
)
from atheria_llm import LLMConfig, LLMError, LLMProvider, PromptRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from ..core.evidence import EvidenceStore, build_evidence_key
from ..models.case import PipelineRunModel, PipelineStageModel, SourceRecordModel
from ..rules.validity import evaluate_validity
from .audit_service import AuditService

logger = structlog.get_logger("triage_service")

PROMPT_NAME = "triage_icsr"
PIPELINE_TYPE = "triage"

#: Maps the rule outcome onto the source record's terminal triage status.
_OUTCOME_STATUS = {
    ICSROutcome.VALID_ICSR: SourceStatus.TRIAGED,
    ICSROutcome.POTENTIAL_ICSR: SourceStatus.TRIAGED,
    ICSROutcome.NON_ICSR: SourceStatus.NON_ICSR,
}


class TriageError(RuntimeError):
    """Triage could not be completed. Surfaces as a terminal stage state."""


@dataclass
class TriageOutcome:
    """Everything a caller (API, UI) needs after triage runs."""

    source_record_id: str
    status: SourceStatus
    outcome: ICSROutcome | None
    triage_result: TriageResult
    rule_trace: dict[str, Any]
    run_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_record_id": self.source_record_id,
            "status": self.status.value,
            "icsr_outcome": self.outcome.value if self.outcome else None,
            "triage": self.triage_result.model_dump(mode="json"),
            "rule_trace": self.rule_trace,
            "run_id": self.run_id,
        }


#: Quote characters models sometimes wrap around an "exact" quote.
_QUOTE_CHARS = "\"'\u201c\u201d\u2018\u2019\u00ab\u00bb"


def _quote_variants(quote: str) -> list[str]:
    """Candidate forms of a quote to search for, most exact first.

    Models are inconsistent about echoing quotes: some wrap the text in
    quotation marks, some normalise internal whitespace. Trying a short ordered
    list of variants recovers the correct offsets in nearly all cases without
    ever guessing at a position.
    """
    candidates: list[str] = []

    def add(value: str) -> None:
        value = value.strip()
        if value and value not in candidates:
            candidates.append(value)

    add(quote)
    stripped = quote.strip().strip(_QUOTE_CHARS)
    add(stripped)
    add(" ".join(stripped.split()))
    return candidates


def _locate_quote(haystack: str, quote: str) -> Locator:
    """Find a verbatim quote in the source text and return char offsets.

    If the quote genuinely cannot be found we return an empty locator rather
    than a wrong one: a bad offset would highlight the wrong sentence for the
    reviewer, which is worse than highlighting nothing.
    """
    if not quote or not haystack:
        return Locator()

    for candidate in _quote_variants(quote):
        index = haystack.find(candidate)
        if index != -1:
            return Locator(char_start=index, char_end=index + len(candidate))

    # Last resort: match the leading fragment, which still lands the reviewer on
    # the right sentence.
    head = " ".join(quote.strip().strip(_QUOTE_CHARS).split())[:40]
    if head:
        index = haystack.find(head)
        if index != -1:
            return Locator(char_start=index, char_end=index + len(head))

    logger.warning("evidence_quote_not_located", quote_preview=quote[:60])
    return Locator()


class TriageService:
    """Runs the triage pipeline for a source record."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        provider: LLMProvider,
        prompts: PromptRegistry,
        evidence_store: EvidenceStore | None = None,
        max_tokens: int = 2000,
    ) -> None:
        self._session = session
        self._provider = provider
        self._prompts = prompts
        self._evidence = evidence_store
        self._max_tokens = max_tokens
        self._audit = AuditService(session)

    # -- persistence --------------------------------------------------------

    async def persist_source_record(self, record: SourceRecord) -> SourceRecordModel:
        """Store a freshly ingested source record and vault its raw text."""
        evidence_key = build_evidence_key(
            tenant_id=record.tenant_id,
            channel=record.channel.value,
            source_record_id=record.source_record_id,
            received_at=record.retrieved_at,
        )
        if self._evidence is not None and record.raw_text:
            self._evidence.put_text(evidence_key, record.raw_text)

        model = SourceRecordModel(
            source_record_id=record.source_record_id,
            tenant_id=record.tenant_id,
            trace_id=record.trace_id,
            sweep_id=record.sweep_id,
            channel=record.channel.value,
            channel_class=record.channel_class.value,
            external_id=record.external_id,
            external_url=record.external_url,
            retrieved_at=record.retrieved_at,
            awareness_datetime=record.awareness_datetime,
            platform_published_at=record.platform_published_at,
            raw_text=record.raw_text,
            raw_language=record.raw_language,
            content_hash=record.content_hash,
            manifest_ref=evidence_key,
            status=SourceStatus.RECEIVED.value,
            derived_case_ids=[],
        )
        self._session.add(model)
        await self._session.flush()

        logger.info(
            "source_record_persisted",
            source_record_id=record.source_record_id,
            channel=record.channel.value,
            tenant_id=record.tenant_id,
            content_hash=record.content_hash[:16],
        )
        return model

    async def existing_content_hashes(self, tenant_id: str) -> set[str]:
        """Content hashes already stored, used to skip duplicate intake."""
        result = await self._session.execute(
            select(SourceRecordModel.content_hash).where(SourceRecordModel.tenant_id == tenant_id)
        )
        return set(result.scalars().all())

    # -- the pipeline -------------------------------------------------------

    async def triage(
        self,
        *,
        tenant_id: str,
        source_record_id: str,
        actor_id: str = "pipeline_triage",
        trace_id: str | None = None,
    ) -> TriageOutcome:
        """Run triage on a stored source record.

        Raises:
            TriageError: if the record is missing or the model call fails. The
                pipeline stage is marked failed and the record moves to ERROR so
                the failure is visible rather than silent.
        """
        record = await self._session.get(SourceRecordModel, source_record_id)
        if not record or record.tenant_id != tenant_id:
            raise TriageError(f"Source record {source_record_id} not found")

        run, stage = await self._start_run(record, trace_id=trace_id)
        record.status = SourceStatus.TRIAGING.value
        await self._session.flush()

        try:
            proposal, invocation = self._propose(record)
        except LLMError as exc:
            await self._fail(run, stage, record, error_type=type(exc).__name__, message=str(exc))
            raise TriageError(f"Triage model call failed: {exc}") from exc

        source_text = record.raw_text or ""
        elements = self._build_elements(proposal, record, source_text)

        # --- The deterministic decision -----------------------------------
        decision = evaluate_validity(elements)

        triage_result = self._build_triage_result(
            proposal=proposal,
            elements=elements,
            record=record,
            source_text=source_text,
            decision_outcome=decision.outcome,
            model_id=invocation["model_id"],
            prompt_version=invocation["prompt_version"],
        )

        record.triage_result = triage_result.model_dump(mode="json")
        record.status = _OUTCOME_STATUS[decision.outcome].value
        if triage_result.is_noise:
            record.status = SourceStatus.NOISE.value

        # --- Audit: the AI proposal, then the rule decision ----------------
        await self._audit.record_ai_invocation(
            tenant_id=tenant_id,
            source_record_id=source_record_id,
            model_id=invocation["model_id"],
            prompt_version=invocation["prompt_version"],
            rationale=proposal.get("rationale"),
            confidence=triage_result.confidence,
            trace_id=trace_id,
        )
        await self._audit.record_rule_evaluation(
            tenant_id=tenant_id,
            source_record_id=source_record_id,
            rule_id=decision.trace.rule_id,
            rule_set_version=decision.trace.rule_set_version,
            field_path="triage.icsr_outcome",
            outcome=decision.outcome.value,
            rationale=decision.trace.explanation,
            trace_id=trace_id,
        )

        await self._complete_stage(stage, run, output=triage_result.model_dump(mode="json"))
        await self._session.flush()

        logger.info(
            "triage_complete",
            source_record_id=source_record_id,
            tenant_id=tenant_id,
            icsr_outcome=decision.outcome.value,
            status=record.status,
            fired_rules=decision.trace.fired_rules,
            model_id=invocation["model_id"],
            actor_id=actor_id,
        )

        return TriageOutcome(
            source_record_id=source_record_id,
            status=SourceStatus(record.status),
            outcome=decision.outcome,
            triage_result=triage_result,
            rule_trace=decision.trace.model_dump(mode="json"),
            run_id=run.run_id,
        )

    # -- steps --------------------------------------------------------------

    def _propose(self, record: SourceRecordModel) -> tuple[dict[str, Any], dict[str, str]]:
        """Ask the model to report the four criteria. No decisions made here."""
        template = self._prompts.get_or_raise(PROMPT_NAME)
        prompt = template.render_user(
            channel=record.channel,
            source_text=record.raw_text or "",
        )
        prompt_version = f"{template.name}_v{template.version}"

        response = self._provider.invoke(
            prompt,
            LLMConfig(
                prompt_version=prompt_version,
                system_prompt=template.system_prompt,
                output_schema=template.output_schema,
                max_tokens=max(template.max_tokens, self._max_tokens),
                temperature=template.temperature,
                tenant_id=record.tenant_id,
                trace_id=record.trace_id,
            ),
        )
        proposal = response.require_structured()
        model_id = response.record.model_id if response.record else "unknown"
        return proposal, {"model_id": model_id, "prompt_version": prompt_version}

    def _build_elements(
        self,
        proposal: dict[str, Any],
        record: SourceRecordModel,
        source_text: str,
    ) -> ICSRElements:
        """Convert the model's four observations into contract elements.

        Each present element gets an EvidenceSpan whose locator points at the
        actual character offsets in the stored source text, which is what makes
        "click the field, see the sentence" work in the workbench.
        """

        def element(name: str) -> ICSRElement:
            raw = proposal.get(name) or {}
            present = bool(raw.get("present"))
            # Strip any quotation marks the model wrapped around the quote so
            # the stored evidence matches the source text exactly.
            quote = (raw.get("evidence_quote") or "").strip().strip(_QUOTE_CHARS).strip()
            span = None
            if present and quote:
                span = EvidenceSpan(
                    source_record_id=record.source_record_id,
                    evidence_ref=record.manifest_ref or "",
                    locator=_locate_quote(source_text, quote),
                    quote=quote,
                )
            return ICSRElement(present=present, evidence_span=span)

        return ICSRElements(
            identifiable_patient=element("identifiable_patient"),
            identifiable_reporter=element("identifiable_reporter"),
            suspect_product=element("suspect_product"),
            adverse_event=element("adverse_event"),
        )

    def _build_triage_result(
        self,
        *,
        proposal: dict[str, Any],
        elements: ICSRElements,
        record: SourceRecordModel,
        source_text: str,
        decision_outcome: ICSROutcome,
        model_id: str,
        prompt_version: str,
    ) -> TriageResult:
        """Assemble the TriageResult stored on the source record."""
        from ..rules.validity import RULE_ID, RULE_SET_VERSION

        products = [
            ProductMention(
                verbatim=name,
                confidence=0.0,
                span=EvidenceSpan(
                    source_record_id=record.source_record_id,
                    evidence_ref=record.manifest_ref or "",
                    locator=_locate_quote(source_text, name),
                    quote=name,
                ),
            )
            for name in (proposal.get("product_names") or [])
            if isinstance(name, str) and name.strip()
        ]
        events = [
            EventMention(
                verbatim=term,
                confidence=0.0,
                span=EvidenceSpan(
                    source_record_id=record.source_record_id,
                    evidence_ref=record.manifest_ref or "",
                    locator=_locate_quote(source_text, term),
                    quote=term,
                ),
            )
            for term in (proposal.get("event_terms") or [])
            if isinstance(term, str) and term.strip()
        ]

        try:
            content_type = ContentType(proposal.get("content_type") or "none")
        except ValueError:
            content_type = ContentType.NONE

        present_count = sum(
            1
            for name in (
                "identifiable_patient",
                "identifiable_reporter",
                "suspect_product",
                "adverse_event",
            )
            if getattr(elements, name).present
        )

        return TriageResult(
            is_noise=bool(proposal.get("is_noise")),
            noise_reason="Model reported no pharmacovigilance-relevant content"
            if proposal.get("is_noise")
            else None,
            products_mentioned=products,
            content_types=[content_type],
            ae_candidates=events,
            patient_count=int(proposal.get("patient_count") or 0),
            icsr_elements=elements,
            icsr_outcome=decision_outcome,
            outcome_rule_id=RULE_ID,
            outcome_rule_version=RULE_SET_VERSION,
            # Priority: completeness of the four criteria, nudged up when the
            # text hints at seriousness so those surface first in the inbox.
            priority_score=round(
                min(1.0, present_count / 4 + (0.25 if proposal.get("seriousness_signal") else 0.0)),
                2,
            ),
            seriousness_signal=bool(proposal.get("seriousness_signal")),
            confidence=0.0,
            model_id=model_id,
            prompt_version=prompt_version,
            rationale=proposal.get("rationale"),
        )

    # -- pipeline bookkeeping ----------------------------------------------

    async def _start_run(
        self, record: SourceRecordModel, *, trace_id: str | None
    ) -> tuple[PipelineRunModel, PipelineStageModel]:
        """Open a durable pipeline run + triage stage."""
        now = datetime.now(UTC)
        run = PipelineRunModel(
            run_id=str(ULID()),
            tenant_id=record.tenant_id,
            source_record_id=record.source_record_id,
            pipeline_type=PIPELINE_TYPE,
            status="running",
            started_at=now,
        )
        stage = PipelineStageModel(
            id=str(ULID()),
            tenant_id=record.tenant_id,
            run_id=run.run_id,
            stage_name="triage",
            stage_order=1,
            status="running",
            started_at=now,
            input_hash=record.content_hash,
        )
        self._session.add(run)
        self._session.add(stage)
        await self._session.flush()
        return run, stage

    async def _complete_stage(
        self,
        stage: PipelineStageModel,
        run: PipelineRunModel,
        *,
        output: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC)
        payload = json.dumps(output, sort_keys=True, default=str)
        stage.status = "completed"
        stage.completed_at = now
        stage.output_hash = hashlib.sha256(payload.encode()).hexdigest()
        if stage.started_at:
            stage.duration_ms = (now - stage.started_at).total_seconds() * 1000
        run.status = "completed"
        run.completed_at = now

    async def _fail(
        self,
        run: PipelineRunModel,
        stage: PipelineStageModel,
        record: SourceRecordModel,
        *,
        error_type: str,
        message: str,
    ) -> None:
        """Mark everything failed and visible. Never swallow the error."""
        now = datetime.now(UTC)
        stage.status = "failed"
        stage.completed_at = now
        stage.error_type = error_type
        stage.error_message = message[:2000]
        run.status = "failed"
        run.completed_at = now
        run.error_type = error_type
        run.error_message = message[:2000]
        record.status = SourceStatus.ERROR.value
        record.error_type = error_type
        record.error_message = message[:2000]
        await self._session.flush()
        logger.error(
            "triage_failed",
            source_record_id=record.source_record_id,
            tenant_id=record.tenant_id,
            error_type=error_type,
            error=message[:300],
        )
