import sys

path = 'gateway/routes/feature_routes.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('from fastapi import APIRouter, Depends, HTTPException, Query, status', 'from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks')

new_endpoint = """
# ===========================================================================
# POST /features/extract-historical
# ===========================================================================
@router.post("/extract-historical")
def extract_historical(
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(require_auth),
):
    def run_historical_etl():
        import subprocess
        from pathlib import Path
        repo_root = Path(__file__).resolve().parent.parent.parent
        subprocess.run(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", "run_historical_etl.ps1"],
            cwd=str(repo_root),
            timeout=3600
        )
    background_tasks.add_task(run_historical_etl)
    return {"status": "extraction_started"}

# ===========================================================================
# POST /features/compute-batch
"""

content = content.replace('# ===========================================================================\n# POST /features/compute-batch', new_endpoint.strip())

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated successfully")
