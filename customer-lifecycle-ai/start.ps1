# ABSA Backend - Start All 5 Services
# Run: .\start.ps1

$root = $PSScriptRoot
$py = "$root\.venv\Scripts\python.exe"
$env:PYTHONPATH = $root
$tailscaleIP = (tailscale ip -4 2>$null) -replace '\s',''

Write-Host "`nStarting 5 services..." -ForegroundColor Cyan
Write-Host "Tailscale IP: $tailscaleIP`n" -ForegroundColor DarkGray

taskkill /F /IM python.exe 2>$null
Start-Sleep 2

Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","gateway.main:create_app","--factory","--host","0.0.0.0","--port","8080","--reload" -WorkingDirectory $root
Write-Host "  :8080 Gateway         → http://${tailscaleIP}:8080/docs"

Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8002","--reload" -WorkingDirectory "$root\services\feature-engineering-service"
Write-Host "  :8002 Feature Engineering"

Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8003","--reload" -WorkingDirectory "$root\services\customer-state-service"
Write-Host "  :8003 Customer State (L1)"

Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8004","--reload" -WorkingDirectory "$root\services\prediction-service"
Write-Host "  :8004 Prediction (L2)"

Start-Process -NoNewWindow $py -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8005","--reload" -WorkingDirectory "$root\services\decision-intelligence-service"
Write-Host "  :8005 Decision Intelligence (L3)"

Start-Sleep 5
netstat -ano | findstr "LISTENING" | findstr "8002 8003 8004 8005 8080"
Write-Host "`nDone - Remote devs use: $tailscaleIP" -ForegroundColor Green
