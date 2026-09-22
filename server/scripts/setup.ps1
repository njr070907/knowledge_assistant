$ErrorActionPreference = 'Stop'
$serverRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $serverRoot '.venv'

if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = 'python'
    $pythonArgs = @()
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = 'py'
    $pythonArgs = @('-3')
} else {
    throw '未找到 Python。请安装 Python 3.11 或更高版本后重试。'
}

if (-not (Test-Path -LiteralPath $venvPath)) {
    & $pythonCommand @pythonArgs -m venv $venvPath
}

$pythonPath = Join-Path $venvPath 'Scripts\python.exe'
& $pythonPath -m pip install --upgrade pip
& $pythonPath -m pip install -r (Join-Path $serverRoot 'requirements-dev.txt')
Write-Host '知流本机服务依赖安装完成。'
