param(
    [Parameter(Mandatory = $true)]
    [string]$AudioPath,
    [string]$Model = 'small'
)

$ErrorActionPreference = 'Stop'
$serverRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $serverRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '尚未创建虚拟环境，请先运行 scripts\setup.ps1。'
}
if (-not (Test-Path -LiteralPath $AudioPath)) {
    throw "找不到测试文件：$AudioPath"
}

Set-Location $serverRoot
& $pythonPath -m scripts.benchmark_asr --audio $AudioPath --model $Model

