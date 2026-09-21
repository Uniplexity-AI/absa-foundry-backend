"""
Gateway Request Logging Middleware — structured HTTP request/response logging.

Logs every incoming request with method, path, status, duration, client IP,
and authenticated user/service context.
"""

from __future__ import annotations

import logging
import time

from fastapi import Request, Response

logger = logging.getLogger("gateway.http")


async def request_logging_middleware(request: Request, call_next):
    """ASGI middleware: log every request with timing and context.

    Output format:
        [timestamp] METHOD /path -> STATUS  duration_ms  (user/service, ip)

    The format string is deliberately ASCII: the Windows console runs cp1252,
    so a non-ASCII arrow in the log message raises UnicodeEncodeError and turns
    every request into a 500. Logging is also wrapped, because a logging failure
    must never take down a response that was produced successfully.
    """
    t_start = time.monotonic()

    # Resolve caller identity
    caller = "-"
    user = getattr(request.state, "user", None)
    service = getattr(request.state, "service", None)
    if user:
        caller = f"u:{user.username}"
    elif service:
        caller = f"s:{service.service_name}"

    ip = request.client.host if request.client else "-"

    # Process request
    response: Response = await call_next(request)

    duration_ms = (time.monotonic() - t_start) * 1000
    status = response.status_code if hasattr(response, "status_code") else 0

    try:
        logger.info(
            "%s %s -> %d  %.0fms  (%s, %s)",
            request.method,
            request.url.path,
            status,
            duration_ms,
            caller,
            ip,
        )
    except Exception:  # noqa: BLE001 - never fail a served request over a log line
        logger.debug("Request logging failed", exc_info=True)

    return response
