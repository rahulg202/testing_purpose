"""Inbox service — the triage work queue.

The inbox is what a safety officer actually looks at: source records ordered so
the ones needing attention come first. Ordering is by priority score then
recency, and escalated (``potential_icsr``) records are the ones carrying real
work.
"""

from __future__ import annotations

from typing import Any

import structlog
from atheria_contracts.enums import SourceStatus
from atheria_contracts.source_record import ICSRElements
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.case import SourceRecordModel
from ..rules.validity import evaluate_validity

logger = structlog.get_logger("inbox_service")

_SNIPPET_CHARS = 240


def _replay_rule_trace(triage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Re-evaluate the validity rule from stored criteria.

    Deterministic replay: the rule is a pure function, so this reproduces the
    original decision exactly without re-invoking the model. Returns None when
    the record has not been triaged yet.
    """
    if not triage:
        return None
    raw_elements = triage.get("icsr_elements")
    if not raw_elements:
        return None

    try:
        elements = ICSRElements.model_validate(raw_elements)
    except ValidationError:
        logger.warning("rule_replay_failed_invalid_elements")
        return None

    return evaluate_validity(elements).trace.model_dump(mode="json")


def _summarise(record: SourceRecordModel) -> dict[str, Any]:
    """Flatten a source record + triage result into an inbox row."""
    triage = record.triage_result or {}
    elements = triage.get("icsr_elements") or {}

    present = {
        name: bool((elements.get(name) or {}).get("present"))
        for name in (
            "identifiable_patient",
            "identifiable_reporter",
            "suspect_product",
            "adverse_event",
        )
    }

    return {
        "source_record_id": record.source_record_id,
        "channel": record.channel,
        "channel_class": record.channel_class,
        "external_id": record.external_id,
        "external_url": record.external_url,
        "status": record.status,
        "awareness_datetime": record.awareness_datetime.isoformat()
        if record.awareness_datetime
        else None,
        "content_hash": record.content_hash,
        "snippet": (record.raw_text or "")[:_SNIPPET_CHARS],
        "icsr_outcome": triage.get("icsr_outcome"),
        "outcome_rule_id": triage.get("outcome_rule_id"),
        "outcome_rule_version": triage.get("outcome_rule_version"),
        "priority_score": triage.get("priority_score", 0.0),
        "seriousness_signal": triage.get("seriousness_signal", False),
        "content_types": triage.get("content_types") or [],
        "patient_count": triage.get("patient_count"),
        "rationale": triage.get("rationale"),
        "model_id": triage.get("model_id"),
        "prompt_version": triage.get("prompt_version"),
        "criteria_present": present,
        "criteria_met_count": sum(1 for value in present.values() if value),
        "is_noise": triage.get("is_noise", False),
        "error_type": record.error_type,
        "error_message": record.error_message,
    }


class InboxService:
    """Read-side queries for the triage inbox."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_items(
        self,
        *,
        tenant_id: str,
        status: str | None = None,
        outcome: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List inbox items, highest priority first."""
        query = select(SourceRecordModel).where(SourceRecordModel.tenant_id == tenant_id)
        if status:
            query = query.where(SourceRecordModel.status == status)

        query = query.order_by(SourceRecordModel.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(query)
        rows = [_summarise(record) for record in result.scalars().all()]

        if outcome:
            rows = [row for row in rows if row["icsr_outcome"] == outcome]

        # Priority first, then most recently received.
        rows.sort(
            key=lambda row: (row.get("priority_score") or 0.0, row.get("awareness_datetime") or ""),
            reverse=True,
        )
        return rows

    async def get_item(self, *, tenant_id: str, source_record_id: str) -> dict[str, Any] | None:
        """Full detail for one inbox item, including the raw source text.

        The rule trace is *recomputed* from the stored criteria rather than
        cached. Because ``val_001`` is a pure function of those four facts,
        replaying it is free, needs no model call, and is guaranteed to
        reproduce the original decision — which is the whole point of keeping
        regulatory determinations in deterministic rules.
        """
        record = await self._session.get(SourceRecordModel, source_record_id)
        if not record or record.tenant_id != tenant_id:
            return None

        detail = _summarise(record)
        detail["raw_text"] = record.raw_text
        detail["raw_language"] = record.raw_language
        detail["triage"] = record.triage_result
        detail["evidence_ref"] = record.manifest_ref
        detail["retrieved_at"] = record.retrieved_at.isoformat() if record.retrieved_at else None
        detail["rule_trace"] = _replay_rule_trace(record.triage_result)
        return detail

    async def stats(self, *, tenant_id: str) -> dict[str, Any]:
        """Counts for the dashboard: totals by status and by ICSR outcome."""
        status_rows = await self._session.execute(
            select(SourceRecordModel.status, func.count())
            .where(SourceRecordModel.tenant_id == tenant_id)
            .group_by(SourceRecordModel.status)
        )
        by_status = {status: count for status, count in status_rows.all()}

        # Outcome lives inside the triage JSON, so aggregate in Python. Fine at
        # prototype volumes; would become a generated column in production.
        outcome_rows = await self._session.execute(
            select(SourceRecordModel.triage_result).where(
                SourceRecordModel.tenant_id == tenant_id,
                SourceRecordModel.triage_result.is_not(None),
            )
        )
        by_outcome: dict[str, int] = {}
        awaiting_review = 0
        for (triage,) in outcome_rows.all():
            if not triage:
                continue
            outcome = triage.get("icsr_outcome") or "unknown"
            by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
            if outcome == "potential_icsr":
                awaiting_review += 1

        return {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "by_outcome": by_outcome,
            "awaiting_review": awaiting_review,
            "untriaged": by_status.get(SourceStatus.RECEIVED.value, 0),
        }
