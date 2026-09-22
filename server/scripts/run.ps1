$ErrorActionPreference = 'Stop'
$serverRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $serverRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '尚未创建虚拟环境，请先运行 scripts\setup.ps1。'
}

Set-Location $serverRoot
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8765

