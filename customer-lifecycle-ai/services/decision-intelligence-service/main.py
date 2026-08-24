"""Decision & Insight Intelligence Platform v3.0 — FastAPI Entry Point.

The bank's central intelligence layer. 6 engines, 25+ endpoints.
Answers: Why? What? Who? When? What next? What if?

Start: uvicorn main:app --host 0.0.0.0 --port 8005
"""
from __future__ import annotations

import os
import sys

# Ensure project root for shared.* imports
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

from fastapi import FastAPI

from app.api.routes import (
    router as decision_router,
    customer_intel_router,
    churn_intel_router,
    forecast_router,
    recommendation_router,
    insight_router,
    outcomes_router,
)
from app.schemas.schemas import PlatformHealth

# Upstream service URLs — env-configurable, default localhost (pilot runs
# all services on a single host).
_upstream_host = os.getenv("UPSTREAM_HOST", "127.0.0.1")

app = FastAPI(
    title="Decision & Insight Intelligence Platform",
    version="3.0.0",
    description="Transforms predictions into decisions, insights, forecasts, and explanations.",
)

app.include_router(decision_router)
app.include_router(customer_intel_router)
app.include_router(churn_intel_router)
app.include_router(forecast_router)
app.include_router(recommendation_router)
app.include_router(insight_router)
app.include_router(outcomes_router)


@app.get("/health", response_model=PlatformHealth)
def health() -> PlatformHealth:
    return PlatformHealth(
        status="healthy",
        upstream={
            "feature_service": f"http://{_upstream_host}:8002",
            "state_service": f"http://{_upstream_host}:8003",
            "prediction_service": f"http://{_upstream_host}:8004",
        },
    )
