# Runs every automated test: backend (pytest) and frontend (type-check + vitest).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
& .\.venv\Scripts\python.exe -X utf8 -m pytest -q -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Set-Location "$root\frontend"
npx tsc -b
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
npx vitest run
exit $LASTEXITCODE
