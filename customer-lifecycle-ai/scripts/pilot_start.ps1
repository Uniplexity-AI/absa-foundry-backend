# =============================================================================
# ABSA Backend — Pilot Start (all 5 services, production mode)
#
# Differences from dev start.ps1:
#   - NO --reload (production mode)
#   - NO taskkill python.exe (won't kill unrelated processes)
#   - PID tracking for graceful stop via pilot_stop.ps1
#   - Logs written to logs\pilot\
#
# Usage:
#   .\scripts\pilot_start.ps1
# =============================================================================

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root '.venv\Scripts\python.exe'
$logs = Join-Path $root 'logs\pilot'

if (-not (Test-Path $py)) {
    Write-Host "ERROR: .venv not found. Run scripts\pilot_setup.ps1 first." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $logs | Out-Null
$env:PYTHONPATH = $root

# ── Read service ports from .env (fallback to defaults) ──
$envMap = @{}
$envFile = Join-Path $root '.env'
if (Test-Path $envFile) {
    Get-Content $envFile | Where-Object { $_ -match '^\s*([A-Z0-9_]+)\s*=\s*(.+?)\s*$' } | ForEach-Object {
        $envMap[$Matches[1]] = $Matches[2]
    }
}
function Get-Port($name, $default) {
    if ($envMap.ContainsKey($name) -and $envMap[$name] -match '^\d+$') { return [int]$envMap[$name] }
    return $default
}
$gatewayPort    = Get-Port 'GATEWAY_PORT' 8080
$featurePort    = Get-Port 'FEATURE_ENGINEERING_SERVICE_PORT' 8002
$statePort      = Get-Port 'CUSTOMER_STATE_SERVICE_PORT' 8003
$predictionPort = Get-Port 'PREDICTION_SERVICE_PORT' 8004
$decisionPort   = Get-Port 'DECISION_INTELLIGENCE_SERVICE_PORT' 8005

# name, port, working directory, app target, use --factory
$services = @(
    @{ Name = 'gateway';    Port = $gatewayPort;    Dir = $root;                                             App = 'gateway.main:create_app'; Factory = $true  },
    @{ Name = 'feature';    Port = $featurePort;    Dir = "$root\services\feature-engineering-service";       App = 'main:app';                 Factory = $false },
    @{ Name = 'state';      Port = $statePort;      Dir = "$root\services\customer-state-service";            App = 'main:app';                 Factory = $false },
    @{ Name = 'prediction'; Port = $predictionPort; Dir = "$root\services\prediction-service";                App = 'main:app';                 Factory = $false },
    @{ Name = 'decision';   Port = $decisionPort;   Dir = "$root\services\decision-intelligence-service";     App = 'main:app';                 Factory = $false }
)

# Stop anything we started previously (by pid file, not blanket taskkill)
$pidFile = Join-Path $logs 'pids.txt'
if (Test-Path $pidFile) {
    Get-Content $pidFile | ForEach-Object {
        try { Stop-Process -Id ([int]$_) -Force -ErrorAction SilentlyContinue } catch {}
    }
}

$pids = @()
Write-Host "Starting 5 services (production mode)..." -ForegroundColor Cyan

foreach ($s in $services) {
    $args = @('-m', 'uvicorn', $s.App, '--host', '0.0.0.0', '--port', "$($s.Port)")
    if ($s.Factory) { $args += '--factory' }
    $stdout = Join-Path $logs "$($s.Name).log"
    $stderr = Join-Path $logs "$($s.Name).err.log"
    $p = Start-Process $py -ArgumentList $args -WorkingDirectory $s.Dir `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr `
        -PassThru -WindowStyle Hidden
    $pids += $p.Id
    Write-Host "  :$($s.Port) $($s.Name) (pid $($p.Id))" -ForegroundColor DarkGray
}

$pids | Set-Content $pidFile

Write-Host "`nServices starting. Logs: $logs" -ForegroundColor Green
Write-Host "Health checks (after ~15s):" -ForegroundColor Cyan
Write-Host "  http://localhost:$gatewayPort/health  (gateway)" -ForegroundColor DarkGray
Write-Host "  http://localhost:$featurePort/health  (feature)" -ForegroundColor DarkGray
Write-Host "  http://localhost:$statePort/health  (state)" -ForegroundColor DarkGray
Write-Host "  http://localhost:$predictionPort/health  (prediction)" -ForegroundColor DarkGray
Write-Host "  http://localhost:$decisionPort/health  (decision)" -ForegroundColor DarkGray
