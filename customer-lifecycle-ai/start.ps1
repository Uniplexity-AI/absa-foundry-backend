# ABSA Backend - Start All 5 Services
# Run: .\start.ps1

$root = $PSScriptRoot
$py = "$root\.venv\Scripts\python.exe"
$tailscaleIP = (tailscale ip -4 2>$null) -replace '\s',''

Write-Host "`nStarting 5 services..." -ForegroundColor Cyan
Write-Host "Tailscale IP: $tailscaleIP`n" -ForegroundColor DarkGray

taskkill /F /IM python.exe 2>$null
Start-Sleep 2

$env:PYTHONPATH = $root

# Gateway :8080
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","gateway.main:create_app","--factory","--host","0.0.0.0","--port","8080","--reload" -WorkingDirectory $root
Write-Host "  :8080 Gateway"

# Feature :8002
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8002","--reload" -WorkingDirectory "$root\services\feature-engineering-service"
Write-Host "  :8002 Feature Engineering"

# State :8003
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8003","--reload" -WorkingDirectory "$root\services\customer-state-service"
Write-Host "  :8003 Customer State (L1)"

# Prediction :8004
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8004","--reload" -WorkingDirectory "$root\services\prediction-service"
Write-Host "  :8004 Prediction (L2)"

# Decision :8005
Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8005","--reload" -WorkingDirectory "$root\services\decision-intelligence-service"
Write-Host "  :8005 Decision Intelligence (L3)"

Start-Sleep 10
$running = netstat -ano 2>$null | Select-String "LISTENING" | Select-String "8002|8003|8004|8005|8080"
$count = ($running | Measure-Object -Line).Lines

if ($count -eq 5) {
    Write-Host "`nAll 5 services running" -ForegroundColor Green
} else {
    Write-Host "`n$count/5 services running (some failed - check terminal output above)" -ForegroundColor Yellow
}
$running
Write-Host "`nRemote: http://${tailscaleIP}:8080/docs" -ForegroundColor Cyan
