"""Monitoring Service — Model performance history, feature drift, prediction logs.

Generates realistic monitoring data from model metrics and simulation.
In production, this would query a time-series database (e.g., InfluxDB, TimescaleDB).
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

from app.schemas.schemas import (
    PerformanceHistoryResponse,
    PerformancePoint,
    FeatureDriftResponse,
    FeatureDriftItem,
    PredictionLogResponse,
    PredictionLogEntry,
)

# Baseline metrics from champion churn model
BASELINE_AUC = 0.7672
BASELINE_LOG_LOSS = 0.5663
BASELINE_BRIER = 0.1892

FEATURE_DEFS: list[dict] = [
    {"name": "days_since_last_txn", "train_mean": 45.2, "current_mean": 67.8, "psi": 0.31, "invert": False, "status": "CRITICAL"},
    {"name": "engagement_score", "train_mean": 52.3, "current_mean": 38.1, "psi": 0.28, "invert": True, "status": "CRITICAL"},
    {"name": "txn_count_90d", "train_mean": 12.7, "current_mean": 8.9, "psi": 0.22, "invert": True, "status": "WARNING"},
    {"name": "balance_growth_30d_pct", "train_mean": 3.2, "current_mean": -2.1, "psi": 0.19, "invert": True, "status": "WARNING"},
    {"name": "customer_tenure_days", "train_mean": 820.0, "current_mean": 845.0, "psi": 0.05, "invert": False, "status": "STABLE"},
    {"name": "clv_percentile", "train_mean": 48.5, "current_mean": 44.2, "psi": 0.12, "invert": True, "status": "STABLE"},
    {"name": "new_products_60d", "train_mean": 0.8, "current_mean": 0.3, "psi": 0.15, "invert": True, "status": "STABLE"},
    {"name": "risk_dormant_indicator", "train_mean": 0.35, "current_mean": 0.48, "psi": 0.09, "invert": False, "status": "STABLE"},
]

SEGMENTS = ["MASS_MARKET", "MASS_AFFLUENT", "AFFLUENT", "SME", "CORPORATE"]


class MonitoringService:
    """Generates monitoring data from model baselines and simulation."""

    def get_performance_history(self, horizon_days: int = 30) -> PerformanceHistoryResponse:
        """Generate realistic performance-over-time data with slight degradation trend."""
        random.seed(42)
        history: list[PerformancePoint] = []
        end_date = datetime.now()

        for i in range(horizon_days, -1, -1):
            d = end_date - timedelta(days=i)
            # Slight upward trend in AUC over time (model improving), noise in precision/recall
            day_frac = (horizon_days - i) / max(horizon_days, 1)
            auc = round(BASELINE_AUC + day_frac * 0.02 + random.uniform(-0.01, 0.01), 4)
            precision = round(0.72 + day_frac * 0.03 + random.uniform(-0.02, 0.02), 4)
            recall = round(0.68 + day_frac * 0.02 + random.uniform(-0.02, 0.02), 4)
            log_loss = round(BASELINE_LOG_LOSS - day_frac * 0.05 + random.uniform(-0.02, 0.02), 4)

            history.append(PerformancePoint(
                date=d.strftime("%b %d"),
                auc=auc,
                precision=precision,
                recall=recall,
                log_loss=log_loss,
            ))

        return PerformanceHistoryResponse(
            model_id="churn_v1",
            horizon_days=horizon_days,
            history=history,
        )

    def get_feature_drift(self) -> FeatureDriftResponse:
        """Return PSI-based feature drift analysis."""
        features = [
            FeatureDriftItem(
                name=f["name"],
                training_mean=f["train_mean"],
                current_mean=f["current_mean"],
                drift_score=f["psi"],
                invert_shift=f["invert"],
                status=f["status"],
            )
            for f in FEATURE_DEFS
        ]
        return FeatureDriftResponse(
            model_id="churn_v1",
            threshold=0.20,
            features=features,
        )

    def get_prediction_log(self, limit: int = 50, offset: int = 0) -> PredictionLogResponse:
        """Generate realistic prediction log entries."""
        random.seed(123 + offset)
        total = 4211
        predictions: list[PredictionLogEntry] = []
        base_time = datetime.now() - timedelta(hours=1)

        for i in range(min(limit, total - offset)):
            t = base_time + timedelta(seconds=i * 7 + random.randint(0, 5))
            cid = f"CUST{10000 + offset + i:05d}"
            churn_prob = round(random.uniform(0.05, 0.85), 4)
            pred_class = "CHURN" if churn_prob > 0.5 else "RETAIN"

            predictions.append(PredictionLogEntry(
                timestamp=t.strftime("%H:%M:%S"),
                correlation_id=str(uuid.uuid4())[:8],
                customer_id=cid,
                churn_probability=churn_prob,
                predicted_class=pred_class,
                latency_ms=round(random.uniform(12, 95), 1),
            ))

        return PredictionLogResponse(
            model_id="churn_v1",
            total_predictions=total,
            predictions=predictions,
        )
