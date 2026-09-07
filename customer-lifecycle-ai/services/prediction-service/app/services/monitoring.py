"""Monitoring Service — real telemetry from etl_clean.

Replaces the previous random.seed() simulation. Sources:
  - prediction_log table: per-prediction rows written best-effort by the
    scoring endpoints (customer, model, probability, class, latency).
  - customer_features: PSI feature drift between the model's training
    snapshot and the latest snapshot (both real data windows).
  - realized outcomes: prediction_log joined with later CHURNED
    transitions (90-day horizon) → rolling AUC / precision / recall /
    log-loss by prediction date. Sparse until labels accrue — returned
    empty with a status field rather than fabricated.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date

from app.repository.repository import PredictionRepository
from app.schemas.schemas import (
    PerformanceHistoryResponse,
    PerformancePoint,
    FeatureDriftResponse,
    FeatureDriftItem,
    PredictionLogResponse,
    PredictionLogEntry,
)

logger = logging.getLogger("prediction.monitoring")

_MODEL_ID = "churn_v1"
_DRIFT_THRESHOLD = 0.20
# Numeric features monitored for drift (subset of training features that
# exist as columns in customer_features).
_DRIFT_FEATURES = [
    "days_since_last_txn",
    "txn_count_90d",
    "txn_count_30d",
    "total_amount_90d",
    "avg_amount_90d",
    "distinct_channels_90d",
    "credit_sum_30d",
    "debit_sum_30d",
    "customer_tenure_days",
    "engagement_score",
    "inactivity_streak_days",
    "rel_products_owned",
]


def _psi(baseline: list[float], current: list[float], bins: int = 10) -> float:
    """Population Stability Index of current vs baseline using baseline deciles."""
    if not baseline or not current:
        return 0.0
    cuts = sorted(baseline)[:: max(1, len(baseline) // bins)][1:bins]
    if not cuts:
        return 0.0

    def bucket_counts(values):
        counts = [0] * (len(cuts) + 1)
        for v in values:
            idx = 0
            while idx < len(cuts) and v > cuts[idx]:
                idx += 1
            counts[idx] += 1
        return counts

    b = bucket_counts(baseline)
    c = bucket_counts(current)
    n_b, n_c = len(baseline), len(current)
    psi = 0.0
    for bi, ci in zip(b, c):
        pb = (bi / n_b) if n_b else 0.0
        pc = (ci / n_c) if n_c else 0.0
        if pb > 0 and pc > 0:
            psi += (pc - pb) * math.log(pc / pb)
    return psi


def _auc(scores: list[float], labels: list[int]) -> float | None:
    """Mann-Whitney AUC (no sklearn dependency)."""
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return None
    wins = ties = 0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1
            elif p == n:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def _log_loss(probs: list[float], labels: list[int]) -> float | None:
    if not probs:
        return None
    eps = 1e-9
    total = 0.0
    for p, l in zip(probs, labels):
        p = min(max(p, eps), 1 - eps)
        total += -(l * math.log(p) + (1 - l) * math.log(1 - p))
    return total / len(probs)


class MonitoringService:
    """Real monitoring data from the prediction_log + customer_features tables."""

    def __init__(self) -> None:
        self._repo = PredictionRepository()

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _registry() -> dict:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
        )
        try:
            with open(os.path.join(project_root, "models/registry.json")) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("registry unavailable: %s", e)
            return {}

    def _champion(self) -> dict:
        reg = self._registry()
        for m in reg.get("models", []):
            if m.get("type") == "churn" and m.get("status") == "champion":
                return m
        return {}

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def get_performance_history(self, horizon_days: int = 30) -> PerformanceHistoryResponse:
        """Rolling realized performance by prediction date.

        Groups realized_outcomes by as_of_date; a date yields a point only
        when both classes are observed (AUC needs both). Sparse/empty until
        outcome labels accrue — never fabricated.
        """
        rows = self._repo.realized_outcomes(horizon_days=90)
        threshold = float(self._champion().get("metrics", {}).get("optimal_threshold", 0.5))

        by_date: dict[str, list[dict]] = {}
        for r in rows:
            by_date.setdefault(str(r["as_of_date"]), []).append(r)

        history: list[PerformancePoint] = []
        for d in sorted(by_date):
            group = by_date[d]
            scores = [float(g["churn_probability"]) for g in group]
            labels = [int(g["churned"]) for g in group]
            auc = _auc(scores, labels)
            if auc is None:
                continue  # single-class day — not evaluable
            preds = [1 if s >= threshold else 0 for s in scores]
            tp = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 1)
            fp = sum(1 for p, l in zip(preds, labels) if p == 1 and l == 0)
            fn = sum(1 for p, l in zip(preds, labels) if p == 0 and l == 1)
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / (tp + fn) if (tp + fn) else 0.0
            history.append(PerformancePoint(
                date=date.fromisoformat(d).strftime("%b %d"),
                auc=round(auc, 4),
                precision=round(precision, 4),
                recall=round(recall, 4),
                log_loss=round(_log_loss(scores, labels) or 0.0, 4),
            ))

        # Most-recent-first window of horizon_days points
        history = history[-horizon_days:] if horizon_days else history
        return PerformanceHistoryResponse(
            model_id=self._champion().get("model_id", _MODEL_ID),
            horizon_days=horizon_days,
            history=history,
            status="OK" if history else "AWAITING_OUTCOME_LABELS",
        )

    def get_feature_drift(self) -> FeatureDriftResponse:
        """Real PSI: training-window snapshot vs latest snapshot."""
        champion = self._champion()
        training_dates = champion.get("training_dates") or []
        baseline_date = training_dates[-1] if training_dates else None

        features = self._repo.drift_feature_windows(
            _DRIFT_FEATURES, baseline_date=baseline_date,
        )
        items = []
        for f in features:
            psi = _psi(f.get("baseline_vals") or [], f.get("current_vals") or [])
            status = "CRITICAL" if psi > 0.25 else "WARNING" if psi > _DRIFT_THRESHOLD else "STABLE"
            items.append(FeatureDriftItem(
                name=f["name"],
                training_mean=round(f["baseline_mean"], 4),
                current_mean=round(f["current_mean"], 4),
                drift_score=round(psi, 4),
                invert_shift=False,
                status=status,
            ))
        return FeatureDriftResponse(
            model_id=champion.get("model_id", _MODEL_ID),
            threshold=_DRIFT_THRESHOLD,
            baseline_date=baseline_date,
            current_date=self._repo.latest_feature_date().isoformat()
            if self._repo.latest_feature_date() else None,
            features=items,
        )

    def get_prediction_log(self, limit: int = 50, offset: int = 0) -> PredictionLogResponse:
        """Recent real predictions from prediction_log."""
        rows = self._repo.recent_predictions(limit=limit + offset)[offset:]
        entries = [
            PredictionLogEntry(
                timestamp=r["created_at"].strftime("%H:%M:%S"),
                correlation_id=str(r.get("id", ""))[:8],
                customer_id=r["customer_id"],
                churn_probability=round(float(r["churn_probability"]), 4),
                predicted_class=r["predicted_class"],
                latency_ms=round(float(r.get("latency_ms") or 0.0), 1),
            )
            for r in rows
        ]
        return PredictionLogResponse(
            model_id=self._champion().get("model_id", _MODEL_ID),
            total_predictions=self._repo.total_predictions(),
            predictions=entries,
        )
