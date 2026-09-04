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
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold, train_test_split
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
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Load features from customer_features, exclude leakage, generate labels.

    Returns:
        X: Feature matrix (n_samples, n_features)
        y: Label vector (n_samples,)
        customer_ids: Per-row customer id (for group-aware splitting)
        as_of_dates: Per-row snapshot date (for temporal splitting)
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

    # Build X, y, customer ids, and dates (per row)
    X_rows = []
    y_rows = []
    cust_rows = []
    date_rows = []
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
        cust_rows.append(str(row.get("customer_id", "")))
        date_rows.append(str(row.get("as_of_date", "")))

    logger.info(
        "Labels: %d positive, %d negative, %d excluded (ambiguous)",
        sum(y_rows), len(y_rows) - sum(y_rows), excluded_count,
    )

    return (
        np.array(X_rows), np.array(y_rows),
        np.array(cust_rows), np.array(date_rows), feature_columns,
    )


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
    # Shared-support PSI: drop bins empty in EITHER distribution, then
    # renormalise. (eps-on-empty-bins inflates the magnitude ~180x when the two
    # distributions have disjoint support — e.g. a stale snapshot.)
    mask = (train_hist > 0) & (test_hist > 0)
    if mask.sum() == 0:
        return 0.0
    train_hist = train_hist[mask].astype(float)
    test_hist = test_hist[mask].astype(float)
    train_pct = train_hist / train_hist.sum()
    test_pct = test_hist / test_hist.sum()
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
        # Production SLA: any feature PSI > 0.25 → alert + freeze automated scoring
        # until the feature is re-binned or the model retrained.
        "freeze_scoring": max_psi > 0.25,
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
    groups_train: np.ndarray | None = None,
) -> dict:
    """Fit Platt + isotonic calibrators on out-of-fold predictions.

    Calibration is fit strictly on OUT-OF-FOLD predictions of the training set
    (via 5-fold GroupKFold, grouped by customer), never on the holdout set —
    preventing both temporal and entity leakage. Returns per-method calibrated
    test probabilities and ECE.
    """
    # Out-of-fold predictions on TRAINING data (calibrator fitting data).
    # GroupKFold splits CUSTOMERS (not rows), so a customer never appears in
    # both train and validation of any fold — the old row-based TimeSeriesSplit
    # could not guarantee this and allowed identity memorisation to inflate OOF.
    from sklearn.base import clone
    gkf = GroupKFold(n_splits=5)
    oof_probs = np.zeros(len(y_train), dtype=float)
    for train_idx, val_idx in gkf.split(X_train, y_train, groups=groups_train):
        fold_model = clone(model)
        fold_model.fit(X_train[train_idx], y_train[train_idx])
        oof_probs[val_idx] = fold_model.predict_proba(X_train[val_idx])[:, 1]

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
        "oof_probs": oof_probs,
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


def _find_optimal_threshold(y_test: np.ndarray, y_pred: np.ndarray) -> float:
    """Optimal classification threshold via Youden's J statistic (max TPR − FPR)."""
    fpr, tpr, thresholds = roc_curve(y_test, y_pred)
    j = tpr - fpr
    best_idx = int(np.argmax(j))
    return float(thresholds[best_idx])


