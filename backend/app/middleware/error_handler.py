"""Global error handling — fail loud, never silent (Principle 3)."""

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = structlog.get_logger("error_handler")


class ErrorDetail:
    """Structured error response."""

    def __init__(self, status_code: int, error_type: str, message: str, detail: str | None = None):
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        self.detail = detail

    def to_response(self) -> JSONResponse:
        body = {
            "error": {
                "type": self.error_type,
                "message": self.message,
            }
        }
        if self.detail:
            body["error"]["detail"] = self.detail
        return JSONResponse(status_code=self.status_code, content=body)


class GlobalErrorMiddleware(BaseHTTPMiddleware):
    """Catches unhandled exceptions and returns structured error responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            logger.exception(
                "unhandled_exception",
                error_type=type(exc).__name__,
                path=request.url.path,
            )
            error = ErrorDetail(
                status_code=500,
                error_type="internal_error",
                message="An unexpected error occurred. The error has been logged.",
            )
            return error.to_response()
