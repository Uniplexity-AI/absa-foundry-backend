"""
Gateway Dependencies — FastAPI dependency injection for auth and RBAC.

Provides reusable Depends() callables for route handlers:
- get_current_user: Requires valid JWT
- require_auth: Requires JWT + RBAC check
- require_role(role): Requires specific role
- get_current_service: Requires valid API key
"""

from __future__ import annotations

from fastapi import Request, HTTPException, status, Depends

from shared.auth.models import UserContext, ServiceContext
from gateway.middleware.auth import auth_middleware
from gateway.middleware.rbac import rbac_middleware
from gateway.middleware.api_key import api_key_middleware


async def get_current_user(request: Request) -> UserContext:
    """FastAPI dependency: require a valid JWT."""
    user = await auth_middleware(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


async def get_current_service(request: Request) -> ServiceContext:
    """FastAPI dependency: require a valid API key.

    Usage:
        @router.post("/internal/predict")
        async def predict(service: ServiceContext = Depends(get_current_service)):
            ...
    """
    service = await api_key_middleware(request)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid API key required for this endpoint",
        )
    return service


async def require_auth(request: Request) -> UserContext:
    """FastAPI dependency: require JWT + RBAC check."""
    user = await auth_middleware(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    await rbac_middleware(request)
    return user


def require_role(role: str):
    """Factory: create a dependency that requires a specific role."""
    async def _check(request: Request) -> UserContext:
        user = await auth_middleware(request)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        if role not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )
        return user
    return _check
