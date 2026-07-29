"""Train XGBoost churn model with leakage-free feature selection.

Follows prediction-service.md §4.4 exactly:
- Loads features from customer_features (2026-07-17 + 2026-07-22)
- Excludes 9 LEAKAGE_FEATURES before model.fit()
- Account-closure-only labels via generate_churn_label()
- Class-weight balancing for imbalanced labels
- Evaluates on holdout 2026-07-27
- Saves model to models/champion/churn/
- Updates models/registry.json with training_features + metrics
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date
from typing import Any

import numpy as np
import psycopg2
import xgboost as xgb
from dotenv import load_dotenv
from psycopg2 import extras
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    brier_score_loss,
    log_loss,
    roc_auc_score,
)

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from shared.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("train_models")

# ── Leakage Guard ──────────────────────────────────────────────────
# These features are derived from recency timing or used in the churn
# label definition. They MUST be dropped before model.fit().
# The label column is pulled from shared config — if you change
# LABEL_CHURN_COLUMN, it's automatically excluded from training.

def _get_leakage_features() -> set[str]:
    """Build leakage set from hardcoded recency features + configurable label column."""
    base = {
        "days_since_last_txn", "behav_recency_score",
        "risk_dormant_indicator",
        "engagement_score", "behav_inactive_days_90d",
        "inactivity_streak_days", "behav_activity_consistency",
        "txn_frequency_trend",
    }
    # Dynamically add the label column to prevent target leakage
    try:
        from shared.config.settings import settings as s
        label_col = s.label_churn_column
        if label_col:
            base.add(label_col)
    except Exception:
        base.add("rel_customer_status")  # fallback
    return base


def _get_non_feature_columns() -> set[str]:
    """Build non-feature column set from shared config."""
    try:
        from shared.config.settings import settings as s
        return {s.col_customer_id, s.col_as_of_date}
    except Exception:
        return {"customer_id", "as_of_date"}


LEAKAGE_FEATURES = _get_leakage_features()
NON_FEATURE_COLUMNS = _get_non_feature_columns()

TRAINING_DATES = ["2026-07-17", "2026-07-22"]
HOLDOUT_DATE = "2026-07-27"


def _get_training_dates() -> list[str]:
    """Resolve training dates from shared config, with hardcoded fallback."""
    try:
        from shared.config.settings import settings as s
        return s.training_date_list
    except Exception:
        return TRAINING_DATES


def _get_holdout_date() -> str:
    try:
        from shared.config.settings import settings as s
        return s.training_holdout_date
    except Exception:
        return HOLDOUT_DATE


# ── Helpers ────────────────────────────────────────────────────────

def _safe_float(val: Any) -> float:
    """Convert value to float, return 0.0 for anything non-numeric."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


# ── Label Generator ────────────────────────────────────────────────

def generate_churn_label(features: dict) -> int | None:
    """Generate binary churn label from configurable status column.

    Reads label_churn_column and label_churn_positive_value from
    shared config. Falls back to rel_customer_status / "Closed".
    """
    try:
        from shared.config.settings import settings as s
        col = s.label_churn_column
        pos = s.label_churn_positive_value
    except Exception:
        col = "rel_customer_status"
        pos = "Closed"

    status = features.get(col, "")
    if status == pos:
        return 1
    if status and status != pos:
        return 0
    return None


# ── Data Loading ───────────────────────────────────────────────────