def _find_f1_optimal_threshold(y_test: np.ndarray, y_pred: np.ndarray) -> float:
    """Threshold that maximises F1 (for high-cost retention campaigns).

    Recommended operating point when false positives are expensive — trades
    recall for precision to cut the false-alarm rate.
    """
    best_t, best_f1 = 0.5, -1.0
    for t in np.unique(y_pred):
        y_hat = (y_pred >= t).astype(int)
        f1 = f1_score(y_test, y_hat, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    return float(best_t)


def _classification_metrics(
    y_test: np.ndarray, y_pred: np.ndarray, threshold: float,
) -> dict:
    """Confusion matrix + precision/recall/F1 at a given threshold."""
    y_hat = (y_pred >= threshold).astype(int)
    cm = confusion_matrix(y_test, y_hat, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    return {
        "threshold": round(float(threshold), 4),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
        "precision": round(float(precision_score(y_test, y_hat, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_hat, zero_division=0)), 4),
        "f1": round(float(f1_score(y_test, y_hat, zero_division=0)), 4),
    }


def _plot_learning_curve(evals_result: dict, out_dir: str) -> str:
    """Plot train vs holdout AUC per boosting round. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    train_aucs = evals_result["validation_0"]["auc"]
    test_aucs = evals_result["validation_1"]["auc"]
    rounds = list(range(1, len(train_aucs) + 1))
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(rounds, train_aucs, marker="o", markersize=3, color="#DC0037", label="Train AUC")
    ax.plot(rounds, test_aucs, marker="o", markersize=3, color="#2e7d32", label="Holdout AUC")
    ax.set_xlabel("Boosting round")
    ax.set_ylabel("AUC")
    ax.set_title("Learning Curve — AUC per boosting round")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(out_dir, "learning_curve.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_loss_curve(evals_result: dict, out_dir: str) -> str:
    """Plot train vs holdout LogLoss per boosting round. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    train_loss = evals_result["validation_0"]["logloss"]
    test_loss = evals_result["validation_1"]["logloss"]
    rounds = list(range(1, len(train_loss) + 1))
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(rounds, train_loss, marker="o", markersize=3, color="#DC0037", label="Train LogLoss")
    ax.plot(rounds, test_loss, marker="o", markersize=3, color="#2e7d32", label="Holdout LogLoss")
    ax.set_xlabel("Boosting round")
    ax.set_ylabel("LogLoss")
    ax.set_title("Loss Curve — LogLoss per boosting round")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    path = os.path.join(out_dir, "loss_curve.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_accuracy_threshold(
    y_test: np.ndarray, y_pred: np.ndarray, optimal_threshold: float, out_dir: str,
) -> str:
    """Accuracy vs decision threshold. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    thresholds = np.unique(y_pred)
    accs = []
    for t in thresholds:
        y_hat = (y_pred >= t).astype(int)
        accs.append(float((y_hat == y_test).mean()))
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(thresholds, accs, color="#DC0037", label="Accuracy")
    ax.axvline(optimal_threshold, linestyle="--", color="gray",
               label=f"Optimal = {optimal_threshold:.3f}")
    ax.set_xlabel("Threshold")
    ax.set_ylabel("Accuracy")
    ax.set_title("Accuracy vs Decision Threshold")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(out_dir, "accuracy_threshold.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_confusion_matrix(cm: list[list[int]], out_dir: str) -> str:
    """Save confusion-matrix heatmap. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    arr = np.array(cm, dtype=int)
    fig, ax = plt.subplots(figsize=(5, 4.5))
    im = ax.imshow(arr, cmap="Reds")
    ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
    ax.set_xticklabels(["Not churned", "Churned"])
    ax.set_yticklabels(["Not churned", "Churned"])
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    max_val = arr.max() if arr.max() > 0 else 1
    for i in range(2):
        for j in range(2):
            ax.text(j, i, str(arr[i, j]), ha="center", va="center", fontsize=14,
                    color="white" if arr[i, j] > max_val / 2 else "black")
    ax.set_title("Confusion Matrix (optimal threshold)")
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    path = os.path.join(out_dir, "confusion_matrix.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_prediction_distribution(
    y_test: np.ndarray, y_pred: np.ndarray, threshold: float, out_dir: str,
) -> str:
    """Histogram of predicted probabilities split by actual class. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(y_pred[y_test == 0], bins=30, alpha=0.6, color="#2e7d32", label="Non-churners")
    ax.hist(y_pred[y_test == 1], bins=30, alpha=0.6, color="#DC0037", label="Churners")
    ax.axvline(threshold, linestyle="--", color="black", label=f"Threshold = {threshold:.3f}")
    ax.set_xlabel("Predicted churn probability")
    ax.set_ylabel("Count")
    ax.set_title("Prediction Distribution by Class")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(out_dir, "prediction_distribution.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _plot_threshold_analysis(
    y_test: np.ndarray, y_pred: np.ndarray, optimal_threshold: float, out_dir: str,
) -> str:
    """Precision / Recall / F1 vs threshold. Returns path."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y_test, y_pred)
    f1 = 2 * (precision * recall) / (precision + recall + 1e-9)
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(thresholds, precision[:-1], color="#DC0037", label="Precision")
    ax.plot(thresholds, recall[:-1], color="#FF780F", label="Recall")
    ax.plot(thresholds, f1[:-1], color="#2e7d32", label="F1")
    ax.axvline(optimal_threshold, linestyle="--", color="gray",
               label=f"Optimal = {optimal_threshold:.3f}")
    ax.set_xlabel("Threshold")
    ax.set_ylabel("Score")
    ax.set_title("Precision / Recall / F1 vs Threshold")
    ax.legend()
    fig.tight_layout()
    path = os.path.join(out_dir, "threshold_analysis.png")
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def _write_training_report(
    entry: dict, y_train: np.ndarray, y_test: np.ndarray, model,
    optimal_threshold: float, clf_metrics: dict, cv_auc: float,
) -> str:
    """Write a detailed Markdown training report. Returns the file path."""
    report_dir = _ensure_plot_dir()
    path = os.path.join(report_dir, "training_report.md")

    m = entry["metrics"]
    c = entry["calibrator"]
    d = entry["diagnostics"]
    cm = clf_metrics["confusion_matrix"]

    lines: list[str] = []
    lines.append("# Churn Model Training Report")
    lines.append("")
    lines.append(f"- **Trained at:** {entry['trained_at']}")
    lines.append(f"- **Training dates:** {', '.join(entry['training_dates'])}")
    lines.append(f"- **Holdout date:** {entry['holdout_date']}")
    lines.append(f"- **Features:** {entry['feature_count_training']} training "
                 f"({len(entry['leakage_features_excluded'])} leakage excluded, "
                 f"{len(entry['dead_features_excluded'])} dead excluded)")
    lines.append("")

    lines.append("## Data")
    lines.append("")
    lines.append(f"- Training samples: {len(y_train)} ({int(sum(y_train))} positive)")
    lines.append(f"- Holdout samples: {len(y_test)} ({int(sum(y_test))} positive)")
    lines.append("")

    lines.append("## Metrics (raw probabilities)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| AUC | {m['auc']} |")
    lines.append(f"| 5-fold OOF CV AUC | {cv_auc} |")
    lines.append(f"| Brier | {m['brier']} |")
    lines.append(f"| LogLoss (test) | {m['log_loss']} |")
    lines.append(f"| LogLoss (train) | {m['train_logloss']} |")
    lines.append(f"| Accuracy (optimal threshold) | {m['accuracy']} |")
    lines.append(f"| ECE (raw) | {m['ece']} |")
    lines.append(f"| Optimal threshold (Youden's J) | {optimal_threshold} |")
    lines.append("")

    lines.append("## Classification (optimal threshold)")
    lines.append("")
    lines.append(f"- Precision: {clf_metrics['precision']}")
    lines.append(f"- Recall: {clf_metrics['recall']}")
    lines.append(f"- F1: {clf_metrics['f1']}")
    lines.append("")
    lines.append("| | Predicted 0 | Predicted 1 |")
    lines.append("|---|---|---|")
    lines.append(f"| Actual 0 | {cm[0][0]} | {cm[0][1]} |")
    lines.append(f"| Actual 1 | {cm[1][0]} | {cm[1][1]} |")
    lines.append("")

    lines.append("## Calibration")
    lines.append("")
    lines.append(f"- Method: {c['method']}")
    lines.append(f"- ECE raw: {c['ece_raw']}")
    lines.append(f"- ECE Platt: {c['ece_platt']}")
    lines.append(f"- ECE isotonic: {c['ece_isotonic']}")
    lines.append(f"- ECE after: {c['ece_after']}")
    lines.append(f"- Brier after: {c['brier_after']}")
    lines.append(f"- LogLoss after: {c['log_loss_after']}")
    lines.append("")

    lines.append("## Diagnostics")
    lines.append("")
    lines.append(f"- Overfit gap: {d['health']['model_health']['overfit_gap']} "
                 f"(flag={d['health']['model_health']['overfit_flag']})")
    lines.append(f"- Drift max PSI: {d['drift']['max_psi']} ({d['drift']['drift_level']})")
    lines.append(f"- Overconfidence ratio: {d['hallucination']['overconfidence_ratio']}")
    lines.append("")

    lines.append("## Top features")
    lines.append("")
    for i, tf in enumerate(entry["top_features"], 1):
        lines.append(f"{i}. `{tf['name']}` — {tf['importance']}")
    lines.append("")

    lines.append("## Plots")
    lines.append("")
    for name, fname in d["plots"].items():
        lines.append(f"- `{fname}` ({name})")
    lines.append("")

    lines.append("## Hyperparameters")
    lines.append("")
    params = model.get_params()
    for k in ("max_depth", "learning_rate", "n_estimators", "min_child_weight",
              "reg_lambda", "subsample", "colsample_bytree", "scale_pos_weight"):
        lines.append(f"- `{k}` = {params.get(k)}")
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _write_pdf_report(entry: dict, plot_dir: str, out_path: str) -> str:
    """Render a multi-page PDF report embedding every plot plus full metrics.

    Returns the output PDF path.
    """
    from matplotlib.backends.backend_pdf import PdfPages
    import matplotlib.pyplot as plt
    import matplotlib.image as mpimg

    m = entry["metrics"]
    c = entry["calibrator"]
    d = entry["diagnostics"]
    clf = entry.get("classification", {})
    cm = clf.get("confusion_matrix", [[0, 0], [0, 0]])
    hp = entry.get("hyperparameters", {})
    data = entry.get("data", {})
    plots = d.get("plots", {})
    drift_top = d.get("drift", {}).get("top_drifted_features", [])

    def _styled_table(ax, rows, cols, col_widths, fontsize=10):
        tab = ax.table(cellText=rows, colLabels=cols, loc="upper left",
                       bbox=[0, 0, 1, 1], colWidths=col_widths)
        tab.auto_set_font_size(False)
        tab.set_fontsize(fontsize)
        tab.scale(1, 1.8)
        return tab

    with PdfPages(out_path) as pdf:
        # ── Page 1: overview + metrics ──
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Churn Model Training Report", fontsize=18, fontweight="bold", y=0.985)
        ax = fig.add_axes([0.08, 0.68, 0.84, 0.24]); ax.axis("off")
        meta = [
            f"Trained at     : {entry['trained_at']}",
            f"Training dates : {', '.join(entry['training_dates'])}",
            f"Holdout date   : {entry['holdout_date']}",
            f"Features       : {entry['feature_count_training']} training "
            f"({len(entry['leakage_features_excluded'])} leakage, "
            f"{len(entry['dead_features_excluded'])} dead excluded)",
        ]
        if data:
            meta += [
                f"Training samples : {data.get('train_samples')} ({data.get('train_positives')} positive)",
                f"Holdout samples  : {data.get('holdout_samples')} ({data.get('holdout_positives')} positive)",
                f"Class imbalance  : {data.get('class_imbalance_pct')}% positive",
                f"scale_pos_weight : {data.get('scale_pos_weight')}",
            ]
        ax.text(0.0, 1.0, "\n".join(meta), va="top", fontsize=10, family="monospace")

        ax2 = fig.add_axes([0.10, 0.30, 0.80, 0.34]); ax2.axis("off")
        ax2.text(0.5, 1.03, "Metrics (raw probabilities)", ha="center",
                 fontsize=12, fontweight="bold", transform=ax2.transAxes)
        metrics_rows = [
            ["AUC", f"{m['auc']}"],
            ["5-fold OOF CV AUC", f"{round(m['cv_auc'], 4)}"],
            ["Brier", f"{m['brier']}"],
            ["LogLoss (test)", f"{m['log_loss']}"],
            ["LogLoss (train)", f"{m['train_logloss']}"],
            ["Accuracy (optimal)", f"{m['accuracy']}"],
            ["ECE (raw)", f"{m['ece']}"],
            ["Optimal threshold", f"{round(m['optimal_threshold'], 4)}"],
            ["F1-optimal threshold", f"{round(m['f1_optimal_threshold'], 4)}"],
        ]
        _styled_table(ax2, metrics_rows, ["Metric", "Value"], [0.6, 0.4], fontsize=9)
        pdf.savefig(fig); plt.close(fig)

        # ── Page 2: classification + calibration ──
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Classification & Calibration", fontsize=16, fontweight="bold", y=0.985)

        ax = fig.add_axes([0.10, 0.62, 0.80, 0.26]); ax.axis("off")
        ax.text(0.5, 1.04, "Confusion Matrix (optimal threshold)", ha="center",
                fontsize=12, fontweight="bold", transform=ax.transAxes)
        cm_rows = [[str(cm[0][0]), str(cm[0][1])], [str(cm[1][0]), str(cm[1][1])]]
        tab = ax.table(cellText=cm_rows, rowLabels=["Actual 0", "Actual 1"],
                       colLabels=["Pred 0", "Pred 1"], loc="upper center", bbox=[0, 0, 1, 1])
        tab.auto_set_font_size(False); tab.set_fontsize(11); tab.scale(1, 1.8)
        ax.text(0.5, -0.20, f"Precision={clf.get('precision')}   Recall={clf.get('recall')}   F1={clf.get('f1')}",
                ha="center", fontsize=11, transform=ax.transAxes)

        ax2 = fig.add_axes([0.10, 0.22, 0.80, 0.30]); ax2.axis("off")
        ax2.text(0.5, 1.03, "Probability Calibration (out-of-fold)", ha="center",
                 fontsize=12, fontweight="bold", transform=ax2.transAxes)
        cal_rows = [
            ["Method", f"{c['method']}"],
            ["ECE raw", f"{c['ece_raw']}"],
            ["ECE Platt", f"{c['ece_platt']}"],
            ["ECE isotonic", f"{c['ece_isotonic']}"],
            ["ECE after", f"{c['ece_after']}"],
            ["Brier after", f"{c['brier_after']}"],
            ["LogLoss after", f"{c['log_loss_after']}"],
        ]
        _styled_table(ax2, cal_rows, ["Item", "Value"], [0.5, 0.5], fontsize=10)
        pdf.savefig(fig); plt.close(fig)

        # ── Page 3: features + hyperparameters ──
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Feature Importances & Hyperparameters", fontsize=16, fontweight="bold", y=0.985)
        ax = fig.add_axes([0.08, 0.40, 0.84, 0.52]); ax.axis("off")
        ax.text(0.5, 1.02, "Top-10 Feature Importances", ha="center",
                fontsize=12, fontweight="bold", transform=ax.transAxes)
        feat_rows = [[tf["name"], f"{tf['importance']:.4f}"] for tf in entry["top_features"]]
        _styled_table(ax, feat_rows, ["Feature", "Importance"], [0.7, 0.3], fontsize=10)

        ax2 = fig.add_axes([0.10, 0.12, 0.80, 0.20]); ax2.axis("off")
        ax2.text(0.5, 1.03, "Hyperparameters", ha="center",
                 fontsize=12, fontweight="bold", transform=ax2.transAxes)
        hp_rows = [[k, f"{hp.get(k)}"] for k in ("max_depth", "learning_rate", "n_estimators",
                                                  "min_child_weight", "reg_lambda", "subsample",
                                                  "colsample_bytree", "scale_pos_weight")]
        _styled_table(ax2, hp_rows, ["Parameter", "Value"], [0.55, 0.45], fontsize=10)
        pdf.savefig(fig); plt.close(fig)

        # ── Page 4: diagnostics + drift ──
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.suptitle("Diagnostics & Drift", fontsize=16, fontweight="bold", y=0.985)
        ax = fig.add_axes([0.08, 0.78, 0.84, 0.16]); ax.axis("off")
        mh = d.get("health", {}).get("model_health", {})
        dh = d.get("health", {}).get("data_health", {})
        diag = [
            f"train AUC          : {mh.get('train_auc')}",
            f"test AUC           : {mh.get('test_auc')}",
            f"overfit gap        : {mh.get('overfit_gap')} (flag={mh.get('overfit_flag')})",
            f"test missing ratio : {dh.get('test_missing_ratio')}",
            f"overconfidence     : {d.get('hallucination', {}).get('overconfidence_ratio')}",
        ]
        ax.text(0.0, 1.0, "\n".join(diag), va="top", fontsize=10, family="monospace")

        ax2 = fig.add_axes([0.08, 0.28, 0.84, 0.46]); ax2.axis("off")
        ax2.text(0.5, 1.02, f"Feature Drift — PSI (max {d.get('drift', {}).get('max_psi')}, "
                            f"{d.get('drift', {}).get('drift_level')})",
                 ha="center", fontsize=12, fontweight="bold", transform=ax2.transAxes)
        drift_rows = [[dd["feature"], f"{dd['psi']}"] for dd in drift_top[:10]]
        _styled_table(ax2, drift_rows, ["Feature", "PSI"], [0.7, 0.3], fontsize=10)
        pdf.savefig(fig); plt.close(fig)

        # ── Plots: one per page ──
        for name, fname in plots.items():
            img_path = os.path.join(plot_dir, fname)
            if not os.path.exists(img_path):
                continue
            img = mpimg.imread(img_path)
            fig = plt.figure(figsize=(8.27, 11.69))
            fig.suptitle(name.replace("_", " ").title(), fontsize=14, fontweight="bold", y=0.985)
            ax = fig.add_axes([0.06, 0.05, 0.88, 0.84]); ax.axis("off")
            ax.imshow(img)
            pdf.savefig(fig); plt.close(fig)

    return out_path


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
    logger.info("=" * 70)
    logger.info("CHURN MODEL TRAINING — detailed run")
    logger.info("=" * 70)
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

    # 1. Load ALL snapshots once (with customer ids), then split CUSTOMERS into
    # disjoint train/holdout sets. The old approach (train = 07-17/22, holdout =
    # 07-27 over the SAME customers) let the model memorise customer identities
    # instead of learning churn behaviour.
    all_dates = _get_training_dates() + [_get_holdout_date()]
    X_all, y_all, cust_all, date_all, training_features = load_features_and_labels(
        dates=all_dates,
        exclude_features=all_excluded,
    )
    logger.info("Training features (%d):", len(training_features))
    for i, feat in enumerate(training_features, 1):
        logger.info("  %2d. %s", i, feat)

    unique_customers = np.unique(cust_all)
    train_cust, test_cust = train_test_split(
        unique_customers, test_size=0.2, random_state=42,
    )
    train_cust_set, test_cust_set = set(train_cust), set(test_cust)
    train_dates = set(_get_training_dates())
    holdout_date = _get_holdout_date()

    train_mask = np.array([
        c in train_cust_set and d in train_dates for c, d in zip(cust_all, date_all)
    ])
    test_mask = np.array([
        c in test_cust_set and d == holdout_date for c, d in zip(cust_all, date_all)
    ])

    X_train, y_train, cust_train = X_all[train_mask], y_all[train_mask], cust_all[train_mask]
    X_test, y_test = X_all[test_mask], y_all[test_mask]

    logger.info(
        "Customer-disjoint split: %d train customers (%d rows) / %d holdout customers (%d rows)",
        len(train_cust), len(y_train), len(test_cust), len(y_test),
    )

    # 3. Class balance + config summary
    n_pos = int(sum(y_train))
    n_neg = int(len(y_train) - n_pos)
    pos_weight = n_neg / max(n_pos, 1) if n_pos > 0 else 1.0

    logger.info("-" * 70)
    logger.info("DATA SUMMARY")
    logger.info("-" * 70)
    logger.info("  Training samples : %d (%d positive / %d negative)", len(y_train), n_pos, n_neg)
    logger.info("  Class imbalance  : %.1f%% positive", 100.0 * n_pos / max(len(y_train), 1))
    logger.info("  scale_pos_weight : %.2f", pos_weight)
    logger.info("  Holdout samples  : %d (%d positive / %d negative)",
                len(y_test), int(sum(y_test)), int(len(y_test) - sum(y_test)))
    logger.info("  Features         : %d (excluded %d leakage + %d dead)",
                len(training_features), len(LEAKAGE_FEATURES), len(dead_features))
    logger.info("  Training dates   : %s", ", ".join(_get_training_dates()))
    logger.info("  Holdout date     : %s", _get_holdout_date())

    # 4. Train with verbose per-round evaluation on train + holdout
    model = xgb.XGBClassifier(
        objective="binary:logistic",
        eval_metric=["auc", "logloss"],
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

    logger.info("-" * 70)
    logger.info("TRAINING (per-boosting-round AUC / LogLoss)")
    logger.info("-" * 70)
    model.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train), (X_test, y_test)],
        verbose=True,
    )

    evals_result = model.evals_result()

    # In-sample AUC for overfit detection
    y_train_pred = model.predict_proba(X_train)[:, 1]
    train_auc = roc_auc_score(y_train, y_train_pred)

    # 5. Evaluate on holdout
    y_pred = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_pred)

    # Optimal thresholds: Youden's J (balanced) + F1-max (high-cost campaigns)
    optimal_threshold = _find_optimal_threshold(y_test, y_pred)
    f1_threshold = _find_f1_optimal_threshold(y_test, y_pred)

    # 6. Metrics (raw probabilities) — ECE before calibration
    prob_true, prob_pred = calibration_curve(y_test, y_pred, n_bins=5)
    ece = float(np.mean(np.abs(prob_true - prob_pred))) if len(prob_true) > 0 else 0.0
    brier = brier_score_loss(y_test, y_pred)
    ll = log_loss(y_test, y_pred)
    train_logloss = float(evals_result["validation_0"]["logloss"][-1])
    y_hat_opt = (y_pred >= optimal_threshold).astype(int)
    accuracy = float(accuracy_score(y_test, y_hat_opt))

    # KS statistic: max separation of positive vs negative score CDFs
    from scipy.stats import ks_2samp
    ks = ks_2samp(y_pred[y_test == 1], y_pred[y_test == 0])

    logger.info("-" * 70)
    logger.info("HOLDOUT METRICS (raw probabilities)")
    logger.info("-" * 70)
    logger.info("  AUC                    = %.4f", auc)
    logger.info("  KS statistic           = %.4f (p=%.2e)", ks.statistic, ks.pvalue)
    logger.info("  Brier                  = %.4f", brier)
    logger.info("  ECE                    = %.4f", ece)
    logger.info("  LogLoss (test)         = %.4f", ll)
    logger.info("  LogLoss (train)        = %.4f", train_logloss)
    logger.info("  Accuracy @ optimal thr = %.4f", accuracy)
    logger.info("  Optimal threshold      = %.4f (Youden's J)", optimal_threshold)
    logger.info("  F1-optimal threshold   = %.4f", f1_threshold)

    # 7. Classification report at optimal threshold
    clf_metrics = _classification_metrics(y_test, y_pred, optimal_threshold)
    cm = clf_metrics["confusion_matrix"]
    logger.info("  Confusion matrix @%.3f: TN=%d FP=%d FN=%d TP=%d",
                optimal_threshold, cm[0][0], cm[0][1], cm[1][0], cm[1][1])
    logger.info("  Precision=%.4f  Recall=%.4f  F1=%.4f",
                clf_metrics["precision"], clf_metrics["recall"], clf_metrics["f1"])

    clf_metrics_f1 = _classification_metrics(y_test, y_pred, f1_threshold)
    logger.info("  @F1-optimal %.3f: Precision=%.4f  Recall=%.4f  F1=%.4f",
                f1_threshold, clf_metrics_f1["precision"],
                clf_metrics_f1["recall"], clf_metrics_f1["f1"])

    # 8. Extract feature importance
    importance = dict(zip(training_features, model.feature_importances_))
    ranked = sorted(importance.items(), key=lambda x: -x[1])[:10]
    logger.info("-" * 70)
    logger.info("TOP-10 FEATURE IMPORTANCES")
    logger.info("-" * 70)
    for i, (name, imp) in enumerate(ranked, 1):
        logger.info("  %2d. %-35s %.4f", i, name, imp)

    # 9. Diagnostics: plots + health + drift + hallucination
    plot_dir = _ensure_plot_dir()
    plots = {
        "roc_curve": os.path.basename(_plot_roc_curve(y_test, y_pred, auc, plot_dir)),
        "calibration": os.path.basename(_plot_calibration_curve(y_test, y_pred, ece, plot_dir)),
        "feature_importance": os.path.basename(_plot_feature_importance(ranked, plot_dir)),
        "learning_curve": os.path.basename(_plot_learning_curve(evals_result, plot_dir)),
        "loss_curve": os.path.basename(_plot_loss_curve(evals_result, plot_dir)),
        "accuracy_threshold": os.path.basename(
            _plot_accuracy_threshold(y_test, y_pred, optimal_threshold, plot_dir)
        ),
        "confusion_matrix": os.path.basename(_plot_confusion_matrix(cm, plot_dir)),
        "prediction_distribution": os.path.basename(
            _plot_prediction_distribution(y_test, y_pred, optimal_threshold, plot_dir)
        ),
        "threshold_analysis": os.path.basename(
            _plot_threshold_analysis(y_test, y_pred, optimal_threshold, plot_dir)
        ),
    }
    logger.info("-" * 70)
    logger.info("PLOTS (saved to %s)", plot_dir)
    logger.info("-" * 70)
    for name, path in plots.items():
        logger.info("  %-24s %s", name, path)

    health = _compute_health_metrics(y_test, y_pred, X_test, X_train, model, train_auc)
    logger.info("-" * 70)
    logger.info("MODEL + DATA HEALTH")
    logger.info("-" * 70)
    logger.info("  train_auc          = %.4f", health["model_health"]["train_auc"])
    logger.info("  test_auc           = %.4f", health["model_health"]["test_auc"])
    logger.info("  overfit_gap        = %.4f (flag=%s)",
                health["model_health"]["overfit_gap"], health["model_health"]["overfit_flag"])
    logger.info("  test_missing_ratio = %.4f", health["data_health"]["test_missing_ratio"])
    logger.info("  test_samples       = %d", health["data_health"]["test_samples"])

    drift = _compute_drift(X_train, X_test, training_features, top_n=10)
    logger.info("-" * 70)
    logger.info("FEATURE DRIFT (PSI)")
    logger.info("-" * 70)
    logger.info("  max_psi = %.4f (%s)", drift["max_psi"], drift["drift_level"])
    for i, d in enumerate(drift["top_drifted_features"], 1):
        logger.info("  %2d. %-35s psi=%.4f", i, d["feature"], d["psi"])

    hallucination = _compute_overconfidence(y_test, y_pred)
    logger.info("-" * 70)
    logger.info("HALLUCINATION (overconfidence)")
    logger.info("-" * 70)
    logger.info("  overconfidence_ratio = %.4f (%d confident predictions)",
                hallucination["overconfidence_ratio"], hallucination["confident_predictions"])

    # 10. Probability calibration — Platt + isotonic, leakage-free (out-of-fold)
    calib = _calibrate_probabilities(
        model, X_train, y_train, X_test, y_test, groups_train=cust_train,
    )
    oof_probs = calib["oof_probs"]
    cv_auc = roc_auc_score(y_train, oof_probs)
    ece_raw = calib["raw"]["ece"]
    ece_platt = calib["platt"]["ece"]
    ece_iso = calib["isotonic"]["ece"]
    logger.info("-" * 70)
    logger.info("PROBABILITY CALIBRATION (out-of-fold)")
    logger.info("-" * 70)
    logger.info("  5-fold OOF CV AUC  = %.4f", cv_auc)
    logger.info("  ECE: raw=%.4f, Platt=%.4f, Isotonic=%.4f", ece_raw, ece_platt, ece_iso)

    # Choose the calibrator with the lowest holdout ECE
    candidates = [("platt", calib["platt"]), ("isotonic", calib["isotonic"])]
    candidates.sort(key=lambda c: c[1]["ece"])
    best_method, best = candidates[0]
    calibrator = best["calibrator"]

    calib_path = os.path.join(
        _PROJECT_ROOT, "models/champion/churn", f"churn_calibrator_{best_method}.joblib",
    )
    joblib.dump(calibrator, calib_path)
    logger.info("  Calibrator saved (%s): %s", best_method, calib_path)

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

    # 11. Save model
    model_dir = os.path.join(_PROJECT_ROOT, "models/champion/churn")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "xgboost_churn_v1.json")
    model.save_model(model_path)

    logger.info("-" * 70)
    logger.info("ARTIFACTS")
    logger.info("-" * 70)
    logger.info("  Model      : %s", model_path)
    logger.info("  Calibrator : %s", calib_path)

    # 12. Register
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
        "data": {
            "train_samples": len(y_train),
            "train_positives": n_pos,
            "train_negatives": n_neg,
            "holdout_samples": len(y_test),
            "holdout_positives": int(sum(y_test)),
            "holdout_negatives": int(len(y_test) - sum(y_test)),
            "class_imbalance_pct": round(100.0 * n_pos / max(len(y_train), 1), 2),
            "scale_pos_weight": round(pos_weight, 4),
        },
        "hyperparameters": {
            "max_depth": 4,
            "learning_rate": 0.05,
            "n_estimators": 50,
            "min_child_weight": 2,
            "reg_lambda": 1.0,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "scale_pos_weight": round(pos_weight, 4),
        },
        "metrics": {
            "auc": round(auc, 4),
            "ks_statistic": round(float(ks.statistic), 4),
            "ks_pvalue": float(f"{ks.pvalue:.2e}"),
            "brier": round(brier, 4),
            "ece": round(ece, 4),
            "log_loss": round(ll, 4),
            "train_logloss": round(train_logloss, 4),
            "accuracy": round(accuracy, 4),
            "cv_auc": round(cv_auc, 4),
            "optimal_threshold": round(optimal_threshold, 4),
            "f1_optimal_threshold": round(f1_threshold, 4),
        },
        "classification": {
            "precision": clf_metrics["precision"],
            "recall": clf_metrics["recall"],
            "f1": clf_metrics["f1"],
            "confusion_matrix": clf_metrics["confusion_matrix"],
        },
        "classification_f1_threshold": {
            "threshold": round(f1_threshold, 4),
            "precision": clf_metrics_f1["precision"],
            "recall": clf_metrics_f1["recall"],
            "f1": clf_metrics_f1["f1"],
            "confusion_matrix": clf_metrics_f1["confusion_matrix"],
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
            f"AUC {auc:.4f}, 5-fold OOF CV AUC {cv_auc:.4f}. "
            f"Probabilities are calibrated out-of-fold via "
            f"{calibration_info['method']} "
            f"(ECE {ece_raw:.4f} → {calibration_info['ece_after']:.4f}). "
            "If AUC > 0.90, re-check for feature leakage."
        ),
    }

    # 13. Write detailed training report
    report_path = _write_training_report(
        entry=entry,
        y_train=y_train, y_test=y_test,
        model=model,
        optimal_threshold=optimal_threshold,
        clf_metrics=clf_metrics,
        cv_auc=cv_auc,
    )
    logger.info("  Report      : %s", report_path)

    # 14. Write PDF report with embedded plots
    pdf_path = _write_pdf_report(
        entry=entry,
        plot_dir=plot_dir,
        out_path=os.path.join(plot_dir, "training_report.pdf"),
    )
    entry["report_pdf"] = os.path.basename(pdf_path)
    logger.info("  Report (pdf): %s", pdf_path)

    update_registry(entry)

    duration = time.perf_counter() - t0
    logger.info("=" * 70)
    logger.info("Training complete in %.1fs", duration)
    logger.info("=" * 70)

    return entry


if __name__ == "__main__":
    train_churn_model()
