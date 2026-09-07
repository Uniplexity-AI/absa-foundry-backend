"""Gateway route — /api/v1/models → Prediction Service (:8004).

Returns the registered model registry (champion/challenger models with
metrics) and triggers a background churn-model retrain job.

TODO:
Surface a job-status endpoint once a durable job store exists; for now the
client polls the registry (GET /api/v1/models) for a changed trained_at.
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/v1/models", tags=["models"])

_MODELS_URL = "http://127.0.0.1:8004"

# Repo-root paths (mirrors gateway/routes/etl_routes.py trigger pattern)
_ROOT = Path(__file__).resolve().parent.parent.parent
_TRAIN_SCRIPT = _ROOT / "scripts" / "train_models.py"
_LOGS_DIR = _ROOT / "logs" / "training"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("")
async def proxy_models(request: Request):
    """Forward model registry query to Prediction Service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{_MODELS_URL}/predict/models")
            return JSONResponse(
                content=resp.json() if resp.content else None,
                status_code=resp.status_code,
            )
        except httpx.ConnectError:
            raise HTTPException(status_code=502, detail="Prediction Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Prediction Service timed out")


@router.post("/retrain")
async def trigger_retrain(request: Request):
    """Kick off a background churn-model retrain (scripts/train_models.py).

    Returns immediately with the log path. Training runs detached and writes
    models/registry.json on completion — poll GET /api/v1/models and watch
    the champion model's trained_at/version to detect completion.
    """
    if not _TRAIN_SCRIPT.exists():
        raise HTTPException(status_code=404, detail=f"Train script not found: {_TRAIN_SCRIPT}")

    started_at = datetime.now().isoformat(timespec="seconds")
    log_name = f"retrain_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_path = _LOGS_DIR / log_name

    try:
        with open(log_path, "w") as log_file:
            cmd = [sys.executable, str(_TRAIN_SCRIPT)]
            subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(_ROOT))
        return {
            "status": "triggered",
            "message": f"Retrain started — logs: logs/training/{log_name}",
            "started_at": started_at,
            "log": f"logs/training/{log_name}",
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to start retrain: {str(e)}")