def load_features_and_labels(
    dates: list[str],
    exclude_features: set[str],
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load features from customer_features, exclude leakage, generate labels.

    Returns:
        X: Feature matrix (n_samples, n_features)
        y: Label vector (n_samples,)
        training_features: Ordered list of column names used
    """
    conn = psycopg2.connect(
        settings.database_target_url_sync,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )

    all_rows: list[dict] = []
    try:
        cur = conn.cursor(cursor_factory=extras.RealDictCursor)
        for dt in dates:
            cur.execute(
                "SELECT * FROM customer_features WHERE as_of_date = %s",
                (dt,),
            )
            all_rows.extend(dict(r) for r in cur.fetchall())
    finally:
        conn.close()

    # Discover all feature columns (exclude identifiers + leakage)
    if not all_rows:
        raise ValueError("No features loaded — check dates and DB connection")

    all_columns = set(all_rows[0].keys())
    feature_columns = sorted(
        all_columns - NON_FEATURE_COLUMNS - exclude_features
    )
    logger.info(
        "Loaded %d rows from %s. %d total columns → %d training features "
        "(excluded %d leakage + %d non-feature)",
        len(all_rows), dates,
        len(all_columns), len(feature_columns),
        len(exclude_features), len(NON_FEATURE_COLUMNS),
    )

    # Build X, y
    X_rows = []
    y_rows = []
    excluded_count = 0
    for row in all_rows:
        label = generate_churn_label(row)
        if label is None:
            excluded_count += 1
            continue
        X_rows.append([
            _safe_float(row.get(col))
            for col in feature_columns
        ])
        y_rows.append(label)

    logger.info(
        "Labels: %d positive, %d negative, %d excluded (ambiguous)",
        sum(y_rows), len(y_rows) - sum(y_rows), excluded_count,
    )

    return np.array(X_rows), np.array(y_rows), feature_columns


# ── Registry Update ────────────────────────────────────────────────

def update_registry(entry: dict) -> None:
    """Add or update a model entry in models/registry.json."""
    registry_path = os.path.join(_PROJECT_ROOT, "models/registry.json")

    registry: dict = {}
    if os.path.exists(registry_path):
        logger.info("Reading registry: %s (size=%d)", registry_path, os.path.getsize(registry_path))
        with open(registry_path, encoding="utf-8-sig") as f:
            content = f.read().strip()
            if content:
                registry = json.loads(content)

    # Support both legacy (no models array) and new format
    models: list[dict] = registry.get("models", [])
    replaced = False
    for i, m in enumerate(models):
        if m.get("model_id") == entry["model_id"]:
            models[i] = entry
            replaced = True
            break
    if not replaced:
        models.append(entry)

    registry["models"] = models

    os.makedirs(os.path.dirname(registry_path), exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, default=str)

    logger.info("Registry updated: %s (status=%s)", entry["model_id"], entry["status"])


# ── Main Training Pipeline ─────────────────────────────────────────

def _detect_dead_features(dates: list[str]) -> set[str]:
    """Pre-flight: detect features that are ALL_ZERO or 100% NULL across all training dates.

    These features provide no signal and should be excluded from training.
    Returns a set of feature names to exclude.
    """
    import psycopg2
    from shared.config.settings import settings as s

    dead: set[str] = set()
    table = s.table_customer_features
    as_of_col = s.col_as_of_date

    try:
        conn = psycopg2.connect(
            s.database_target_url_sync, connect_timeout=10,
            keepalives=1, keepalives_idle=30,
            keepalives_interval=10, keepalives_count=3,
        )
        cur = conn.cursor()

        # Get all numeric columns
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = %s AND table_schema = 'public' "
            "AND data_type IN ('integer','bigint','smallint','numeric','real','double precision')",
            (table,),
        )
        all_cols = {r[0] for r in cur.fetchall()}

        # Skip non-feature columns
        skip = NON_FEATURE_COLUMNS | LEAKAGE_FEATURES
        cols_to_check = sorted(all_cols - skip)

        for col in cols_to_check:
            # Check if ALL_ZERO or 100% NULL across all training dates
            placeholders = ",".join(["%s"] * len(dates))
            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE "{col}" IS NULL) AS nulls,
                    COUNT(*) FILTER (WHERE "{col}" = 0) AS zeros,
                    COUNT(*) AS total
                FROM {table}
                WHERE "{as_of_col}" IN ({placeholders})
                """,
                dates,
            )
            nulls, zeros, total = cur.fetchone()
            if total == 0:
                continue
            if nulls == total:
                dead.add(col)
                logger.warning("  DEAD: %s — 100%% NULL, auto-excluding", col)
            elif zeros == total:
                dead.add(col)
                logger.warning("  DEAD: %s — ALL_ZERO across training data, auto-excluding", col)

        conn.close()
    except Exception as e:
        logger.warning("Pre-flight quality check skipped (DB unavailable): %s", e)

    return dead


