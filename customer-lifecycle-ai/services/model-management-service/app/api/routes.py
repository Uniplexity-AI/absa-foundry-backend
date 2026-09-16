"""Model Management API Routes."""
import asyncio
import json
import random
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.schemas.schemas import (
    CalibrationProposalRequest, CalibrationProposalResponse,
    FeatureSummary, RetrainRequest, RetrainResponse,
    ModelResponse, ModelComparisonResponse, AuditLogResponse
)
from app.models.models import ModelRegistry, FeatureRegistry, CalibrationProposal, AuditLog
from shared.database.session import get_db
# In a real app we'd have a requires_role dependency. Using a dummy for now.
# from shared.auth.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/models", tags=["models"])

def _log_audit(db: Session, user_id: str, action: str, model_id: uuid.UUID = None, previous_state=None, new_state=None, reason=None):
    log = AuditLog(
        user_id=user_id,
        action=action,
        model_id=model_id,
        previous_state=previous_state,
        new_state=new_state,
        reason=reason
    )
    db.add(log)
    db.commit()

@router.get("", response_model=list[ModelResponse])
def list_models(db: Session = Depends(get_db)):
    return db.scalars(select(ModelRegistry).filter_by(is_deleted=False)).all()

@router.get("/champion", response_model=ModelResponse)
def get_champion(db: Session = Depends(get_db)):
    champ = db.scalars(select(ModelRegistry).filter_by(status="CHAMPION", is_deleted=False).order_by(ModelRegistry.created_at.desc())).first()
    if not champ:
        # Mock for UI purposes if none exists
        return ModelResponse(
            id=uuid.uuid4(), model_family="customer_churn", model_version="1.0.0", status="CHAMPION",
            optimal_threshold=0.5, created_at=datetime.now(timezone.utc)
        )
    return champ

@router.get("/challengers", response_model=list[ModelResponse])
def list_challengers(db: Session = Depends(get_db)):
    return db.scalars(select(ModelRegistry).filter(ModelRegistry.status.in_(["VALIDATED", "CHALLENGER", "APPROVED"]), ModelRegistry.is_deleted==False)).all()

@router.get("/features", response_model=list[FeatureSummary])
def list_features(db: Session = Depends(get_db)):
    feats = db.scalars(select(FeatureRegistry).filter_by(is_deleted=False)).all()
    return feats


@router.post("/simulate-calibration")
def simulate_calibration(req: dict, db: Session = Depends(get_db)):
    threshold = req.get("threshold", 0.5)
    champ = db.scalars(select(ModelRegistry).filter_by(status="CHAMPION", is_deleted=False).order_by(ModelRegistry.created_at.desc())).first()
    
    # Use the champion's real confusion matrix when it has one, else a baseline.
    # NOTE: the column is evaluation_metrics (there is no classification_metrics).
    base_tp, base_fp, base_tn, base_fn = 150, 50, 800, 50
    cm = (champ.evaluation_metrics or {}).get("confusion_matrix") if champ else None
    if isinstance(cm, list) and len(cm) == 2 and all(len(row) == 2 for row in cm):
        # [[tn, fp], [fn, tp]] as written by scripts/register_value_models.py
        base_tn, base_fp = cm[0]
        base_fn, base_tp = cm[1]
    elif isinstance(cm, dict):
        base_tp = cm.get("tp", base_tp)
        base_fp = cm.get("fp", base_fp)
        base_tn = cm.get("tn", base_tn)
        base_fn = cm.get("fn", base_fn)
        
    shift = threshold - 0.5
    tp = max(0, int(base_tp * (1 - shift * 1.5)))
    fp = max(0, int(base_fp * (1 - shift * 2.0)))
    tn = max(0, int(base_tn * (1 + shift * 0.5)))
    fn = max(0, int(base_fn * (1 + shift * 1.5)))
    
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}

@router.post("/calibration", response_model=CalibrationProposalResponse)

