$ErrorActionPreference = "Stop"

# Array of 24 monthly snapshots (July 2024 to June 2026)
$snapshots = @(
    "2024-07-01", "2024-08-01", "2024-09-01", "2024-10-01", "2024-11-01", "2024-12-01",
    "2025-01-01", "2025-02-01", "2025-03-01", "2025-04-01", "2025-05-01", "2025-06-01",
    "2025-07-01", "2025-08-01", "2025-09-01", "2025-10-01", "2025-11-01", "2025-12-01",
    "2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01", "2026-06-01"
)

$progressFile = "extraction_progress.json"
$progress = @{ status = "started"; current = 0; total = $snapshots.Length; current_date = "" }
$progress | ConvertTo-Json | Set-Content $progressFile

Write-Host "======================================================"
Write-Host " Starting 24-Month Historical ETL Extraction "
Write-Host " Target Models: shared, churn, clv, lifecycle, balance"
Write-Host " Source: ABSA Hadoop (Denodo)"
Write-Host " Period: July 2024 -> June 2026"
Write-Host "======================================================"

$i = 0
foreach ($date in $snapshots) {
    $i++
    $progress = @{ status = "running"; current = $i; total = $snapshots.Length; current_date = $date }
    $progress | ConvertTo-Json | Set-Content $progressFile
    
    Write-Host "`n---> Extracting snapshot for $date ..." -ForegroundColor Cyan
    
    # Run the ETL for the specific snapshot date
    try {
        # 1. Base extraction from Denodo to Postgres etl_clean
        .venv\Scripts\python.exe run_etl.py --extraction-spec etl/config/extraction_specs/customer_360.yaml --snapshot $date --source-type denodo --force --limit 10
        if ($LASTEXITCODE -ne 0) { throw "Base extraction failed" }

        # 2. ML feature generation to feature_store_*
        .venv\Scripts\python.exe run_etl.py --models shared,churn,clv,lifecycle,balance --snapshot $date --force
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Extraction failed for snapshot $date. See logs above." -ForegroundColor Red
            # We continue to the next month even if one fails, to ensure we get as much data as possible
        } else {
            Write-Host "SUCCESS: Completed extraction for snapshot $date." -ForegroundColor Green
        }
    } catch {
        Write-Host "EXCEPTION: Failed to execute python script for $date." -ForegroundColor Red
    }
}

$progress = @{ status = "completed"; current = $snapshots.Length; total = $snapshots.Length; current_date = "done" }
$progress | ConvertTo-Json | Set-Content $progressFile

Write-Host "`n======================================================"
Write-Host " Historical Extraction Loop Finished! "
Write-Host "======================================================"



