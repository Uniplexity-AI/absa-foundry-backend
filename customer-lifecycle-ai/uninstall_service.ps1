#Requires -RunAsAdministrator
# Stops and removes the ABSA AI Backend Windows Service (this also stops all 6 microservices).
$name = "ABSABackend"
if (Get-Service $name -ErrorAction SilentlyContinue) {
    Stop-Service $name -Force -ErrorAction SilentlyContinue
    sc.exe delete $name
} else {
    Write-Host "$name is not installed."
}
