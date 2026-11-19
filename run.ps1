# One command, end to end, on Windows. Needs Python 3.11+ and Java 17 on PATH.
#   .\run.ps1                 2,000 patients, seed 20261118
#   .\run.ps1 -Patients 200   quicker
param(
    [int]$Patients = 2000,
    [int]$Seed = 20261118
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    python -m venv .venv
    .\.venv\Scripts\python -m pip install --quiet --upgrade pip
    .\.venv\Scripts\python -m pip install --quiet -e ".[dev]"
}
.\.venv\Scripts\python -m ces run --patients $Patients --seed $Seed --no-extend
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host ""
Write-Host "done. open site\index.html via:  .\.venv\Scripts\python -m http.server -d site 8000"
