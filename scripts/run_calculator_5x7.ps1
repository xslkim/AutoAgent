# 计算器 5×7 视觉自动化用例（依赖 UI-TARS / config/model.yaml）
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
} else {
    $PythonExe = "python"
    $env:PYTHONPATH = Join-Path $RepoRoot "src"
}
& $PythonExe -m autovisiontest --config (Join-Path $RepoRoot "config\model.yaml") run --case (Join-Path $RepoRoot "examples\cases\calculator_5x7.py")
