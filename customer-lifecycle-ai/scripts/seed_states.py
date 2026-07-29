"""Seed script — Run initial state computation.

Usage:
    cd customer-lifecycle-ai
    python scripts/seed_states.py [--as-of-date 2026-07-29]

Reads customer_features from the Feature Store, classifies all customers
via the Customer State Service's StateEngine, and writes customer_states
+ state_transitions to etl_clean.

This is equivalent to calling POST /states/compute?as_of_date=<date>
but runs as a standalone script for initial seeding without needing
the service to be running.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime

import psycopg2
from psycopg2 import extras

# Path setup
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "customer-state-service"))

from shared.config.settings import settings
from app.config.settings import StateConfig
from app.services.state_engine import StateEngine
from app.services.transition_analyzer import TransitionAnalyzer
from app.repository.state_repository import StateRepository
from app.repository.journey_repository import JourneyRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-7s] %(message)s")
logger = logging.getLogger("seed_states")


def seed(as_of_date: date) -> dict:
    t0 = time.monotonic()
    state_repo = StateRepository()
    journey_repo = JourneyRepository()
    engine = StateEngine(StateConfig())
    analyzer = TransitionAnalyzer()

    # Step 1: Read features
    logger.info("Reading customer_features for %s...", as_of_date)
    conn = state_repo._connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT customer_id, as_of_date,
                      days_since_last_txn, engagement_score,
                      rel_customer_status, risk_dormant_indicator,
                      txn_count_90d
               FROM customer_features
               WHERE as_of_date = %(d)s::date""",
            {"d": as_of_date},
        )
        columns = [desc[0] for desc in cur.description]
        rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    finally:
        conn.close()

    if not rows:
        logger.warning("No customer_features for %s — run Feature Engine first", as_of_date)
        return {"status": "NO_DATA", "customers": 0}

    logger.info("  %d customers found", len(rows))

    # Step 2: Get previous states
    customer_ids = [r["customer_id"] for r in rows]
    previous_states = state_repo.get_previous_states(customer_ids, as_of_date)

    # Step 3: Classify + detect transitions
    states: list[dict] = []
    transitions: list[dict] = []

    for row in rows:
        cid = row["customer_id"]
        prev = previous_states.get(cid)
        result = engine.classify(row, previous_state=prev)

        states.append({
            "customer_id": cid,
            "state": result.state,
            "classification_rules": result.classification_rules,
        })

        if result.is_transition and prev:
            reason = analyzer.detect(result.state, prev, row)
            transitions.append({
                "customer_id": cid,
                "from_state": prev,
                "to_state": result.state,
                "transition_date": as_of_date,
                "trigger_reason": reason,
                "feature_snapshot": {
                    "days_since_last_txn": row.get("days_since_last_txn"),
                    "engagement_score": row.get("engagement_score"),
                    "risk_dormant_indicator": row.get("risk_dormant_indicator"),
                },
            })

    # Step 4: Batch upsert
    upserted = state_repo.upsert_batch(states, as_of_date)
    logger.info("  States upserted: %d", upserted)

    # Step 5: Batch insert transitions
    inserted = journey_repo.insert_transitions(transitions)
    logger.info("  Transitions detected: %d", inserted)

    elapsed = time.monotonic() - t0
    logger.info("Seed complete: %d customers, %.1fs", len(rows), elapsed)

    state_breakdown = {}
    for s in states:
        state_breakdown[s["state"]] = state_breakdown.get(s["state"], 0) + 1

    return {
        "status": "COMPLETED",
        "customers": len(rows),
        "states_upserted": upserted,
        "transitions_detected": inserted,
        "duration_seconds": round(elapsed, 2),
        "breakdown": state_breakdown,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed initial customer states")
    parser.add_argument(
        "--as-of-date",
        type=str,
        default=date.today().isoformat(),
        help="Date to compute states for (default: today)",
    )
    args = parser.parse_args()
    as_of_date = date.fromisoformat(args.as_of_date)

    logger.info("=" * 60)
    logger.info("SEEDING CUSTOMER STATES for %s", as_of_date)
    logger.info("=" * 60)

    result = seed(as_of_date)
    logger.info("Result: %s", result)
