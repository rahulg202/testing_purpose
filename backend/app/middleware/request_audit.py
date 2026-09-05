"""Request audit middleware — logs every request with structured context.

Attaches trace_id, request_id, tenant_id to every log line for the
duration of the request via structlog contextvars.
"""

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestAuditMiddleware(BaseHTTPMiddleware):
    """Middleware that adds structured context to every request and logs it."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
        tenant_id = request.headers.get("x-tenant-id", "default")

        # Bind context for all log calls during this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            trace_id=trace_id,
            tenant_id=tenant_id,
            method=request.method,
            path=request.url.path,
        )

        logger = structlog.get_logger("request_audit")
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "request_completed",
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

            # Add trace headers to response
            response.headers["x-request-id"] = request_id
            response.headers["x-trace-id"] = trace_id

            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                error=str(exc),
                error_type=type(exc).__name__,
                duration_ms=round(duration_ms, 2),
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()
