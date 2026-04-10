Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "python is not available on PATH"
}

Write-Host "Building epidemic_cli executable from $repoRoot"
python -m PyInstaller --noconfirm epidemic_cli.spec

if (-not (Test-Path "$repoRoot\\dist\\epidemic.exe")) {
    throw "Build completed but dist\\epidemic.exe was not produced"
}

Write-Host "Build complete: $repoRoot\\dist\\epidemic.exe"
