# Director 2.0 — one-command setup (Windows PowerShell)
# Usage: powershell -ExecutionPolicy Bypass -File setup.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Director 2.0 setup" -ForegroundColor Cyan

python -m pip install -e ".[dev,mem]"
if (-not $?) { throw "pip install failed" }

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "created .env - add your API keys (ANTHROPIC_API_KEY, XAI_API_KEY, ...)" -ForegroundColor Yellow
}

director init
director doctor

Write-Host ""
Write-Host "Ready. Try:" -ForegroundColor Green
Write-Host '  director new "first mission" --objective "research X and build Y"'
Write-Host "  director evolve run topk"
