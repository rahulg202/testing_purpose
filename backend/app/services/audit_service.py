"""Audit service — append-only, hash-chained event recording.

The audit trail is what makes Atheria inspectable. Every AI decision,
every rule evaluation, every human action is an audit event.
Hash chaining provides tamper evidence.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from ..models.case import AuditEventModel

logger = structlog.get_logger("audit_service")

# Genesis hash — the first event in any tenant's chain
GENESIS_HASH = "0" * 64


class AuditService:
    """Service for recording and querying audit events."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _get_last_hash(self, tenant_id: str) -> str:
        """Get the hash of the most recent audit event for this tenant."""
        result = await self._session.execute(
            select(AuditEventModel.content_hash)
            .where(AuditEventModel.tenant_id == tenant_id)
            .order_by(AuditEventModel.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row or GENESIS_HASH

    def _compute_content_hash(self, event_data: dict[str, Any], previous_hash: str) -> str:
        """Compute SHA-256 hash of event content + previous hash."""
        # Include the previous hash in this event's hash for chain integrity
        content = json.dumps(event_data, sort_keys=True, default=str)
        hash_input = f"{previous_hash}:{content}"
        return hashlib.sha256(hash_input.encode()).hexdigest()

    async def record_field_change(
        self,
        *,
        tenant_id: str,
        case_id: str,
        field_path: str,
        old_value: Any,
        new_value: Any,
        actor_type: str,
        actor_id: str | None = None,
        model_id: str | None = None,
        prompt_version: str | None = None,
        rule_id: str | None = None,
        rule_set_version: str | None = None,
        reason_code: str | None = None,
        rationale: str | None = None,
        confidence: float | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> AuditEventModel:
        """Record a field-level change in the audit trail."""
        return await self._record_event(
            tenant_id=tenant_id,
            case_id=case_id,
            event_type="field_change",
            field_path=field_path,
            old_value=json.dumps(old_value, default=str) if old_value is not None else None,
            new_value=json.dumps(new_value, default=str) if new_value is not None else None,
            actor_type=actor_type,
            actor_id=actor_id,
            model_id=model_id,
            prompt_version=prompt_version,
            rule_id=rule_id,
            rule_set_version=rule_set_version,
            reason_code=reason_code,
            rationale=rationale,
            confidence=confidence,
            trace_id=trace_id,
            request_id=request_id,
        )

    async def record_state_change(
        self,
        *,
        tenant_id: str,
        case_id: str,
        old_state: str,
        new_state: str,
        actor_type: str,
        actor_id: str | None = None,
        reason_code: str | None = None,
        trace_id: str | None = None,
    ) -> AuditEventModel:
        """Record a case state transition."""
        return await self._record_event(
            tenant_id=tenant_id,
            case_id=case_id,
            event_type="state_change",
            field_path="lifecycle_state",
            old_value=old_state,
            new_value=new_state,
            actor_type=actor_type,
            actor_id=actor_id,
            reason_code=reason_code,
            trace_id=trace_id,
        )

    async def record_approval(
        self,
        *,
        tenant_id: str,
        case_id: str,
        actor_id: str,
        content_hash: str,
        meaning: str,
        trace_id: str | None = None,
    ) -> AuditEventModel:
        """Record an approval/signature event."""
        return await self._record_event(
            tenant_id=tenant_id,
            case_id=case_id,
            event_type="approval",
            new_value=json.dumps(
                {
                    "content_hash": content_hash,
                    "meaning": meaning,
                }
            ),
            actor_type="human",
            actor_id=actor_id,
            trace_id=trace_id,
        )

    async def record_ai_invocation(
        self,
        *,
        tenant_id: str,
        case_id: str | None = None,
        source_record_id: str | None = None,
        model_id: str,
        prompt_version: str,
        rationale: str | None = None,
        confidence: float | None = None,
        trace_id: str | None = None,
    ) -> AuditEventModel:
        """Record an AI model invocation."""
        return await self._record_event(
            tenant_id=tenant_id,
            case_id=case_id,
            source_record_id=source_record_id,
            event_type="ai_invocation",
            actor_type="ai",
            model_id=model_id,
            prompt_version=prompt_version,
            rationale=rationale,
            confidence=confidence,
            trace_id=trace_id,
        )

    async def record_rule_evaluation(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        rule_set_version: str,
        case_id: str | None = None,
        source_record_id: str | None = None,
        field_path: str | None = None,
        outcome: str | None = None,
        rationale: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> AuditEventModel:
        """Record a deterministic rule evaluation in the audit trail.

        This is the "rules decide" leg of the AI-proposes / rules-decide /
        human-approves model. It answers "which rule decided this, and what
        did it decide" for any inspector reading the chain.
        """
        return await self._record_event(
            tenant_id=tenant_id,
            case_id=case_id,
            source_record_id=source_record_id,
            event_type="rule_evaluation",
            field_path=field_path,
            new_value=json.dumps(outcome, default=str) if outcome is not None else None,
            actor_type="rule",
            rule_id=rule_id,
            rule_set_version=rule_set_version,
            rationale=rationale,
            trace_id=trace_id,
            request_id=request_id,
        )

    async def _record_event(
        self,
        *,
        tenant_id: str,
        event_type: str,
        actor_type: str,
        case_id: str | None = None,
        source_record_id: str | None = None,
        field_path: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        actor_id: str | None = None,
        model_id: str | None = None,
        prompt_version: str | None = None,
        rule_id: str | None = None,
        rule_set_version: str | None = None,
        reason_code: str | None = None,
        rationale: str | None = None,
        confidence: float | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
    ) -> AuditEventModel:
        """Internal method to create and persist an audit event."""
        now = datetime.now(UTC)
        event_id = str(ULID())

        # Get previous hash for chain integrity
        previous_hash = await self._get_last_hash(tenant_id)

        # Compute content hash
        event_data = {
            "event_id": event_id,
            "tenant_id": tenant_id,
            "case_id": case_id,
            "event_type": event_type,
            "field_path": field_path,
            "old_value": old_value,
            "new_value": new_value,
            "actor_type": actor_type,
            "actor_id": actor_id,
            "model_id": model_id,
            "timestamp": now.isoformat(),
        }
        content_hash = self._compute_content_hash(event_data, previous_hash)

        event = AuditEventModel(
            event_id=event_id,
            tenant_id=tenant_id,
            case_id=case_id,
            source_record_id=source_record_id,
            event_type=event_type,
            field_path=field_path,
            old_value=old_value,
            new_value=new_value,
            actor_type=actor_type,
            actor_id=actor_id,
            model_id=model_id,
            prompt_version=prompt_version,
            rule_id=rule_id,
            rule_set_version=rule_set_version,
            reason_code=reason_code,
            rationale=rationale,
            confidence=confidence,
            timestamp=now,
            content_hash=content_hash,
            previous_hash=previous_hash,
            trace_id=trace_id,
            request_id=request_id,
        )

        self._session.add(event)

        logger.info(
            "audit_event_recorded",
            event_id=event_id,
            event_type=event_type,
            case_id=case_id,
            actor_type=actor_type,
            tenant_id=tenant_id,
        )

        return event

    async def get_case_audit_trail(
        self, tenant_id: str, case_id: str, limit: int = 100
    ) -> list[AuditEventModel]:
        """Get the audit trail for a specific case."""
        result = await self._session.execute(
            select(AuditEventModel)
            .where(
                AuditEventModel.tenant_id == tenant_id,
                AuditEventModel.case_id == case_id,
            )
            .order_by(AuditEventModel.timestamp.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def verify_chain_integrity(self, tenant_id: str) -> bool:
        """Verify the hash chain integrity for a tenant's audit trail.

        Returns True if the chain is intact, False if tampered.
        """
        result = await self._session.execute(
            select(AuditEventModel)
            .where(AuditEventModel.tenant_id == tenant_id)
            .order_by(AuditEventModel.timestamp.asc())
        )
        events = list(result.scalars().all())

        if not events:
            return True

        expected_previous = GENESIS_HASH
        for event in events:
            if event.previous_hash != expected_previous:
                logger.error(
                    "audit_chain_broken",
                    event_id=event.event_id,
                    expected_previous=expected_previous,
                    actual_previous=event.previous_hash,
                    tenant_id=tenant_id,
                )
                return False
            expected_previous = event.content_hash

        return True
