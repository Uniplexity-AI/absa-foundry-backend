# =============================================================================
# ABSA Backend — Pilot Stop (graceful, stops only our services)
#
# Stops only the PIDs recorded by pilot_start.ps1. Does NOT kill other
# Python processes on the machine.
#
# Usage:
#   .\scripts\pilot_stop.ps1
# =============================================================================

$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root 'logs\pilot\pids.txt'

if (-not (Test-Path $pidFile)) {
    Write-Host "No pid file found (logs\pilot\pids.txt). Services may not be running." -ForegroundColor Yellow
    exit 0
}

Write-Host "Stopping pilot services..." -ForegroundColor Cyan
Get-Content $pidFile | ForEach-Object {
    $id = [int] $_
    try {
        Stop-Process -Id $id -Force -ErrorAction Stop
        Write-Host "  Stopped pid $id" -ForegroundColor DarkGray
    } catch {
        Write-Host "  Already stopped: $id" -ForegroundColor DarkGray
    }
}

Remove-Item $pidFile -ErrorAction SilentlyContinue
Write-Host "All pilot services stopped." -ForegroundColor Green
