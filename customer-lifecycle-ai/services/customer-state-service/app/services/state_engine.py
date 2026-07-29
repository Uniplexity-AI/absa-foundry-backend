"""State Engine — Deterministic rule-based state classifier.

Rules evaluated in priority order; first match wins.
All thresholds configurable via StateConfig (env-prefixed: CS_).

IMPORTANT: This classifier does NOT use health_score as an input.
Health Score belongs to Layer 2 (Prediction Service) per system-design.md §8.
"""
from __future__ import annotations

from datetime import date

from app.config.settings import StateConfig
from app.schemas.state import StateResult


class StateEngine:
    """Deterministic rule-based state classifier.

    Mirrors the generator pattern from FeaturePipeline — single
    classify() call per customer, no side effects, pure function.
    """

    def __init__(self, config: StateConfig) -> None:
        self._cfg = config

    def classify(
        self, features: dict, previous_state: str | None = None
    ) -> StateResult:
        """Classify a single customer from their feature snapshot.

        Args:
            features: Dict of feature_name → value from customer_features.
                      Required: days_since_last_txn, engagement_score,
                      rel_customer_status, risk_dormant_indicator, txn_count_90d.
            previous_state: Previous state for transition-aware logic.

        Returns:
            StateResult with state and classification metadata.
        """
        rules_fired: list[str] = []
        state: str

        # Extract feature values with safe defaults
        days = features.get("days_since_last_txn")
        engagement = features.get("engagement_score")
        status = features.get("rel_customer_status", "")
        dormant_indicator = features.get("risk_dormant_indicator", False)
        txn_count = features.get("txn_count_90d")

        # Priority 1: CHURNED
        if status == "Closed":
            rules_fired.append("account_closed")
            state = "CHURNED"
        elif days is not None and days > self._cfg.churned_days_threshold:
            rules_fired.append(f"inactive_{self._cfg.churned_days_threshold}d")
            state = "CHURNED"

        # Priority 2: DORMANT (strict > threshold)
        #
        # The three sub-conditions are independent OR branches:
        #   1. days_since_last_txn > 90  — primary inactivity signal
        #   2. txn_count_90d = 0          — implicit: days>90 guarantees this,
        #      but explicitly checked as a hedge against future Feature Engine
        #      changes that could decouple txn_count_90d from days_since_last_txn.
        #   3. engagement_score < 10      — deliberate: engagement collapse is a
        #      legitimate independent dormancy signal. A customer still transacting
        #      (auto-debits, minimum required) but with near-zero engagement is
        #      functionally dormant. See decision log D9.
        elif days is not None and days > self._cfg.dormant_days_threshold:
            rules_fired.append(f"inactive_{self._cfg.dormant_days_threshold}d")
            state = "DORMANT"
        elif txn_count is not None and txn_count <= self._cfg.dormant_txn_count_threshold and days is not None and days > 30:
            rules_fired.append("zero_txn_90d")
            state = "DORMANT"
        elif engagement is not None and engagement < self._cfg.engagement_dormant_threshold:
            rules_fired.append("engagement_collapse")
            state = "DORMANT"

        # Priority 3: AT_RISK (>= min threshold)
        elif days is not None and days >= self._cfg.atrisk_days_min:
            rules_fired.append(f"inactive_{self._cfg.atrisk_days_min}d")
            state = "AT_RISK"
        elif dormant_indicator:
            rules_fired.append("dormant_indicator")
            state = "AT_RISK"
        elif engagement is not None and engagement < self._cfg.engagement_atrisk_max:
            rules_fired.append("engagement_decay")
            state = "AT_RISK"

        # Priority 4: ACTIVE (default)
        else:
            state = "ACTIVE"

        is_transition = previous_state is not None and previous_state != state

        rule_key = "risk_rules" if state in ("AT_RISK", "DORMANT", "CHURNED") else "active_rules"

        return StateResult(
            customer_id=features.get("customer_id", "unknown"),
            as_of_date=date.today(),  # caller should set this
            state=state,
            classification_rules={rule_key: rules_fired},
            previous_state=previous_state,
            is_transition=is_transition,
        )