param(
    [ValidateSet('native', 'bf16', 'fp32')]
    [string]$Precision = 'bf16',

    [ValidateSet('none', 'int8', 'nf4')]
    [string]$Quantization = 'none',

    [string]$Device = 'cuda:0',
    [int]$Port = 8892,
    [switch]$LowMedia
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$projectRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$python = Join-Path $workspaceRoot 'Valen\.venv\Scripts\python.exe'
$server = Join-Path $PSScriptRoot 'server.py'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Valen uv environment not found: $python"
}

$arguments = @(
    $server,
    '--host', '127.0.0.1',
    '--port', $Port,
    '--device', $Device,
    '--dtype', $Precision,
    '--quant', $Quantization
)
if ($LowMedia) {
    $arguments += '--low-media'
}

Write-Host "Valen Local Lab: http://127.0.0.1:$Port/"
Write-Host "Profile: $Precision / $Quantization / $Device"
& $python @arguments
