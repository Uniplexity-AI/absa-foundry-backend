"""LifecyclePredictor — 14 / 30 / 90-day lifecycle-STAGE forecasts.

Three independently trained 6-class LightGBM classifiers, one per horizon. Each
predicts the customer's lifecycle stage **at that horizon**. The *current* stage
stays owned by ``StateEngine`` (deterministic rules in the state service) — these
models are the forward view only, so the two can never disagree about "now".

Artifacts: ``models/churn-lifecycle-prediction/lgbm_{14,30,90}d_model.pkl``.

Class labels
------------
The training scripts encoded ``["NEW","ACTIVE","AT_RISK","DORMANT","CHURNED",
"GROWING"]`` through ``LabelEncoder``, which **sorts**, so ``predict_proba``
column *i* is ``sorted(STAGES)[i]`` — ACTIVE, AT_RISK, CHURNED, DORMANT, GROWING,
NEW — **not** the list order the scripts use in their own ``stages`` variable.
The ``label_encoder_*.pkl`` files were not shipped with the artifacts, so the
order is recovered from that rule and *asserted* against ``model.classes_``; a
mismatch marks the horizon unavailable rather than silently mislabelling every
prediction by one position.

Feature contract
----------------
The models do not consume ``customer_features`` directly — each script derived
its inputs, and those derivations are replayed in :func:`_engineer`. Three
deliberate decisions are documented there:

* the balance **rank perturbation** IS replayed (the model was fitted on
  perturbed ``txn_count_30d``, so matching it is part of the input contract);
* the random **payday balance multiplier** is NOT replayed (that is noise, not
  signal, and it is not reproducible at inference);
* the artificial **MNAR holes** are NOT replayed (the model handles missing
  values, but we pass real ones rather than deleting 35% of them).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("prediction.lifecycle_predictor")

# app/models/lifecycle_predictor.py -> app/models -> app -> prediction-service
# -> services -> project root
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    )
)

DEFAULT_MODEL_DIR = os.path.join(_PROJECT_ROOT, "models", "churn-lifecycle-prediction")

#: Lifecycle stages, as the training scripts list them.
STAGES = ("NEW", "ACTIVE", "AT_RISK", "DORMANT", "CHURNED", "GROWING")

#: `predict_proba` column order. `LabelEncoder` sorts its classes, so this is
#: the mapping from column index to stage — see the module docstring.
STAGE_ORDER = tuple(sorted(STAGES))

HORIZONS = (14, 30, 90)

#: Input contract per horizon, in training column order (read off the scripts).
#: 30d is absent: its script built the list from the dataset's own column order,
#: so the artifact bundle's ``feature_names`` is the only source of truth.
FEATURES: dict[int, tuple[str, ...]] = {
    14: (
        "tenure_days", "days_since_last_txn", "total_balance", "txn_count_30d",
        "txn_count_90d_weighted", "txn_velocity_ratio", "balance_per_txn",
        "is_zero_balance", "dormancy_edge_proximity", "churn_edge_proximity",
        "balance_drain_risk",
    ),
    90: (
        "tenure_days", "days_since_last_txn", "total_balance", "txn_count_30d",
        "txn_count_90d_weighted", "txn_velocity_ratio", "balance_per_txn",
        "is_zero_balance", "tenure_inactivity_ratio", "dormancy_boundary_dist",
        "churn_boundary_dist",
    ),
}

#: Exponential-decay constant per horizon, as trained.
_DECAY = {14: (0.10, 14.0), 90: (0.03, 90.0)}

#: The rank perturbation is a training-time artefact: setting this False scores
#: the raw ``txn_count_30d``, which no longer matches what the model was fitted on.
REPLAY_RANK_PERTURBATION = os.getenv("LIFECYCLE_REPLAY_RANK_PERTURBATION", "1") not in (
    "0", "false", "False",
)

try:  # scipy is a sklearn dependency, but never assume it at import time
    from scipy.stats import norm, rankdata

    _SCIPY = True
except ImportError:  # pragma: no cover - environment dependent
    norm = rankdata = None  # type: ignore[assignment]
    _SCIPY = False

# Reused rather than re-derived: the CLV predictor already owns the fiddly
# LightGBM categorical-dtype recovery rule (booster.pandas_categorical vs
# feature_infos), and a second copy would drift.
from app.models.clv_predictor import _code_for, _derive_categorical_spec  # noqa: E402

_perturbation_warned = False


def _num(value, default: float = 0.0) -> float:
    """None/blank-safe float, so a sparse feature row cannot raise."""
    if value is None or value == "":
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return default if out != out else out  # NaN -> default


def _as_list(value) -> list:
    """Plain list for any container, [] when absent.

    LightGBM/sklearn expose ``classes_`` and friends as **numpy arrays**, and
    ``value or []`` raises "truth value of an array is ambiguous" — so every
    optional attribute has to be unwrapped through here rather than truth-tested.
    """
    if value is None:
        return []
    try:
        return list(value)
    except TypeError:
        return []


def _engineer(rows: list[dict], horizon: int) -> list[dict]:
    """Replay the training script's feature derivations for a whole batch.

    Batch-wise because one step is a *population* transform: the scripts add a
    ``rankdata``-based perturbation to ``txn_count_30d``, which by construction
    depends on every row in the cohort. Scoring one customer at a time would
    produce a different (rank-1) value for the same customer, so callers should
    score the cohort once and serve per-customer reads from that result — the
    same shape the CLV percentile already uses.
    """
    global _perturbation_warned

    out: list[dict] = []
    for row in rows:
        balance = _num(row.get("total_balance", row.get("total_amount_90d")))
        tenure = _num(row.get("tenure_days", row.get("customer_tenure_days")), 999.0)
        days = _num(row.get("days_since_last_txn"), 999.0)
        txn_30 = _num(row.get("txn_count_30d"))
        txn_90 = _num(row.get("txn_count_90d"))

        # Clipped to tenure by both the 14d and 90d scripts.
        days = min(days, tenure)

        decay, scale = _DECAY.get(horizon, (0.10, 14.0))
        weighted = round(txn_90 * pow(2.718281828459045, -decay * (days / scale)), 2)

        feats = {
            "tenure_days": tenure,
            "days_since_last_txn": days,
            "total_balance": balance,
            "txn_count_30d": txn_30,
            "txn_count_90d_weighted": weighted,
            "txn_velocity_ratio": (txn_30 + 1) / ((weighted / 3) + 1),
            "balance_per_txn": balance / (txn_30 + 1),
            "is_zero_balance": 1 if balance < 10.0 else 0,
        }

        if horizon == 14:
            feats["dormancy_edge_proximity"] = max(0.0, 14 - abs(days - 76))
            feats["churn_edge_proximity"] = max(0.0, 14 - abs(days - 166))
            feats["balance_drain_risk"] = (
                1.0 if feats["is_zero_balance"] == 1 and days > 14 else 0.0
            )
        elif horizon == 90:
            feats["tenure_inactivity_ratio"] = days / (tenure + 1.0)
            feats["dormancy_boundary_dist"] = max(0.0, 90 - days)
            feats["churn_boundary_dist"] = max(0.0, 365 - days)

        feats["_customer_id"] = row.get("customer_id")
        out.append(feats)

    if horizon not in (14, 90):
        return out

    if not REPLAY_RANK_PERTURBATION:
        return out

    if not _SCIPY:
        if not _perturbation_warned:
            _perturbation_warned = True
            logger.error(
                "scipy is unavailable — the training-time txn_count_30d rank "
                "perturbation cannot be replayed. Predictions for 14d/90d will be "
                "off-contract (set LIFECYCLE_REPLAY_RANK_PERTURBATION=0 to silence)."
            )
        return out

    n = len(out)
    if n == 0:
        return out
    balances = [r["total_balance"] for r in out]
    ranks = rankdata(balances)  # 1-based, ties average — matches the scripts
    for r, rank in zip(out, ranks):
        u = rank / (n + 1)
        adjusted = r["txn_count_30d"] + int(norm.ppf(u) * 1.5)
        r["txn_count_30d"] = float(max(0, adjusted))
    return out


def _load_disk_encoder(horizon: int, model_dir: str):
    """Load ``label_encoder_{h}d.pkl`` sitting next to the model, if present.

    The 14d/90d training scripts dumped the encoder as a *separate* file and only
    the classifier was copied into the repo, which left their stage names
    unrecoverable (the classifier stores the encoded integers). Dropping the
    encoder beside the model is the fix, so it is checked before giving up.
    """
    for name in (f"label_encoder_{horizon}d.pkl", f"label_encoder_{horizon}d_model.pkl"):
        path = os.path.join(model_dir, name)
        if not os.path.exists(path):
            continue
        try:
            import joblib

            encoder = joblib.load(path)
            logger.info("lifecycle %dd: encoder loaded from %s", horizon, name)
            return encoder
        except Exception as exc:  # noqa: BLE001 - a bad encoder must not stop boot
            logger.error(
                "lifecycle %dd: encoder %s failed to load: %s", horizon, name, exc
            )
            return None
    return None


class LifecyclePredictor:
    """Loads the per-horizon stage classifiers and scores a cohort."""

    def __init__(self, model_dir: str | None = None) -> None:
        self._dir = model_dir or DEFAULT_MODEL_DIR
        self._models: dict[int, object] = {}
        self._features: dict[int, list[str]] = {}
        self._stages: dict[int, tuple[str, ...]] = {}
        self._versions: dict[int, str] = {}
        self._categorical: dict[int, dict[str, list]] = {}
        for horizon in HORIZONS:
            self._load(horizon)

    # ── Loading ────────────────────────────────────────────────────

    def _load(self, horizon: int) -> None:
        path = os.path.join(self._dir, f"lgbm_{horizon}d_model.pkl")
        if not os.path.exists(path):
            logger.error(
                "lifecycle %dd model NOT LOADED (missing %s) — that horizon is "
                "reported unavailable. No fallback is applied.",
                horizon, path,
            )
            return
        try:
            import joblib

            obj = joblib.load(path)
        except Exception as exc:  # noqa: BLE001 - a bad artifact must not stop boot
            logger.error("lifecycle %dd model load failed (%s): %s", horizon, path, exc)
            return

        bundle = obj if isinstance(obj, dict) and "model" in obj else None
        model = bundle["model"] if bundle else obj
        try:
            # Bundled feature_names first (the 30d shape), else the model's own.
            # `_as_list` is mandatory here: these attributes are numpy arrays.
            names = [str(n) for n in _as_list(
                bundle.get("feature_names") if bundle else None
            )]
            if not names:
                names = [str(n) for n in _as_list(getattr(model, "feature_name_", None))]
        except Exception as exc:  # noqa: BLE001
            logger.error("lifecycle %dd: cannot read feature names: %s", horizon, exc)
            return

        if not names:
            logger.error(
                "lifecycle %dd: model exposes no feature names — refusing to predict "
                "with an unknown column order.", horizon,
            )
            return

        expected = FEATURES.get(horizon)
        if expected is not None and tuple(names) != expected:
            logger.error(
                "lifecycle %dd: model's columns do not match the trained contract "
                "(model=%s expected=%s) — refusing to predict.",
                horizon, names, list(expected),
            )
            return

        # An explicit encoder file wins, then whatever the artifact carries
        # itself (the 30d bundle, or sklearn's internal _le).
        encoder = bundle.get("target_encoder") if bundle else None
        if encoder is None:
            encoder = _load_disk_encoder(horizon, self._dir)

        stages = self._stage_order(horizon, model, encoder)
        if stages is None:
            return

        self._models[horizon] = model
        self._features[horizon] = names
        self._stages[horizon] = stages
        self._versions[horizon] = os.path.splitext(os.path.basename(path))[0]

        # LightGBM bakes the training categories into the booster and rejects any
        # frame whose categories differ, so recover that contract the same way the
        # CLV predictor does (single implementation of a fiddly rule).
        declared = bundle.get("categorical_features") if bundle else None
        spec = _derive_categorical_spec(model, names)
        if declared and not spec:
            self._models.pop(horizon, None)
            self._features.pop(horizon, None)
            self._stages.pop(horizon, None)
            logger.error(
                "lifecycle %dd: artifact declares %d categorical column(s) but they "
                "could not be mapped to feature names — refusing to predict with "
                "silently mis-encoded categories.", horizon, len(declared),
            )
            return
        self._categorical[horizon] = spec

        logger.info(
            "lifecycle %dd model loaded: %s (%s, %d features, %d categorical)",
            horizon, self._versions[horizon], type(model).__name__, len(names), len(spec),
        )

    @staticmethod
    def _stage_order(horizon: int, model, encoder) -> tuple[str, ...] | None:
        """Column index -> stage name. Never guesses silently.

        Verified against the artifacts (2026-09-14):

        * **30d** ships a bundle whose ``target_encoder.classes_`` is
          ``['ACTIVE','AT_RISK','CHURNED','DORMANT','GROWING','NEW']`` — i.e. the
          alphabetical rule, empirically confirmed.
        * **90d** is a bare model with ``classes_ == 0..5``. Six classes means the
          training target was exactly the six stage strings, and ``LabelEncoder``
          sorts, so the alphabetical order is provably the column order.
        * **14d** has ``classes_ == 0..4`` — five classes, and its internal ``_le``
          holds only the encoded ints. The names *are* recoverable, but only from
          ``label_encoder_14d.pkl``; without that file the horizon is reported
          unavailable rather than guessed.
        """
        candidates = []
        if encoder is not None:
            candidates.append(encoder)
        internal = getattr(model, "_le", None)
        if internal is not None:
            candidates.append(internal)

        for candidate in candidates:
            raw = _as_list(getattr(candidate, "classes_", None))
            labels = [str(s) for s in raw]
            # Any subset of the known stages is usable: the 14d model was trained
            # on only five of them, so a 5-class encoder is correct, not a fault.
            if labels and all(s in STAGES for s in labels):
                return tuple(labels)
            if labels:
                logger.warning(
                    "lifecycle %dd: encoder holds %s, which are not stage names - "
                    "ignoring it.", horizon, repr(raw)[:60],
                )

        classes = [int(c) for c in _as_list(getattr(model, "classes_", None))]
        if classes == list(range(len(STAGES))):
            return STAGE_ORDER
        logger.error(
            "lifecycle %dd: %d classes (%s) and no usable encoder. The label->stage "
            "mapping cannot be recovered, so this horizon is reported unavailable "
            "rather than guessed - put label_encoder_%dd.pkl next to the model.",
            horizon, len(classes), classes, horizon,
        )
        return None

    # ── Introspection ──────────────────────────────────────────────

    def is_loaded(self, horizon: int) -> bool:
        return horizon in self._models

    def model_version(self, horizon: int) -> str:
        return self._versions.get(horizon, "not_loaded")

    def status(self) -> dict[str, dict]:
        """Per-horizon load state, for the API payload."""
        return {
            str(h): {"loaded": self.is_loaded(h), "version": self.model_version(h)}
            for h in HORIZONS
        }

    # ── Scoring ────────────────────────────────────────────────────

    def predict_batch(self, rows: list[dict], horizon: int) -> list[dict]:
        """Forecast one horizon for the whole batch.

        Returns ``[{customer_id, stage, confidence, probabilities}]`` — one entry
        per input row, or ``[]`` when the horizon's model is unavailable (callers
        must surface that as UNAVAILABLE, there is no fallback).
        """
        model = self._models.get(horizon)
        names = self._features.get(horizon)
        stages = self._stages.get(horizon)
        if model is None or not names or not stages or not rows:
            return []

        import pandas as pd

        engineered = _engineer(rows, horizon)
        # The 30d contract is the *raw* feature row (80 columns), the 14d/90d ones
        # are engineered-only — merging covers both, and the projection below
        # keeps whatever the artifact actually asked for.
        merged = [{**row, **eng} for row, eng in zip(rows, engineered)]
        frame = pd.DataFrame(
            [{name: m.get(name) for name in names} for m in merged],
            columns=names,
        )

        # Categorical columns must reach LightGBM as the integer codes seen at
        # training time; a plain to_numeric would coerce their text to NaN.
        for name, categories in self._categorical.get(horizon, {}).items():
            if name in frame.columns:
                frame[name] = [_code_for(v, categories) for v in frame[name]]

        matrix = frame.apply(pd.to_numeric, errors="coerce").astype("float64").to_numpy()
        probs = model.predict_proba(matrix)  # type: ignore[attr-defined]

        out: list[dict] = []
        for row, vector in zip(engineered, probs):
            values = [float(v) for v in vector]
            best = max(range(len(values)), key=values.__getitem__)
            out.append({
                "customer_id": row.get("_customer_id"),
                "stage": stages[best] if best < len(stages) else None,
                "confidence": round(values[best], 4),
                "probabilities": {
                    stage: round(values[i], 4)
                    for i, stage in enumerate(stages)
                    if i < len(values)
                },
            })
        return out
