"""
Gateway Auth Middleware — JWT validation and user context injection.

Every request (except public routes) must carry a valid JWT in the
Authorization header. The middleware decodes it, checks the blacklist,
and injects a UserContext into request.state for downstream handlers.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError, ExpiredSignatureError

from shared.auth.models import UserContext
from shared.auth.token_service import TokenService

logger = logging.getLogger("gateway.auth")

# Public routes that don't require authentication
PUBLIC_ROUTES: set[tuple[str, str]] = {
    ("POST", "/auth/login"),
    ("POST", "/auth/refresh"),  # self-authenticates via refresh token in body
    ("GET",  "/health"),
    ("GET",  "/docs"),
    ("GET",  "/openapi.json"),
    ("GET",  "/redoc"),
}

security = HTTPBearer(auto_error=False)


class JWTAuthMiddleware:
    """FastAPI middleware that validates JWT and injects UserContext."""

    def __init__(self, redis_client=None) -> None:  # noqa: ANN001 - legacy arg, ignored
        """Initialize middleware.

        Args:
            redis_client: Deprecated legacy argument. Redis is not used in the
                          pilot/local deployment; revocation is in-process.
        """
        self._redis = None
        self._token_service = TokenService()

    async def __call__(self, request: Request) -> UserContext | None:
        """Validate JWT and return UserContext, or None for public routes.

        Called at the start of each request via FastAPI dependency.

        Args:
            request: The incoming FastAPI request.

        Returns:
            UserContext if authenticated, None for public routes.

        Raises:
            HTTPException 401: Missing or invalid token.
            HTTPException 403: Token is blacklisted (logged out).
        """
        # Allow public routes + CORS preflight
        if request.method == "OPTIONS":
            return None
        route_key = (request.method.upper(), request.url.path)
        if route_key in PUBLIC_ROUTES or request.url.path.startswith("/docs") or request.url.path.startswith("/openapi"):
            return None

        # Extract token
        credentials: HTTPAuthorizationCredentials | None = await security(request)
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.credentials
        ts = self._token_service

        # Decode and verify
        try:
            payload = ts.decode_access_token(token)
        except ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Blacklist check
        jti = payload.get("jti")
        if jti and await ts.is_blacklisted(jti):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token has been revoked",
            )

        # Build user context
        user = UserContext(
            user_id=UUID(payload["sub"]),
            username=payload["username"],
            display_name=payload.get("display_name", ""),
            email=payload.get("email", ""),
            roles=payload.get("roles", []),
            branch_code=payload.get("branch_code"),
        )

        # Inject into request state for downstream handlers
        request.state.user = user

        return user


# Singleton — pilot/local runs without Redis (revocation is in-process).
auth_middleware = JWTAuthMiddleware()


async def get_current_user(request: Request) -> UserContext:
    """FastAPI dependency: require a valid JWT and return the current user."""
    return await auth_middleware(request)
