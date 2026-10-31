$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\frontend"
$host.UI.RawUI.WindowTitle = "Ledger frontend (port 5173)"
npx vite --host 127.0.0.1
