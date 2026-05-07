# 批量运行 examples/cases 下所有用例
param(
    [switch]$DebugTrace,
    [string]$CasePattern = "*.py",
    [string]$Config = ""
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# 自动检测 Python
$VenvPy = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPy) {
    $PythonExe = $VenvPy
    Write-Host "[INFO] Using venv Python: $PythonExe" -ForegroundColor Cyan
} else {
    $PythonExe = "python"
    $env:PYTHONPATH = Join-Path $RepoRoot "src"
    Write-Host "[INFO] Using system Python with PYTHONPATH=$env:PYTHONPATH" -ForegroundColor Cyan
}

# 配置文件
if (-not $Config) {
    $Config = Join-Path $RepoRoot "config\model.yaml"
}
if (-not (Test-Path $Config)) {
    Write-Host "[ERROR] Config file not found: $Config" -ForegroundColor Red
    exit 1
}

$CasesDir = Join-Path $RepoRoot "examples\cases"
$CaseFiles = Get-ChildItem -Path $CasesDir -Filter $CasePattern | Sort-Object Name

if ($CaseFiles.Count -eq 0) {
    Write-Host "[ERROR] No case files found matching '$CasePattern' in $CasesDir" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " AutoVisionTest - Batch Run" -ForegroundColor Yellow
Write-Host " Config : $Config" -ForegroundColor Yellow
Write-Host " Cases  : $($CaseFiles.Count) file(s) matching '$CasePattern'" -ForegroundColor Yellow
Write-Host " Debug  : $DebugTrace" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow
Write-Host ""

$Results = @()
$Total = $CaseFiles.Count
$Index = 0

foreach ($CaseFile in $CaseFiles) {
    $Index++
    $CasePath = $CaseFile.FullName
    $CaseName = $CaseFile.BaseName

    Write-Host "----------------------------------------" -ForegroundColor DarkGray
    Write-Host "[$Index/$Total] Running: $CaseName" -ForegroundColor White
    Write-Host "----------------------------------------" -ForegroundColor DarkGray

    $Args = @(
        "-m", "autovisiontest",
        "--config", $Config,
        "run",
        "--case", $CasePath
    )
    if ($DebugTrace) {
        $Args += "--debug-trace"
    }

    $StartTime = Get-Date
    $ExitCode = 0
    & $PythonExe $Args 2>&1 | ForEach-Object { Write-Host "  $_" }
    $ExitCode = $LASTEXITCODE
    $Elapsed = (Get-Date) - $StartTime

    $Status = switch ($ExitCode) {
        0 { "PASS" }
        1 { "FAIL" }
        2 { "ABORTED" }
        3 { "ERROR" }
        default { "UNKNOWN($ExitCode)" }
    }

    $Color = if ($ExitCode -eq 0) { "Green" } else { "Red" }
    Write-Host "  [$CaseName] $Status (${Elapsed:hh\:mm\:ss})" -ForegroundColor $Color

    $Results += [PSCustomObject]@{
        CaseName = $CaseName
        ExitCode = $ExitCode
        Status   = $Status
        Elapsed  = $Elapsed
    }
}

# 汇总
Write-Host ""
Write-Host "========================================" -ForegroundColor Yellow
Write-Host " Summary" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Yellow

$Passed  = ($Results | Where-Object { $_.ExitCode -eq 0 }).Count
$Failed  = ($Results | Where-Object { $_.ExitCode -ne 0 }).Count

foreach ($R in $Results) {
    $Color = if ($R.ExitCode -eq 0) { "Green" } else { "Red" }
    Write-Host "  $($R.CaseName) : $($R.Status) ($($R.Elapsed -replace '\.\d+$',''))" -ForegroundColor $Color
}

Write-Host ""
Write-Host " Passed: $Passed | Failed: $Failed | Total: $Total" -ForegroundColor White
Write-Host ""

exit ($Failed -gt 0 ? 1 : 0)
