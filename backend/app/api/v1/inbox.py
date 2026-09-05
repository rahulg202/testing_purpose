"""Inbox endpoints — the triage work queue.

GET /v1/inbox        — prioritised list of source records
GET /v1/inbox/stats  — counts by status and ICSR outcome
GET /v1/inbox/{id}   — full detail including raw source text and rule trace
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_session
from ...services.inbox_service import InboxService

router = APIRouter(prefix="/inbox", tags=["inbox"])


@router.get("")
async def list_inbox(
    status: str | None = Query(default=None, description="Filter by source status"),
    outcome: str | None = Query(default=None, description="Filter by ICSR outcome"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """List triage inbox items, highest priority first."""
    service = InboxService(session)
    return await service.list_items(
        tenant_id=x_tenant_id,
        status=status,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )


@router.get("/stats")
async def inbox_stats(
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Aggregate counts for the dashboard."""
    service = InboxService(session)
    return await service.stats(tenant_id=x_tenant_id)


@router.get("/{source_record_id}")
async def get_inbox_item(
    source_record_id: str,
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Full detail for a single inbox item."""
    service = InboxService(session)
    detail = await service.get_item(tenant_id=x_tenant_id, source_record_id=source_record_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Source record {source_record_id} not found")
    return detail
