"""Business Insights Report — answers stakeholder questions, not just scores.

Produces a business-facing summary with:
  1. Churn risk overview — how many at risk, by segment
  2. Most valuable customer segments
  3. Priority contact list for relationship managers
  4. State migration trends (who moved where)
  5. Estimated retention uplift from interventions

Usage:
    python scripts/business_insights.py [--as-of-date 2026-07-27]
"""
from __future__ import annotations

import argparse
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


def generate(as_of_date: str):
    conn = psycopg2.connect(
        settings.database_target_url_sync,
        connect_timeout=10,
        keepalives=1, keepalives_idle=30,
        keepalives_interval=10, keepalives_count=3,
    )
    cur = conn.cursor(cursor_factory=extras.RealDictCursor)

    print(f"\n{'='*80}")
    print(f"  ABSA Customer Lifecycle — Business Insights Report")
    print(f"  As of: {as_of_date}")
    print(f"{'='*80}")

    # ═══════════════════════════════════════════════════════════════
    # 1. How many customers are at high churn risk?
    # ═══════════════════════════════════════════════════════════════
    print(f"\n  ── 1. Churn Risk Overview ──")

    cur.execute("""
        SELECT
            cs.state,
            COUNT(*) AS customers,
            ROUND(AVG(cs.health_score)::numeric, 1) AS avg_health,
            ROUND(AVG(cf.total_amount_90d)::numeric, 0) AS avg_balance,
            ROUND(AVG(cf.txn_count_90d)::numeric, 1) AS avg_txns
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = %s
        GROUP BY cs.state
        ORDER BY CASE cs.state
            WHEN 'CHURNED' THEN 1 WHEN 'DORMANT' THEN 2
            WHEN 'AT_RISK' THEN 3 WHEN 'ACTIVE' THEN 4 END
    """, (as_of_date,))

    total = 0
    state_data = {}
    for r in cur.fetchall():
        state_data[r["state"]] = r
        total += r["customers"]

    at_risk_n = state_data.get("AT_RISK", {}).get("customers", 0)
    dormant_n = state_data.get("DORMANT", {}).get("customers", 0)
    churned_n = state_data.get("CHURNED", {}).get("customers", 0)
    at_risk_pct = (at_risk_n + dormant_n) / total * 100 if total else 0
    churned_pct = churned_n / total * 100 if total else 0

    print(f"\n  {at_risk_n + dormant_n:,} customers ({at_risk_pct:.0f}%) are "
          f"AT_RISK or DORMANT — need attention before they churn.")
    print(f"  {churned_n} ({churned_pct:.0f}%) have already churned.\n")

    for state in ["NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"]:
        if state in state_data:
            r = state_data[state]
            pct = r["customers"] / total * 100
            bar = "█" * max(1, int(pct))
            print(f"  {state:<10s}: {r['customers']:>5d} ({pct:>5.1f}%) "
                  f"avg_health={r['avg_health']:>5.1f}  "
                  f"avg_balance=R{r['avg_balance']:>10,.0f}  "
                  f"avg_txns={r['avg_txns']:>5.1f}  {bar}")

    # ═══════════════════════════════════════════════════════════════
    # 2. Most valuable segments
    # ═══════════════════════════════════════════════════════════════
    print(f"\n  ── 2. Most Valuable Segments ──")

    # Compute portfolio total first
    cur.execute(
        "SELECT SUM(total_amount_90d) FROM customer_features WHERE as_of_date = %s",
        (as_of_date,),
    )
    portfolio_total = float(cur.fetchone()["sum"] or 0)

    cur.execute("""
        SELECT q,
               COUNT(*) AS customers,
               ROUND(AVG(total_amount_90d)::numeric, 0) AS avg_balance,
               ROUND(SUM(total_amount_90d)::numeric, 0) AS total_value
        FROM (
            SELECT total_amount_90d,
                   NTILE(5) OVER (ORDER BY total_amount_90d DESC) AS q
            FROM customer_features
            WHERE as_of_date = %s AND total_amount_90d IS NOT NULL
        ) sub
        GROUP BY q ORDER BY q
    """, (as_of_date,))

    labels = {1: "Top 20% (Premium)", 2: "2nd Quintile",
              3: "3rd Quintile", 4: "4th Quintile", 5: "Bottom 20%"}

    for r in cur.fetchall():
        q = r["q"]
        pct = (float(r["total_value"]) / portfolio_total * 100) if portfolio_total else 0
        print(f"  {labels[q]:<22s}: {r['customers']:>4d} customers, "
              f"avg=R{r['avg_balance']:>10,.0f}, "
              f"total=R{r['total_value']:>14,.0f} ({pct:.1f}% of portfolio)")

    for r in cur.fetchall():
        print(f"  {r['segment']:<22s}: {r['customers']:>4d} customers, "
              f"avg=R{r['avg_balance']:>10,.0f}, "
              f"total=R{r['total_value']:>14,.0f} ({r['pct']}% of portfolio)")

    # ═══════════════════════════════════════════════════════════════
    # 3. Priority contact list
    # ═══════════════════════════════════════════════════════════════
    print(f"\n  ── 3. Priority Contact List (Top 10) ──")
    print(f"  Ranked by: deteriorating state + low health + high value")
    print(f"  {'Rank':<5s} {'Customer':<12s} {'State':<10s} {'Health':>7s} "
          f"{'Balance':>12s} {'Txns':>7s}  Reason")
    print(f"  {'-'*80}")

    cur.execute("""
        SELECT cs.customer_id, cs.state, cs.health_score,
               cf.total_amount_90d, cf.txn_count_90d, cf.days_since_last_txn
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = %s
          AND cs.state IN ('AT_RISK', 'DORMANT')
          AND cf.total_amount_90d IS NOT NULL
        ORDER BY CASE cs.state WHEN 'DORMANT' THEN 0 ELSE 1 END,
                 cs.health_score ASC, cf.total_amount_90d DESC
        LIMIT 10
    """, (as_of_date,))

    for i, r in enumerate(cur.fetchall(), 1):
        amount = r["total_amount_90d"] or 0
        reasons = []
        if r["state"] == "DORMANT":
            reasons.append("inactive 90d+")
        else:
            reasons.append("declining activity")
        if amount > 500000:
            reasons.append("high value")
        if r["health_score"] and r["health_score"] < 35:
            reasons.append("critical health")
        print(f"  {i:<5d} {r['customer_id']:<12s} {r['state']:<10s} "
              f"{r['health_score']:>6.1f}  R{amount:>11,.0f}  "
              f"{r['txn_count_90d'] or 0:>6.1f}  {', '.join(reasons)}")

    # ═══════════════════════════════════════════════════════════════
    # 4. State migration
    # ═══════════════════════════════════════════════════════════════
    print(f"\n  ── 4. State Migration ──")

    cur.execute("""
        SELECT DISTINCT as_of_date FROM customer_states
        WHERE as_of_date < %s ORDER BY as_of_date DESC LIMIT 1
    """, (as_of_date,))
    prev_row = cur.fetchone()
    if prev_row:
        prev_date = str(prev_row["as_of_date"])
        cur.execute("""
            SELECT prev.state AS f, curr.state AS t, COUNT(*) AS n
            FROM customer_states prev
            JOIN customer_states curr
              ON prev.customer_id = curr.customer_id
             AND prev.as_of_date = %s AND curr.as_of_date = %s
            GROUP BY 1,2 ORDER BY 1,2
        """, (prev_date, as_of_date))

        states = ["NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"]
        matrix = {(r["f"], r["t"]): r["n"] for r in cur.fetchall()}

        print(f"  {prev_date} → {as_of_date}:")
        header = "From \\ To"
        print(f"  {header:<12s} {'NEW':>8s} {'ACTIVE':>8s} {'GROWING':>8s} "
              f"{'AT_RISK':>8s} {'DORMANT':>8s} {'CHURNED':>8s}")
        print(f"  {'-'*50}")

        for fs in states:
            row_total = sum(matrix.get((fs, ts), 0) for ts in states)
            if row_total == 0:
                continue
            parts = [f"  {fs:<12s}"]
            for ts in states:
                n = matrix.get((fs, ts), 0)
                marker = ""
                if fs != ts and n > 0:
                    fi, ti = states.index(fs), states.index(ts)
                    marker = "↓" if ti > fi else "↑"
                parts.append(f"{n:>7d}{marker} " if marker else f"{n:>8d}")
            print("".join(parts))

        # Key migration counts
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE prev.state IN ('ACTIVE','AT_RISK')
                                 AND curr.state = 'DORMANT') AS to_dormant,
                COUNT(*) FILTER (WHERE prev.state != 'CHURNED'
                                 AND curr.state = 'CHURNED') AS new_churns
            FROM customer_states prev
            JOIN customer_states curr
              ON prev.customer_id = curr.customer_id
             AND prev.as_of_date = %s AND curr.as_of_date = %s
        """, (prev_date, as_of_date))
        m = cur.fetchone()
        print(f"\n  Key moves: {m['to_dormant']} into Dormant, "
              f"{m['new_churns']} newly churned")

    # ═══════════════════════════════════════════════════════════════
    # 5. Retention uplift scenario
    # ═══════════════════════════════════════════════════════════════
    print(f"\n  ── 5. Retention Uplift Scenario ──")

    cur.execute("""
        SELECT
            COUNT(*) AS targetable,
            ROUND(SUM(total_amount_90d)::numeric, 0) AS at_risk_value,
            COUNT(*) FILTER (WHERE total_amount_90d > 100000) AS high_value
        FROM customer_states cs
        JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = %s
          AND cs.state IN ('AT_RISK', 'DORMANT')
          AND cf.total_amount_90d IS NOT NULL
    """, (as_of_date,))
    r = cur.fetchone()

    if r:
        targetable = int(r["targetable"])
        at_risk_value = float(r["at_risk_value"] or 0)
        high_value = int(r["high_value"] or 0)

        print(f"  Targetable (AT_RISK + DORMANT):     {targetable:,}")
        print(f"  Portfolio value at risk:            R{at_risk_value:,.0f}")
        print(f"  High-value at risk (>R100K):        {high_value:,}")
        print(f"\n  Scenario: retain X% of at-risk customers:")
        for rate in [0.05, 0.10, 0.15, 0.20]:
            saved = int(targetable * rate)
            value = int(at_risk_value * rate)
            print(f"    {rate:.0%}: save {saved:,} customers, "
                  f"~R{value:,.0f} portfolio value")
        print(f"\n  → Prioritize {high_value:,} high-value at-risk customers first.")

    # ═══════════════════════════════════════════════════════════════
    # Dashboard
    # ═══════════════════════════════════════════════════════════════
    print(f"\n  ── Executive Dashboard ──")

    cur.execute("""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE state IN ('AT_RISK','DORMANT')) AS atrisk,
            COUNT(*) FILTER (WHERE state = 'CHURNED') AS churned,
            ROUND(AVG(health_score) FILTER (WHERE health_score IS NOT NULL)::numeric,1) AS health,
            ROUND(AVG(cf.total_amount_90d) FILTER (WHERE cf.total_amount_90d IS NOT NULL)::numeric,0) AS balance
        FROM customer_states cs
        LEFT JOIN customer_features cf
          ON cs.customer_id = cf.customer_id AND cs.as_of_date = cf.as_of_date
        WHERE cs.as_of_date = %s
    """, (as_of_date,))
    d = cur.fetchone()

    print(f"""
  ┌──────────────────────────────────────────────────────┐
  │  Total Customers:        {d['total']:>6,}                       │
  │  Needs Attention:        {d['atrisk']:>6,}  ({d['atrisk']/d['total']*100:.0f}%)                  │
  │  Already Churned:        {d['churned']:>6,}  ({d['churned']/d['total']*100:.0f}%)                  │
  │  Average Health Score:   {d['health']:>6.1f} / 100                  │
  │  Average Balance:        R{d['balance']:>10,.0f}                  │
  └──────────────────────────────────────────────────────┘
  """)

    conn.close()
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Business Insights Report")
    parser.add_argument("--as-of-date", default="2026-07-27")
    args = parser.parse_args()
    generate(args.as_of_date)