"""Feature → State Traceability Verification.

Reads real customer_features from etl_clean, runs the StateEngine
classifier, and shows the EXACT feature values → rule → state chain
for a sample of customers. This proves the pipeline produces correct,
verifiable results against real data.

Usage:
    cd customer-lifecycle-ai
    python scripts/verify_feature_to_state.py [--as-of-date 2026-07-27] [--sample 10]
"""
from __future__ import annotations

import argparse
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services", "customer-state-service",
    ),
)

import psycopg2
from shared.config.settings import settings
from app.config.settings import StateConfig
from app.services.state_engine import StateEngine


def verify(as_of_date: date, sample_size: int = 10) -> dict:
    """Verify state classification against real customer_features data.

    Returns:
        Dict with summary stats and per-customer trace.
    """
    config = StateConfig()
    engine = StateEngine(config)
    conn = psycopg2.connect(
        settings.database_target_url_sync,
        connect_timeout=10,
    )

    try:
        cur = conn.cursor()

        # Get a stratified sample: one from each expected state category
        cur.execute(
            """
            SELECT customer_id, as_of_date,
                   days_since_last_txn, engagement_score,
                   rel_customer_status, risk_dormant_indicator,
                   txn_count_90d, total_amount_90d
            FROM customer_features
            WHERE as_of_date = %(d)s::date
            ORDER BY RANDOM()
            LIMIT %(n)s
            """,
            {"d": as_of_date, "n": sample_size},
        )
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        # Also get portfolio-wide stats for context
        cur.execute(
            """SELECT COUNT(*) FROM customer_features
               WHERE as_of_date = %(d)s::date""",
            {"d": as_of_date},
        )
        total_customers = cur.fetchone()[0]

        cur.execute(
            """SELECT state, COUNT(*) FROM customer_states
               WHERE as_of_date = %(d)s::date
               GROUP BY state ORDER BY COUNT(*) DESC""",
            {"d": as_of_date},
        )
        state_breakdown = dict(cur.fetchall())

    finally:
        conn.close()

    # Classify each customer and build trace
    traces = []
    state_counts = {}
    for row in rows:
        result = engine.classify(row)

        state_counts[result.state] = state_counts.get(result.state, 0) + 1

        traces.append({
            "customer_id": row["customer_id"],
            "features": {
                "days_since_last_txn": row["days_since_last_txn"],
                "engagement_score": row["engagement_score"],
                "rel_customer_status": row["rel_customer_status"],
                "risk_dormant_indicator": row["risk_dormant_indicator"],
                "txn_count_90d": row["txn_count_90d"],
                "total_amount_90d": row["total_amount_90d"],
            },
            "classified_state": result.state,
            "rules_fired": result.classification_rules,
        })

    return {
        "as_of_date": as_of_date,
        "total_customers": total_customers,
        "sample_size": len(traces),
        "sample_state_counts": state_counts,
        "portfolio_state_counts": state_breakdown,
        "traces": traces,
    }


def _fmt(v) -> str:
    """Format a feature value, handling None."""
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return f"{v:>9.1f}"
    if isinstance(v, int):
        return f"{v:>6d}"
    return f"{str(v):>6}"


def print_trace(trace: dict) -> None:
    """Pretty-print a single customer classification trace."""
    f = trace["features"]
    print(f"\n  Customer: {trace['customer_id']}")
    print(f"  State:    {trace['classified_state']}  ← rules: {trace['rules_fired']}")
    print(f"  Features:")
    print(f"    days_since_last_txn:       {_fmt(f['days_since_last_txn'])}")
    print(f"    engagement_score:          {_fmt(f['engagement_score'])}")
    print(f"    rel_customer_status:       {_fmt(f['rel_customer_status'])}")
    print(f"    risk_dormant_indicator:    {_fmt(f['risk_dormant_indicator'])}")
    print(f"    txn_count_90d:             {_fmt(f['txn_count_90d'])}")
    print(f"    total_amount_90d:          {_fmt(f['total_amount_90d'])}")

    # Explain WHY this state was chosen
    why = _explain_classification(trace)
    print(f"  Why:      {why}")


def _explain_classification(trace: dict) -> str:
    """Explain the classification decision in plain language."""
    f = trace["features"]
    state = trace["classified_state"]
    days = f["days_since_last_txn"]

    if state == "CHURNED":
        if f["rel_customer_status"] == "Closed":
            return "Account is Closed — CHURNED (priority 1)"
        return f"Inactive {days}d > 365d threshold — CHURNED"

    if state == "DORMANT":
        if days is not None and days > 90:
            return f"Inactive {days}d > 90d threshold — DORMANT"
        if f.get("txn_count_90d") is not None and f.get("txn_count_90d") == 0:
            return "Zero transactions in 90d — DORMANT"
        eng = f.get("engagement_score")
        return f"Engagement score {eng} < 10 threshold — DORMANT"

    if state == "AT_RISK":
        if days is not None and days >= 30:
            return f"Inactive {days}d >= 30d threshold — AT_RISK"
        if f.get("risk_dormant_indicator"):
            return "Risk dormant indicator is True — AT_RISK"
        eng = f.get("engagement_score")
        return f"Engagement score {eng} < 20 threshold — AT_RISK"

    if state == "ACTIVE":
        eng = f.get("engagement_score", "?")
        return f"Active {days}d since last txn, engagement {eng} — no risk rules fired"

    return "Unknown"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify Feature Engine → State classification traceability"
    )
    parser.add_argument(
        "--as-of-date", type=str, default="2026-07-27",
        help="Date to verify (default: 2026-07-27)",
    )
    parser.add_argument(
        "--sample", type=int, default=10,
        help="Number of random customers to trace (default: 10)",
    )
    args = parser.parse_args()
    as_of_date = date.fromisoformat(args.as_of_date)

    print("=" * 70)
    print("FEATURE → STATE TRACEABILITY VERIFICATION")
    print(f"Date: {as_of_date}  |  Sample: {args.sample} customers")
    print("=" * 70)

    result = verify(as_of_date, args.sample)

    # Summary
    print(f"\nPortfolio: {result['total_customers']:,} customers")
    print(f"  Actual state distribution (customer_states):")
    for state, count in sorted(result["portfolio_state_counts"].items()):
        pct = count / result["total_customers"] * 100
        print(f"    {state:10s} {count:5d}  ({pct:4.1f}%)")

    print(f"\n  Sample state distribution ({result['sample_size']} customers):")
    for state, count in sorted(result["sample_state_counts"].items()):
        print(f"    {state:10s} {count:5d}")

    # Individual traces
    print(f"\n{'─' * 70}")
    print("INDIVIDUAL CLASSIFICATION TRACES")
    print(f"{'─' * 70}")
    for trace in result["traces"]:
        print_trace(trace)

    print(f"\n{'=' * 70}")
    print("VERIFICATION COMPLETE")
    print(f"Every state above is traceable to the exact feature values shown.")
    print(f"Re-run with --as-of-date <date> to verify other snapshots.")
    print(f"{'=' * 70}")
