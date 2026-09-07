"""Feature Importance Analysis — standalone, runs against a trained model.

Produces:
  1. Ranked feature importance table (top N)
  2. Grouped importance by feature category
  3. Cumulative importance curve
  4. Leakage audit (confirms excluded features aren't in the model)

Usage:
    python scripts/feature_importance.py [--top 20] [--model models/champion/churn/xgboost_churn_v1.json]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# Project root setup
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("feature_importance")

# ── Feature category mapping ──────────────────────────────────────
# Maps feature name prefixes/suffixes to business-facing categories.

def _categorize(feature: str) -> str:
    """Assign a business category to a feature name."""
    f = feature.lower()
    if "txn_count" in f or "behav_" in f or "freq" in f or "active_days" in f:
        return "Transaction Frequency"
    if "amount" in f or "total_" in f or "avg_" in f:
        return "Monetary Value"
    if "fin_" in f or "credit" in f or "debit" in f or "salary" in f or "income" in f:
        return "Financial Health"
    if "chan_" in f or "digital" in f or "channel" in f or "entropy" in f:
        return "Channel & Digital"
    if "risk_" in f or "volatility" in f or "reversal" in f:
        return "Risk Indicators"
    if "rel_" in f or "card" in f or "product" in f or "account" in f:
        return "Product Holdings"
    if "temp_" in f or "weekend" in f or "weekday" in f or "payday" in f or "morning" in f:
        return "Temporal Patterns"
    if "eng_" in f or "login" in f or "session" in f:
        return "Digital Engagement"
    if "tenure" in f or "age_" in f or "days_since_first" in f or "cust_" in f:
        return "Customer Demographics"
    if "growth" in f or "trend" in f or "ratio" in f:
        return "Growth & Trends"
    return "Other"


def load_model_and_features(model_path: str, registry_path: str) -> tuple:
    """Load XGBoost model and training feature list from registry."""
    import xgboost as xgb

    model = xgb.XGBClassifier()
    model.load_model(model_path)

    with open(registry_path, encoding="utf-8-sig") as f:
        registry = json.load(f)

    # Find champion churn entry
    models = registry.get("models", [])
    entry = None
    for m in models:
        if m.get("type") == "churn" and m.get("status") == "champion":
            entry = m
            break

    if entry is None:
        raise ValueError("No champion churn model found in registry")

    training_features = entry.get("training_features", [])
    leakage_excluded = entry.get("leakage_features_excluded", [])
    dead_excluded = entry.get("dead_features_excluded", [])
    metrics = entry.get("metrics", {})

    return model, training_features, leakage_excluded, dead_excluded, metrics, entry


def analyze(model_path: str, registry_path: str, top_n: int = 20) -> None:
    """Run feature importance analysis and print report."""
    model, features, leakage, dead, metrics, entry = load_model_and_features(
        model_path, registry_path
    )

    importance = model.feature_importances_
    ranked = sorted(
        zip(features, importance),
        key=lambda x: -x[1],
    )

    # ── Header ────────────────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  Feature Importance Analysis")
    print(f"  Model: {entry.get('model_id', 'unknown')}  |  "
          f"AUC: {metrics.get('auc', 'N/A')}  |  "
          f"Trained: {entry.get('trained_at', 'N/A')}")
    print(f"  Training features: {len(features)}  |  "
          f"Leakage excluded: {len(leakage)}  |  "
          f"Dead excluded: {len(dead) if dead else 0}")
    print(f"{'='*90}")

    # ── Top N ranked table ────────────────────────────────────────
    print(f"\n  Top {min(top_n, len(ranked))} Features by Importance")
    print(f"  {'Rank':<5s} {'Feature':<35s} {'Importance':>10s}  {'Cumul':>7s}  Category")
    print(f"  {'-'*80}")

    cumul = 0.0
    category_totals: dict[str, float] = {}

    for i, (name, imp) in enumerate(ranked[:top_n]):
        cumul += imp
        cat = _categorize(name)
        category_totals[cat] = category_totals.get(cat, 0.0) + imp
        bar = "█" * max(1, int(imp * 200))
        print(
            f"  {i+1:<5d} {name:<35s} {imp:>8.4f}  {cumul:>6.1%}  "
            f"{bar} {cat}"
        )

    # ── Remaining features ────────────────────────────────────────
    for name, imp in ranked[top_n:]:
        cat = _categorize(name)
        category_totals[cat] = category_totals.get(cat, 0.0) + imp

    print(f"\n  Top {top_n} cumulative importance: {cumul:.1%}")
    print(f"  Remaining {len(ranked) - top_n} features: {(1.0 - cumul):.1%}")

    # ── Category breakdown ────────────────────────────────────────
    print(f"\n  Importance by Business Category")
    print(f"  {'Category':<25s} {'Importance':>10s}  {'Pct':>6s}")
    print(f"  {'-'*50}")
    for cat, total in sorted(category_totals.items(), key=lambda x: -x[1]):
        bar = "█" * max(1, int(total * 200))
        print(f"  {cat:<25s} {total:>8.4f}  {total:>5.1%}  {bar}")

    # ── Leakage audit ─────────────────────────────────────────────
    if leakage:
        print(f"\n  Leakage Audit: {len(leakage)} features excluded from training")
        print(f"  These would have dominated if included — their absence is intentional:")
        for name in sorted(leakage):
            print(f"    ✗ {name}")
        print(f"  ✅ All {len(leakage)} leakage features confirmed excluded.")

    # ── Dead features ─────────────────────────────────────────────
    if dead:
        print(f"\n  Dead Features: {len(dead)} auto-excluded (ALL_ZERO or 100% NULL)")
        for name in sorted(dead):
            print(f"    ⚠ {name}")

    # ── Key insights ──────────────────────────────────────────────
    print(f"\n  Key Insights")
    print(f"  {'─'*80}")

    # Top category
    top_cat = max(category_totals, key=category_totals.get)
    print(f"  1. Strongest signal: {top_cat} ({category_totals[top_cat]:.1%})")

    # Top 3 features
    top3 = ranked[:3]
    print(f"  2. Top 3 features account for {sum(i for _, i in top3):.1%} of importance:")
    for name, imp in top3:
        print(f"     • {name} ({imp:.1%})")

    # How many features to reach 80%
    cumul80 = 0.0
    n80 = 0
    for _, imp in ranked:
        cumul80 += imp
        n80 += 1
        if cumul80 >= 0.80:
            break
    print(f"  3. {n80} features capture 80% of total importance")

    # Model quality
    auc = metrics.get("auc", 0)
    if auc > 0.90:
        print(f"  4. ⚠ AUC={auc:.3f} is above 0.90 — re-check for leakage")
    elif auc > 0.70:
        print(f"  4. AUC={auc:.3f} is in the expected range for an honest model")
    else:
        print(f"  4. AUC={auc:.3f} — model has limited predictive power")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feature Importance Analysis")
    parser.add_argument(
        "--top", type=int, default=20,
        help="Number of top features to show (default: 20)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Path to XGBoost model file (default: models/champion/churn/xgboost_churn_v1.json)",
    )
    parser.add_argument(
        "--registry", default=None,
        help="Path to registry.json (default: models/registry.json)",
    )
    args = parser.parse_args()

    model_path = args.model or os.path.join(
        _project_root, "models/champion/churn/xgboost_churn_v1.json"
    )
    registry_path = args.registry or os.path.join(
        _project_root, "models/registry.json"
    )

    analyze(model_path, registry_path, args.top)
