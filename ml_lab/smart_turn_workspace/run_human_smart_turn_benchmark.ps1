$workspaceDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$manifestPath = Join-Path $workspaceDirectory "smart_turn_human_manifest.csv"
$pythonPath = Join-Path $workspaceDirectory ".venv-cpu\Scripts\python.exe"
$benchmarkPath = Join-Path $workspaceDirectory "benchmark_smart_turn.py"

if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Human recording manifest not found: $manifestPath"
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Smart Turn CPU environment not found: $pythonPath"
}

& $pythonPath $benchmarkPath `
    --manifest $manifestPath `
    --model cpu `
    --warmup-runs 2 `
    --runs 10 `
    --output "results/smart_turn_human_results.json"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