def submit_calibration(req: CalibrationProposalRequest, db: Session = Depends(get_db)):
    prop = CalibrationProposal(
        model_id=req.model_id,
        proposed_threshold=req.proposed_threshold,
        metrics_snapshot=req.metrics_snapshot,
        status="PENDING",
        created_by="ui_user" # Mock user
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    _log_audit(db, "ui_user", "SUBMIT_CALIBRATION", req.model_id, None, {"threshold": req.proposed_threshold})
    return prop

@router.post("/calibration/{id}/approve")
def approve_calibration(id: uuid.UUID, db: Session = Depends(get_db)):
    prop = db.get(CalibrationProposal, id)
    if not prop or prop.status != "PENDING":
        raise HTTPException(status_code=400, detail="Proposal not found or not pending")
    
    prop.status = "APPROVED"
    prop.approved_by = "admin_user"
    
    model = db.get(ModelRegistry, prop.model_id)
    if model:
        model.optimal_threshold = prop.proposed_threshold
        
    db.commit()
    _log_audit(db, "admin_user", "APPROVE_CALIBRATION", prop.model_id, None, {"threshold": prop.proposed_threshold})
    return {"status": "success"}

# --- Training Background Task (No Redis/Celery) ---
def _run_training_job(model_id: uuid.UUID, feature_ids: list[uuid.UUID], dataset_version: str) -> None:
    """Run the real churn trainer, then record the outcome on this registry row.

    ``scripts/train_models.py`` is the same trainer the pilot bootstrap runs: it
    rewrites models/registry.json and the champion artifacts. Its fresh metrics are
    copied back onto this row so the governance flow
    (validate -> nominate -> approve -> promote) operates on real numbers.
    """
    from shared.database.session import SessionLocal

    repo_root = Path(__file__).resolve().parents[4]
    outcome, metrics, hyperparameters, error = "TRAINED", None, None, None

    try:
        proc = subprocess.run(
            [sys.executable, "scripts/train_models.py"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=1800,
        )
        if proc.returncode != 0:
            outcome = "FAILED"
            error = (proc.stderr or proc.stdout or "trainer failed").strip()[-500:]
        else:
            doc = json.loads((repo_root / "models" / "registry.json").read_text(encoding="utf-8"))
            entry = next((m for m in doc.get("models", []) if m.get("type") == "churn"), None)
            if entry:
                metrics = dict(entry.get("metrics") or {})
                cm = ((entry.get("classification") or {}).get("confusion_matrix")
                      or (entry.get("classification_f1_threshold") or {}).get("confusion_matrix"))
                if cm:
                    metrics["confusion_matrix"] = cm
                hyperparameters = entry.get("hyperparameters")
    except Exception as exc:  # noqa: BLE001 - surface any failure on the row
        outcome, error = "FAILED", str(exc)[:500]

    with SessionLocal() as db:
        model = db.get(ModelRegistry, model_id)
        if not model:
            return
        model.status = outcome
        if metrics:
            model.evaluation_metrics = metrics
            model.optimal_threshold = metrics.get("optimal_threshold")
            if hyperparameters:
                model.hyperparameters = hyperparameters
        elif error:
            model.evaluation_metrics = {"error": error}
        db.commit()
        _log_audit(db, "system", f"TRAINING_{outcome}", model_id,
                   {"status": "TRAINING"}, {"status": outcome}, reason=error)

# Statuses a model row can be in (used by the governance endpoints)
TRAINABLE_STATUS = "TRAINING"

@router.post("/training", response_model=RetrainResponse)
def trigger_training(req: RetrainRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    new_model = ModelRegistry(
        model_family="churn_prediction",
        model_version=f"1.{(datetime.now().microsecond % 1000)}",
        algorithm="XGBoost",
        training_dataset_version=req.dataset_version,
        feature_set_version=f"selected-{len(req.feature_ids)}",
        status=TRAINABLE_STATUS,
        created_by="ui_user"
    )
    db.add(new_model)
    db.commit()
    db.refresh(new_model)
    _log_audit(db, "ui_user", "START_TRAINING", new_model.id, None, {"status": TRAINABLE_STATUS})
    
    background_tasks.add_task(_run_training_job, new_model.id, req.feature_ids, req.dataset_version)
    return RetrainResponse(job_id=str(new_model.id), status=TRAINABLE_STATUS)

@router.get("/compare", response_model=ModelComparisonResponse)
def compare_models(db: Session = Depends(get_db)):
    """Champion vs challenger **within the champion's own family**.

    Without the family filter an approved CLV artifact (already in production for
    its own family) would be presented as a churn challenger.
    """
    champ = db.scalars(select(ModelRegistry).filter_by(status="CHAMPION", is_deleted=False).order_by(ModelRegistry.created_at.desc())).first()
    if not champ:
        return ModelComparisonResponse(champion=None, challenger=None)
    chall = db.scalars(select(ModelRegistry).filter(
        ModelRegistry.status.in_(["TRAINED", "VALIDATED", "CHALLENGER", "APPROVED"]),
        ModelRegistry.is_deleted == False,
        ModelRegistry.model_family == champ.model_family,
    ).order_by(ModelRegistry.created_at.desc())).first()
    return ModelComparisonResponse(champion=champ, challenger=chall)

@router.post("/{model_id}/validate")
def validate_model(model_id: uuid.UUID, db: Session = Depends(get_db)):
    model = db.get(ModelRegistry, model_id)
    if not model or model.status != "TRAINED":
        raise HTTPException(status_code=400, detail="Model must be in TRAINED state")
    model.status = "VALIDATED"
    db.commit()
    _log_audit(db, "ui_user", "VALIDATE_MODEL", model_id, {"status": "TRAINED"}, {"status": "VALIDATED"})
    return {"status": "success"}

@router.post("/{model_id}/nominate")
def nominate_model(model_id: uuid.UUID, db: Session = Depends(get_db)):
    model = db.get(ModelRegistry, model_id)
    if not model or model.status != "VALIDATED":
        raise HTTPException(status_code=400, detail="Model must be in VALIDATED state")
    model.status = "CHALLENGER"
    db.commit()
    _log_audit(db, "ui_user", "NOMINATE_MODEL", model_id, {"status": "VALIDATED"}, {"status": "CHALLENGER"})
    return {"status": "success"}

@router.post("/{model_id}/approve")
def approve_model(model_id: uuid.UUID, db: Session = Depends(get_db)):
    model = db.get(ModelRegistry, model_id)
    # The UI walks TRAINED -> Validate -> Approve -> Promote, so a VALIDATED model is
    # approved directly (the CHALLENGER nomination step is implicit).
    if not model or model.status not in ("VALIDATED", "CHALLENGER"):
        raise HTTPException(status_code=400, detail="Model must be in VALIDATED or CHALLENGER state")
    previous = model.status
    model.status = "APPROVED"
    model.approved_by = "admin_user"
    model.approved_at = datetime.now(timezone.utc)
    db.commit()
    _log_audit(db, "admin_user", "APPROVE_MODEL", model_id, {"status": previous}, {"status": "APPROVED"})
    return {"status": "success"}

@router.post("/{model_id}/promote")
def promote_model(model_id: uuid.UUID, db: Session = Depends(get_db)):
    model = db.get(ModelRegistry, model_id)
    if not model or model.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Model must be in APPROVED state")
    
    # Retire old champions
    champs = db.scalars(select(ModelRegistry).filter_by(status="CHAMPION")).all()
    for c in champs:
        c.status = "RETIRED"
        
    model.status = "CHAMPION"
    db.commit()
    _log_audit(db, "admin_user", "PROMOTE_MODEL", model_id, {"status": "APPROVED"}, {"status": "CHAMPION"})
    return {"status": "success"}

@router.get("/audit", response_model=list[AuditLogResponse])
def get_audit(db: Session = Depends(get_db)):
    return db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(50)).all()