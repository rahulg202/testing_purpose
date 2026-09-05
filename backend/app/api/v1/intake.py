"""Intake endpoints — where source records enter the platform.

POST /v1/intake/web-form          — submit a direct adverse-event report
POST /v1/intake/literature/pubmed — run a PubMed literature sweep

Both persist SourceRecords and, unless ``triage=false``, immediately run triage
so the caller gets the ICSR decision in one round trip. That keeps the demo
path short: submit a report, see the determination.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...connectors.pubmed import PubMedConnector
from ...connectors.web_form import WebFormSubmission, ingest_web_form
from ...core.config import get_settings
from ...core.database import get_session
from ...core.evidence import get_evidence_store
from ...core.llm import get_llm_provider, get_prompt_registry
from ...services.triage_service import TriageError, TriageService

logger = structlog.get_logger("api.intake")

router = APIRouter(prefix="/intake", tags=["intake"])


def _build_triage_service(session: AsyncSession) -> TriageService:
    settings = get_settings()
    return TriageService(
        session,
        provider=get_llm_provider(),
        prompts=get_prompt_registry(),
        evidence_store=get_evidence_store(),
        max_tokens=settings.llm_max_tokens,
    )


class WebFormRequest(BaseModel):
    """Public adverse-event report form.

    Only the narrative is required — incomplete reports are precisely what the
    validity rule exists to classify, so they must be accepted.
    """

    narrative: str = Field(min_length=1, description="Free-text description of what happened")
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
    triage: bool = Field(default=True, description="Run triage immediately")


class PubMedSweepRequest(BaseModel):
    """A literature monitoring sweep."""

    query: str = Field(min_length=1, description="PubMed search expression")
    max_results: int = Field(default=5, ge=1, le=25)
    triage: bool = Field(default=True, description="Triage each new record immediately")


@router.post("/web-form", status_code=201)
async def submit_web_form(
    body: WebFormRequest,
    x_tenant_id: str = Header(default="default"),
    x_actor_id: str = Header(default="web_form"),
    x_trace_id: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Accept a direct report, store it, and triage it."""
    submission = WebFormSubmission(**body.model_dump(exclude={"triage"}))
    record = ingest_web_form(
        tenant_id=x_tenant_id,
        submission=submission,
        trace_id=x_trace_id or None,
    )

    service = _build_triage_service(session)
    await service.persist_source_record(record)

    response: dict[str, Any] = {
        "source_record_id": record.source_record_id,
        "channel": record.channel.value,
        "content_hash": record.content_hash,
        "awareness_datetime": record.awareness_datetime.isoformat(),
        "status": record.status.value,
    }

    if body.triage:
        try:
            outcome = await service.triage(
                tenant_id=x_tenant_id,
                source_record_id=record.source_record_id,
                actor_id=x_actor_id,
                trace_id=x_trace_id or None,
            )
        except TriageError as exc:
            await session.commit()  # keep the record + the failure state
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        response.update(outcome.to_dict())

    await session.commit()
    return response


@router.post("/literature/pubmed", status_code=201)
async def sweep_pubmed(
    body: PubMedSweepRequest,
    x_tenant_id: str = Header(default="default"),
    x_actor_id: str = Header(default="pipeline_literature"),
    x_trace_id: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Search PubMed, ingest new articles, and triage them."""
    settings = get_settings()
    connector = PubMedConnector(
        api_key=settings.ncbi_api_key,
        tool_email=settings.ncbi_tool_email,
    )
    service = _build_triage_service(session)

    known = await service.existing_content_hashes(x_tenant_id)
    try:
        sweep = connector.sweep(
            tenant_id=x_tenant_id,
            query=body.query,
            max_results=body.max_results,
            trace_id=x_trace_id or None,
            known_content_hashes=known,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    for record in sweep.records:
        await service.persist_source_record(record)

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []

    if body.triage:
        for record in sweep.records:
            try:
                outcome = await service.triage(
                    tenant_id=x_tenant_id,
                    source_record_id=record.source_record_id,
                    actor_id=x_actor_id,
                    trace_id=x_trace_id or None,
                )
                results.append(outcome.to_dict())
            except TriageError as exc:
                # One bad article must not abort the sweep; record and continue.
                failures.append({"source_record_id": record.source_record_id, "error": str(exc)})
    else:
        results = [
            {"source_record_id": record.source_record_id, "status": record.status.value}
            for record in sweep.records
        ]

    await session.commit()

    return {
        "query": body.query,
        "summary": sweep.summary,
        "ingested": len(sweep.records),
        "duplicates_skipped": sweep.duplicates_skipped,
        "triaged": len(results),
        "failures": failures,
        "results": results,
    }
