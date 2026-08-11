"""Markov Chain Engine — First-order discrete-time Markov Chain.

Builds N×N transition probability matrix from observed state_transitions.
Predicts next-state probabilities and computes steady-state distribution.
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger("customer_state.markov")

_STATES = ["NEW", "ACTIVE", "GROWING", "AT_RISK", "DORMANT", "CHURNED"]
_STATE_INDEX: dict[str, int] = {s: i for i, s in enumerate(_STATES)}


class MarkovEngine:
    """First-order discrete-time Markov Chain for customer states."""

    def __init__(self, min_transitions: int = 50) -> None:
        self._matrix: np.ndarray | None = None  # 4×4 probability matrix
        self._min_transitions = min_transitions
        self._warnings: list[dict] = []

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def fit(
        self, transition_counts: list[dict], window_days: int = 180
    ) -> None:
        """Build transition probability matrix from aggregated counts.

        Args:
            transition_counts: List of {from_state, to_state, transition_count}
                               from JourneyRepository.get_transition_matrix_data().
            window_days: Time window for context (metadata only).
        """
        self._warnings = []

        # Initialize count matrix
        n = len(_STATES)
        count_matrix = np.zeros((n, n), dtype=np.float64)

        for row in transition_counts:
            from_s = row["from_state"]
            to_s = row["to_state"]
            cnt = row["transition_count"]

            if from_s in _STATE_INDEX and to_s in _STATE_INDEX:
                count_matrix[_STATE_INDEX[from_s], _STATE_INDEX[to_s]] = cnt

        # Build probability matrix with cold-start handling
        n = len(_STATES)
        prob_matrix = np.full((n, n), np.nan, dtype=np.float64)

        for i, state_name in enumerate(_STATES):
            row_total = count_matrix[i].sum()

            if state_name == "CHURNED":
                # Absorbing-state prior: even with zero observations,
                # CHURNED → CHURNED = 1.0 is the theoretical default.
                prob_matrix[i, :] = 0.0
                prob_matrix[i, i] = 1.0

            elif row_total < self._min_transitions:
                # Insufficient data — row stays NaN (null in JSON)
                self._warnings.append({
                    "state": state_name,
                    "observed_transitions": int(row_total),
                    "min_required": self._min_transitions,
                    "action": "row_masked",
                })
                # prob_matrix row stays NaN

            else:
                prob_matrix[i, :] = count_matrix[i, :] / row_total

        self._matrix = prob_matrix

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @property
    def matrix(self) -> list[list[float | None]]:
        """Return the 4×4 probability matrix as nested lists.
        NaN rows become None lists.
        """
        if self._matrix is None:
            raise RuntimeError("MarkovEngine not fitted — call fit() first.")

        result: list[list[float | None]] = []
        for row in self._matrix:
            if np.isnan(row).any():
                n = len(_STATES)
                result.append([None] * n)
            else:
                result.append([float(v) for v in row])
        return result

    @property
    def total_transitions(self) -> int:
        """Sum of observed transitions used to build the matrix."""
        if self._matrix is None:
            return 0
        return int(np.nansum(self._matrix))

    @property
    def warnings(self) -> list[dict]:
        return list(self._warnings)

    def predict_next(self, current_state: str) -> dict[str, float | None] | None:
        """Return {next_state: probability} for a given current state.

        Returns None if the current state has insufficient observations.
        """
        if self._matrix is None:
            raise RuntimeError("MarkovEngine not fitted — call fit() first.")

        if current_state not in _STATE_INDEX:
            return None

        idx = _STATE_INDEX[current_state]
        row = self._matrix[idx]

        if np.isnan(row).any():
            return None

        return {
            state: float(prob) for state, prob in zip(_STATES, row)
        }

    def steady_state(self) -> dict[str, float] | None:
        """Compute steady-state distribution (eigenvector of eigenvalue 1).

        Returns None if the matrix is degenerate (has zero-rows in
        non-absorbing states, which should never happen with the 4-state
        design but guards against future state additions).
        """
        if self._matrix is None:
            raise RuntimeError("MarkovEngine not fitted — call fit() first.")

        # Check for degenerate rows (zero outgoing from non-absorbing)
        for i, state_name in enumerate(_STATES):
            if state_name == "CHURNED":
                continue
            if np.isnan(self._matrix[i]).any() or self._matrix[i].sum() == 0:
                return None  # degenerate

        # Fill NaN rows (masked) with zeros — they won't appear in steady-state
        P = np.nan_to_num(self._matrix, nan=0.0)

        # Solve πP = π, Σπ = 1
        # (P^T - I)π = 0 → append Σπ=1 constraint
        n = P.shape[0]
        A = np.vstack([(P.T - np.eye(n))[:-1, :], np.ones(n)])
        b = np.zeros(n)
        b[-1] = 1.0

        try:
            pi = np.linalg.lstsq(A, b, rcond=None)[0]
            # Normalize to ensure sum = 1
            pi = pi / pi.sum()
            pi = np.maximum(pi, 0)  # clamp negative values from floating error
            return {state: float(pi[i]) for i, state in enumerate(_STATES)}
        except np.linalg.LinAlgError:
            logger.warning("Steady-state computation failed — matrix may be degenerate")
            return None
