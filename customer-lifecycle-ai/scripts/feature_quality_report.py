"""Feature Quality Report — run before any model training or batch inference.

Produces per-feature statistics and flags suspicious patterns:
- Missing % (NULL values)
- Distribution: mean, median, std, min, max, p1, p99
- Outlier count (values beyond 3× IQR from median)
- Sensibility flags: all-zero, all-null, extreme skew, constant

Usage:
    python scripts/feature_quality_report.py [--as-of-date 2026-07-27] [--output report.csv]
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from datetime import date
from typing import Any

# Project root setup
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

import psycopg2
from psycopg2 import extras

from shared.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("feature_quality")

# ── Columns to skip (not features) ──
SKIP_COLUMNS = {
    "customer_id", "as_of_date", "created_at", "updated_at",
    "computed_at", "loaded_at",
}

# ── Known leakage/excluded features (flagged for awareness, not removed) ──
LEAKAGE_FLAG = {
    "days_since_last_txn", "behav_recency_score",
    "risk_dormant_indicator", "rel_customer_status",
    "engagement_score", "behav_inactive_days_90d",
    "inactivity_streak_days", "behav_activity_consistency",
    "txn_frequency_trend",
}


def compute_stats(cur, table: str, col: str, as_of: str) -> dict | None:
    """Compute descriptive statistics for a single numeric column."""
    try:
        cur.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                COUNT("{col}") AS non_null,
                ROUND(AVG("{col}"::float)::numeric, 2) AS mean,
                ROUND(STDDEV("{col}"::float)::numeric, 2) AS stddev,
                ROUND(MIN("{col}"::float)::numeric, 2) AS min_val,
                ROUND(MAX("{col}"::float)::numeric, 2) AS max_val,
                ROUND(PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY "{col}"::float)::numeric, 2) AS p1,
                ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY "{col}"::float)::numeric, 2) AS median,
                ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY "{col}"::float)::numeric, 2) AS p99
            FROM {table}
            WHERE "{settings.col_as_of_date}" = %(d)s::date
            """,
            {"d": as_of},
        )
        row = cur.fetchone()
        if row is None or row[0] == 0:
            return None

        total, non_null, mean, stddev, min_v, max_v, p1, median, p99 = row
        missing_pct = round((1 - non_null / total) * 100, 1) if total else 0.0

        # Outliers: values beyond 3× IQR from median
        cur.execute(
            f"""
            WITH bounds AS (
                SELECT
                    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY "{col}"::float) AS q1,
                    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY "{col}"::float) AS q3
                FROM {table}
                WHERE "{settings.col_as_of_date}" = %(d)s::date
                  AND "{col}" IS NOT NULL
            )
            SELECT COUNT(*) FROM {table}, bounds
            WHERE "{settings.col_as_of_date}" = %(d)s::date
              AND "{col}" IS NOT NULL
              AND ("{col}"::float < q1 - 3*(q3-q1) OR "{col}"::float > q3 + 3*(q3-q1))
            """,
            {"d": as_of},
        )
        outliers = cur.fetchone()[0] if cur.rowcount else 0

        return {
            "feature": col,
            "total": total,
            "missing_pct": missing_pct,
            "mean": mean,
            "median": median,
            "stddev": stddev,
            "min": min_v,
            "max": max_v,
            "p1": p1,
            "p99": p99,
            "outliers": outliers,
        }
    except Exception as e:
        logger.debug("Skipping %s: %s", col, e)
        return None


