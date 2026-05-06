# 在项目根目录创建 .venv 并安装 AutoVisionTest（含 dev / HTTP / MCP 可选依赖）
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$Py = Get-Command python -ErrorAction SilentlyContinue
if (-not $Py) {
    Write-Error "未找到 python，请先安装 Python 3.11+ 并加入 PATH。"
}

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip setuptools wheel
.\.venv\Scripts\pip.exe install -e ".[dev,http,mcp]"
Write-Host "完成。激活虚拟环境: .\.venv\Scripts\Activate.ps1"
Write-Host "或直接使用: .\.venv\Scripts\autovisiontest.exe --version"
