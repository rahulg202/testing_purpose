"""Tests for the inbox read model, including deterministic rule replay."""

from __future__ import annotations

from atheria_llm import PromptRegistry
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.case import SourceRecordModel
from backend.app.services.inbox_service import InboxService
from backend.app.services.triage_service import TriageService

from .conftest import StubProvider, make_proposal

TENANT = "acme_pharma"


async def _triage(
    session: AsyncSession, prompts: PromptRegistry, record: SourceRecordModel, **kwargs: bool
) -> None:
    service = TriageService(
        session,
        provider=StubProvider(make_proposal(**kwargs)),  # type: ignore[arg-type]
        prompts=prompts,
        evidence_store=None,
    )
    await service.triage(tenant_id=TENANT, source_record_id=record.source_record_id)


class TestRuleReplay:
    """The inbox recomputes the trace instead of caching it.

    Because the rule is a pure function this must reproduce the original
    decision exactly, with no model call.
    """

    async def test_replayed_trace_matches_the_original_decision(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        await _triage(session, prompts, stored_record)

        detail = await InboxService(session).get_item(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert detail is not None
        trace = detail["rule_trace"]
        assert trace is not None
        assert trace["rule_id"] == "val_001"
        assert trace["rule_set_version"] == "1.0.0"
        assert trace["outcome"] == "valid_icsr"
        assert trace["fired_rules"] == ["val_001_all_criteria_present"]
        # The trace must agree with the persisted outcome.
        assert trace["outcome"] == detail["icsr_outcome"]

    async def test_replay_reproduces_escalation_and_its_reasoning(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        await _triage(session, prompts, stored_record, patient=False, reporter=False)

        detail = await InboxService(session).get_item(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert detail is not None
        trace = detail["rule_trace"]
        assert trace["outcome"] == "potential_icsr"
        assert "do not guess" in trace["explanation"]
        assert trace["input_provenance"]["identifiable_patient"].startswith("ABSENT")

    async def test_replay_is_stable_across_repeated_reads(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        await _triage(session, prompts, stored_record)
        service = InboxService(session)

        first = await service.get_item(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        second = await service.get_item(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert first is not None and second is not None
        assert first["rule_trace"] == second["rule_trace"]

    async def test_untriaged_record_has_no_trace(
        self, session: AsyncSession, stored_record: SourceRecordModel
    ) -> None:
        detail = await InboxService(session).get_item(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert detail is not None
        assert detail["rule_trace"] is None


class TestInboxQueries:
    async def test_detail_includes_source_text_for_evidence_highlighting(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        await _triage(session, prompts, stored_record)
        detail = await InboxService(session).get_item(
            tenant_id=TENANT, source_record_id=stored_record.source_record_id
        )
        assert detail is not None
        assert detail["raw_text"] == stored_record.raw_text

    async def test_list_reports_criteria_counts(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        await _triage(session, prompts, stored_record, patient=False)
        rows = await InboxService(session).list_items(tenant_id=TENANT)
        assert len(rows) == 1
        assert rows[0]["criteria_met_count"] == 3
        assert rows[0]["criteria_present"]["identifiable_patient"] is False

    async def test_stats_group_by_outcome(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        await _triage(session, prompts, stored_record)
        stats = await InboxService(session).stats(tenant_id=TENANT)
        assert stats["total"] == 1
        assert stats["by_outcome"]["valid_icsr"] == 1
        assert stats["awaiting_review"] == 0

    async def test_tenant_isolation_on_detail_read(
        self, session: AsyncSession, prompts: PromptRegistry, stored_record: SourceRecordModel
    ) -> None:
        await _triage(session, prompts, stored_record)
        detail = await InboxService(session).get_item(
            tenant_id="other_tenant", source_record_id=stored_record.source_record_id
        )
        assert detail is None
