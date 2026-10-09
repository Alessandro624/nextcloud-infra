$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
& "$repoRoot/.venv/Scripts/python.exe" -u "$repoRoot/scripts/automation.py" serve
exit $LASTEXITCODE
