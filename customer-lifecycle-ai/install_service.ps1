#Requires -RunAsAdministrator
# Installs (or re-installs) the ABSA AI Backend Windows Service.
# Run from an Administrator PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\install_service.ps1
$ErrorActionPreference = "Stop"

$root   = $PSScriptRoot
$name   = "ABSABackend"
$script = Join-Path $root "absa_service.py"

# The service must run the *base* interpreter (the venv's python.exe is only a launcher,
# and pythonservice.exe can't see uv venv packages). Read its location from pyvenv.cfg.
$homeLine = Get-Content (Join-Path $root ".venv\pyvenv.cfg") | Where-Object { $_ -match '^\s*home\s*=' }
$basePy   = Join-Path (($homeLine -split '=', 2)[1].Trim()) "python.exe"
if (-not (Test-Path $basePy)) { throw "Base Python interpreter not found: $basePy" }

# Remove any previous registration (including the old pythonservice.exe one).
if (Get-Service $name -ErrorAction SilentlyContinue) {
    Write-Host "Removing existing $name service..."
    Stop-Service $name -Force -ErrorAction SilentlyContinue
    sc.exe delete $name | Out-Null

    # Windows only finishes deleting a service once every handle to it is closed
    # (services.msc, Event Viewer, Task Manager's Services tab, etc.).
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Service $name -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
        Write-Host "  waiting for Windows to finish deleting $name (close the Services window if it is open)..."
        Start-Sleep -Seconds 3
    }
    if (Get-Service $name -ErrorAction SilentlyContinue) {
        throw "$name is still 'marked for deletion'. Close services.msc / Event Viewer / Task Manager and run this script again (or reboot)."
    }
}

Write-Host "Installing $name -> `"$basePy`" `"$script`""
New-Service -Name $name `
    -DisplayName "ABSA AI Backend Service" `
    -Description "Manages and runs the 6 ABSA microservices (gateway, feature, state, prediction, decision, model)." `
    -BinaryPathName "`"$basePy`" `"$script`"" `
    -StartupType Automatic | Out-Null

# Start at boot (delayed until networking/DB drivers are up) and restart automatically if it fails.
sc.exe config  $name start= delayed-auto | Out-Null
sc.exe failure $name reset= 86400 actions= restart/10000/restart/10000/restart/30000 | Out-Null

Write-Host "Starting $name..."
Start-Service $name
Get-Service $name | Format-Table Status, Name, DisplayName -AutoSize
Write-Host "Logs: $root\logs\service\"
