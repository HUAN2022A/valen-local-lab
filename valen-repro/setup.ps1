param([switch]$Quantization)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$root = Split-Path $PSScriptRoot -Parent
$repo = Join-Path $root 'Valen'
$python = Join-Path $repo '.venv/Scripts/python.exe'
$existing = Join-Path $root 'laya-learning/.venv/Scripts/python.exe'
function Invoke-Checked { param([scriptblock]$Action) & $Action; if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" } }
if (!(Test-Path $repo)) { throw 'Expected sibling Valen checkout.' }
$sha = & git -C $repo rev-parse HEAD
if ($sha -ne '95f06e8be99bd41e4a98aceddd3e4339c5a8e652') { throw "Unexpected source revision: $sha" }
if (!(Test-Path $python)) {
    $base = if (Test-Path $existing) { $existing } else { '3.11' }
    Invoke-Checked { uv venv --python $base (Join-Path $repo '.venv') }
}
Invoke-Checked { uv pip install --python $python 'torch==2.6.0' 'torchvision==0.21.0' --index-url https://download.pytorch.org/whl/cu124 }
Invoke-Checked { uv pip install --python $python -e "$repo[test]" }
if ($Quantization) { Invoke-Checked { uv pip install --python $python 'bitsandbytes==0.49.2' 'accelerate==1.15.0' } }
Invoke-Checked { uv pip check --python $python }
uv pip freeze --python $python | Set-Content -Encoding utf8 (Join-Path $PSScriptRoot 'environment.freeze.txt')
Invoke-Checked { & $python (Join-Path $PSScriptRoot 'run.py') preflight }
