"""State Service — Orchestrates state computation, mirrors FeatureService pattern.

Reads customer_features → classifies via StateEngine → writes customer_states.
"""
from __future__ import annotations

import logging
import time
from datetime import date as date_type

from app.config.settings import Settings
from app.repository.state_repository import StateRepository
from app.repository.journey_repository import JourneyRepository
from app.services.state_engine import StateEngine
from app.services.transition_analyzer import TransitionAnalyzer
from app.schemas.state import ComputeStatesResponse
from app.schemas.transition import NextStatePrediction, TransitionMatrix
from app.engines.markov.engine import MarkovEngine
from shared.config.settings import settings as shared

logger = logging.getLogger("customer_state.service")


class StateService:
    """Orchestrates state computation. Mirrors FeatureService pattern."""

    def __init__(self) -> None:
        self._settings = Settings()
        self._state_repo = StateRepository()
        self._journey_repo = JourneyRepository()

        # Validate schema mappings at startup
        try:
            conn = self._state_repo._connect()
            warnings = shared.validate_schema_mappings(conn)
            conn.close()
        except Exception as e:
            warnings = [f"Schema validation skipped (DB unavailable): {e}"]
        for w in warnings:
            logger.warning(w)

        self._engine = StateEngine(self._settings.state)
        self._transition_analyzer = TransitionAnalyzer()
        self._features_table = shared.table_customer_features
        self._cust_col = shared.col_customer_id
        self._as_of_col = shared.col_as_of_date

    def compute_states(self, as_of_date: date_type | None = None) -> ComputeStatesResponse:
        """Classify all customers for a given date.

        Pipeline:
            1. Read customer_features for as_of_date
            2. Classify each customer via StateEngine
            3. Detect transitions vs previous as_of_date
            4. Batch upsert customer_states
            5. Batch insert state_transitions

        Idempotent — re-running on the same date produces identical results.
        """
        effective_date = as_of_date or date_type.today()
        t0 = time.monotonic()

        # Step 1: Read features from the Feature Store
        conn = self._state_repo._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT {self._cust_col}, {self._as_of_col},
                       days_since_last_txn, engagement_score,
                       rel_customer_status, risk_dormant_indicator,
                       txn_count_90d
                FROM {self._features_table}
                WHERE {self._as_of_col} = %(d)s::date
                """,
                {"d": effective_date},
            )
            columns = [desc[0] for desc in cur.description]
            feature_rows = [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            conn.close()

        if not feature_rows:
            logger.warning(
                "No customer_features found for %s — run Feature Engine first",
                effective_date,
            )
            return ComputeStatesResponse(
                as_of_date=effective_date,
                customers_processed=0,
                states_upserted=0,
                transitions_detected=0,
                duration_seconds=round(time.monotonic() - t0, 2),
                status="NO_DATA",
            )

        # Step 2: Get previous states for transition detection
        customer_ids = [r["customer_id"] for r in feature_rows]
        previous_states = self._state_repo.get_previous_states(
            customer_ids, effective_date
        )

        # Step 3: Classify + detect transitions
        states_to_upsert: list[dict] = []
        transitions_to_insert: list[dict] = []

        for row in feature_rows:
            cid = row["customer_id"]
            prev = previous_states.get(cid)

            result = self._engine.classify(row, previous_state=prev)
            result.as_of_date = effective_date

            states_to_upsert.append({
                "customer_id": cid,
                "state": result.state,
                "classification_rules": result.classification_rules,
            })

            if result.is_transition and prev:
                reason = self._transition_analyzer.detect(
                    result.state, prev, row
                )
                transitions_to_insert.append({
                    "customer_id": cid,
                    "from_state": prev,
                    "to_state": result.state,
                    "transition_date": effective_date,
                    "trigger_reason": reason,
                    "feature_snapshot": {
                        "days_since_last_txn": row.get("days_since_last_txn"),
                        "engagement_score": row.get("engagement_score"),
                        "risk_dormant_indicator": row.get("risk_dormant_indicator"),
                    },
                })

        # Step 4: Batch upsert states
        states_upserted = self._state_repo.upsert_batch(states_to_upsert, effective_date)
        logger.info("  States upserted: %d", states_upserted)

        # Step 5: Batch insert transitions
        transitions_inserted = self._journey_repo.insert_transitions(transitions_to_insert)
        logger.info("  Transitions detected: %d", transitions_inserted)

        elapsed = time.monotonic() - t0
        return ComputeStatesResponse(
            as_of_date=effective_date,
            customers_processed=len(feature_rows),
            states_upserted=states_upserted,
            transitions_detected=transitions_inserted,
            duration_seconds=round(elapsed, 2),
            status="COMPLETED",
        )

    def get_state(self, customer_id: str, as_of_date: date_type) -> dict | None:
        """Get a single customer's state snapshot."""
        return self._state_repo.get_state(customer_id, as_of_date)

    def get_timeline(self, customer_id: str, limit: int = 50) -> dict:
        """Get full state history + transitions for a customer."""
        timeline = self._state_repo.get_timeline(customer_id, limit)
        transitions = self._journey_repo.get_transitions(customer_id)
        return {
            "customer_id": customer_id,
            "timeline": timeline,
            "transitions": [
                {
                    "transition_date": t["transition_date"],
                    "from_state": t["from_state"],
                    "to_state": t["to_state"],
                    "trigger_reason": t.get("trigger_reason"),
                    "days_in_previous_state": t.get("days_in_previous_state"),
                }
                for t in transitions
            ],
        }

    def get_portfolio_summary(
        self, as_of_date: date_type, branch_code: str | None = None
    ) -> dict:
        """Aggregate state counts."""
        return self._state_repo.get_portfolio_summary(as_of_date, branch_code)

    def list_all_states(
        self, as_of_date: date_type, limit: int = 100, offset: int = 0
    ) -> list[dict]:
        """List all customer state snapshots for a given date (paginated)."""
        return self._state_repo.list_all(as_of_date, limit, offset)

    # ------------------------------------------------------------------
    # Markov Chain
    # ------------------------------------------------------------------

    def get_markov_matrix(
        self, as_of_date: date_type, window_days: int = 180
    ) -> TransitionMatrix:
        """Compute the 4x4 transition probability matrix."""
        counts = self._journey_repo.get_transition_matrix_data(
            as_of_date, window_days
        )
        engine = MarkovEngine(
            min_transitions=self._settings.state.markov_min_transitions
        )
        engine.fit(counts, window_days)

        return TransitionMatrix(
            as_of_date=as_of_date,
            window_days=window_days,
            matrix=engine.matrix,
            steady_state=engine.steady_state(),
            warnings=engine.warnings,
            total_transitions_observed=engine.total_transitions,
        )

    def predict_next_state(
        self, customer_id: str, as_of_date: date_type
    ) -> NextStatePrediction:
        """Predict next-state probabilities for a customer."""
        # Get current state
        state_row = self._state_repo.get_state(customer_id, as_of_date)
        if not state_row:
            return NextStatePrediction(
                customer_id=customer_id,
                current_state="UNKNOWN",
                predictions=None,
                warning=f"No state found for {customer_id} as of {as_of_date}",
            )

        current = state_row["state"]

        # Build Markov matrix from recent transitions
        window_days = self._settings.state.markov_window_days
        counts = self._journey_repo.get_transition_matrix_data(
            as_of_date, window_days
        )
        engine = MarkovEngine(
            min_transitions=self._settings.state.markov_min_transitions
        )
        engine.fit(counts, window_days)

        predictions = engine.predict_next(current)
        if predictions is None:
            return NextStatePrediction(
                customer_id=customer_id,
                current_state=current,
                predictions=None,
                warning=(
                    f"Insufficient transitions from {current} "
                    f"(need {self._settings.state.markov_min_transitions}). "
                    "Try a wider window or re-run after more data accumulates."
                ),
            )

        return NextStatePrediction(
            customer_id=customer_id,
            current_state=current,
            predictions=predictions,
        )
