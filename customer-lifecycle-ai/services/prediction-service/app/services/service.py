"""PredictionService — Unified prediction orchestration.

Mirrors StateService pattern.
Follows prediction-service.md §4.6 (chunking) + §8 (API contract).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timezone

from app.config.settings import PredictionConfig
from app.models.churn_predictor import ChurnPredictor
from app.models.clv_predictor import CLVPredictor
from app.repository.repository import PredictionRepository
from app.schemas.schemas import (
    BatchPredictResponse,
    ComponentScores,
    CustomerChurn,
    CustomerHealth,
    CustomerPrediction,
    ModelSummary,
    ModelsResponse,
    ModelVersions,
)
from app.services.health_score import HealthScorer

logger = logging.getLogger("prediction.service")


class PredictionService:
    """Score all customers in chunks to bound memory usage.

    Mirrors StateService: singleton pattern, compute_batch() for bulk.
    """

    def __init__(self) -> None:
        self._repo = PredictionRepository()

        # Validate schema mappings at startup — config + DB-level
        from shared.config.settings import settings as shared
        try:
            conn = self._repo._connect()
            warnings = shared.validate_schema_mappings(conn)
            conn.close()
        except Exception as e:
            warnings = [f"Schema validation skipped (DB unavailable): {e}"]
        for w in warnings:
            logger.warning(w)
        if warnings:
            logger.warning(
                "Schema validation found %d issue(s). "
                "Update shared.config settings or .env to match your database.",
                len(warnings),
            )

        self._churn = ChurnPredictor()
        self._clv = CLVPredictor()
        self._health = HealthScorer(PredictionConfig())
        self._config = PredictionConfig()

        # Feature snapshot cache — avoids re-scanning customer_features
        # (~5,000 rows × ~64 cols) plus a PERCENT_RANK() pass on every
        # single-customer request. Keyed by as_of_date.isoformat():
        #   { "2026-07-27": (loaded_at_monotonic, features_list, clv_percentiles) }
        self._feature_cache: dict[str, tuple[float, list[dict], dict[str, float]]] = {}
        self._cache_lock = threading.Lock()
        self._cache_ttl = self._config.feature_cache_ttl_seconds

    # ── Batch ──────────────────────────────────────────────────────

    def compute_batch(self, as_of_date: date | None = None) -> BatchPredictResponse:
        """Score all customers for a date, backfill health scores.  §4.6

        Chunks customers to bound memory usage:
        - 1,000 customers/chunk → ~500 MB peak memory
        - Each chunk independently scored + backfilled
        - Partial failure isolates to one chunk
        """
        if as_of_date is None:
            as_of_date = date.today()

        t0 = time.perf_counter()

        all_features = self._repo.load_features(as_of_date)
        clv_percentiles = self._repo.load_clv_percentiles(as_of_date)
        chunk_size = self._config.batch_chunk_size

        total_scored = 0
        total_backfilled = 0
        chunks_processed = 0

        for i in range(0, len(all_features), chunk_size):
            chunk = all_features[i : i + chunk_size]

            # 1. Churn prediction — full 56-feature dict passed through;
            #    ChurnPredictor._dict_to_vector() strips leakage features.
            churn_probs = self._churn.predict_batch(chunk)

            # 2. Health scoring
            scores = []
            for row, cp in zip(chunk, churn_probs):
                clv_pct = self._clv.get_percentile(row["customer_id"], clv_percentiles)
                result = self._health.compute(cp, clv_pct, row.get("engagement_score"))
                scores.append({
                    "customer_id": row["customer_id"],
                    "health_score": result["health_score"],
                    "component_scores": result["component_scores"],
                })

            # 3. Backfill — one chunk at a time
            backfilled = self._repo.backfill_health_scores(scores, as_of_date)
            total_scored += len(chunk)
            total_backfilled += backfilled
            chunks_processed += 1

            logger.debug(
                "Chunk %d: scored=%d backfilled=%d",
                chunks_processed, len(chunk), backfilled,
            )

        duration = round(time.perf_counter() - t0, 2)
        logger.info(
            "Batch complete: date=%s scored=%d backfilled=%d chunks=%d duration=%.1fs",
            as_of_date, total_scored, total_backfilled, chunks_processed, duration,
        )

        return BatchPredictResponse(
            as_of_date=as_of_date,
            customers_scored=total_scored,
            chunks_processed=chunks_processed,
            chunk_size=chunk_size,
            churn_model=self._churn.model_version,
            health_scores_backfilled=total_backfilled,
            duration_seconds=duration,
            status="COMPLETED",
        )

    # ── Single Customer ────────────────────────────────────────────

    def _get_feature_snapshot(
        self, as_of_date: date
    ) -> tuple[list[dict], dict[str, float]]:
        """Return (features, clv_percentiles) for a date, cached with TTL.

        customer_features is ~5,000 rows × ~64 columns and was previously
        re-scanned (plus a PERCENT_RANK() pass) on every single-customer
        request. The decision service triggers churn + health + health per
        decision, so this cache turns ~4 full-table scans into 1.
        """
        key = as_of_date.isoformat()
        now = time.monotonic()

        cached = self._feature_cache.get(key)
        if cached is not None and (now - cached[0]) < self._cache_ttl:
            logger.info("feature cache HIT  %s (age %.2fs)", key, now - cached[0])
            return cached[1], cached[2]

        logger.info("feature cache MISS %s — loading features + clv", key)

        # Miss or expired — load under lock (single-flight) to avoid a
        # thundering herd of duplicate full-table scans.
        with self._cache_lock:
            cached = self._feature_cache.get(key)
            if cached is not None and (time.monotonic() - cached[0]) < self._cache_ttl:
                logger.info("feature cache HIT  %s (after lock)", key)
                return cached[1], cached[2]

            t0 = time.perf_counter()
            features = self._repo.load_features(as_of_date)
            t1 = time.perf_counter()
            clv = self._repo.load_clv_percentiles(as_of_date)
            t2 = time.perf_counter()
            self._feature_cache[key] = (time.monotonic(), features, clv)
            logger.info(
                "feature cache LOAD %s (features %.2fs, clv %.2fs)",
                key, t1 - t0, t2 - t1,
            )
            return features, clv

    def get_prediction(
        self, customer_id: str, as_of_date: date
    ) -> CustomerPrediction | None:
        """Full prediction for one customer: churn + CLV + health.  §8.2"""
        features_list, clv_percentiles = self._get_feature_snapshot(as_of_date)
        state = self._repo.load_state(customer_id, as_of_date)

        # Find this customer's feature row
        customer_features = None
        for row in features_list:
            if row["customer_id"] == customer_id:
                customer_features = row
                break

        if customer_features is None:
            return None

        churn_prob = self._churn.predict(customer_features)
        clv_pct = self._clv.get_percentile(customer_id, clv_percentiles)
        result = self._health.compute(
            churn_prob, clv_pct, customer_features.get("engagement_score")
        )

        return CustomerPrediction(
            customer_id=customer_id,
            as_of_date=as_of_date,
            state=state,
            churn_probability=round(churn_prob, 4),
            clv_percentile=round(clv_pct, 4),
            health_score=result["health_score"],
            component_scores=ComponentScores(**result["component_scores"]),
            model_versions=ModelVersions(
                churn=self._churn.model_version,
                clv=self._clv.model_version,
            ),
            computed_at=datetime.now(timezone.utc),
        )

    def get_churn(
        self, customer_id: str, as_of_date: date
    ) -> CustomerChurn | None:
        """Churn probability only.  §8.2"""
        features_list, _ = self._get_feature_snapshot(as_of_date)
        customer_features = None
        for row in features_list:
            if row["customer_id"] == customer_id:
                customer_features = row
                break

        if customer_features is None:
            return None

        churn_prob = self._churn.predict(customer_features)
        return CustomerChurn(
            customer_id=customer_id,
            as_of_date=as_of_date,
            churn_probability=round(churn_prob, 4),
            model_version=self._churn.model_version,
            computed_at=datetime.now(timezone.utc),
        )

    def get_health(
        self, customer_id: str, as_of_date: date
    ) -> CustomerHealth | None:
        """Health score breakdown.  §8.2"""
        features_list, clv_percentiles = self._get_feature_snapshot(as_of_date)

        customer_features = None
        for row in features_list:
            if row["customer_id"] == customer_id:
                customer_features = row
                break

        if customer_features is None:
            return None

        churn_prob = self._churn.predict(customer_features)
        clv_pct = self._clv.get_percentile(customer_id, clv_percentiles)
        result = self._health.compute(
            churn_prob, clv_pct, customer_features.get("engagement_score")
        )

        return CustomerHealth(
            customer_id=customer_id,
            as_of_date=as_of_date,
            health_score=result["health_score"],
            component_scores=ComponentScores(**result["component_scores"]),
            model_versions=ModelVersions(
                churn=self._churn.model_version,
                clv=self._clv.model_version,
            ),
            computed_at=datetime.now(timezone.utc),
        )

    # ── Models ─────────────────────────────────────────────────────

    def get_models(self) -> ModelsResponse:
        """List registered models from registry.  §8.2"""
        import json
        import os

        # app/services/service.py → app/services/ → app/ → prediction-service/ → services/ → project_root
        project_root = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))
                    )
                )
            )
        )
        registry_path = os.path.join(project_root, "models/registry.json")

        models = []
        try:
            with open(registry_path) as f:
                registry = json.load(f)

            for m in registry.get("models", []):
                summary = ModelSummary(
                    model_id=m["model_id"],
                    type=m["type"],
                    status=m["status"],
                    metrics=m.get("metrics"),
                )
                models.append(summary)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.warning("Could not load registry: %s", e)

        # Always include CLV percentile entry
        models.append(ModelSummary(
            model_id="clv_percentile_v1",
            type="clv",
            status="champion",
            method="percentile_rank",
        ))

        return ModelsResponse(models=models)
