"""Case Service — CRUD + versioning for the canonical ICSR.

The Case Service is the authority for case state within Atheria.
It enforces versioning (immutable snapshots), audit recording,
and content hashing for signature integrity.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ulid import ULID

from ..models.case import CaseModel, CaseVersionModel
from .audit_service import AuditService

logger = structlog.get_logger("case_service")


class CaseService:
    """Service for managing canonical ICSR cases."""

    def __init__(self, session: AsyncSession):
        self._session = session
        self._audit = AuditService(session)

    @staticmethod
    def _compute_content_hash(data: dict[str, Any]) -> str:
        """SHA-256 of the case version data — used for signature binding."""
        content = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()

    async def create_case(
        self,
        *,
        tenant_id: str,
        case_data: dict[str, Any],
        created_by: str,
        case_number: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new case with its initial version."""
        case_id = str(ULID())
        version_id = str(ULID())
        now = datetime.now(UTC)

        if not case_number:
            # Generate a case number: ATH-{tenant prefix}-{sequential}
            case_number = f"ATH-{tenant_id[:4].upper()}-{str(ULID())[-6:]}"

        # Enrich the case data with identity fields
        case_data.update(
            {
                "case_id": case_id,
                "tenant_id": tenant_id,
                "case_number": case_number,
                "version": 1,
                "version_type": "initial",
                "lifecycle_state": "draft",
                "lock_state": "open",
                "created_at": now.isoformat(),
                "created_by": created_by,
            }
        )

        content_hash = self._compute_content_hash(case_data)

        # Create case header
        case = CaseModel(
            case_id=case_id,
            tenant_id=tenant_id,
            case_number=case_number,
            current_version=1,
            lifecycle_state="draft",
            lock_state="open",
            created_by=created_by,
        )
        self._session.add(case)

        # Create version 1
        version = CaseVersionModel(
            id=version_id,
            case_id=case_id,
            tenant_id=tenant_id,
            version=1,
            version_type="initial",
            data=case_data,
            content_hash=content_hash,
        )
        self._session.add(version)

        # Audit
        await self._audit.record_state_change(
            tenant_id=tenant_id,
            case_id=case_id,
            old_state="(new)",
            new_state="draft",
            actor_type="system",
            actor_id=created_by,
            trace_id=trace_id,
        )

        await self._session.flush()

        logger.info(
            "case_created",
            case_id=case_id,
            case_number=case_number,
            tenant_id=tenant_id,
            created_by=created_by,
        )

        return case_data

    async def get_case(self, tenant_id: str, case_id: str) -> dict[str, Any] | None:
        """Get the latest version of a case."""
        case = await self._session.get(CaseModel, case_id)
        if not case or case.tenant_id != tenant_id:
            return None

        # Get the latest version
        result = await self._session.execute(
            select(CaseVersionModel).where(
                CaseVersionModel.case_id == case_id,
                CaseVersionModel.version == case.current_version,
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            return None

        return version.data

    async def get_case_version(
        self, tenant_id: str, case_id: str, version: int
    ) -> dict[str, Any] | None:
        """Get a specific version of a case."""
        result = await self._session.execute(
            select(CaseVersionModel).where(
                CaseVersionModel.case_id == case_id,
                CaseVersionModel.tenant_id == tenant_id,
                CaseVersionModel.version == version,
            )
        )
        version_model = result.scalar_one_or_none()
        return version_model.data if version_model else None

    async def update_case(
        self,
        *,
        tenant_id: str,
        case_id: str,
        updates: dict[str, Any],
        actor_id: str,
        actor_type: str = "human",
        reason_code: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Update case fields and create a new version.

        This is a PATCH operation — only the provided fields are updated.
        A new immutable version is created with the delta applied.
        """
        case = await self._session.get(CaseModel, case_id)
        if not case or case.tenant_id != tenant_id:
            return None

        if case.lock_state != "open":
            raise ValueError(f"Case {case_id} is locked ({case.lock_state}), cannot update")

        # Get current version data
        current_data = await self.get_case(tenant_id, case_id)
        if not current_data:
            return None

        # Apply updates and record field changes
        new_data = {**current_data}
        for field_path, new_value in updates.items():
            old_value = new_data.get(field_path)
            new_data[field_path] = new_value

            # Record the field change in audit
            await self._audit.record_field_change(
                tenant_id=tenant_id,
                case_id=case_id,
                field_path=field_path,
                old_value=old_value,
                new_value=new_value,
                actor_type=actor_type,
                actor_id=actor_id,
                reason_code=reason_code,
                trace_id=trace_id,
            )

        # Create new version
        new_version_num = case.current_version + 1
        new_data["version"] = new_version_num
        content_hash = self._compute_content_hash(new_data)

        version = CaseVersionModel(
            id=str(ULID()),
            case_id=case_id,
            tenant_id=tenant_id,
            version=new_version_num,
            version_type="follow_up",
            supersedes_version=case.current_version,
            data=new_data,
            content_hash=content_hash,
        )
        self._session.add(version)

        # Update case header
        case.current_version = new_version_num
        if "lifecycle_state" in updates:
            old_state = case.lifecycle_state
            case.lifecycle_state = updates["lifecycle_state"]
            await self._audit.record_state_change(
                tenant_id=tenant_id,
                case_id=case_id,
                old_state=old_state,
                new_state=updates["lifecycle_state"],
                actor_type=actor_type,
                actor_id=actor_id,
                reason_code=reason_code,
                trace_id=trace_id,
            )

        await self._session.flush()

        logger.info(
            "case_updated",
            case_id=case_id,
            version=new_version_num,
            fields_changed=list(updates.keys()),
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

        return new_data

    async def list_cases(
        self, tenant_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List cases for a tenant."""
        result = await self._session.execute(
            select(CaseModel)
            .where(CaseModel.tenant_id == tenant_id)
            .order_by(CaseModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        cases = result.scalars().all()

        # For list view, return summaries from the header
        return [
            {
                "case_id": c.case_id,
                "case_number": c.case_number,
                "lifecycle_state": c.lifecycle_state,
                "lock_state": c.lock_state,
                "current_version": c.current_version,
                "created_by": c.created_by,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "approved_at": c.approved_at.isoformat() if c.approved_at else None,
            }
            for c in cases
        ]

    async def approve_case(
        self,
        *,
        tenant_id: str,
        case_id: str,
        actor_id: str,
        meaning: str = "Approval of case data",
        trace_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Approve a case — records the electronic signature."""
        case = await self._session.get(CaseModel, case_id)
        if not case or case.tenant_id != tenant_id:
            return None

        # Get current version for content hash
        result = await self._session.execute(
            select(CaseVersionModel).where(
                CaseVersionModel.case_id == case_id,
                CaseVersionModel.version == case.current_version,
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            return None

        now = datetime.now(UTC)
        case.approved_at = now
        case.approved_by = actor_id
        case.lifecycle_state = "approved"
        case.lock_state = "locked_for_review"

        # Record approval in audit
        await self._audit.record_approval(
            tenant_id=tenant_id,
            case_id=case_id,
            actor_id=actor_id,
            content_hash=version.content_hash,
            meaning=meaning,
            trace_id=trace_id,
        )

        await self._session.flush()

        logger.info(
            "case_approved",
            case_id=case_id,
            actor_id=actor_id,
            content_hash=version.content_hash,
            tenant_id=tenant_id,
        )

        return version.data
