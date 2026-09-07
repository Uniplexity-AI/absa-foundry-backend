"""CLVPredictor — Customer Lifetime Value via percentile-rank (PoC).

Follows prediction-service.md §5.1 exactly.
No ML model — uses PERCENT_RANK of total_amount_90d from SQL.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("prediction.clv_predictor")


class CLVPredictor:
    """PoC CLV via SQL percentile-rank of total_amount_90d.

    Production path (§5.3): swap in trained XGBoost regressor when
    historical CLV data becomes available. API stays identical.
    """

    def __init__(self) -> None:
        self._model_version = "percentile_v1"
        logger.info("CLVPredictor loaded: percentile-rank (PoC)")

    @property
    def model_version(self) -> str:
        return self._model_version

    def get_percentile(
        self, customer_id: str, clv_percentiles: dict[str, float]
    ) -> float:
        """Look up pre-computed CLV percentile for a customer.

        Args:
            customer_id: Customer identifier.
            clv_percentiles: Dict from PredictionRepository.load_clv_percentiles().

        Returns:
            Percentile [0, 1]. Returns 0.5 (median) if customer not found.
        """
        return clv_percentiles.get(customer_id, 0.5)
