"""Case API endpoints — CRUD for canonical ICSR cases.

GET /v1/cases — list cases for the tenant
POST /v1/cases — create a new case
GET /v1/cases/{case_id} — get the latest version
GET /v1/cases/{case_id}/versions/{version} — get a specific version
PATCH /v1/cases/{case_id} — update fields (creates new version)
POST /v1/cases/{case_id}/approve — approve and sign
GET /v1/cases/{case_id}/audit — get the audit trail
"""

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_session
from ...services.audit_service import AuditService
from ...services.case_service import CaseService

router = APIRouter(prefix="/cases", tags=["cases"])


class CreateCaseRequest(BaseModel):
    """Request body for creating a new case."""

    case_number: str | None = None
    report_type: dict[str, Any] | None = None
    patient: dict[str, Any] | None = None
    drugs: list[dict[str, Any]] = []
    reactions: list[dict[str, Any]] = []
    reporters: list[dict[str, Any]] = []
    source_records: list[str] = []
    narrative: dict[str, Any] | None = None


class UpdateCaseRequest(BaseModel):
    """Request body for updating case fields."""

    updates: dict[str, Any]
    reason_code: str | None = None


class ApproveCaseRequest(BaseModel):
    """Request body for case approval."""

    meaning: str = "Approval of case data"


@router.get("")
async def list_cases(
    limit: int = 50,
    offset: int = 0,
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List cases for the current tenant."""
    service = CaseService(session)
    return await service.list_cases(x_tenant_id, limit=limit, offset=offset)


@router.post("", status_code=201)
async def create_case(
    body: CreateCaseRequest,
    x_tenant_id: str = Header(default="default"),
    x_actor_id: str = Header(default="system"),
    x_trace_id: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Create a new case."""
    service = CaseService(session)
    case_data = body.model_dump(exclude_none=True)
    result = await service.create_case(
        tenant_id=x_tenant_id,
        case_data=case_data,
        created_by=x_actor_id,
        case_number=body.case_number,
        trace_id=x_trace_id or None,
    )
    await session.commit()
    return result


@router.get("/{case_id}")
async def get_case(
    case_id: str,
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get the latest version of a case."""
    service = CaseService(session)
    result = await service.get_case(x_tenant_id, case_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return result


@router.get("/{case_id}/versions/{version}")
async def get_case_version(
    case_id: str,
    version: int,
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Get a specific version of a case."""
    service = CaseService(session)
    result = await service.get_case_version(x_tenant_id, case_id, version)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"Case {case_id} version {version} not found",
        )
    return result


@router.patch("/{case_id}")
async def update_case(
    case_id: str,
    body: UpdateCaseRequest,
    x_tenant_id: str = Header(default="default"),
    x_actor_id: str = Header(default="system"),
    x_trace_id: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Update case fields — creates a new version."""
    service = CaseService(session)
    try:
        result = await service.update_case(
            tenant_id=x_tenant_id,
            case_id=case_id,
            updates=body.updates,
            actor_id=x_actor_id,
            reason_code=body.reason_code,
            trace_id=x_trace_id or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e

    if not result:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    await session.commit()
    return result


@router.post("/{case_id}/approve")
async def approve_case(
    case_id: str,
    body: ApproveCaseRequest,
    x_tenant_id: str = Header(default="default"),
    x_actor_id: str = Header(default="system"),
    x_trace_id: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Approve a case — records electronic signature."""
    service = CaseService(session)
    result = await service.approve_case(
        tenant_id=x_tenant_id,
        case_id=case_id,
        actor_id=x_actor_id,
        meaning=body.meaning,
        trace_id=x_trace_id or None,
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    await session.commit()
    return {"status": "approved", "case_id": case_id}


@router.get("/{case_id}/audit")
async def get_case_audit_trail(
    case_id: str,
    limit: int = 100,
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Get the audit trail for a case."""
    audit_service = AuditService(session)
    events = await audit_service.get_case_audit_trail(x_tenant_id, case_id, limit=limit)
    return [
        {
            "event_id": e.event_id,
            "event_type": e.event_type,
            "field_path": e.field_path,
            "old_value": e.old_value,
            "new_value": e.new_value,
            "actor_type": e.actor_type,
            "actor_id": e.actor_id,
            "model_id": e.model_id,
            "prompt_version": e.prompt_version,
            "rule_id": e.rule_id,
            "reason_code": e.reason_code,
            "timestamp": e.timestamp.isoformat(),
            "content_hash": e.content_hash,
            "previous_hash": e.previous_hash,
        }
        for e in events
    ]
