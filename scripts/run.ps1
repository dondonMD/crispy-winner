param([ValidateSet('DEMO','OBSERVE','PAPER','MANUAL ASSIST')][string]$Mode='OBSERVE')
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$env:RADAR_MODE=$Mode
& .\.venv\Scripts\python.exe -m backend.app.main
exit $LASTEXITCODE
