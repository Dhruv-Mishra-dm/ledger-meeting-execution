# Wipes the local database and re-creates the demo accounts and projects (no meetings).
# Stop the backend window first. Add -Scenario to also run all three demo meetings automatically.
param([switch]$Scenario)
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
if ($Scenario) {
    & .\.venv\Scripts\python.exe -X utf8 -m app.seed --scenario
} else {
    & .\.venv\Scripts\python.exe -X utf8 -m app.seed --reset
}
