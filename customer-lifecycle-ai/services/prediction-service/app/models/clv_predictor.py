"""CLVPredictor — Customer Lifetime Value.

Scores an **absolute** 12-month net revenue (ZMW) per customer from the
``customer_features`` snapshot using the trained LightGBM regressor at
``models/customer-lifetime-value-prediction/lightgbm_clv_model.pkl``.

There is deliberately NO statistical fallback. If the model is missing or fails
to load, ``is_model_loaded`` is False and ``predict_batch`` returns ``[]`` —
callers must surface CLV as *unavailable*. The old PoC percentile-rank of
``total_amount_90d`` was removed because a proxy percentile is indistinguishable
from a model prediction downstream (it populated real-looking CLV bands and the
CLV component of the health score, masking a failed model load).

Contract:
  * ``predict_batch(rows)``            -> absolute CLV per customer (model only)
  * ``percentiles_from_predictions()`` -> [0, 1] percentile for bands/health score
  * ``get_percentile()``               -> lookup with a 0.5 (median) default
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("prediction.clv_predictor")

# app/models/clv_predictor.py -> app/models -> app -> prediction-service -> services -> project_root
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
DEFAULT_CLV_MODEL_PATH = os.path.join(
    _PROJECT_ROOT,
    "models",
    "customer-lifetime-value-prediction",
    "lightgbm_clv_model.pkl",
)

#: LightGBM treats *negative* categorical values as missing (same as NaN), which
#: is the correct encoding for a value the model never saw during training.
_MISSING_CATEGORY_CODE = -1
_TRUTHY = ("1", "true", "t", "yes", "y")


def _code_for(value, categories: list) -> int:
    """Map a raw column value to the integer category code used at training time.

    Falls back to a normalised comparison (case-insensitive for text,
    truthiness for booleans) so that ``"mobile_app"`` or ``0``/``"0"`` still
    land on the right category. Unrecognised values become ``-1`` = missing.
    """
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
    """Recover the categorical-column contract from the trained artifact.

    LightGBM stores the training category values in the booster's
    ``pandas_categorical``, and the categorical features themselves are visible
    in ``feature_infos``: entries carrying a non-empty ``values`` list are
    exactly the categorical ones, in feature order — which is the same order
    ``pandas_categorical`` was built in. Returns ``{}`` when the metadata cannot
    be reconciled.
    """
    booster = getattr(model, "booster_", None)
    if booster is None:
        return {}
    categories = list(getattr(booster, "pandas_categorical", None) or [])
    if not categories:
        return {}
    try:
        infos = booster.dump_model().get("feature_infos", {})
    except Exception as e:  # noqa: BLE001
        logger.error("Could not read CLV feature_infos: %s", e)
        return {}
    cat_features = [
        name
        for name in feature_names
        if isinstance(infos.get(name), dict) and infos[name].get("values")
    ]
    if len(cat_features) != len(categories):
        logger.error(
            "CLV categorical metadata is inconsistent (%d categorical features "
            "vs %d stored category lists) — refusing to guess the encoding.",
            len(cat_features), len(categories),
        )
        return {}
    return {name: list(cats) for name, cats in zip(cat_features, categories)}


class CLVPredictor:
    """Absolute-CLV regressor (no fallback).

    The model was trained on the full ``customer_features`` column set; its
    ``feature_name_`` list is the authoritative, ordered input contract, so the
    predictor builds the input frame from those names (extra columns are
    ignored, missing values become NaN).
    """

    def __init__(self, model_path: str | None = None) -> None:
        self._model = None
        self._feature_names: list[str] = []
        self._categorical: dict[str, list] = {}
        self._model_version = "not_loaded"

        resolved = model_path if model_path is not None else DEFAULT_CLV_MODEL_PATH
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

                # The model was trained from a pandas frame that had categorical
                # dtypes; LightGBM rejects any frame whose categorical columns do
                # not match the ones baked into the artifact, so the encoding
                # contract is recovered here and applied explicitly at predict
                # time (see predict_batch).
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
                    "CLVPredictor loaded %s (%s, %d features, %d categorical)",
                    self._model_version, type(model).__name__, len(names),
                    len(self._categorical),
                )
            except Exception as e:  # noqa: BLE001 - a bad model must not stop the service
                self._model = None
                self._model_version = "not_loaded"
                logger.error(
                    "CLV model load failed (%s): %s — CLV will be reported as "
                    "UNAVAILABLE (no fallback applied).", resolved, e,
                )
        else:
            self._model_version = "not_loaded"
            logger.error(
                "CLVPredictor: CLV model NOT LOADED (missing file: %s). CLV will be "
                "reported as UNAVAILABLE — no fallback is applied.", resolved,
            )

    @property
    def is_model_loaded(self) -> bool:
        return self._model is not None

    @property
    def model_version(self) -> str:
        return self._model_version

    def predict_batch(self, feature_rows: list[dict]) -> list[float]:
        """Absolute CLV for each row. Returns ``[]`` when no model is loaded.

        Only the model's own ``feature_name_`` columns are projected, in that
        exact order, so column order matches training. Categorical columns are
        encoded to the training-time integer codes and the frame is handed to
        LightGBM as a plain numeric matrix — passing a DataFrame would drag in
        the pandas ``category`` dtype contract and LightGBM rejects any frame
        whose categorical columns differ from the ones stored in the artifact.
        """
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

    @staticmethod
    def percentiles_from_predictions(
        feature_rows: list[dict], predictions: list[float]
    ) -> dict[str, float]:
        """PERCENT_RANK of the predicted CLV values (ties share the lower rank).

        Mirrors PostgreSQL ``PERCENT_RANK()``: ``(rank - 1) / (n - 1)``.
        """
        n = len(predictions)
        if n == 0:
            return {}
        if n == 1:
            return {feature_rows[0]["customer_id"]: 0.5}

        order = sorted(range(n), key=lambda i: predictions[i])
        out: dict[str, float] = {}
        prev_value: float | None = None
        prev_pct = 0.0
        for position, idx in enumerate(order):
            value = predictions[idx]
            if prev_value is not None and value == prev_value:
                pct = prev_pct  # tie -> same rank
            else:
                pct = position / (n - 1)
                prev_value = value
                prev_pct = pct
            out[feature_rows[idx]["customer_id"]] = round(pct, 6)
        return out

    def get_percentile(
        self, customer_id: str, clv_percentiles: dict[str, float]
    ) -> float:
        """Look up pre-computed CLV percentile for a customer.

        Args:
            customer_id: Customer identifier.
            clv_percentiles: Dict from ``percentiles_from_predictions``.

        Returns:
            Percentile [0, 1]. Returns 0.5 (median) if customer not found.
        """
        return clv_percentiles.get(customer_id, 0.5)
