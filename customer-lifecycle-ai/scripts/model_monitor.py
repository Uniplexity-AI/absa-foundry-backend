"""Model Monitoring Report — tracks prediction health and data quality over time.

Detects:
  1. Churn prediction distribution shifts
  2. Health score trends
  3. Feature drift (PSI / distribution change)
  4. Missing feature counts
  5. Model confidence distribution
  6. State distribution changes

Usage:
    python scripts/model_monitor.py [--dates 2026-07-17,2026-07-22,2026-07-27]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

import psycopg2
from psycopg2 import extras
from shared.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("model_monitor")


def _psi(expected: list[float], actual: list[float], bins: int = 10) -> float:
    """Population Stability Index — measures distribution shift. <0.1 = stable."""
    import numpy as np
    if len(expected) < bins or len(actual) < bins:
        return 0.0
    all_vals = expected + actual
    bin_edges = np.linspace(min(all_vals), max(all_vals), bins + 1)
    e_hist, _ = np.histogram(expected, bins=bin_edges)
    a_hist, _ = np.histogram(actual, bins=bin_edges)
    e_pct = e_hist / max(sum(e_hist), 1)
    a_pct = a_hist / max(sum(a_hist), 1)
    e_pct = np.clip(e_pct, 0.0001, None)
    a_pct = np.clip(a_pct, 0.0001, None)
    return float(np.sum((a_pct - e_pct) * np.log(a_pct / e_pct)))


def _drift_label(psi: float) -> str:
    if psi < 0.1:
        return "STABLE"
    elif psi < 0.25:
        return "MODERATE"
    return "SIGNIFICANT"


def monitor(dates: list[str]) -> None:
    conn = psycopg2.connect(
        settings.database_target_url_sync,
        connect_timeout=10,
        keepalives=1, keepalives_idle=30,
        keepalives_interval=10, keepalives_count=3,
    )
    cur = conn.cursor(cursor_factory=extras.RealDictCursor)

    print(f"\n{'='*85}")
    print(f"  Model Monitoring Report")
    print(f"  Dates: {', '.join(dates)}  |  {len(dates)} snapshots")
    print(f"{'='*85}")

    # ── 1. Churn prediction distribution ──────────────────────────
    #    churn_prob is NOT stored in customer_states — only health_score is.
    #    We approximate from the health_score component (churn_risk_sub).
    print(f"\n  ── Health Score Distribution (churn-driven) ──")
    print(f"  {'Date':<12s} {'Min':>6s} {'P25':>6s} {'Median':>6s} "
          f"{'P75':>6s} {'Max':>6s} {'Mean':>6s} {'Std':>6s}")
    print(f"  {'-'*60}")

    health_data: dict[str, list[float]] = {}
    churn_sub_data: dict[str, list[float]] = {}
    for dt in dates:
        cur.execute("""
            SELECT health_score,
                   (component_scores->>'churn_risk_sub')::float AS churn_sub
            FROM customer_states
            WHERE as_of_date = %s AND health_score IS NOT NULL
        """, (dt,))
        rows = cur.fetchall()
        health_vals = [float(r["health_score"]) for r in rows if r["health_score"] is not None]
        churn_vals = [r["churn_sub"] for r in rows if r["churn_sub"] is not None]
        health_data[dt] = health_vals

        if health_vals:
            import numpy as np
            arr = np.array(health_vals)
            print(f"  {dt:<12s} {arr.min():.1f}  {np.percentile(arr,25):.1f}  "
                  f"{np.median(arr):.1f}  {np.percentile(arr,75):.1f}  "
                  f"{arr.max():.1f}  {arr.mean():.1f}  {arr.std():.1f}")

    # PSI on health scores vs baseline
    if len(dates) > 1:
        baseline = dates[0]
        print(f"\n  Health Score PSI vs {baseline}:")
        for dt in dates[1:]:
            if health_data[baseline] and health_data[dt]:
                psi = _psi(health_data[baseline], health_data[dt])
                print(f"    {dt}: PSI={psi:.4f} ({_drift_label(psi)})")

    # ── 2. Health score trend ─────────────────────────────────────
    print(f"\n  ── Health Score Trend ──")
    print(f"  {'Date':<12s} {'Count':>6s} {'Mean':>7s} {'Median':>7s} "
          f"{'Healthy%':>8s} {'AtRisk%':>8s} {'Critical%':>9s}")
    print(f"  {'-'*60}")

    for dt in dates:
        cur.execute("""
            SELECT
                COUNT(*) AS n,
                ROUND(AVG(health_score)::numeric, 1) AS mean,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY health_score)::numeric, 1) AS median,
                COUNT(*) FILTER (WHERE health_score >= 70) * 100.0 / NULLIF(COUNT(*),0) AS healthy,
                COUNT(*) FILTER (WHERE health_score >= 40 AND health_score < 70) * 100.0 / NULLIF(COUNT(*),0) AS atrisk,
                COUNT(*) FILTER (WHERE health_score < 40) * 100.0 / NULLIF(COUNT(*),0) AS critical
            FROM customer_states
            WHERE as_of_date = %s AND health_score IS NOT NULL
        """, (dt,))
        r = cur.fetchone()
        if r and r["n"]:
            print(f"  {dt:<12s} {r['n']:>6d} {r['mean']:>7.1f} {r['median']:>7.1f} "
                  f"{r['healthy']:>7.1f}% {r['atrisk']:>7.1f}% {r['critical']:>8.1f}%")

    # ── 3. State distribution stability ───────────────────────────
    print(f"\n  ── State Distribution ──")
    states = ["ACTIVE", "AT_RISK", "DORMANT", "CHURNED"]
    header = f"  {'Date':<12s}"
    for s in states:
        header += f" {s:>8s}"
    print(header)
    print(f"  {'-'*50}")

    for dt in dates:
        cur.execute("""
            SELECT state, COUNT(*) AS n FROM customer_states
            WHERE as_of_date = %s GROUP BY state ORDER BY state
        """, (dt,))
        counts = {r["state"]: r["n"] for r in cur.fetchall()}
        total = sum(counts.values())
        row = f"  {dt:<12s}"
        for s in states:
            c = counts.get(s, 0)
            row += f" {c:>7d}" if total == 0 else f" {c/total*100:>6.1f}%"
        print(row)

    # ── 4. Feature missing-value counts ───────────────────────────
    print(f"\n  ── Feature Completeness (missing % across dates) ──")
    print(f"  {'Feature':<35s}", end="")
    for dt in dates:
        print(f" {dt[-5:]:>7s}", end="")
    print(f"  {'Trend':>8s}")
    print(f"  {'-'*75}")

    # Key features to track
    track_features = [
        "txn_count_90d", "total_amount_90d", "engagement_score",
        "days_since_last_txn", "fin_total_credit_90d",
        "behav_frequency_score", "chan_digital_adoption_score",
        "rel_accounts_active", "fin_income_growth", "amount_growth_ratio",
        "credit_sum_30d", "monthly_income_estimate",
    ]

    for feat in track_features:
        missing_pcts = []
        print(f"  {feat:<35s}", end="")
        for dt in dates:
            cur.execute(f"""
                SELECT COUNT(*) FILTER (WHERE "{feat}" IS NULL) * 100.0 / NULLIF(COUNT(*),0)
                FROM customer_features WHERE as_of_date = %s
            """, (dt,))
            pct = list(cur.fetchone().values())[0] if cur.rowcount else 0
            missing_pcts.append(pct or 0)
            arrow = ""
            if pct and pct > 20:
                arrow = " ⚠"
            elif pct and pct > 5:
                arrow = " ·"
            print(f" {pct:>6.1f}%", end="")
        # Trend
        if len(missing_pcts) >= 2:
            if missing_pcts[-1] > missing_pcts[0] + 5:
                trend = "↑ WORSE"
            elif missing_pcts[-1] < missing_pcts[0] - 5:
                trend = "↓ BETTER"
            else:
                trend = "→ STABLE"
        else:
            trend = ""
        print(f"  {trend:>8s}")

    # ── 5. Feature drift (PSI for key numeric features) ───────────
    if len(dates) >= 2:
        print(f"\n  ── Feature Drift (PSI vs {dates[0]}) ──")
        print(f"  {'Feature':<35s} {'PSI':>8s}  Status")
        print(f"  {'-'*55}")

        drift_features = [
            "txn_count_90d", "total_amount_90d", "engagement_score",
            "days_since_last_txn", "behav_frequency_score", "age_years",
        ]
        for feat in drift_features:
            values_by_date = {}
            for dt in dates:
                cur.execute(f"""
                    SELECT "{feat}" FROM customer_features
                    WHERE as_of_date = %s AND "{feat}" IS NOT NULL
                """, (dt,))
                values_by_date[dt] = [float(list(r.values())[0]) for r in cur.fetchall()]

            if values_by_date[dates[0]] and values_by_date[dates[-1]]:
                psi = _psi(values_by_date[dates[0]], values_by_date[dates[-1]])
                label = _drift_label(psi)
                flag = ""
                if label != "STABLE":
                    flag = " ⚠"
                print(f"  {feat:<35s} {psi:>8.4f}  {label}{flag}")

    # ── 6. Model confidence (via health score distribution) ──────
    print(f"\n  ── Health Score Distribution by Date ──")
    bins = [(0, 39), (40, 69), (70, 100)]
    for dt in dates:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE health_score < 40) AS critical,
                COUNT(*) FILTER (WHERE health_score >= 40 AND health_score < 70) AS atrisk,
                COUNT(*) FILTER (WHERE health_score >= 70) AS healthy,
                COUNT(*) AS total
            FROM customer_states
            WHERE as_of_date = %s AND health_score IS NOT NULL
        """, (dt,))
        r = cur.fetchone()
        if r and r["total"]:
            print(f"  {dt}: total={r['total']}")
            for label, count in [("Critical (<40)", r["critical"] or 0),
                                  ("At Risk (40-69)", r["atrisk"] or 0),
                                  ("Healthy (70+)", r["healthy"] or 0)]:
                pct = count / r["total"] * 100
                bar = "█" * max(1, int(pct / 2))
                print(f"    {label:<18s}: {count:>5d} ({pct:>5.1f}%) {bar}")

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n  ── Monitoring Summary ──")
    alerts = []

    # Check health score drift
    if len(dates) > 1 and health_data[dates[0]] and health_data[dates[-1]]:
        psi = _psi(health_data[dates[0]], health_data[dates[-1]])
        if psi > 0.25:
            alerts.append(f"HEALTH DRIFT: PSI={psi:.3f} — significant distribution shift")
        elif psi > 0.1:
            alerts.append(f"HEALTH DRIFT: PSI={psi:.3f} — moderate shift, monitor")

    # Check health score trend
    cur.execute("""
        SELECT as_of_date, ROUND(AVG(health_score)::numeric,1) AS avg_h
        FROM customer_states WHERE health_score IS NOT NULL
        GROUP BY as_of_date ORDER BY as_of_date
    """)
    health_trend = [(r["as_of_date"], float(r["avg_h"])) for r in cur.fetchall()]
    if len(health_trend) >= 2 and health_trend[-1][1] < health_trend[0][1] - 2:
        alerts.append(f"HEALTH DECLINE: {health_trend[0][1]:.1f} → {health_trend[-1][1]:.1f}")

    # Check missing data
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE health_score IS NULL) * 100.0 / NULLIF(COUNT(*),0)
        FROM customer_states WHERE as_of_date = %s
    """, (dates[-1],))
    null_pct = list(cur.fetchone().values())[0] if cur.rowcount else 0
    if null_pct > 5:
        alerts.append(f"MISSING HEALTH: {null_pct:.0f}% of predictions missing on {dates[-1]}")

    if alerts:
        for a in alerts:
            print(f"  ⚠ {a}")
    else:
        print(f"  ✅ All metrics within normal range. No alerts.")

    conn.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model Monitoring Report")
    parser.add_argument(
        "--dates", default="2026-07-17,2026-07-22,2026-07-27",
        help="Comma-separated dates to monitor (default: all 3 PoC dates)",
    )
    args = parser.parse_args()
    monitor([d.strip() for d in args.dates.split(",") if d.strip()])
