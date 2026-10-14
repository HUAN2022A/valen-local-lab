param([int]$Port = 8893)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv and add it to PATH first.' }
$python = Join-Path $PSScriptRoot '.venv-demo/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    uv venv --python 3.11 (Join-Path $PSScriptRoot '.venv-demo')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the demo environment.' }
}
uv pip install --python $python -r (Join-Path $PSScriptRoot 'valen-repro/case-viewer/requirements-local.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install demo dependencies.' }
Write-Host "Synthetic UI demo: http://127.0.0.1:$Port/ (no model inference)"
& $python (Join-Path $PSScriptRoot 'valen-repro/case-viewer/server.py') --demo --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw 'Demo server exited with an error.' }
