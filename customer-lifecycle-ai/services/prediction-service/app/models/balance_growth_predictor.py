"""BalanceGrowthPredictor — Customer Balance Growth.

Scores the **balance growth percentage** per customer from the
``customer_features`` snapshot using the trained LightGBM regressor at
``models/balance-forecast-prediction/lightgbm_balance_growth_model.pkl``.

Contract:
  * ``predict_batch(rows)`` -> percentage growth per customer
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("prediction.balance_growth_predictor")

# app/models/balance_growth_predictor.py -> app/models -> app -> prediction-service -> services -> project_root
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))
            )
        )
    )
)

#: Default trained regressor, shipped in the repo.
DEFAULT_BALANCE_GROWTH_MODEL_PATH = os.path.join(
    _PROJECT_ROOT,
    "models",
    "balance-forecast-prediction",
    "lightgbm_balance_growth_model.pkl",
)

#: LightGBM treats *negative* categorical values as missing (same as NaN), which
#: is the correct encoding for a value the model never saw during training.
_MISSING_CATEGORY_CODE = -1
_TRUTHY = ("1", "true", "t", "yes", "y")


def _code_for(value, categories: list) -> int:
    """Map a raw column value to the integer category code used at training time."""
    if value is None:
        return _MISSING_CATEGORY_CODE
    if isinstance(value, float) and value != value:  # NaN
        return _MISSING_CATEGORY_CODE

    for i, cat in enumerate(categories):
        try:
            if value == cat:
                return i
        except Exception:  # noqa: BLE001 - exotic dtypes simply do not match
            continue

    if all(isinstance(c, bool) for c in categories):
        truthy = str(value).strip().lower() in _TRUTHY
        for i, cat in enumerate(categories):
            if bool(cat) is truthy:
                return i
    elif all(isinstance(c, str) for c in categories):
        text = str(value).strip().upper()
        for i, cat in enumerate(categories):
            if text == cat.strip().upper():
                return i

    return _MISSING_CATEGORY_CODE


def _derive_categorical_spec(model, feature_names: list[str]) -> dict[str, list]:
    """Recover the categorical-column contract from the trained artifact."""
    booster = getattr(model, "booster_", None)
    if booster is None:
        return {}
    categories = list(getattr(booster, "pandas_categorical", None) or [])
    if not categories:
        return {}
    try:
        infos = booster.dump_model().get("feature_infos", {})
    except Exception as e:  # noqa: BLE001
        logger.error("Could not read Balance Growth feature_infos: %s", e)
        return {}
    cat_features = [
        name
        for name in feature_names
        if isinstance(infos.get(name), dict) and infos[name].get("values")
    ]
    if len(cat_features) != len(categories):
        logger.error(
            "Balance Growth categorical metadata is inconsistent (%d categorical features "
            "vs %d stored category lists) — refusing to guess the encoding.",
            len(cat_features), len(categories),
        )
        return {}
    return {name: list(cats) for name, cats in zip(cat_features, categories)}


class BalanceGrowthPredictor:
    """Balance Growth regressor (no fallback)."""

    def __init__(self, model_path: str | None = None) -> None:
        self._model = None
        self._feature_names: list[str] = []
        self._categorical: dict[str, list] = {}
        self._model_version = "not_loaded"

        resolved = model_path if model_path is not None else DEFAULT_BALANCE_GROWTH_MODEL_PATH
        if resolved and not os.path.isabs(resolved):
            resolved = os.path.join(_PROJECT_ROOT, resolved)
        self._model_path = resolved

        if resolved and os.path.exists(resolved):
            try:
                import joblib

                model = joblib.load(resolved)
                names = list(getattr(model, "feature_name_", []) or [])
                if not names:
                    raise ValueError(
                        "model exposes no feature_name_ — cannot build the input vector"
                    )
                self._model = model
                self._feature_names = names
                self._model_version = os.path.splitext(os.path.basename(resolved))[0]

                raw_categories = list(
                    getattr(getattr(model, "booster_", None), "pandas_categorical", None)
                    or []
                )
                self._categorical = _derive_categorical_spec(model, names)
                if raw_categories and not self._categorical:
                    raise ValueError(
                        f"model declares {len(raw_categories)} categorical column(s) "
                        "but they could not be mapped back to feature names — "
                        "refusing to predict with silently mis-encoded categories"
                    )

                logger.info(
                    "BalanceGrowthPredictor loaded %s (%s, %d features, %d categorical)",
                    self._model_version, type(model).__name__, len(names),
                    len(self._categorical),
                )
            except Exception as e:  # noqa: BLE001
                self._model = None
                self._model_version = "not_loaded"
                logger.error(
                    "Balance Growth model load failed (%s): %s", resolved, e,
                )
        else:
            self._model_version = "not_loaded"
            logger.error(
                "BalanceGrowthPredictor: model NOT LOADED (missing file: %s).", resolved,
            )

    @property
    def is_model_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_version(self) -> str:
        return self._model_version

    def predict_batch(self, feature_rows: list[dict]) -> list[float]:
        """Percentage growth for each row. Returns ``[]`` when no model is loaded."""
        if self._model is None or not feature_rows:
            return []
        import pandas as pd

        frame = pd.DataFrame(
            [
                {name: row.get(name) for name in self._feature_names}
                for row in feature_rows
            ],
            columns=self._feature_names,
        )
        for name, categories in self._categorical.items():
            frame[name] = [_code_for(v, categories) for v in frame[name]]
        matrix = frame.apply(pd.to_numeric, errors="coerce").astype("float64").to_numpy()
        return [float(v) for v in self._model.predict(matrix)]
