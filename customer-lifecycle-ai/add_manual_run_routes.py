import sys

path = 'gateway/routes/etl_routes.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'BackgroundTasks' not in content:
    content = content.replace('from fastapi import APIRouter', 'from fastapi import APIRouter, BackgroundTasks')

new_endpoints = \"\"\"
# ===========================================================================
# POST /api/etl/trigger-manual-run
# ===========================================================================
import json
import httpx
import asyncio

_MANUAL_PROGRESS_FILE = Path(__file__).resolve().parent.parent.parent / "manual_progress.json"

@router.get("/manual-run-status")
def get_manual_run_status():
    if _MANUAL_PROGRESS_FILE.exists():
        try:
            with open(_MANUAL_PROGRESS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"status": "idle", "step": 0, "results": []}

@router.post("/trigger-manual-run")
def trigger_manual_run(
    background_tasks: BackgroundTasks,
    snapshot: str = Query(...),
):
    def run_pipeline():
        state = {"status": "running", "step": 1, "results": [], "snapshot": snapshot}
        def save_state():
            with open(_MANUAL_PROGRESS_FILE, "w") as f:
                json.dump(state, f)
        
        save_state()
        try:
            # Step 1: Extraction & Models
            cmd = [sys.executable, str(_RUN_ETL), "--extraction-spec", str(_SPECS_DIR / "customer_360.yaml"), "--source-type", "denodo", "--snapshot", snapshot, "--force"]
            subprocess.run(cmd, check=True)
            models_cmd = [sys.executable, str(_RUN_ETL), "--models", "shared,churn,clv,lifecycle,balance", "--snapshot", snapshot, "--force"]
            subprocess.run(models_cmd, check=True)
            state["results"].append({"step": 1, "message": "Extraction complete"})
            
            # Step 2: Feature Engine
            state["step"] = 2
            save_state()
            with httpx.Client(base_url="http://127.0.0.1:8000", timeout=3600) as client:
                r = client.post("/features/compute-batch", params={"as_of_date": snapshot})
                r.raise_for_status()
                state["results"].append({"step": 2, "message": f"{r.json().get('customers_processed', '?')} customers processed"})
            
            # Step 3: State Engine
            state["step"] = 3
            save_state()
            with httpx.Client(base_url="http://127.0.0.1:8000", timeout=3600) as client:
                r = client.post("/api/v1/customers/compute-states", params={"as_of_date": snapshot})
                r.raise_for_status()
                state["results"].append({"step": 3, "message": f"{r.json().get('customers_processed', '?')} classified"})
                
            # Step 4: Prediction Batch
            state["step"] = 4
            save_state()
            with httpx.Client(base_url="http://127.0.0.1:8000", timeout=3600) as client:
                r = client.post("/api/predict/batch", params={"as_of_date": snapshot})
                r.raise_for_status()
                state["results"].append({"step": 4, "message": f"Predictions generated"})
                
            state["status"] = "completed"
            state["step"] = 5
            save_state()
            
        except Exception as e:
            state["status"] = "error"
            state["error_message"] = str(e)
            save_state()

    background_tasks.add_task(run_pipeline)
    return {"status": "started"}
\"\"\"

content = content.replace('# Existing: GET /api/etl/runs', new_endpoints + '\\n# Existing: GET /api/etl/runs')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated successfully")
