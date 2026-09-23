# Detached service runner for ABSA Backend
$root = $PSScriptRoot
$py = "$root\.venv\Scripts\python.exe"
$env:PYTHONPATH = $root

# Terminate existing services first
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like "*customer-lifecycle-ai*"
} | Stop-Process -Force -ErrorAction SilentlyContinue

Start-Sleep -Seconds 1

$services = @(
    @{ Name = "Gateway"; Dir = $root; Cmd = "`"$py`" -m uvicorn gateway.main:create_app --factory --host 0.0.0.0 --port 8080" },
    @{ Name = "Feature"; Dir = "$root\services\feature-engineering-service"; Cmd = "`"$py`" -m uvicorn main:app --host 0.0.0.0 --port 8002" },
    @{ Name = "State"; Dir = "$root\services\customer-state-service"; Cmd = "`"$py`" -m uvicorn main:app --host 0.0.0.0 --port 8003" },
    @{ Name = "Prediction"; Dir = "$root\services\prediction-service"; Cmd = "`"$py`" -m uvicorn main:app --host 0.0.0.0 --port 8004" },
    @{ Name = "Decision"; Dir = "$root\services\decision-intelligence-service"; Cmd = "`"$py`" -m uvicorn main:app --host 0.0.0.0 --port 8005" },
    @{ Name = "Model"; Dir = "$root\services\model-management-service"; Cmd = "`"$py`" -m uvicorn main:app --host 0.0.0.0 --port 8006" }
)

foreach ($svc in $services) {
    Write-Host "Starting $($svc.Name)..."
    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $svc.Cmd
        CurrentDirectory = $svc.Dir
    } | Out-Null
}

Write-Host "Waiting 8 seconds for startup..."
Start-Sleep -Seconds 8

$ports = 8080, 8002, 8003, 8004, 8005, 8006
Get-NetTCPConnection -LocalPort $ports -ErrorAction SilentlyContinue | Select-Object LocalPort, OwningProcess, State
