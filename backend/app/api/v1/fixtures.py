"""Fixture endpoints — serve golden case fixtures for development.

These endpoints allow the frontend workbench to work against realistic
case data before the pipeline is connected (Sprint 3+).
"""

import json
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/fixtures", tags=["fixtures"])

FIXTURES_DIR = Path(__file__).parent.parent.parent.parent.parent / "fixtures"


@router.get("/cases")
async def list_fixture_cases() -> list[dict[str, Any]]:
    """List available fixture cases."""
    cases = []
    for f in sorted(FIXTURES_DIR.glob("golden_case_*.json")):
        with open(f) as fp:
            data = json.load(fp)
        cases.append(
            {
                "case_id": data["case_id"],
                "case_number": data["case_number"],
                "lifecycle_state": data["lifecycle_state"],
                "version": data["version"],
                "file": f.name,
            }
        )
    return cases


@router.get("/cases/{case_id}")
async def get_fixture_case(case_id: str) -> dict[str, Any]:
    """Get a fixture case by ID — used by the workbench in dev mode."""
    for f in FIXTURES_DIR.glob("golden_case_*.json"):
        with open(f) as fp:
            data = json.load(fp)
        if data["case_id"] == case_id:
            return cast(dict[str, Any], data)

    raise HTTPException(status_code=404, detail=f"Fixture case {case_id} not found")
