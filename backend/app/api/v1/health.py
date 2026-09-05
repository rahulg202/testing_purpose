"""Health check endpoint — the first thing that works in the walking skeleton."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from ...core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Basic health check — returns service status and version."""
    settings = get_settings()
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/ready")
async def readiness_check() -> dict[str, Any]:
    """Readiness check — verifies dependencies are available.

    TODO: Add database and S3 connectivity checks.
    """
    return {
        "status": "ready",
        "checks": {
            "database": "not_configured",
            "s3": "not_configured",
            "bedrock": "not_configured",
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