def flag_issues(stats: dict) -> list[str]:
    """Return list of warning flags for a feature."""
    def _f(v: Any) -> float:
        """Safely convert to float."""
        if v is None:
            return 0.0
        return float(v)

    flags = []
    if stats["missing_pct"] > 50:
        flags.append("HIGH_MISSING")
    elif stats["missing_pct"] > 10:
        flags.append("MODERATE_MISSING")
    if _f(stats["min"]) == _f(stats["max"]) and stats["total"] > 1:
        flags.append("CONSTANT")
    if _f(stats["mean"]) == 0 and _f(stats["max"]) == 0:
        flags.append("ALL_ZERO")
    if _f(stats["median"]) == 0 and _f(stats["mean"]) > 0:
        flags.append("ZERO_MEDIAN_SKEWED")
    mean = _f(stats["mean"])
    std = _f(stats["stddev"])
    if std and mean and std > 3 * abs(mean):
        flags.append("HIGH_VARIANCE")
    if stats["outliers"] and stats["total"]:
        outlier_pct = stats["outliers"] / stats["total"] * 100
        if outlier_pct > 10:
            flags.append(f"MANY_OUTLIERS({outlier_pct:.0f}%)")
        elif outlier_pct > 0:
            flags.append(f"OUTLIERS({outlier_pct:.0f}%)")
    if stats["feature"] in LEAKAGE_FLAG:
        flags.append("LEAKAGE_FEATURE")
    p99 = _f(stats["p99"])
    mx = _f(stats["max"])
    if p99 > 0 and mx / max(p99, 1) > 10:
        flags.append("EXTREME_TAIL")
    return flags


def generate_report(as_of_date: str, output_csv: str | None = None) -> list[dict]:
    """Generate feature quality report for a given date."""
    conn = psycopg2.connect(
        settings.database_target_url_sync,
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=3,
    )
    table = settings.table_customer_features
    report: list[dict] = []

    try:
        cur = conn.cursor()

        # Discover numeric columns
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
            """,
            (table,),
        )
        columns = [(r[0], r[1]) for r in cur.fetchall()]

        numeric_cols = [
            c for c, t in columns
            if c not in SKIP_COLUMNS
            and t in ("integer", "bigint", "smallint", "numeric",
                       "real", "double precision", "float")
        ]
        logger.info(
            "Analyzing %d numeric features from %s (as_of=%s)",
            len(numeric_cols), table, as_of_date,
        )

        for col in numeric_cols:
            stats = compute_stats(cur, table, col, as_of_date)
            if stats is None:
                continue
            stats["flags"] = flag_issues(stats)
            report.append(stats)

    finally:
        conn.close()

    # ── Print report ──
    print(f"\n{'='*100}")
    print(f"  Feature Quality Report — {as_of_date}")
    print(f"  Table: {table}  |  Features analyzed: {len(report)}")
    print(f"{'='*100}")
    print(f"{'Feature':<30s} {'Miss%':>6s} {'Mean':>8s} {'Med':>8s} "
          f"{'Std':>8s} {'Min':>8s} {'Max':>8s} {'Outliers':>8s} {'Flags'}")
    print(f"{'-'*100}")

    flagged = 0
    for s in report:
        flags_str = ",".join(s["flags"]) if s["flags"] else ""
        if s["flags"]:
            flagged += 1
        print(
            f"{s['feature']:<30s} {float(s['missing_pct']):5.1f}% "
            f"{float(s['mean'] or 0):>8.1f} {float(s['median'] or 0):>8.1f} "
            f"{float(s['stddev'] or 0):>8.1f} {float(s['min'] or 0):>8.1f} "
            f"{float(s['max'] or 0):>8.1f} {int(s['outliers']):>8d} {flags_str}"
        )

    print(f"{'-'*100}")
    print(f"  Features with flags: {flagged}/{len(report)}")
    if flagged > 0:
        print(f"  ⚠ Review flagged features before training.")
    else:
        print(f"  ✅ All features clean.")

    # ── Summary by flag ──
    flag_counts: dict[str, int] = {}
    for s in report:
        for f in s["flags"]:
            flag_counts[f] = flag_counts.get(f, 0) + 1
    if flag_counts:
        print(f"\n  Flag summary:")
        for flag, count in sorted(flag_counts.items()):
            print(f"    {flag}: {count} feature(s)")

    # ── Optional CSV output ──
    if output_csv:
        with open(output_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "feature", "total", "missing_pct", "mean", "median",
                    "stddev", "min", "max", "p1", "p99", "outliers", "flags",
                ],
            )
            writer.writeheader()
            for s in report:
                row = {**s}
                row["flags"] = ",".join(s["flags"])
                writer.writerow(row)
        logger.info("Report saved to %s", output_csv)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Feature Quality Report")
    parser.add_argument(
        "--as-of-date", default="2026-07-27",
        help="Date to analyze features for (default: 2026-07-27)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Optional CSV output path",
    )
    args = parser.parse_args()
    generate_report(args.as_of_date, args.output)
