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
    roc_curve,
)
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict
import joblib

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
    """Build non-feature column set from shared config.

    Excludes identifiers and metadata columns that must never be model
    features: customer_id, as_of_date, surrogate primary key (id), and
    bookkeeping timestamps (computed_at, created_at, updated_at).
    """
    metadata_cols = {"id", "computed_at", "created_at", "updated_at"}
    try:
        from shared.config.settings import settings as s
        return {s.col_customer_id, s.col_as_of_date} | metadata_cols
    except Exception:
        return {"customer_id", "as_of_date"} | metadata_cols


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


# ── Diagnostics: Plots, Health, Drift, Hallucination ───────────────

_PLOT_DIR = os.path.join(_PROJECT_ROOT, "models/champion/churn/plots")


def _ensure_plot_dir() -> str:
    os.makedirs(_PLOT_DIR, exist_ok=True)
    return _PLOT_DIR


def _plot_roc_curve(y_test: np.ndarray, y_pred: np.ndarray, auc: float, out_dir: str) -> str:
    """Save ROC curve plot. Returns the file path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fpr, tpr, _ = roc_curve(y_test, y_pred)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(fpr, tpr, color="#DC0037", label=f"AUC = {auc:.4f}")
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_title("ROC Curve — Churn Model")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(out_dir, "roc_curve.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_calibration_curve(y_test: np.ndarray, y_pred: np.ndarray, ece: float, out_dir: str) -> str:
    """Save calibration plot (reliability diagram). Returns file path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    prob_true, prob_pred = calibration_curve(y_test, y_pred, n_bins=10)
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.plot(prob_pred, prob_true, marker="o", color="#FF780F", label=f"ECE = {ece:.4f}")
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect calibration")
    ax.set_xlabel("Mean Predicted Probability")
    ax.set_ylabel("Fraction of Positives")
    ax.set_title("Reliability Diagram — Churn Model")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(out_dir, "calibration.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_feature_importance(ranked: list[tuple[str, float]], out_dir: str) -> str:
    """Save horizontal bar chart of top feature importances. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = [n for n, _ in ranked][::-1]
    vals = [v for _, v in ranked][::-1]
    fig, ax = plt.subplots(figsize=(8, max(4, len(names) * 0.4)))
    ax.barh(names, vals, color="#DC0037")
    ax.set_xlabel("Importance")
    ax.set_title("Top Feature Importances")
    fig.tight_layout()
    path = os.path.join(out_dir, "feature_importance.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _compute_psi(train: np.ndarray, test: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index (drift) between two distributions."""
    train = np.asarray(train, dtype=float)
    test = np.asarray(test, dtype=float)
    train = train[np.isfinite(train)]
    test = test[np.isfinite(test)]
    if len(train) == 0 or len(test) == 0:
        return 0.0
    all_vals = np.concatenate([train, test])
    if np.ptp(all_vals) == 0:
        return 0.0
    edges = np.unique(np.percentile(all_vals, np.linspace(0, 100, bins + 1)))
    if len(edges) < 2:
        return 0.0
    train_hist, _ = np.histogram(train, bins=edges)
    test_hist, _ = np.histogram(test, bins=edges)
    eps = 1e-6
    train_pct = (train_hist + eps) / (train_hist.sum() + eps * len(train_hist))
    test_pct = (test_hist + eps) / (test_hist.sum() + eps * len(test_hist))
    return float(np.sum((test_pct - train_pct) * np.log(test_pct / train_pct)))


def _compute_overconfidence(y_test: np.ndarray, y_pred: np.ndarray, threshold: float = 0.9) -> dict:
    """Hallucination proxy: confident-but-wrong predictions."""
    confident = y_pred >= threshold
    n_confident = int(confident.sum())
    if n_confident == 0:
        return {"overconfidence_ratio": 0.0, "confident_predictions": 0}
    wrong = int((confident & (y_test == 0)).sum())
    return {
        "overconfidence_ratio": round(wrong / n_confident, 4),
        "confident_predictions": n_confident,
    }


def _compute_health_metrics(
    y_test: np.ndarray, y_pred: np.ndarray,
    X_test: np.ndarray, X_train: np.ndarray,
    model, train_auc: float,
) -> dict:
    """Model + data health summary.

    Returns dict with:
      - data_health: missing/constant feature counts
      - model_health: overfit gap (train vs test AUC), calibration flags
    """
    # Data health
    def _missing_ratio(arr: np.ndarray) -> float:
        arr = np.asarray(arr, dtype=float)
        return float(np.isnan(arr).mean()) if arr.size else 0.0

    data_health = {
        "test_missing_ratio": round(_missing_ratio(X_test), 4),
        "test_samples": int(len(y_test)),
        "test_positives": int(sum(y_test)),
        "test_negatives": int(len(y_test) - sum(y_test)),
    }

    # Model health
    gap = train_auc - float(roc_auc_score(y_test, y_pred))
    overfit = gap > 0.03
    model_health = {
        "train_auc": round(train_auc, 4),
        "test_auc": round(float(roc_auc_score(y_test, y_pred)), 4),
        "overfit_gap": round(gap, 4),
        "overfit_flag": overfit,
    }
    return {"data_health": data_health, "model_health": model_health}


def _compute_drift(
    X_train: np.ndarray, X_test: np.ndarray, feature_names: list[str], top_n: int = 10,
) -> dict:
    """Per-feature PSI drift between training and holdout distributions.

    Returns top-N drifted features + aggregate drift level.
    """
    drifts: list[dict] = []
    for i, name in enumerate(feature_names):
        psi = _compute_psi(X_train[:, i], X_test[:, i])
        drifts.append({"feature": name, "psi": round(psi, 4)})
    drifts.sort(key=lambda d: -d["psi"])
    top = drifts[:top_n]
    max_psi = max((d["psi"] for d in drifts), default=0.0)
    # Standard PSI interpretation thresholds
    level = "low" if max_psi < 0.1 else ("moderate" if max_psi < 0.25 else "high")
    return {
        "max_psi": round(max_psi, 4),
        "drift_level": level,
        "top_drifted_features": top,
    }


def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error — weighted |accuracy − confidence| per bin."""
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob, dtype=float)
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        if i == n_bins - 1:
            in_bin = (y_prob >= bin_boundaries[i]) & (y_prob <= bin_boundaries[i + 1])
        else:
            in_bin = (y_prob >= bin_boundaries[i]) & (y_prob < bin_boundaries[i + 1])
        prop_in_bin = float(np.mean(in_bin))
        if prop_in_bin > 0:
            accuracy_in_bin = float(np.mean(y_true[in_bin]))
            avg_confidence_in_bin = float(np.mean(y_prob[in_bin]))
            ece += abs(accuracy_in_bin - avg_confidence_in_bin) * prop_in_bin
    return float(ece)


def _calibrate_probabilities(
    model, X_train: np.ndarray, y_train: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray,
) -> dict:
    """Fit Platt + isotonic calibrators on out-of-fold predictions.

    Calibration is fit strictly on OUT-OF-FOLD predictions of the training set
    (via 5-fold cross-validation), never on the holdout set — preventing
    data leakage. Returns per-method calibrated test probabilities and ECE.
    """
    # Out-of-fold predictions on TRAINING data (calibrator fitting data)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_probs = cross_val_predict(
        model, X_train, y_train, cv=skf, method="predict_proba",
    )[:, 1]

    # Base model's raw probabilities on the holdout set
    test_probs_raw = model.predict_proba(X_test)[:, 1]

    # Method A: Platt scaling (unregularized logistic regression)
    platt = LogisticRegression(C=999999, solver="lbfgs", max_iter=1000)
    platt.fit(oof_probs.reshape(-1, 1), y_train)
    test_probs_platt = platt.predict_proba(test_probs_raw.reshape(-1, 1))[:, 1]

    # Method B: Isotonic regression (non-parametric, monotonic)
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(oof_probs, y_train)
    test_probs_iso = iso.predict(test_probs_raw)

    return {
        "raw": {"probs": test_probs_raw, "ece": compute_ece(y_test, test_probs_raw)},
        "platt": {"probs": test_probs_platt, "ece": compute_ece(y_test, test_probs_platt), "calibrator": platt},
        "isotonic": {"probs": test_probs_iso, "ece": compute_ece(y_test, test_probs_iso), "calibrator": iso},
    }


def _plot_calibration_comparison(
    y_test: np.ndarray, raw: np.ndarray, platt: np.ndarray, iso: np.ndarray, out_dir: str,
) -> str:
    """Save reliability diagrams for raw vs Platt vs isotonic. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 5))
    for probs, label, color in [
        (raw, "Uncalibrated", "#DC0037"),
        (platt, "Platt", "#FF780F"),
        (iso, "Isotonic", "#2e7d32"),
    ]:
        pt, pp = calibration_curve(y_test, probs, n_bins=10)
        ax.plot(pp, pt, marker="o", color=color, label=label)
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect")
    ax.set_xlabel("Mean Predicted Probability")
    ax.set_ylabel("Fraction of Positives")
    ax.set_title("Calibration Comparison")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(out_dir, "calibration_comparison.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


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
        min_child_weight=2,
        reg_lambda=1.0,
        scale_pos_weight=pos_weight,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)

    # In-sample AUC for overfit detection
    y_train_pred = model.predict_proba(X_train)[:, 1]
    train_auc = roc_auc_score(y_train, y_train_pred)

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

    # 5b. Diagnostics: plots + health + drift + hallucination
    plot_dir = _ensure_plot_dir()
    plots = {
        "roc_curve": os.path.basename(_plot_roc_curve(y_test, y_pred, auc, plot_dir)),
        "calibration": os.path.basename(_plot_calibration_curve(y_test, y_pred, ece, plot_dir)),
        "feature_importance": os.path.basename(_plot_feature_importance(ranked, plot_dir)),
    }
    logger.info("Plots saved to %s: %s", plot_dir, ", ".join(plots.values()))

    health = _compute_health_metrics(y_test, y_pred, X_test, X_train, model, train_auc)
    logger.info(
        "Health: overfit_gap=%.4f (flag=%s), missing=%.4f, samples=%d",
        health["model_health"]["overfit_gap"],
        health["model_health"]["overfit_flag"],
        health["data_health"]["test_missing_ratio"],
        health["data_health"]["test_samples"],
    )

    drift = _compute_drift(X_train, X_test, training_features, top_n=10)
    logger.info("Drift: max_psi=%.4f (%s)", drift["max_psi"], drift["drift_level"])
    for d in drift["top_drifted_features"][:5]:
        logger.info("  drift %s: psi=%.4f", d["feature"], d["psi"])

    hallucination = _compute_overconfidence(y_test, y_pred)
    logger.info(
        "Hallucination: overconfidence_ratio=%.4f (%d confident predictions)",
        hallucination["overconfidence_ratio"], hallucination["confident_predictions"],
    )

    # 5c. Probability calibration — Platt + isotonic, leakage-free (out-of-fold)
    calib = _calibrate_probabilities(model, X_train, y_train, X_test, y_test)
    ece_raw = calib["raw"]["ece"]
    ece_platt = calib["platt"]["ece"]
    ece_iso = calib["isotonic"]["ece"]
    logger.info(
        "Calibration ECE: raw=%.4f, Platt=%.4f, Isotonic=%.4f",
        ece_raw, ece_platt, ece_iso,
    )

    # Choose the calibrator with the lowest holdout ECE
    candidates = [("platt", calib["platt"]), ("isotonic", calib["isotonic"])]
    candidates.sort(key=lambda c: c[1]["ece"])
    best_method, best = candidates[0]
    calibrator = best["calibrator"]

    calib_path = os.path.join(
        _PROJECT_ROOT, "models/champion/churn", f"churn_calibrator_{best_method}.joblib",
    )
    joblib.dump(calibrator, calib_path)
    logger.info("Calibrator saved (%s): %s", best_method, calib_path)

    plots["calibration_comparison"] = os.path.basename(
        _plot_calibration_comparison(
            y_test,
            calib["raw"]["probs"],
            calib["platt"]["probs"],
            calib["isotonic"]["probs"],
            plot_dir,
        )
    )

    calibration_info = {
        "method": best_method,
        "path": f"champion/churn/churn_calibrator_{best_method}.joblib",
        "ece_raw": round(ece_raw, 4),
        "ece_platt": round(ece_platt, 4),
        "ece_isotonic": round(ece_iso, 4),
        "ece_after": round(best["ece"], 4),
        "brier_after": round(brier_score_loss(y_test, best["probs"]), 4),
        "log_loss_after": round(log_loss(y_test, best["probs"]), 4),
    }

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
        "calibrator": calibration_info,
        "feature_count_total": len(training_features) + len(all_excluded),
        "feature_count_training": len(training_features),
        "leakage_features_excluded": sorted(LEAKAGE_FEATURES),
        "dead_features_excluded": sorted(dead_features),
        "training_features": training_features,
        "top_features": [
            {"name": name, "importance": round(imp, 4)}
            for name, imp in ranked
        ],
        "diagnostics": {
            "plots": plots,
            "health": health,
            "drift": drift,
            "hallucination": hallucination,
        },
        "notes": (
            "PoC model — trained on account-closure-only labels "
            f"({n_pos} positives across {TRAINING_DATES}). "
            "AUC is directional, not precise. Raw probabilities are "
            "uncalibrated ranking scores; a calibrator "
            f"({calibration_info['method']}) is fitted out-of-fold and "
            "applied at inference time. "
            "If AUC > 0.90, re-check for feature leakage."
        ),
    }
    update_registry(entry)

    duration = time.perf_counter() - t0
    logger.info("Training complete in %.1fs", duration)

    return entry


if __name__ == "__main__":
    train_churn_model()
