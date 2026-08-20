"""Request limits, correlation IDs, security headers, and access logs."""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

LOGGER = logging.getLogger("flooring_catalog.access")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class ProductionHttpMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_request_body_bytes: int,
        enable_hsts: bool,
    ) -> None:
        super().__init__(app)
        self._max_request_body_bytes = max_request_body_bytes
        self._enable_hsts = enable_hsts

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        supplied_request_id = request.headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if REQUEST_ID_PATTERN.fullmatch(supplied_request_id)
            else str(uuid4())
        )
        request.state.request_id = request_id
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                too_large = int(content_length) > self._max_request_body_bytes
            except ValueError:
                too_large = True
            if too_large:
                response = JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large"},
                )
                self._finish(response, request_id)
                return response

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            LOGGER.info(
                "request_completed",
                extra={
                    "event": "request_completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
        self._finish(response, request_id)
        return response

    def _finish(self, response: Response, request_id: str) -> None:
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if self._enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
