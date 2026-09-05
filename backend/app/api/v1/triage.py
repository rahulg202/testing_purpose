"""Triage endpoints — run and inspect the ICSR identification decision.

POST /v1/triage/{source_record_id}      — run (or re-run) triage
GET  /v1/triage/{source_record_id}      — the stored triage result + rule trace
GET  /v1/triage/rules/validity          — the active rule set, for transparency
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.config import get_settings
from ...core.database import get_session
from ...core.evidence import get_evidence_store
from ...core.llm import get_llm_provider, get_prompt_registry
from ...rules import validity
from ...services.inbox_service import InboxService
from ...services.triage_service import TriageError, TriageService

router = APIRouter(prefix="/triage", tags=["triage"])


@router.get("/rules/validity")
async def get_validity_rule_set() -> dict[str, Any]:
    """Describe the active validity rule set.

    Exposed so a reviewer (or an inspector) can see exactly which rules are in
    force without reading the source code.
    """
    return {
        "rule_id": validity.RULE_ID,
        "rule_set_version": validity.RULE_SET_VERSION,
        "criteria": list(validity.CRITERIA),
        "core_criteria": list(validity.CORE_CRITERIA),
        "decision_table": [
            {
                "condition": "All four minimum criteria present",
                "outcome": "valid_icsr",
                "fired_rule": "val_001_all_criteria_present",
            },
            {
                "condition": "Suspect product or adverse event absent",
                "outcome": "non_icsr",
                "fired_rule": "val_001_missing_core_element",
            },
            {
                "condition": "Product and event present, patient or reporter absent",
                "outcome": "potential_icsr",
                "fired_rule": "val_001_incomplete_escalate",
            },
        ],
    }


@router.post("/{source_record_id}")
async def run_triage(
    source_record_id: str,
    x_tenant_id: str = Header(default="default"),
    x_actor_id: str = Header(default="pipeline_triage"),
    x_trace_id: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Run triage for a stored source record."""
    settings = get_settings()
    service = TriageService(
        session,
        provider=get_llm_provider(),
        prompts=get_prompt_registry(),
        evidence_store=get_evidence_store(),
        max_tokens=settings.llm_max_tokens,
    )
    try:
        outcome = await service.triage(
            tenant_id=x_tenant_id,
            source_record_id=source_record_id,
            actor_id=x_actor_id,
            trace_id=x_trace_id or None,
        )
    except TriageError as exc:
        await session.commit()  # persist the visible failure state
        message = str(exc)
        status = 404 if "not found" in message.lower() else 502
        raise HTTPException(status_code=status, detail=message) from exc

    await session.commit()
    return outcome.to_dict()


@router.get("/{source_record_id}")
async def get_triage_result(
    source_record_id: str,
    x_tenant_id: str = Header(default="default"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Fetch the stored triage result for a source record."""
    service = InboxService(session)
    detail = await service.get_item(tenant_id=x_tenant_id, source_record_id=source_record_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Source record {source_record_id} not found")
    return detail
