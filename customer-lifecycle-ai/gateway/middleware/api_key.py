"""
Gateway API Key Middleware — service account authentication.

Validates X-API-Key headers for machine-to-machine calls. Injects
a ServiceContext into request.state for downstream handlers.

Used by: ETL engine, prediction service, feature engineering service,
and any internal API that needs programmatic access.
"""

from __future__ import annotations

import hashlib
import logging

from fastapi import Request, HTTPException, status

from shared.auth.models import ServiceContext

logger = logging.getLogger("gateway.api_key")

# Routes that accept API key auth (service-to-service)
API_KEY_ROUTES: set[tuple[str, str]] = {
    ("POST", "/internal/predict"),
    ("POST", "/internal/features"),
    ("POST", "/internal/etl-trigger"),
}

# Header name
API_KEY_HEADER = "X-API-Key"


class ApiKeyMiddleware:
    """Validates X-API-Key header and injects ServiceContext.

    Only activates for routes in API_KEY_ROUTES. For all other routes,
    this middleware passes through without modification.
    """

    async def __call__(self, request: Request) -> ServiceContext | None:
        """Validate API key if the route requires it.

        Args:
            request: Incoming FastAPI request.

        Returns:
            ServiceContext if authenticated, None for non-API-key routes.

        Raises:
            HTTPException 401: Missing or invalid API key.
            HTTPException 403: Key is expired or deactivated.
        """
        route_key = (request.method.upper(), request.url.path)

        # Only check API keys for designated service routes
        if route_key not in API_KEY_ROUTES:
            return None

        # Extract key
        api_key = request.headers.get(API_KEY_HEADER)
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header",
            )

        # Hash and validate against DB
        from shared.auth.user_repository import UserRepository
        repo = UserRepository()

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        service = repo.validate_api_key(key_hash)

        if service is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        ctx = ServiceContext(
            service_id=service["service_id"],
            service_name=service["service_name"],
            scopes=service["scopes"],
        )

        # Inject into request state
        request.state.service = ctx

        logger.info(
            "API key auth: service=%s scopes=%s",
            service["service_name"], service["scopes"],
        )

        return ctx


# Singleton
api_key_middleware = ApiKeyMiddleware()
