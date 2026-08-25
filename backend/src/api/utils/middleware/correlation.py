"""Correlation ID middleware.

Her request'e `X-Correlation-Id` atar (Orion header'ı varsa korur),
log/metric/audit context'ine yayar. Hassas alanlar redakte edilir (Bölüm 17).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from ....observability.logging_config import (
    set_correlation_id,
)

_HEADER = "x-correlation-id"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Inbound correlation id propagation; log'a yayar."""

    dispatch_started: float | None = None

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        import logging
        import time

        from ....observability.events import log_event

        cid = request.headers.get(_HEADER) or uuid.uuid4().hex
        # Token claim / mail body / raw payload içermez; yalnızca identifier.
        request.state.correlation_id = cid
        set_correlation_id(cid)
        event_logger = logging.getLogger(__name__)
        started = time.monotonic()
        log_event(
            event_logger,
            "http.request.received",
            method=request.method,
            path=request.url.path,
            client=request.client.host if request.client else "-",
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log_event(
                event_logger,
                "http.request.failed",
                level=logging.ERROR,
                exc_type=type(exc).__name__,
                exc_msg=str(exc),
                method=request.method,
                path=request.url.path,
                elapsed_ms=elapsed_ms,
            )
            set_correlation_id(None)
            raise
        elapsed_ms = int((time.monotonic() - started) * 1000)
        log_event(
            event_logger,
            "http.request.completed",
            method=request.method,
            path=request.url.path,
            status=int(response.status_code),
            elapsed_ms=elapsed_ms,
        )
        set_correlation_id(None)
        response.headers[_HEADER] = cid
        return response
