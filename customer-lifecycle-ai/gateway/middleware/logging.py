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
        [timestamp] METHOD /path → STATUS  duration_ms  (user/service, ip)
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

    logger.info(
        "%s %s → %d  %.0fms  (%s, %s)",
        request.method,
        request.url.path,
        status,
        duration_ms,
        caller,
        ip,
    )

    return response
