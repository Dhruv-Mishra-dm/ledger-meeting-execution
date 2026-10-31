# Starts the backend (port 8000) and frontend (port 5173) in two new windows, then opens the browser.
$root = Split-Path -Parent $PSScriptRoot
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$root\scripts\start-backend.ps1`""
Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$root\scripts\start-frontend.ps1`""
Write-Host "Starting... the browser will open in a few seconds. Close the two new windows to stop the app."
Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
