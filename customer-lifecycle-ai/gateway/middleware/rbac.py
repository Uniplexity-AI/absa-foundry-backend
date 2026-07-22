"""
Gateway RBAC Middleware — role-based access control enforcement.

After JWT validation, this middleware checks if the authenticated user's
roles include the required roles for the requested route.
"""

from __future__ import annotations

import logging

from fastapi import Request, HTTPException, status

from shared.auth.models import UserContext
from shared.auth.permissions import has_permission, get_required_roles

logger = logging.getLogger("gateway.rbac")

# Routes that skip RBAC (public endpoints)
SKIP_RBAC: set[tuple[str, str]] = {
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/logout"),
    ("GET",  "/auth/me"),
    ("GET",  "/health"),
}


class RBACMiddleware:
    """Validates that the current user has permission to access the route."""

    async def __call__(self, request: Request) -> None:
        """Check RBAC permissions.

        Args:
            request: FastAPI request with request.state.user already set by JWTAuthMiddleware.

        Raises:
            HTTPException 403: User lacks required roles.
        """
        route_key = (request.method.upper(), request.url.path)

        # Skip RBAC for public auth routes
        if route_key in SKIP_RBAC:
            return

        # Also skip for docs
        if request.url.path.startswith("/docs") or request.url.path.startswith("/openapi"):
            return

        user: UserContext | None = getattr(request.state, "user", None)
        if user is None:
            # No user context — let JWTAuthMiddleware handle the 401
            return

        if not has_permission(user.roles, request.method, request.url.path):
            required = get_required_roles(request.method, request.url.path)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "Insufficient permissions",
                    "required_roles": required,
                    "user_roles": user.roles,
                },
            )


# Singleton
rbac_middleware = RBACMiddleware()
