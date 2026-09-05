"""Atheria API — FastAPI application entry point.

Walking skeleton: health endpoint, structured logging, request audit.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.cases import router as cases_router
from .api.v1.fixtures import router as fixtures_router
from .api.v1.health import router as health_router
from .api.v1.inbox import router as inbox_router
from .api.v1.intake import router as intake_router
from .api.v1.triage import router as triage_router
from .core.config import get_settings
from .core.logging import get_logger, setup_logging
from .middleware.error_handler import GlobalErrorMiddleware
from .middleware.request_audit import RequestAuditMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — setup and teardown."""
    setup_logging()
    logger = get_logger("atheria")
    settings = get_settings()

    # Load versioned prompts at startup so a malformed prompt fails fast and
    # loudly here rather than mid-request.
    from .core.llm import get_prompt_registry

    registry = get_prompt_registry()

    logger.info(
        "application_starting",
        version=settings.app_version,
        environment=settings.environment,
        llm_provider=settings.llm_provider,
        model_id=(
            settings.bedrock_model_id
            if settings.llm_provider == "bedrock"
            else settings.gemini_model_id
        ),
        prompts_loaded=registry.loaded_prompts,
    )
    yield
    logger.info("application_shutting_down")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI-native pharmacovigilance intelligence platform",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Middleware (order matters — outermost first)
    app.add_middleware(GlobalErrorMiddleware)
    app.add_middleware(RequestAuditMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id", "x-trace-id"],
    )

    # Routers
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(intake_router, prefix="/api/v1")
    app.include_router(triage_router, prefix="/api/v1")
    app.include_router(inbox_router, prefix="/api/v1")
    app.include_router(cases_router, prefix="/api/v1")
    app.include_router(fixtures_router, prefix="/api/v1")

    return app


# Module-level app instance for uvicorn
app = create_app()
