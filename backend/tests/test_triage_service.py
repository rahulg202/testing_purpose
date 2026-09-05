"""Tests for the triage service — the AI-proposes / rules-decide pipeline."""

from __future__ import annotations

from typing import Any

import pytest
from atheria_contracts.enums import ICSROutcome, SourceStatus
from atheria_llm import LLMInvocationError, PromptRegistry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.case import (
    AuditEventModel,
    PipelineRunModel,
    PipelineStageModel,
    SourceRecordModel,
)
from backend.app.services.triage_service import TriageError, TriageService

from .conftest import StubProvider, make_proposal

TENANT = "acme_pharma"


def build_service(
    session: AsyncSession, prompts: PromptRegistry, proposal: dict[str, Any]
) -> tuple[TriageService, StubProvider]:
    provider = StubProvider(proposal)
    service = TriageService(session, provider=provider, prompts=prompts, evidence_store=None)
    return service, provider


class TestTriageOutcomes:
    async def test_complete_record_is_valid_icsr(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )

        assert outcome.outcome is ICSROutcome.VALID_ICSR
        assert outcome.status is SourceStatus.TRIAGED
        assert outcome.rule_trace["rule_id"] == "val_001"
        assert outcome.rule_trace["fired_rules"] == ["val_001_all_criteria_present"]

    async def test_incomplete_record_escalates(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal(patient=False, reporter=False))
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )

        assert outcome.outcome is ICSROutcome.POTENTIAL_ICSR
        # Escalated records stay in the queue as work, not marked non-ICSR.
        assert outcome.status is SourceStatus.TRIAGED

    async def test_no_event_is_non_icsr(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(
            session, prompts, make_proposal(event=False, content_type="mi_enquiry")
        )
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )

        assert outcome.outcome is ICSROutcome.NON_ICSR
        assert outcome.status is SourceStatus.NON_ICSR

    async def test_noise_is_marked_noise(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(
            session,
            prompts,
            make_proposal(
                patient=False,
                reporter=False,
                product=False,
                event=False,
                is_noise=True,
                content_type="none",
            ),
        )
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert outcome.status is SourceStatus.NOISE
        assert outcome.triage_result.is_noise is True


class TestEvidenceAndProvenance:
    async def test_evidence_quote_is_located_in_source_text(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        """Offsets must point at the real text so the UI highlights correctly."""
        quote = "54-year-old female"
        service, _ = build_service(
            session, prompts, make_proposal(quotes={"identifiable_patient": quote})
        )
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )

        elements = outcome.triage_result.icsr_elements
        assert elements is not None
        span = elements.identifiable_patient.evidence_span
        assert span is not None
        assert span.quote == quote
        start, end = span.locator.char_start, span.locator.char_end
        assert start is not None and end is not None
        assert (stored_record.raw_text or "")[start:end] == quote

    async def test_quote_wrapped_in_quotation_marks_is_still_located(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        """Models often echo quotes wrapped in "…"; offsets must still resolve."""
        service, _ = build_service(
            session,
            prompts,
            make_proposal(quotes={"suspect_product": '"Atherex 100mg"'}),
        )
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        elements = outcome.triage_result.icsr_elements
        assert elements is not None
        span = elements.suspect_product.evidence_span
        assert span is not None
        # Stored quote is cleaned of the wrapping marks...
        assert span.quote == "Atherex 100mg"
        # ...and the offsets point at the real text.
        start, end = span.locator.char_start, span.locator.char_end
        assert start is not None and end is not None
        assert (stored_record.raw_text or "")[start:end] == "Atherex 100mg"

    async def test_whitespace_normalised_quote_is_located(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(
            session, prompts, make_proposal(quotes={"adverse_event": "severe   rash"})
        )
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        elements = outcome.triage_result.icsr_elements
        assert elements is not None
        span = elements.adverse_event.evidence_span
        assert span is not None
        assert span.locator.char_start is not None

    async def test_unlocatable_quote_yields_empty_locator_not_wrong_offsets(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        """A wrong offset is worse than none: it would mislead the reviewer."""
        service, _ = build_service(
            session,
            prompts,
            make_proposal(quotes={"identifiable_patient": "text that does not appear"}),
        )
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        elements = outcome.triage_result.icsr_elements
        assert elements is not None
        span = elements.identifiable_patient.evidence_span
        assert span is not None
        assert span.locator.char_start is None

    async def test_model_and_prompt_version_recorded(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert outcome.triage_result.model_id == "stub-model-v1"
        assert outcome.triage_result.prompt_version == "triage_icsr_v1.0"
        assert outcome.triage_result.outcome_rule_id == "val_001"
        assert outcome.triage_result.outcome_rule_version == "1.0.0"

    async def test_priority_reflects_completeness_and_seriousness(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal(seriousness=True))
        outcome = await service.triage(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert outcome.triage_result.seriousness_signal is True
        assert outcome.triage_result.priority_score == 1.0


class TestAuditTrail:
    async def test_records_both_ai_proposal_and_rule_decision(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        await service.triage(tenant_id=TENANT, source_record_id=stored_record.source_record_id)

        events = (
            (await session.execute(select(AuditEventModel).order_by(AuditEventModel.timestamp)))
            .scalars()
            .all()
        )
        types = [event.event_type for event in events]
        assert "ai_invocation" in types
        assert "rule_evaluation" in types

        rule_event = next(e for e in events if e.event_type == "rule_evaluation")
        assert rule_event.actor_type == "rule"
        assert rule_event.rule_id == "val_001"
        assert rule_event.rule_set_version == "1.0.0"
        assert rule_event.field_path == "triage.icsr_outcome"

    async def test_audit_chain_is_linked(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        """Each event must chain to the previous one for tamper evidence."""
        service, _ = build_service(session, prompts, make_proposal())
        await service.triage(tenant_id=TENANT, source_record_id=stored_record.source_record_id)

        events = (
            (await session.execute(select(AuditEventModel).order_by(AuditEventModel.timestamp)))
            .scalars()
            .all()
        )
        assert len(events) >= 2
        expected_previous = "0" * 64
        for event in events:
            assert event.previous_hash == expected_previous
            expected_previous = event.content_hash


class TestPipelineTracking:
    async def test_successful_run_and_stage_are_completed(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        await service.triage(tenant_id=TENANT, source_record_id=stored_record.source_record_id)

        run = (await session.execute(select(PipelineRunModel))).scalars().one()
        stage = (await session.execute(select(PipelineStageModel))).scalars().one()

        assert run.pipeline_type == "triage"
        assert run.status == "completed"
        assert stage.stage_name == "triage"
        assert stage.status == "completed"
        assert stage.output_hash is not None
        assert stage.duration_ms is not None


class TestFailureHandling:
    async def test_missing_record_raises(
        self, session: AsyncSession, prompts: PromptRegistry
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        with pytest.raises(TriageError, match="not found"):
            await service.triage(tenant_id=TENANT, source_record_id="does_not_exist")

    async def test_tenant_isolation_prevents_cross_tenant_read(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        with pytest.raises(TriageError):
            await service.triage(
                tenant_id="other_tenant", source_record_id=stored_record.source_record_id
            )

    async def test_model_failure_is_loud_and_leaves_visible_error_state(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        """Fail loud: the record must end in ERROR, never silently succeed."""

        class FailingProvider:
            name = "failing"

            def invoke(self, prompt: str, config: object) -> object:
                raise LLMInvocationError("model exploded")

        service = TriageService(
            session,
            provider=FailingProvider(),  # type: ignore[arg-type]
            prompts=prompts,
            evidence_store=None,
        )

        with pytest.raises(TriageError, match="model call failed"):
            await service.triage(tenant_id=TENANT, source_record_id=stored_record.source_record_id)

        record = await session.get(SourceRecordModel, stored_record.source_record_id)
        assert record is not None
        assert record.status == SourceStatus.ERROR.value
        assert record.error_type == "LLMInvocationError"

        run = (await session.execute(select(PipelineRunModel))).scalars().one()
        assert run.status == "failed"


class TestDeduplication:
    async def test_existing_content_hashes_returns_stored_hashes(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        hashes = await service.existing_content_hashes(TENANT)
        assert stored_record.content_hash in hashes

    async def test_hashes_are_tenant_scoped(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        service, _ = build_service(session, prompts, make_proposal())
        assert await service.existing_content_hashes("other_tenant") == set()
