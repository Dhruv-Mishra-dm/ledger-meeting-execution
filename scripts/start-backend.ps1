$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
$host.UI.RawUI.WindowTitle = "Ledger backend (port 8000)"
& .\.venv\Scripts\python.exe -X utf8 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
