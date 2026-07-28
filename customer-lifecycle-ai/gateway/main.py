"""
API Gateway Entry Point — FastAPI application initialization.

Mounts all route modules and middleware:
- Auth: JWT validation + user context injection
- RBAC: Role-based access control enforcement
- CORS: Cross-origin request handling
- Rate Limiting: Per-IP request throttling
- Logging: Structured request/response logging
"""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gateway.routes import auth_routes, admin_routes, api_key_routes, etl_routes, feature_routes
from shared.config.settings import settings

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)-5s] %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
# Quiet down SQLAlchemy/uvicorn noise unless in debug
for noisy in ("sqlalchemy.engine", "passlib", "watchfiles"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Create and configure the FastAPI gateway application."""
    app = FastAPI(
        title="Customer Lifecycle Prediction — API Gateway",
        description="Absa Bank Zambia — AI-powered customer lifecycle management",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ---- Middleware (order matters — first added = outermost) ----
    # Request logging (outermost — captures full duration including CORS)
    from gateway.middleware.logging import request_logging_middleware
    app.middleware("http")(request_logging_middleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # RBAC — role-based access control (after CORS, before routes)
    from gateway.middleware.rbac import rbac_middleware as _rbac
    @app.middleware("http")
    async def rbac_middleware(request, call_next):
        await _rbac(request)
        return await call_next(request)

    # ---- Routes ----
    app.include_router(auth_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(api_key_routes.router)
    app.include_router(etl_routes.router)
    app.include_router(feature_routes.router)

    # ---- Health check ----
    @app.get("/health")
    async def health():
        return {"status": "healthy", "service": "api-gateway"}

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "gateway.main:app",
        host="0.0.0.0",
        port=settings.gateway_port,
        reload=settings.environment == "development",
    )
