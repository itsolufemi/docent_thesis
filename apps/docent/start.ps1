$ErrorActionPreference = "Stop"

$docentPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$appsPath = Split-Path -Parent $docentPath
$repoRoot = Split-Path -Parent $appsPath
$backendPath = Join-Path $repoRoot "framework"
$frontendPath = Join-Path $docentPath "frontend"
$pythonPath = Join-Path $backendPath "venv\Scripts\python.exe"

Write-Host "backend init..."

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Item Env:PYTHONPATH '$repoRoot'; Set-Location '$backendPath'; & '$pythonPath' -m uvicorn server:app --reload --reload-dir '$backendPath' --reload-dir '$docentPath'"
)

Write-Host "waiting for backend initialisation..."
Start-Sleep -Seconds 3

Write-Host "frontend init..."

Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location '$frontendPath'; npm run dev"
)

Write-Host "dev servers launched."
