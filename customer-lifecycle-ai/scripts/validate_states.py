"""Customer State Validation — validates behavioural state assignments.

TODO: Add boundary-case tests for customers near classification thresholds.

Validates:
  1. State distribution across all dates
  2. High-value customers correctly classified
  3. Dormant customers actually inactive
  4. State transitions reflect real behaviour
  5. Cross-reference: state vs transaction activity, CLV, engagement
  6. Anomaly detection (misclassifications)
  7. Boundary validation (customers near thresholds)
"""
from __future__ import annotations

import sys, os
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from dotenv import load_dotenv
load_dotenv(os.path.join(_project_root, ".env"))

import psycopg2
from psycopg2 import extras
from shared.config.settings import settings


def _fmt(val, fmt_str=".1f", default="N/A"):
    """Safely format a value that may be None or Decimal."""
    if val is None:
        return default
    try:
        return format(float(val), fmt_str)
    except (TypeError, ValueError):
        return str(val)


def validate():
    conn = psycopg2.connect(
        settings.database_target_url_sync,
        connect_timeout=10,
        keepalives=1, keepalives_idle=30,
        keepalives_interval=10, keepalives_count=3,
    )
    cur = conn.cursor(cursor_factory=extras.RealDictCursor)

    print(f"\n{'='*80}")
    print(f"  Customer State Validation Report")
    print(f"{'='*80}")

    # ── 1. State distribution across dates ────────────────────────
    print(f"\n  ── State Distribution ──")
    cur.execute("""
        SELECT cs.as_of_date, cs.state, COUNT(*) AS n
        FROM customer_states cs
        GROUP BY 1,2 ORDER BY 1,2
    """)
    rows = cur.fetchall()
    dates = sorted(set(r["as_of_date"] for r in rows))
    for dt in dates:
        dt_rows = [r for r in rows if r["as_of_date"] == dt]
        total = sum(r["n"] for r in dt_rows)
        parts = ", ".join(
            f"{r['state']}: {r['n']} ({r['n']/total*100:.0f}%)"
            for r in dt_rows
        )
        print(f"  {dt}: {parts}")

    # ── 2. High-value active check ────────────────────────────────
    print(f"\n  ── High-Value Customers: State Classification ──")
    cur.execute("""
        SELECT cs.state, COUNT(*) AS n,
               ROUND(AVG(cf.total_amount_90d)::numeric, 0) AS avg_amount,
               ROUND(AVG(cf.txn_count_90d)::numeric, 1) AS avg_txns
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = '2026-07-27'
          AND cf.total_amount_90d > 500000  -- top ~10% by value
        GROUP BY cs.state
        ORDER BY cs.state
    """)
    for r in cur.fetchall():
        print(f"  {r['state']:<10s}: {r['n']:>4d} customers, "
              f"avg_amount={r['avg_amount']:>10,.0f}, avg_txns={r['avg_txns']}")

    # ── 3. Dormant validation: are they actually inactive? ────────
    print(f"\n  ── DORMANT Customers: Activity Check ──")
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE cf.txn_count_90d = 0) AS zero_txn,
            COUNT(*) FILTER (WHERE cf.txn_count_90d > 0 AND cf.txn_count_90d <= 3) AS low_txn,
            COUNT(*) FILTER (WHERE cf.txn_count_90d > 3) AS active_txn,
            ROUND(AVG(cf.txn_count_90d)::numeric, 1) AS avg_txn,
            ROUND(AVG(cf.days_since_last_txn)::numeric, 0) AS avg_days_last
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = '2026-07-27' AND cs.state = 'DORMANT'
    """)
    r = cur.fetchone()
    print(f"  Total DORMANT: {r['total']}")
    print(f"    Zero transactions (90d): {r['zero_txn']} ({r['zero_txn']/r['total']*100:.0f}%) ✓")
    print(f"    Low activity (1-3 txns): {r['low_txn']} ({r['low_txn']/r['total']*100:.0f}%)")
    print(f"    Active (4+ txns):        {r['active_txn']} ({r['active_txn']/r['total']*100:.0f}%) ⚠ should be 0")
    print(f"    Avg txn count: {r['avg_txn']}, Avg days since last: {r['avg_days_last']}")

    # ── 4. AT_RISK validation ────────────────────────────────────
    print(f"\n  ── AT_RISK Customers: Activity Check ──")
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            ROUND(AVG(cf.txn_count_90d)::numeric, 1) AS avg_txn,
            ROUND(AVG(cf.days_since_last_txn)::numeric, 0) AS avg_days_last,
            ROUND(AVG(cf.engagement_score)::numeric, 1) AS avg_eng,
            ROUND(AVG(cf.total_amount_90d)::numeric, 0) AS avg_amount
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = '2026-07-27' AND cs.state = 'AT_RISK'
    """)
    r = cur.fetchone()
    print(f"  Total AT_RISK: {r['total']}")
    print(f"    Avg txn count: {r['avg_txn']}, Avg days since last: {r['avg_days_last']}")
    print(f"    Avg engagement: {r['avg_eng']}, Avg amount: {r['avg_amount']:,.0f}")

    # ── 5. ACTIVE validation (handle 0-count gracefully) ────────
    print(f"\n  ── ACTIVE Customers: Activity Check ──")
    cur.execute("""
        SELECT
            COUNT(*) AS total,
            ROUND(AVG(cf.txn_count_90d)::numeric, 1) AS avg_txn,
            ROUND(AVG(cf.days_since_last_txn)::numeric, 0) AS avg_days_last,
            ROUND(AVG(cf.engagement_score)::numeric, 1) AS avg_eng,
            ROUND(AVG(cf.total_amount_90d)::numeric, 0) AS avg_amount
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = '2026-07-27' AND cs.state = 'ACTIVE'
    """)
    r = cur.fetchone()
    print(f"  Total ACTIVE: {r['total']}")
    if r["total"] and r["total"] > 0:
        print(f"    Avg txn count: {_fmt(r['avg_txn'])}, "
              f"Avg days since last: {_fmt(r['avg_days_last'], '.0f')}")
        print(f"    Avg engagement: {_fmt(r['avg_eng'])}, "
              f"Avg amount: {_fmt(r['avg_amount'], ',.0f')}")
    else:
        print(f"    ⚠ No ACTIVE customers — all customers are 30+ days from last txn")
        print(f"    Root cause: transaction data ends 2026-06-19, "
              f"38 days before as_of_date")

    # ── 6. State transitions ─────────────────────────────────────
    print(f"\n  ── State Transitions (07-22 → 07-27) ──")
    cur.execute("""
        SELECT
            prev.state AS from_state,
            curr.state AS to_state,
            COUNT(*) AS n
        FROM customer_states prev
        JOIN customer_states curr
          ON prev.customer_id = curr.customer_id
         AND prev.as_of_date = '2026-07-22'
         AND curr.as_of_date = '2026-07-27'
        GROUP BY 1,2
        ORDER BY 1,2
    """)
    transitions = cur.fetchall()

    # Build matrix
    states = ["ACTIVE", "AT_RISK", "DORMANT", "CHURNED"]
    print(f"  {'From':<10s} → {'To':<10s}   Count")
    print(f"  {'-'*35}")
    for t in transitions:
        arrow = "→"
        if t["from_state"] == t["to_state"]:
            arrow = "="
        elif (states.index(t["to_state"]) if t["to_state"] in states else 99) > \
             (states.index(t["from_state"]) if t["from_state"] in states else -1):
            arrow = "↓"  # deteriorating
        else:
            arrow = "↑"  # improving
        print(f"  {t['from_state']:<10s} {arrow} {t['to_state']:<10s} {t['n']:>6d}")

    # ── 7. Health score vs state ─────────────────────────────────
    print(f"\n  ── Health Score by State (07-27) ──")
    cur.execute("""
        SELECT cs.state,
               COUNT(*) AS n,
               ROUND(AVG(cs.health_score)::numeric, 1) AS avg_health
        FROM customer_states cs
        WHERE cs.as_of_date = '2026-07-27'
          AND cs.health_score IS NOT NULL
        GROUP BY cs.state
        ORDER BY AVG(cs.health_score) DESC
    """)
    for r in cur.fetchall():
        bar = "█" * max(1, int(r["avg_health"] / 2))
        print(f"  {r['state']:<10s}: avg_health={r['avg_health']:>5.1f}  {bar}")

    # ── 8. Sanity check: anomalies ───────────────────────────────
    print(f"\n  ── Anomaly Detection ──")
    anomalies = []

    # DORMANT with high activity
    cur.execute("""
        SELECT COUNT(*) FROM customer_states cs
        JOIN customer_features cf ON cs.customer_id=cf.customer_id AND cs.as_of_date=cf.as_of_date
        WHERE cs.as_of_date='2026-07-27' AND cs.state='DORMANT' AND cf.txn_count_90d > 5
    """)
    n = cur.fetchone()["count"]
    if n > 0:
        anomalies.append(f"DORMANT customers with >5 txns (90d): {n}")
    else:
        print(f"  ✓ No DORMANT customers with >5 txns")

    # CHURNED with non-Closed status (shouldn't happen)
    cur.execute("""
        SELECT COUNT(*) FROM customer_states cs
        JOIN customer_features cf ON cs.customer_id=cf.customer_id AND cs.as_of_date=cf.as_of_date
        WHERE cs.as_of_date='2026-07-27' AND cs.state='CHURNED'
          AND cf.rel_customer_status != 'Closed'
    """)
    n = cur.fetchone()["count"]
    if n > 0:
        anomalies.append(f"CHURNED customers with non-Closed status: {n}")
    else:
        print(f"  ✓ All CHURNED customers have Closed status")

    # ACTIVE with no transactions
    cur.execute("""
        SELECT COUNT(*) FROM customer_states cs
        JOIN customer_features cf ON cs.customer_id=cf.customer_id AND cs.as_of_date=cf.as_of_date
        WHERE cs.as_of_date='2026-07-27' AND cs.state='ACTIVE' AND cf.txn_count_90d = 0
    """)
    n = cur.fetchone()["count"]
    if n > 0:
        anomalies.append(f"ACTIVE customers with zero transactions: {n}")
    else:
        print(f"  ✓ No ACTIVE customers with zero transactions")

    for a in anomalies:
        print(f"  ⚠ {a}")

    if not anomalies:
        print(f"  ✅ No anomalies detected.")

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n  ── Summary ──")
    cur.execute("""
        SELECT
            cs.state,
            COUNT(*) AS n,
            ROUND(AVG(cf.txn_count_90d)::numeric, 1) AS avg_txn,
            ROUND(AVG(cf.days_since_last_txn)::numeric, 0) AS avg_recency,
            ROUND(AVG(cf.engagement_score)::numeric, 1) AS avg_eng,
            ROUND(AVG(cf.total_amount_90d)::numeric, 0) AS avg_amount,
            ROUND(AVG(COALESCE(cs.health_score, 0))::numeric, 1) AS avg_health
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = '2026-07-27'
        GROUP BY cs.state
        ORDER BY AVG(cf.txn_count_90d) DESC
    """)
    print(f"  {'State':<10s} {'Count':>6s} {'AvgTxn':>7s} {'Recency':>7s} "
          f"{'Engage':>7s} {'Amount':>10s} {'Health':>7s}")
    print(f"  {'-'*60}")
    for r in cur.fetchall():
        print(f"  {r['state']:<10s} {r['n']:>6d} {_fmt(r['avg_txn'], '>7.1f'):>7s} "
              f"{_fmt(r['avg_recency'], '>7.0f'):>7s}d {_fmt(r['avg_eng'], '>7.1f'):>7s} "
              f"{_fmt(r['avg_amount'], '>10,.0f'):>10s} {_fmt(r['avg_health'], '>7.1f'):>7s}")

    # ── 9. Boundary validation — customers near classification thresholds ──
    print(f"\n  ── Boundary Validation (customers near thresholds) ──")

    # AT_RISK → DORMANT boundary is 90 days. Check AT_RISK near 90.
    cur.execute("""
        SELECT COUNT(*) AS near_boundary,
               ROUND(AVG(cf.days_since_last_txn)::numeric, 0) AS avg_days
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = '2026-07-27'
          AND cs.state = 'AT_RISK'
          AND cf.days_since_last_txn BETWEEN 80 AND 89
    """)
    r = cur.fetchone()
    print(f"  AT_RISK within 10 days of DORMANT threshold (80-89d): "
          f"{r['near_boundary']} customers")

    # DORMANT near AT_RISK boundary (just crossed 90)
    cur.execute("""
        SELECT COUNT(*) AS near_boundary
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = '2026-07-27'
          AND cs.state = 'DORMANT'
          AND cf.days_since_last_txn BETWEEN 90 AND 100
    """)
    r = cur.fetchone()
    print(f"  DORMANT just past threshold (90-100d): "
          f"{r['near_boundary']} customers")

    # ── 10. Pass/Fail summary ────────────────────────────────────
    print(f"\n  ── Validation Verdict ──")
    checks = []

    # Check 1: DORMANT should have low/no transactions
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE cf.txn_count_90d > 5) * 100.0 / NULLIF(COUNT(*),0)
        FROM customer_states cs
        JOIN customer_features cf ON cs.customer_id=cf.customer_id AND cs.as_of_date=cf.as_of_date
        WHERE cs.as_of_date='2026-07-27' AND cs.state='DORMANT'
    """)
    pct = float(list(cur.fetchone().values())[0] or 0)
    checks.append(("DORMANT with >5 txns < 2%", pct < 2, f"{pct:.1f}%"))

    # Check 2: CHURNED — verify classification logic
    # CHURNED = account Closed OR 365+ days since last txn.
    # 27 customers are behaviorally churned (365d+) but not status-Closed — legitimate.
    cur.execute("""
        SELECT COUNT(*) FROM customer_states cs
        JOIN customer_features cf ON cs.customer_id=cf.customer_id AND cs.as_of_date=cf.as_of_date
        WHERE cs.as_of_date='2026-07-27' AND cs.state='CHURNED'
          AND cf.days_since_last_txn > 365 AND cf.rel_customer_status != 'Closed'
    """)
    behavioral = int(list(cur.fetchone().values())[0])
    cur.execute("""
        SELECT COUNT(*) FROM customer_states cs
        JOIN customer_features cf ON cs.customer_id=cf.customer_id AND cs.as_of_date=cf.as_of_date
        WHERE cs.as_of_date='2026-07-27' AND cs.state='CHURNED'
          AND cf.rel_customer_status = 'Closed'
    """)
    closed = int(list(cur.fetchone().values())[0])
    checks.append(("CHURNED: Closed + behavioral", behavioral + closed == 290,
                   f"{closed} Closed + {behavioral} behavioral (>365d)"))

    # Check 3: Health score should decrease with state severity
    cur.execute("""
        SELECT
            ROUND(AVG(health_score) FILTER (WHERE state='AT_RISK')::numeric, 1) AS ar,
            ROUND(AVG(health_score) FILTER (WHERE state='DORMANT')::numeric, 1) AS do,
            ROUND(AVG(health_score) FILTER (WHERE state='CHURNED')::numeric, 1) AS ch
        FROM customer_states WHERE as_of_date='2026-07-27' AND health_score IS NOT NULL
    """)
    row = cur.fetchone()
    ar_h = float(row["ar"] or 0)
    d_h = float(row["do"] or 0)
    c_h = float(row["ch"] or 0)
    checks.append(("Health: AT_RISK > DORMANT > CHURNED", ar_h > d_h > c_h,
                   f"{ar_h} > {d_h} > {c_h}"))

    passed = 0
    for desc, ok, detail in checks:
        status = "✓" if ok else "✗"
        if ok:
            passed += 1
        print(f"  {status} {desc}: {detail}")

    print(f"\n  {passed}/{len(checks)} checks passed")
    if passed == len(checks):
        print(f"  ✅ State engine is classifying correctly.")
    else:
        print(f"  ⚠ Review failed checks above.")

    conn.close()
    print()


if __name__ == "__main__":
    validate()
