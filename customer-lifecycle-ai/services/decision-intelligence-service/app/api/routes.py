"""Decision Intelligence Platform — API Routes v3.0.

Decision Engine (/decisions) + Customer Intelligence (/customer-intel).
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.schemas.schemas import (
    BatchDecisionResponse, CustomerIntelligence, DecisionPackage,
    ExecutionRequest, OutcomeRequest,
)
from app.services.service import DecisionService
from app.services.customer_intelligence_service import customer_intel_service

router = APIRouter(prefix="/decisions", tags=["decisions"])
customer_intel_router = APIRouter(prefix="/customer-intel", tags=["customer-intel"])
_service = DecisionService()


# ===========================================================================
# Decision Engine
# ===========================================================================

@router.post("/compute", response_model=BatchDecisionResponse)
def compute_batch(
    as_of_date: date | None = Query(default=None),
    strategy: str = Query(default="BALANCED"),
    max_customers: int | None = Query(default=None),
) -> BatchDecisionResponse:
    return _service.compute_batch(as_of_date, strategy, max_customers)


@router.get("/{customer_id}", response_model=DecisionPackage)
def get_decision(
    customer_id: str,
    as_of_date: date = Query(...),
    strategy: str = Query(default="BALANCED"),
) -> DecisionPackage:
    result = _service.compute_for_customer(customer_id, as_of_date, strategy)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No decision for {customer_id}")
    return result


@router.get("/queue/{rm_id}")
def get_queue(rm_id: str, limit: int = Query(default=20)):
    batch = _service.compute_batch(None, "BALANCED", max_customers=limit)
    return {"rm_id": rm_id, "queue_size": batch.decisions_generated, "limit": limit}


@router.post("/{customer_id}/execute")
def execute_decision(customer_id: str, body: ExecutionRequest):
    return {"status": "logged", "customer_id": customer_id, "rm_id": body.rm_id}


@router.patch("/{decision_id}/outcome")
def record_outcome(decision_id: str, body: OutcomeRequest):
    return {"status": "recorded", "decision_id": decision_id, "outcome": body.outcome}


@router.get("/strategies/list")
def list_strategies():
    from app.engines.strategy_layer import StrategyLayer
    return {"strategies": StrategyLayer.list_strategies()}


# ===========================================================================
# Customer Intelligence
# ===========================================================================

@customer_intel_router.get("/alerts/{customer_id}")
def get_alerts(customer_id: str, as_of_date: date | None = Query(default=None)):
    result = customer_intel_service.analyze(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404)
    return {"customer_id": customer_id, "count": len(result.alerts),
            "alerts": [a.model_dump() for a in result.alerts]}


@customer_intel_router.get("/trajectory/{customer_id}")
def get_trajectory(customer_id: str, as_of_date: date | None = Query(default=None)):
    result = customer_intel_service.analyze(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404)
    ht = result.health_trajectory
    return {"trajectory": ht.trajectory if ht else "UNKNOWN",
            "score": ht.current_score if ht else 0}


@customer_intel_router.get("/{customer_id}", response_model=CustomerIntelligence)
def get_customer_intelligence(
    customer_id: str,
    as_of_date: date | None = Query(default=None),
) -> CustomerIntelligence:
    result = customer_intel_service.analyze(customer_id, as_of_date)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No data for {customer_id}")
    return result


# ===========================================================================
# Churn Intelligence
# ===========================================================================

churn_intel_router = APIRouter(prefix="/churn-intel", tags=["churn-intel"])


@churn_intel_router.get("/drivers")
def get_churn_drivers(as_of_date: date | None = Query(default=None)):
    """Top churn drivers across the portfolio."""
    from app.engines.churn_intelligence.root_cause import analyze_root_causes
    drivers = analyze_root_causes(as_of_date)
    return {"as_of_date": as_of_date or date.today(), "drivers": [d.model_dump() for d in drivers]}


@churn_intel_router.get("/segments")
def get_segment_analysis(as_of_date: date | None = Query(default=None)):
    """Segment-level churn deterioration analysis."""
    from app.engines.churn_intelligence.segment_analyzer import analyze_segments
    segments = analyze_segments(as_of_date)
    return {"as_of_date": as_of_date or date.today(), "segments": segments}


# ===========================================================================
# Forecast
# ===========================================================================

forecast_router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@forecast_router.get("/churn")
def get_churn_forecast(as_of_date: date | None = Query(default=None), horizon_days: int = Query(default=90)):
    """Portfolio churn forecast for the given horizon."""
    from app.engines.forecast_engine.churn_forecast import forecast_churn
    return forecast_churn(as_of_date, horizon_days)


@forecast_router.get("/revenue-at-risk")
def get_revenue_at_risk(as_of_date: date | None = Query(default=None), horizon_days: int = Query(default=90)):
    """Estimated revenue at risk (ZMW) from projected churn."""
    from app.engines.forecast_engine.revenue_at_risk import forecast_revenue_at_risk
    return forecast_revenue_at_risk(as_of_date, horizon_days)
