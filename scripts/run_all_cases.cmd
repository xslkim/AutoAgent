@echo off
REM 批量运行 examples/cases 下所有用例
REM 默认运行所有 .py 文件，也可传参筛选，如: run_all_cases.cmd notepad

setlocal enabledelayedexpansion

set "REPO_ROOT=%~dp0.."
pushd "%REPO_ROOT%"

REM 自动检测 Python
if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
    echo [INFO] Using venv Python
) else (
    set "PYTHON=python"
    set "PYTHONPATH=%REPO_ROOT%\src"
    echo [INFO] Using system Python
)

set "CONFIG=%REPO_ROOT%\config\model.yaml"
if not exist "%CONFIG%" (
    echo [ERROR] Config file not found: %CONFIG%
    popd
    exit /b 1
)

set "CASES_DIR=%REPO_ROOT%\examples\cases"
set "PATTERN=*.py"
if not "%~1"=="" (
    set "PATTERN=*%~1*.py"
)

echo.
echo ========================================
echo   AutoVisionTest - Batch Run
echo   Config: %CONFIG%
echo   Cases : %PATTERN%
echo ========================================
echo.

set PASSED=0
set FAILED=0

for %%f in ("%CASES_DIR%\%PATTERN%") do (
    echo ----------------------------------------
    echo Running: %%~nf
    echo ----------------------------------------

    set "START=!TIME!"
    "%PYTHON%" -m autovisiontest --config "%CONFIG%" run --case "%%f"
    set "EC=!ERRORLEVEL!"
    set "END=!TIME!"

    if !EC! equ 0 (
        echo   [%%~nf] PASS
        set /a PASSED+=1
    ) else (
        echo   [%%~nf] FAIL ^(exit code: !EC!^)
        set /a FAILED+=1
    )
    echo.
)

set /a TOTAL=%PASSED%+%FAILED%
echo ========================================
echo   Summary
echo ========================================
echo   Passed: %PASSED% | Failed: %FAILED% | Total: %TOTAL%
echo ========================================

popd
if %FAILED% gtr 0 exit /b 1
exit /b 0
