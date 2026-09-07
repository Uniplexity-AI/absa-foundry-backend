"""Journey Analyzer — Milestone detection and path analysis."""
from __future__ import annotations

from datetime import date

import psycopg2
from shared.config.settings import settings


class JourneyAnalyzer:
    """Analyzes customer lifecycle journeys and detects milestones."""

    def __init__(self) -> None:
        self._conn_str = settings.database_target_url_sync

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(
            self._conn_str,
            connect_timeout=10,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
        )

    def detect_milestones(self, customer_id: str) -> list[dict]:
        """Return chronological list of milestones for a customer."""
        milestones: list[dict] = []
        conn = self._connect()
        try:
            cur = conn.cursor()

            # First transaction
            cur.execute(
                """SELECT MIN(transaction_date) FROM customer_transactions_clean
                   WHERE customer_id = %(cid)s""",
                {"cid": customer_id},
            )
            first_txn = cur.fetchone()
            if first_txn and first_txn[0]:
                milestones.append({
                    "milestone_type": "first_transaction",
                    "milestone_date": str(first_txn[0]),
                    "description": "First transaction recorded",
                })

            # First churn risk
            cur.execute(
                """SELECT MIN(as_of_date) FROM customer_states
                   WHERE customer_id = %(cid)s AND state = 'AT_RISK'""",
                {"cid": customer_id},
            )
            first_risk = cur.fetchone()
            if first_risk and first_risk[0]:
                milestones.append({
                    "milestone_type": "first_churn_risk",
                    "milestone_date": str(first_risk[0]),
                    "description": "First AT_RISK classification",
                })

            # First dormancy
            cur.execute(
                """SELECT MIN(as_of_date) FROM customer_states
                   WHERE customer_id = %(cid)s AND state = 'DORMANT'""",
                {"cid": customer_id},
            )
            first_dormant = cur.fetchone()
            if first_dormant and first_dormant[0]:
                milestones.append({
                    "milestone_type": "first_dormancy",
                    "milestone_date": str(first_dormant[0]),
                    "description": "First DORMANT classification",
                })

            # Recovery (AT_RISK/DORMANT -> ACTIVE)
            cur.execute(
                """SELECT transition_date, from_state, to_state
                   FROM state_transitions
                   WHERE customer_id = %(cid)s
                     AND from_state IN ('AT_RISK', 'DORMANT')
                     AND to_state = 'ACTIVE'
                   ORDER BY transition_date""",
                {"cid": customer_id},
            )
            for row in cur.fetchall():
                milestones.append({
                    "milestone_type": "recovery",
                    "milestone_date": str(row[0]),
                    "description": f"Recovered from {row[1]} to ACTIVE",
                })

        finally:
            conn.close()

        milestones.sort(key=lambda m: m["milestone_date"])
        return milestones

    def avg_time_in_state(self, as_of_date: date) -> dict[str, float]:
        """Average days spent in each state across all customers."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT from_state,
                          AVG(days_in_previous_state)::float AS avg_days
                   FROM state_transitions
                   WHERE transition_date <= %(d)s::date
                     AND days_in_previous_state IS NOT NULL
                   GROUP BY from_state""",
                {"d": as_of_date},
            )
            return {row[0]: round(row[1], 1) for row in cur.fetchall()}
        finally:
            conn.close()

    def top_paths(self, n: int = 5) -> list[dict]:
        """Most common state sequences (top-N by frequency)."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """SELECT from_state, to_state, COUNT(*) AS cnt
                   FROM state_transitions
                   GROUP BY from_state, to_state
                   ORDER BY cnt DESC
                   LIMIT %(n)s""",
                {"n": n},
            )
            return [
                {"from_state": row[0], "to_state": row[1], "count": row[2]}
                for row in cur.fetchall()
            ]
        finally:
            conn.close()