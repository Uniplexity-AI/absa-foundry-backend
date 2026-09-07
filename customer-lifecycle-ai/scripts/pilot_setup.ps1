# =============================================================================
# ABSA Backend — Pilot Setup (one-time)
#
# Creates the virtual environment, installs dependencies, prepares .env,
# creates the two databases, and runs migrations.
#
# Usage (PowerShell, run from project root or anywhere):
#   .\scripts\pilot_setup.ps1
# =============================================================================

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$venvPy = Join-Path $root '.venv\Scripts\python.exe'

Write-Host "=== ABSA Pilot Setup ===" -ForegroundColor Cyan
Write-Host "Root: $root" -ForegroundColor DarkGray

# ---------------------------------------------------------------------------
# 1. Verify Python is available
# ---------------------------------------------------------------------------
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) {
    Write-Host "ERROR: Python 3.11+ not found on PATH." -ForegroundColor Red
    exit 1
}
Write-Host "Python: $($pyCmd.Source)" -ForegroundColor DarkGray

# ---------------------------------------------------------------------------
# 2. Create virtual environment if missing
# ---------------------------------------------------------------------------
if (-not (Test-Path $venvPy)) {
    Write-Host "Creating virtual environment..." -ForegroundColor Cyan
    python -m venv (Join-Path $root '.venv')
} else {
    Write-Host ".venv already exists - skipping creation" -ForegroundColor DarkGray
}

# ---------------------------------------------------------------------------
# 3. Install dependencies
# ---------------------------------------------------------------------------
Write-Host "Installing dependencies (this can take several minutes)..." -ForegroundColor Cyan

# uv-managed venvs have no pip module — detect and fall back to uv
$hasPip = & $venvPy -c "import pip" 2>$null
$install = $null
if ($hasPip) {
    $install = { param($req) & $venvPy -m pip install -r $req }
} else {
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        Write-Host "ERROR: no pip in .venv and no uv on PATH. Install uv first." -ForegroundColor Red
        exit 1
    }
    $install = { param($req) & uv pip install -r $req }
}

& $install (Join-Path $root 'requirements.txt')
& $install (Join-Path $root 'gateway\requirements.txt')
Get-ChildItem (Join-Path $root 'services') -Directory | ForEach-Object {
    $req = Join-Path $_.FullName 'requirements.txt'
    if (Test-Path $req) {
        Write-Host "  Installing $($_.Name) deps..." -ForegroundColor DarkGray
        & $install $req
    }
}

# ---------------------------------------------------------------------------
# 4. Prepare .env
# ---------------------------------------------------------------------------
$envFile = Join-Path $root '.env'
if (-not (Test-Path $envFile)) {
    $example = Join-Path $root '.env.example'
    if (Test-Path $example) {
        Copy-Item $example $envFile
        Write-Host "Created .env from .env.example - EDIT it with pilot DB credentials." -ForegroundColor Yellow
    } else {
        Write-Host "WARNING: no .env or .env.example found. Create .env manually." -ForegroundColor Yellow
    }
}

# Rotate placeholder secrets
if (Test-Path $envFile) {
    $content = Get-Content $envFile -Raw
    if ($content -match 'change-me-in-production') {
        $secret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
        $content = $content -replace 'change-me-in-production', $secret
        Set-Content -Path $envFile -Value $content -NoNewline
        Write-Host "Rotated placeholder secrets in .env" -ForegroundColor Green
    }
}

Write-Host "`nSetup complete." -ForegroundColor Green
Write-Host "NEXT STEPS:" -ForegroundColor Cyan
Write-Host "  1. Review and edit $envFile (DB host/credentials, secrets)" -ForegroundColor Yellow
Write-Host "  2. Run migrations:  $venvPy scripts\pilot_migrate.py --create-databases" -ForegroundColor Yellow
Write-Host "  3. Start services:  .\scripts\pilot_start.ps1" -ForegroundColor Yellow
