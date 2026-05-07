# 计算器 5×7 视觉自动化用例（依赖 UI-TARS / config/model.yaml）
# Repo root: prefer $PSScriptRoot; if empty (some hosts), use $PSCommandPath (PS3+) or MyInvocation path.
$ScriptDir = $PSScriptRoot
if (-not $ScriptDir -and $PSCommandPath) {
    $ScriptDir = Split-Path -Parent $PSCommandPath
}
if (-not $ScriptDir -and $MyInvocation.MyCommand.Path) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if (-not $ScriptDir) {
    Write-Error 'Cannot resolve script directory; run this file as a saved .ps1 with PowerShell 3 or newer.'
    exit 1
}
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot
$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
} else {
    $PythonExe = "python"
    $env:PYTHONPATH = Join-Path $RepoRoot "src"
}
& $PythonExe -m autovisiontest --config (Join-Path $RepoRoot "config\model.yaml") run --case (Join-Path $RepoRoot "examples\cases\calculator_5x7.py")
