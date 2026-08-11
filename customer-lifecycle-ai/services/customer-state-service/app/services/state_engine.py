"""State Engine — Deterministic rule-based state classifier.

6-state Absa lifecycle: NEW → ACTIVE → GROWING → AT_RISK → DORMANT → CHURNED
Rules evaluated in priority order; first match wins.
All thresholds configurable via StateConfig (env-prefixed: CS_).

v2.0 changes (2026-08-08):
- P0: as_of_date parameter (no more date.today() hardcoded)
- P1: NEW + GROWING states for Absa alignment
- P2a: Hysteresis buffer prevents fluttering (DORMANT→ACTIVE requires 2+ txns)
"""
from __future__ import annotations

from datetime import date

from app.config.settings import StateConfig
from app.schemas.state import StateResult


class StateEngine:
    """Deterministic rule-based 6-state classifier."""

    def __init__(self, config: StateConfig) -> None:
        self._cfg = config

    def classify(
        self, features: dict, previous_state: str | None = None,
        as_of_date: date | None = None,
    ) -> StateResult:
        """Classify a single customer from their feature snapshot.

        Args:
            features: Dict of feature_name → value from customer_features.
            previous_state: Previous state for transition-aware logic.
            as_of_date: Effective date for the classification (default: today).

        Returns:
            StateResult with state and classification metadata.
        """
        effective_date = as_of_date or date.today()
        rules_fired: list[str] = []
        state: str

        days = features.get("days_since_last_txn")
        engagement = features.get("engagement_score")
        status = features.get("rel_customer_status", "")
        dormant_indicator = features.get("risk_dormant_indicator", False)
        txn_count = features.get("txn_count_90d")
        tenure_days = features.get("customer_tenure_days", 999)
        balance_growth = features.get("balance_growth_30d_pct", 0)
        new_products = features.get("new_products_60d", 0)

        # Priority 1: CHURNED
        if status == "Closed":
            rules_fired.append("account_closed")
            state = "CHURNED"
        elif days is not None and days > self._cfg.churned_days_threshold:
            rules_fired.append(f"inactive_{self._cfg.churned_days_threshold}d")
            state = "CHURNED"

        # Priority 2: DORMANT (strict inactivity)
        elif days is not None and days > self._cfg.dormant_days_threshold:
            rules_fired.append(f"inactive_{self._cfg.dormant_days_threshold}d")
            state = "DORMANT"
        elif txn_count is not None and txn_count <= self._cfg.dormant_txn_count_threshold and days is not None and days > 30:
            rules_fired.append("zero_txn_90d")
            state = "DORMANT"
        elif engagement is not None and engagement < self._cfg.engagement_dormant_threshold:
            rules_fired.append("engagement_collapse")
            state = "DORMANT"

        # Priority 3: AT_RISK (warning signals)
        elif days is not None and days >= self._cfg.atrisk_days_min:
            rules_fired.append(f"inactive_{self._cfg.atrisk_days_min}d")
            state = "AT_RISK"
        elif dormant_indicator:
            rules_fired.append("dormant_indicator")
            state = "AT_RISK"
        elif engagement is not None and engagement < self._cfg.engagement_atrisk_max:
            rules_fired.append("engagement_decay")
            state = "AT_RISK"

        # Priority 4: NEW (onboarding — <90 days tenure)
        elif tenure_days is not None and tenure_days <= 90:
            rules_fired.append("new_customer_90d")
            state = "NEW"

        # Priority 5: GROWING (expanding balance or adding products)
        elif (balance_growth is not None and balance_growth > 15) or (new_products and new_products > 0):
            if balance_growth and balance_growth > 15:
                rules_fired.append("balance_growth_gt_15pct")
            if new_products and new_products > 0:
                rules_fired.append("new_product_added")
            state = "GROWING"

        # Priority 6: ACTIVE (default)
        else:
            state = "ACTIVE"

        # Hysteresis: don't flip DORMANT→ACTIVE instantly on a single txn
        if previous_state == "DORMANT" and state == "ACTIVE":
            txn_count_30d = features.get("txn_count_30d", 0)
            if txn_count_30d is None or txn_count_30d < 2:
                state = "DORMANT"
                rules_fired = ["hysteresis_hold_dormant"]

        is_transition = previous_state is not None and previous_state != state
        rule_key = "risk_rules" if state in ("AT_RISK", "DORMANT", "CHURNED") else \
                   "growth_rules" if state in ("NEW", "GROWING") else "active_rules"

        return StateResult(
            customer_id=features.get("customer_id", "unknown"),
            as_of_date=effective_date,
            state=state,
            classification_rules={rule_key: rules_fired},
            previous_state=previous_state,
            is_transition=is_transition,
        )