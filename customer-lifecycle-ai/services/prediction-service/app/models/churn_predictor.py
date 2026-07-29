"""ChurnPredictor — XGBoost churn classifier with leakage guard.

Follows prediction-service.md §4.5 exactly.
"""
from __future__ import annotations

import json
import logging
import os

import xgboost as xgb

logger = logging.getLogger("prediction.churn_predictor")

# Project root — registry.json and models/ are relative to this
# app/models/churn_predictor.py → app/models/ → app/ → prediction-service/ → services/ → project_root
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
    )
)


class ChurnPredictor:
    """Loads XGBoost model + training feature list from registry.

    Design contract — three layers of leakage prevention:

    1. REGISTRY (source of truth): training_features is written by
       train_models.py at training time. It is the exact, ordered list
       of columns that were passed to model.fit(). Leakage features are
       NOT in this list.

    2. API LAYER (pass-through): The PredictionService reads all 56
       feature columns from customer_features and passes the full dict
       to ChurnPredictor. The API does NOT filter columns — it stays
       clean and doesn't need to know about leakage.

    3. PREDICTOR (gatekeeper): ChurnPredictor receives the full 56-feature
       dict and iterates over its internal training_features list, pulling
       only the columns it needs. Leakage features are present in the dict
       but silently ignored — they never reach the model.

    This means:
    - No leakage can reach XGBoost (predictor is the sole gatekeeper)
    - Column order is guaranteed identical to training (single list, no
      dict key lookups at vector-build time)
    - API contracts stay clean (PredictionService doesn't know about leakage)
    - If the registry is corrupted (leakage column in training_features),
      the defensive cross-check raises ValueError at startup
    """

    def __init__(
        self,
        model_path: str | None = None,
        registry_path: str | None = None,
    ) -> None:
        # Resolve paths relative to project root
        if model_path is None:
            model_path = os.path.join(
                _PROJECT_ROOT,
                "models/champion/churn/xgboost_churn_v1.json",
            )
        if registry_path is None:
            registry_path = os.path.join(_PROJECT_ROOT, "models/registry.json")

        self._model = xgb.XGBClassifier()
        self._model.load_model(model_path)
        self._calibrator = None  # PoC default — no calibrator (D12)
        self._model_version = "churn_v1"

        # Load training feature list from registry (written at training time)
        with open(registry_path) as f:
            registry = json.load(f)

        # Look up champion churn model in the registry
        models = registry.get("models", [])
        churn_entry = None
        for m in models:
            if m.get("type") == "churn" and m.get("status") == "champion":
                churn_entry = m
                break

        if churn_entry is None:
            raise ValueError(
                "No champion churn model found in registry. "
                "Run scripts/train_models.py first."
            )

        self._training_features: list[str] = churn_entry["training_features"]
        self._leakage_excluded: list[str] = churn_entry.get(
            "leakage_features_excluded", []
        )
        self._model_version = churn_entry.get("model_id", "churn_v1")

        # Load calibrator if registered (production path — PoC is None)
        cal_path = churn_entry.get("calibrator")
        if cal_path:
            import joblib
            cal_full = os.path.join(_PROJECT_ROOT, cal_path)
            self._calibrator = joblib.load(cal_full)
            logger.info("Calibrator loaded: %s", cal_path)

        # Defensive: confirm no leakage features are in the training list
        leakage_in_training = set(self._leakage_excluded) & set(
            self._training_features
        )
        if leakage_in_training:
            raise ValueError(
                f"LEAKAGE DETECTED: {leakage_in_training} found in training_features. "
                f"The model registry is corrupted — these columns must never reach "
                f"XGBoost."
            )

        logger.info(
            "ChurnPredictor loaded: model=%s, features=%d (leakage excluded: %d)",
            self._model_version,
            len(self._training_features),
            len(self._leakage_excluded),
        )

    @property
    def model_version(self) -> str:
        return self._model_version

    def predict(self, features: dict) -> float:
        """Receive full 56-feature dict; extract only training_features in order.

        PoC: returns raw XGBoost score (ranking score, NOT a true probability).
        Production: returns calibrated probability if calibrator is registered.
        """
        vector = self._dict_to_vector(features)
        raw = float(self._model.predict_proba([vector])[0, 1])
        if self._calibrator is not None:
            return float(self._calibrator.predict_proba([[raw]])[0, 1])
        return raw

    def predict_batch(self, feature_rows: list[dict]) -> list[float]:
        """Receive list of full 56-feature dicts; extract training_features from each."""
        vectors = [self._dict_to_vector(r) for r in feature_rows]
        raw = self._model.predict_proba(vectors)[:, 1].tolist()
        if self._calibrator is not None:
            raw_2d = [[r] for r in raw]
            return self._calibrator.predict_proba(raw_2d)[:, 1].tolist()
        return raw

    def _dict_to_vector(self, features: dict) -> list[float]:
        """Map a full feature dict to the exact training vector layout.

        Iterates over self._training_features (registry-defined order),
        pulling only those columns. Leakage features in the dict are
        present but silently ignored — they never reach the model.

        NULL values are coerced to 0.0 (same as training).
        """
        result = []
        for col in self._training_features:
            val = features.get(col)
            if val is None:
                result.append(0.0)
            else:
                try:
                    result.append(float(val))
                except (TypeError, ValueError):
                    result.append(0.0)
        return result
