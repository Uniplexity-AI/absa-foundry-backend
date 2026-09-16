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
from gateway.routes import customer_routes, prediction_routes, models_routes
from gateway.routes import customer_profile_routes
from gateway.routes import customer_admin_routes
from gateway.routes import recommendation_routes, insight_routes
from gateway.routes import churn_intel_routes, forecast_routes
from gateway.routes import monitoring_routes, outcome_routes
from gateway.routes import intelligence_routes
from gateway.routes import pilot_action_routes
from gateway.routes import ingest_routes
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

    # Auth + RBAC — enforce a valid JWT on every non-public route, then check roles.
    # Runs inside CORS; sets request.state.user for all downstream handlers.
    # HTTPException raised inside an http middleware must be converted to a
    # Response here (otherwise Starlette's exception middleware turns it into 500).
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse
    from gateway.middleware.auth import auth_middleware as _auth
    from gateway.middleware.rbac import rbac_middleware as _rbac

    @app.middleware("http")
    async def auth_rbac_middleware(request, call_next):
        # CORS preflight — let it through so the CORS layer answers it
        if request.method == "OPTIONS":
            return await call_next(request)
        try:
            await _auth(request)   # 401 if token missing/invalid; public routes pass
            await _rbac(request)   # 403 if the user's roles don't cover the route
        except HTTPException as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
                headers=exc.headers,
            )
        return await call_next(request)

    # CORS MUST be added last to be the outermost middleware!
    # Auth is a Bearer-token flow (no cookies), so credentials are NOT required.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Restrict to frontend origin(s) in production
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- Routes ----
    app.include_router(auth_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(api_key_routes.router)
    app.include_router(etl_routes.router)
    app.include_router(ingest_routes.router)
    app.include_router(feature_routes.router)
    app.include_router(customer_routes.router)
    app.include_router(customer_profile_routes.router)
    app.include_router(customer_admin_routes.router)
    app.include_router(prediction_routes.router)
    app.include_router(models_routes.router)
    app.include_router(recommendation_routes.router)
    app.include_router(insight_routes.router)
    app.include_router(churn_intel_routes.router)
    app.include_router(forecast_routes.router)
    app.include_router(monitoring_routes.router)
    app.include_router(outcome_routes.router)
    app.include_router(intelligence_routes.router)
    app.include_router(pilot_action_routes.router)

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
