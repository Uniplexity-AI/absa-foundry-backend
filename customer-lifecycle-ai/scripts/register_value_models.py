#!/usr/bin/env python3
"""Register the Customer Value Intelligence models (CLV family).

Two things happen, in this order:

1. **models/registry.json** — the document served by ``GET /api/v1/models``:
     * ``models[]`` gains ``value_erosion_v1`` and ``value_forecast_v1`` (type ``clv``)
     * ``champion.clv_prediction`` is promoted from ``placeholder`` to the real
       artifacts + walk-forward metrics
2. **etl_clean.model_registry** — the MLOps control-plane table behind
   ``/api/v1/models/champion``, ``/challengers`` and ``/compare`` — is synced
   with every entry in ``models[]``.

Status mapping (deliberate): the churn model stays the operational ``CHAMPION``
so ``/champion`` keeps returning the model whose ``optimal_threshold`` drives
the threshold/calibration workflow. The value models are written as ``APPROVED``
— they are the champions of their own family and are in production, and
``APPROVED`` makes them visible to ``/challengers`` for champion/challenger
comparison.

Usage (from the repo root, after ``scripts/train_value_model.py`` has run):

    .venv\\Scripts\\python.exe scripts\\register_value_models.py
    .venv\\Scripts\\python.exe scripts\\register_value_models.py --skip-db
    .venv\\Scripts\\python.exe scripts\\register_value_models.py --metrics path\\to\\metrics.json
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REGISTRY_PATH = ROOT / "models" / "registry.json"
DEFAULT_METRICS_PATH = ROOT / "models" / "value_models_metrics.json"

# type -> model_family used by the MLOps tables
_FAMILY_BY_TYPE = {"churn": "churn_prediction", "clv": "clv_prediction"}
# the churn model is the operational champion (threshold/calibration workflow)
_CHAMPION_TYPES = {"churn"}
# artifacts that share a family + semantic version need a distinct DB version tag
_ARTIFACT_ROLE = {
    "value_erosion_v1": "erosion",
    "value_forecast_v1": "forecast",
}
_CREATED_BY = "register_value_models.py"


def _mean(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if v is not None]
    return round(sum(nums) / len(nums), 4) if nums else None


def _fold_metric(folds: list[dict], key: str) -> float | None:
    return _mean([f.get(key) for f in folds])


def load_metrics(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"Metrics file not found: {path}\n"
            "Run the value-model trainer first (from the repo root):\n"
            "  .venv\\Scripts\\python.exe scripts\\train_value_model.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def build_value_entries(metrics: dict) -> list[dict]:
    """Build the two registry entries (CLV family) from trainer metrics."""
    dates = metrics.get("as_of_dates") or []
    holdout = dates[-1] if dates else None
    train_dates = dates[:-1]
    trained_at = metrics.get("trained_at")
    features = metrics.get("features") or []
    hyper = metrics.get("hyperparameters") or {}
    validation = metrics.get("validation") or {}
    e_folds = validation.get("erosion_folds") or []
    f_folds = validation.get("forecast_folds") or []

    common = {
        "type": "clv",
        "family": "clv_prediction",
        "status": "champion",  # family champion (file-level status)
        "framework": "xgboost",
        "version": 1,
        "trained_at": trained_at,
        "training_dates": train_dates,
        "holdout_date": holdout,
        "validation": validation.get("strategy", "walk_forward"),
        "training_rows": metrics.get("training_rows"),
        "feature_count_training": metrics.get("feature_count"),
        # alias consumed by the Models page (Model Details -> "Features Used")
        "n_training_features": metrics.get("feature_count"),
        "training_features": features,
    }

    return [
        {
            **common,
            "model_id": "value_erosion_v1",
            "task": "classification",
            "path": "models/value_erosion_v1.pkl",
            "target": (metrics.get("targets") or {}).get("erosion"),
            "hyperparameters": hyper.get("erosion", {}),
            "metrics": {
                "auc": _fold_metric(e_folds, "roc_auc"),
                "pr_auc": _fold_metric(e_folds, "pr_auc"),
                "recall_at_top10pct": _fold_metric(e_folds, "recall_top10"),
                "precision_at_top10pct": _fold_metric(e_folds, "precision_top10"),
            },
            "fold_metrics": e_folds,
        },
        {
            **common,
            "model_id": "value_forecast_v1",
            "task": "regression",
            "path": "models/value_forecast_v1.pkl",
            "target": (metrics.get("targets") or {}).get("forecast"),
            "hyperparameters": hyper.get("forecast", {}),
            "metrics": {
                "rmse": _fold_metric(f_folds, "rmse"),
                "mae": _fold_metric(f_folds, "mae"),
            },
            "fold_metrics": f_folds,
        },
    ]


def update_registry_document(entries: list[dict], metrics: dict) -> dict:
    """Upsert the CLV entries + champion block into models/registry.json."""
    if not REGISTRY_PATH.exists():
        raise SystemExit(f"Registry not found: {REGISTRY_PATH}")

    doc = json.loads(REGISTRY_PATH.read_text(encoding="utf-8-sig"))
    models: list[dict] = doc.get("models", [])

    added, replaced = [], []
    for entry in entries:
        for i, existing in enumerate(models):
            if existing.get("model_id") == entry["model_id"]:
                models[i] = entry
                replaced.append(entry["model_id"])
                break
        else:
            models.append(entry)
            added.append(entry["model_id"])
    doc["models"] = models

    champion = doc.setdefault("champion", {})
    clv = champion.setdefault("clv_prediction", {})
    clv.update(
        {
            "path": "./champion/clv_prediction/",
            "status": "champion",
            "version": "1.0.0",
            "description": (
                "Champion Customer Value Intelligence models "
                "(value-erosion risk classifier + future-value regressor)"
            ),
            "artifacts": {e["model_id"]: e["path"] for e in entries},
            "targets": metrics.get("targets", {}),
            "training_features": metrics.get("features", []),
            "metrics": {e["model_id"]: e["metrics"] for e in entries},
            "trained_at": entries[0].get("trained_at") if entries else None,
        }
    )

    REGISTRY_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return {"added": added, "replaced": replaced, "total_models": len(models)}


def _version_of(model: dict) -> str:
    """DB version tag for a registry entry.

    ``model_registry`` is keyed by (model_family, model_version), but the CLV
    family ships two artifacts under the same semantic version. The role suffix
    keeps them distinct instead of letting one overwrite the other.
    """
    version = model.get("version")
    version = "1.0.0" if version is None else str(version)
    role = _ARTIFACT_ROLE.get(model.get("model_id") or "")
    return f"{version}-{role}" if role else version


def _family_of(model: dict) -> str:
    return (
        _FAMILY_BY_TYPE.get(model.get("type") or "")
        or model.get("family")
        or model.get("type")
        or "unknown"
    )


def sync_database(models: list[dict]) -> dict:
    """Upsert every models[] entry into etl_clean.model_registry."""
    from sqlalchemy import text

    from shared.database.postgres import get_sync_target_engine

    engine = get_sync_target_engine()
    inserted = updated = pruned = 0
    rows: list[tuple[str, str]] = []

    desired: set[tuple[str, str]] = set()
    for model in models:
        if model.get("model_id"):
            desired.add((_family_of(model), _version_of(model)))

    existing_sql = text(
        "SELECT id, model_family, model_version FROM model_registry WHERE created_by = :who"
    )
    delete_sql = text("DELETE FROM model_registry WHERE id = :id")

    select_sql = text(
        "SELECT id FROM model_registry "
        "WHERE model_family = :family AND model_version = :version AND is_deleted = false"
    )
    insert_sql = text(
        """
        INSERT INTO model_registry (
            id, model_family, model_version, algorithm,
            training_dataset_version, feature_set_version, status,
            optimal_threshold, hyperparameters, evaluation_metrics, created_by
        ) VALUES (
            :id, :family, :version, :algorithm,
            :dataset_version, :feature_set_version, :status,
            :threshold, CAST(:hyperparameters AS JSONB), CAST(:evaluation_metrics AS JSONB),
            :created_by
        )
        """
    )
    update_sql = text(
        """
        UPDATE model_registry SET
            status = :status,
            algorithm = :algorithm,
            training_dataset_version = :dataset_version,
            feature_set_version = :feature_set_version,
            optimal_threshold = :threshold,
            hyperparameters = CAST(:hyperparameters AS JSONB),
            evaluation_metrics = CAST(:evaluation_metrics AS JSONB),
            updated_at = now()
        WHERE id = :id
        """
    )

    with engine.begin() as conn:
        # drop rows this script created earlier whose (family, version) is gone
        for row in conn.execute(existing_sql, {"who": _CREATED_BY}).all():
            if (row.model_family, row.model_version) not in desired:
                conn.execute(delete_sql, {"id": row.id})
                pruned += 1

        for model in models:
            model_id = model.get("model_id")
            if not model_id:
                continue
            family = _family_of(model)
            version = _version_of(model)
            status = "CHAMPION" if model.get("type") in _CHAMPION_TYPES else "APPROVED"
            metrics = model.get("metrics") or {}
            # Carry the confusion matrix through — the calibration simulator reads it.
            evaluation_metrics = dict(metrics)
            confusion = ((model.get("classification") or {}).get("confusion_matrix")
                         or (model.get("classification_f1_threshold") or {}).get("confusion_matrix"))
            if confusion:
                evaluation_metrics["confusion_matrix"] = confusion
            dates = model.get("training_dates") or []
            feature_count = (
                model.get("feature_count_training")
                or len(model.get("training_features") or [])
            )

            payload = {
                "family": family,
                "version": version,
                "status": status,
                "algorithm": (model.get("framework") or "xgboost")[:100],
                "dataset_version": (",".join(str(d) for d in dates) or "unknown")[:100],
                "feature_set_version": f"features-{feature_count}"[:100],
                "threshold": metrics.get("optimal_threshold"),
                "hyperparameters": json.dumps(model.get("hyperparameters") or {}),
                "evaluation_metrics": json.dumps(evaluation_metrics, default=str),
                "created_by": _CREATED_BY,
            }

            existing = conn.execute(
                select_sql, {"family": family, "version": version}
            ).scalar()

            if existing:
                conn.execute(update_sql, {**payload, "id": existing})
                updated += 1
            else:
                conn.execute(insert_sql, {**payload, "id": str(uuid.uuid4())})
                inserted += 1
            rows.append((model_id, status))

    return {"inserted": inserted, "updated": updated, "pruned": pruned, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--metrics",
        type=Path,
        default=DEFAULT_METRICS_PATH,
        help=f"trainer metrics JSON (default: {DEFAULT_METRICS_PATH.name})",
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="only update models/registry.json (do not touch etl_clean.model_registry)",
    )
    args = parser.parse_args()

    metrics = load_metrics(args.metrics)
    entries = build_value_entries(metrics)

    result = update_registry_document(entries, metrics)
    print(f"registry.json : {REGISTRY_PATH}")
    print(f"  added   : {result['added'] or '-'}")
    print(f"  replaced: {result['replaced'] or '-'}")
    print(f"  models[]: {result['total_models']} entries")
    for entry in entries:
        print(f"    - {entry['model_id']} ({entry['task']}) -> {entry['metrics']}")

    if args.skip_db:
        print("model_registry: skipped (--skip-db)")
        return 0

    doc = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    db = sync_database(doc.get("models", []))
    print(
        f"model_registry: inserted={db['inserted']} updated={db['updated']} "
        f"pruned={db['pruned']} (etl_clean)"
    )
    for model_id, status in db["rows"]:
        print(f"    - {model_id}: {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
