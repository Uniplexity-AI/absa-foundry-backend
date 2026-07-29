"""Transition Analyzer — Detects state changes and attributes trigger reasons."""
from __future__ import annotations


class TransitionAnalyzer:
    """Detects state changes and attributes trigger reasons."""

    def detect(
        self,
        current_state: str,
        previous_state: str,
        features: dict,
    ) -> str:
        """Return a human-readable trigger reason for the state change.

        Args:
            current_state: The new state.
            previous_state: The previous state.
            features: Current feature snapshot dict.

        Returns:
            Trigger reason string, e.g. "Inactive 45d (threshold: 30d)".
        """
        days = features.get("days_since_last_txn")
        engagement = features.get("engagement_score")
        status = features.get("rel_customer_status", "")

        # Recovery transitions
        if current_state == "ACTIVE" and previous_state in ("AT_RISK", "DORMANT"):
            return f"Re-engagement — activity resumed (days_since_last_txn={days})"

        # Downward transitions
        if current_state == "CHURNED":
            if status == "Closed":
                return f"Account closed (status={status})"
            return f"Inactive {days}d (threshold: 365d)"

        if current_state == "DORMANT":
            if days is not None and days > 90:
                return f"Inactive {days}d (threshold: 90d)"
            if features.get("txn_count_90d", 0) == 0:
                return "Zero transactions in 90 days"
            return f"Engagement collapse (score={engagement}, threshold=10)"

        if current_state == "AT_RISK":
            if days is not None and days >= 30:
                return f"Inactive {days}d (threshold: 30d)"
            if features.get("risk_dormant_indicator"):
                return "Dormant risk indicator activated"
            return f"Engagement decay (score={engagement}, threshold=20)"

        return f"State transition: {previous_state} -> {current_state}"