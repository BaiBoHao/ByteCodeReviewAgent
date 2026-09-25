$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $venv = Join-Path $projectRoot ".runner-build-venv"
    $python = Join-Path $venv "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python)) {
        python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "Failed to create isolated build environment." }
    }
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to update build pip." }
    & $python -m pip install -e ".[runner]"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install Runner build dependencies." }
    & $python -m PyInstaller --noconfirm --clean packaging/review-agent-runner.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
    $runner = Join-Path $projectRoot "dist\review-agent-runner\review-agent-runner.exe"
    if (-not (Test-Path -LiteralPath $runner)) { throw "Runner output not found: $runner" }
    Write-Output "Runner built: $runner"
}
finally {
    Pop-Location
}
