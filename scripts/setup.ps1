# One-time setup on Windows. Run from the project folder:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== Checking tools" -ForegroundColor Cyan
foreach ($tool in @("python", "node", "npm")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Write-Host "Missing: $tool. Install Python 3.11+ (python.org, tick 'Add to PATH') and Node.js 20+ (nodejs.org), then rerun." -ForegroundColor Red
        exit 1
    }
}
python --version
node --version

Write-Host "== Backend: virtual environment and packages" -ForegroundColor Cyan
Set-Location "$root\backend"
if (-not (Test-Path ".venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if (-not (Test-Path ".env")) {
    Copy-Item "$root\.env.example" ".env"
    Write-Host "Created backend\.env from .env.example (demo mode, no keys needed)."
}

Write-Host "== Database: migrations and demo accounts" -ForegroundColor Cyan
& .\.venv\Scripts\python.exe -X utf8 -m app.seed

Write-Host "== Frontend packages" -ForegroundColor Cyan
Set-Location "$root\frontend"
npm install --no-audit --no-fund

Set-Location $root
Write-Host ""
Write-Host "Setup complete. Start the app with:  powershell -ExecutionPolicy Bypass -File scripts\start.ps1" -ForegroundColor Green
