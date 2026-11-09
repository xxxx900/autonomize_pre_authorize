"""Per-request context: a request id for tracing, and one structured log line per call."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.ops.logs import log_event
from app.ops.timing import elapsed_ms

REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger("pa.api")


def route_template(request: Request) -> str:
    """The matched route's path template, never the URL, so no id leaks into logs."""
    route = request.scope.get("route")
    return route.path if route else "unmatched"


async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Give the request an id, return it in X-Request-ID, and log method, route, status, time."""
    request.state.request_id = uuid.uuid4().hex
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response
    finally:
        log_event(
            logger,
            event="request",
            request_id=request.state.request_id,
            method=request.method,
            route=route_template(request),
            status=status_code,
            duration_ms=elapsed_ms(started),
        )
