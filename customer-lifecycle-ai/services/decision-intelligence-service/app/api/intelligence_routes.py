"""Intelligence Aggregation Routes — /intelligence/* (frontend dashboard contracts).

Endoints:
  GET /intelligence/clv-summary        — CLV bands + portfolio value cards
  GET /intelligence/aum-forecast       — 3-scenario AUM projection time series
  GET /intelligence/business-outcomes  — ROI + pilot-vs-control tracker
  GET /intelligence/lifecycle-summary  — state counts + transition matrix + win-back
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.services.intelligence_service import intelligence_service

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/clv-summary")
def get_clv_summary(as_of_date: date | None = Query(default=None)):
    """Customer Value Intelligence: percentile bands + totals for summary cards."""
    return intelligence_service.clv_summary(as_of_date)


@router.get("/aum-forecast")
def get_aum_forecast(
    as_of_date: date | None = Query(default=None),
    horizon_days: int = Query(default=90, ge=7, le=365),
):
    """AUM Balance Forecast: base/optimistic/pessimistic weekly series."""
    return intelligence_service.aum_forecast(as_of_date, horizon_days)


@router.get("/business-outcomes")
def get_business_outcomes():
    """Business Outcomes & ROI Tracker: intervention ROI by branch + pilot vs control."""
    return intelligence_service.business_outcomes()


@router.get("/lifecycle-summary")
def get_lifecycle_summary(as_of_date: date | None = Query(default=None)):
    """Lifecycle Prediction & Win-Back Pipeline: states, 30d transition matrix, eligible churned."""
    return intelligence_service.lifecycle_summary(as_of_date)
