$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
python -m venv .venv
if ($LASTEXITCODE) { throw 'Python venv failed. Install Python 3.12 or later with pip.' }
& .\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
if ($LASTEXITCODE) { throw 'Dependency installation failed' }
npm --prefix frontend ci
if ($LASTEXITCODE) { throw 'Frontend dependencies failed' }
npm --prefix frontend run build
if ($LASTEXITCODE) { throw 'Frontend build failed' }
Write-Host 'Ready. Run .\scripts\run.ps1 DEMO or .\scripts\run.ps1 OBSERVE'
