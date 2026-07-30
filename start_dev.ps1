$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendPath = Join-Path $repoRoot "backend_python"
$frontendPath = Join-Path $repoRoot "client_side"

Write-Host "backend init..."

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$backendPath'; .\venv\Scripts\Activate.ps1; uvicorn server:app --reload"
)

Write-Host "waiting for backend initialisation..."
Start-Sleep -Seconds 3

Write-Host "clientside init..."

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$frontendPath'; npm run dev"
)

Write-Host "dev servers launched."