def train_churn_model() -> dict:
    """Train XGBoost churn classifier with leakage guard.  §4.4"""
    t0 = time.perf_counter()

    # ── Pre-flight: auto-detect dead features ──
    logger.info("Pre-flight: scanning for dead features across %s...", _get_training_dates())
    dead_features = _detect_dead_features(_get_training_dates())
    all_excluded = LEAKAGE_FEATURES | dead_features
    if dead_features:
        logger.info(
            "Auto-excluding %d dead features + %d leakage = %d total excluded",
            len(dead_features), len(LEAKAGE_FEATURES), len(all_excluded),
        )
    else:
        logger.info("No dead features detected. Excluding %d leakage features.", len(LEAKAGE_FEATURES))

    # 1. Load features — exclude leakage + auto-detected dead columns
    X_train, y_train, training_features = load_features_and_labels(
        dates=_get_training_dates(),
        exclude_features=all_excluded,
    )

    # 2. Train with class-weight balancing
    n_pos = int(sum(y_train))
    n_neg = int(len(y_train) - n_pos)
    pos_weight = n_neg / max(n_pos, 1) if n_pos > 0 else 1.0

    logger.info(
        "Training: %d samples, %d features, pos_weight=%.2f",
        len(y_train), len(training_features), pos_weight,
    )

    model = xgb.XGBClassifier(
        objective="binary:logistic",
        eval_metric="auc",
        max_depth=4,
        learning_rate=0.05,
        n_estimators=50,
        scale_pos_weight=pos_weight,
        subsample=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # 3. Evaluate on holdout date
    X_test, y_test, _ = load_features_and_labels(
        dates=[_get_holdout_date()],
        exclude_features=all_excluded,
    )
    y_pred = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred)

    # 4. Calibration evaluation (assess only — do not fit calibrator per D12)
    prob_true, prob_pred = calibration_curve(y_test, y_pred, n_bins=5)
    # ECE: weighted average of |predicted - observed| per bin
    ece = float(np.mean(np.abs(prob_true - prob_pred))) if len(prob_true) > 0 else 0.0
    brier = brier_score_loss(y_test, y_pred)
    ll = log_loss(y_test, y_pred)

    logger.info("Metrics: AUC=%.4f, Brier=%.4f, ECE=%.4f, LogLoss=%.4f", auc, brier, ece, ll)

    # 5. Extract feature importance
    importance = dict(zip(training_features, model.feature_importances_))
    ranked = sorted(importance.items(), key=lambda x: -x[1])[:10]
    logger.info("Top features:")
    for name, imp in ranked:
        logger.info("  %s: %.4f", name, imp)

    # 6. Save model
    model_dir = os.path.join(
        _PROJECT_ROOT, "models/champion/churn"
    )
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "xgboost_churn_v1.json")
    model.save_model(model_path)
    logger.info("Model saved: %s", model_path)

    # 7. Register
    entry = {
        "model_id": "churn_v1",
        "type": "churn",
        "status": "champion",
        "path": "champion/churn/xgboost_churn_v1.json",
        "framework": "xgboost",
        "version": 1,
        "trained_at": str(date.today()),
        "training_dates": _get_training_dates(),
        "holdout_date": _get_holdout_date(),
        "metrics": {
            "auc": round(auc, 4),
            "brier": round(brier, 4),
            "ece": round(ece, 4),
            "log_loss": round(ll, 4),
        },
        "calibrator": None,
        "feature_count_total": len(training_features) + len(all_excluded),
        "feature_count_training": len(training_features),
        "leakage_features_excluded": sorted(LEAKAGE_FEATURES),
        "dead_features_excluded": sorted(dead_features),
        "training_features": training_features,
        "top_features": [
            {"name": name, "importance": round(imp, 4)}
            for name, imp in ranked
        ],
        "notes": (
            "PoC model — trained on account-closure-only labels "
            f"({n_pos} positives across {TRAINING_DATES}). "
            "AUC is directional, not precise. Probabilities are UNCALIBRATED "
            "ranking scores — do NOT treat churn_prob as a true probability. "
            "If AUC > 0.90, re-check for feature leakage. "
            "Calibration deferred to production (D12)."
        ),
    }
    update_registry(entry)

    duration = time.perf_counter() - t0
    logger.info("Training complete in %.1fs", duration)

    return entry


if __name__ == "__main__":
    train_churn_model()
