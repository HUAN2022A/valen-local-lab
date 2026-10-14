param([switch]$Quantization)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
function Invoke-Checked {
    param([scriptblock]$Action)
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" }
}
foreach ($command in @('git', 'uv')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Install $command and add it to PATH before continuing."
    }
}
$upstream = Join-Path $PSScriptRoot 'Valen'
$revision = '95f06e8be99bd41e4a98aceddd3e4339c5a8e652'
if (-not (Test-Path -LiteralPath $upstream)) {
    Invoke-Checked { git clone https://github.com/Liuziyu77/Valen.git $upstream }
    Invoke-Checked { git -C $upstream checkout --detach $revision }
}
$current = & git -C $upstream rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $current -ne $revision) {
    throw "Expected Valen revision $revision; existing checkout was left untouched."
}
& (Join-Path $PSScriptRoot 'valen-repro/setup.ps1') -Quantization:$Quantization
$python = Join-Path $upstream '.venv/Scripts/python.exe'
$requirements = Join-Path $PSScriptRoot 'valen-repro/case-viewer/requirements-local.txt'
Invoke-Checked { uv pip install --python $python -r $requirements }
Write-Host 'Environment ready. See README.md to download assets and generate predictions.'
