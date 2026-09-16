#Requires -Version 5.1
# =============================================================================
# ABSA Pilot — Full pipeline bootstrap (schema -> data -> features -> states)
#
# Runs the whole synthetic pipeline end-to-end on the pilot box:
#   stop services -> reset etl_clean -> migrations -> seed IAM demo users
#   -> load synthetic data -> feature pipeline (3 dates) -> state engine
#   -> [optional] train models -> start services
#
# Run from anywhere; it resolves paths from its own location:
#
#   # The target DB url is REQUIRED (generator writes to etl_clean, not the
#   # default DATABASE_URL which points at etl_validation):
#   $db = "postgresql://postgres:<PILOT_DB_PASSWORD>@127.0.0.1:5432/etl_clean"
#
#   # Full run:
#   powershell -ExecutionPolicy Bypass -File scripts\pilot_bootstrap.ps1 -DatabaseUrl $db
#
#   # Common tweaks:
#   powershell -ExecutionPolicy Bypass -File scripts\pilot_bootstrap.ps1 -DatabaseUrl $db -SkipTrain -SkipStart
#   powershell -ExecutionPolicy Bypass -File scripts\pilot_bootstrap.ps1 -DatabaseUrl $db -Dates 2026-07-27 -SkipTrain
#
# NOTE: this starts services with pilot_start.ps1. To run as the pywin32 Windows
# service instead, use -SkipStart and then:  python scripts\pilot_service.py start
# =============================================================================

[CmdletBinding()]
param(
    [int]    $Customers   = 5000,
    [string] $AsOfDate    = '2026-07-27',
    [string[]] $Dates     = @('2026-07-17', '2026-07-22', '2026-07-27'),
    [string] $DatabaseUrl = '',            # postgresql://.../etl_clean  (required unless -SkipLoad)
    [switch] $SkipReset,
    [switch] $SkipLoad,
    [switch] $SkipFeatures,
    [switch] $SkipTrain,
    [switch] $SkipStart
)

$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root '.venv\Scripts\python.exe'
Set-Location $root

function Invoke-Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host "`n==== $Name ====" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) { Write-Warning "Step '$Name' exited with code $LASTEXITCODE" }
}

if (-not (Test-Path $py)) { Write-Error ".venv python not found at $py"; exit 1 }
if (-not $SkipLoad -and -not $DatabaseUrl) {
    Write-Error 'DatabaseUrl is required for the synthetic load. Pass -DatabaseUrl "postgresql://.../etl_clean"'
    exit 1
}

if (-not $SkipStart) { Invoke-Step 'Stop running services'        { powershell -ExecutionPolicy Bypass -File "$root\scripts\pilot_stop.ps1" } }
if (-not $SkipReset) { Invoke-Step "Reset etl_clean (downstream)" { & $py "$root\scripts\pilot_reset_clean.py" } }
Invoke-Step 'Apply DB migrations'      { & $py "$root\scripts\pilot_migrate.py" }
Invoke-Step 'Seed IAM demo users'      { & $py "$root\scripts\seed_iam.py" }
if (-not $SkipLoad) {
    Invoke-Step "Load synthetic data ($Customers customers @ $AsOfDate)" {
        & $py "$root\scripts\generate_synthetic_feature_store_data.py" `
            --load --customers $Customers --as-of-date $AsOfDate --seed 42 `
            --database-url $DatabaseUrl
    }
}
if (-not $SkipFeatures) {
    Invoke-Step "Feature pipeline (dates: $($Dates -join ', '))" {
        & $py "$root\scripts\run_full_pipeline_all_dates.py" $Dates
    }
}
Invoke-Step 'State engine (customer_states)' {
    foreach ($d in $Dates) { & $py "$root\scripts\seed_states.py" --as-of-date $d }
}
if (-not $SkipTrain) {
    Invoke-Step 'Train / register champion model' { & $py "$root\scripts\train_models.py" }
    Invoke-Step 'Train / register value models (CLV family)' {
        & $py "$root\scripts\train_value_model.py"
        & $py "$root\scripts\register_value_models.py"
    }
}
if (-not $SkipStart) {
    Invoke-Step 'Start backend services' { powershell -ExecutionPolicy Bypass -File "$root\scripts\pilot_start.ps1" }
    Write-Host "`nWaiting 15s for services to come up..." -ForegroundColor Yellow
    Start-Sleep 15

    # Value-model scoring needs the prediction service up (it loads the pickles).
    # Writes erosion_probability / predicted_future_value into customer_states — the
    # Branch Manager "at risk cases" list and the CLV views read those columns.
    Invoke-Step 'Score value models (erosion + future value)' {
        $login = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8080/auth/login' `
                 -ContentType application/json -Body '{"username":"admin","password":"Pilot@2025"}'
        $hdr = @{ Authorization = "Bearer $($login.access_token)" }
        foreach ($d in $Dates) {
            Invoke-RestMethod -Method Post -Headers $hdr `
                -Uri "http://127.0.0.1:8080/api/v1/predictions/value-batch?as_of_date=$d" | Out-Null
        }
    }
}

Write-Host @"

==============================================================================
PILOT BOOTSTRAP COMPLETE
==============================================================================
Verify:
  http://localhost:8080/health            (gateway)
  Login:  admin / Pilot@2025              (ADMIN — full access)
  Other:  rm.demo | ds.demo | ops.demo    (pw Pilot@2025)

Row counts:
  psql ... -d etl_clean -c "SELECT count(*) FROM customers_clean;"
  psql ... -d etl_clean -c "SELECT as_of_date, count(*) FROM customer_features GROUP BY 1 ORDER BY 1;"
  psql ... -d etl_clean -c "SELECT as_of_date, count(*) FROM customer_states GROUP BY 1 ORDER BY 1;"

Service alternative (pywin32): python scripts\pilot_service.py start
See: docs\deployment\PILOT-PIPELINE-RUNBOOK.md
==============================================================================
"@
