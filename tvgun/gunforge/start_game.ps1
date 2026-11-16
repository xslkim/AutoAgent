param(
    [switch]$Gun,
    [switch]$Test,
    [string]$Godot = $env:GODOT_BIN
)
$ErrorActionPreference = 'Stop'
$gameWorkspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$gameProject = Join-Path $PSScriptRoot 'framework'
if (-not $Godot) {
    $gameCandidates = @(
        (Join-Path $gameWorkspace '../gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe'),
        (Join-Path $env:LOCALAPPDATA 'Temp/tvgun-art2d-godot-research/Godot_v4.6.3-stable_win64_console.exe')
    )
    $gameCommand = Get-Command godot -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($gameCommand) { $gameCandidates = @($gameCommand.Source) + $gameCandidates }
    $Godot = $gameCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $Godot -or -not (Test-Path -LiteralPath $Godot)) {
    throw 'Set GODOT_BIN to a Godot 4.6.3 console executable, or pass -Godot <path>.'
}
$gamePython = Join-Path $gameWorkspace 'gunforge/pipeline/art/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $gamePython)) {
    throw 'The art pipeline Python environment with Pillow is required. See gunforge/pipeline/art/README.md.'
}
Push-Location $gameWorkspace
try {
    & $gamePython gunforge/pipeline/build_0b.py
    if ($LASTEXITCODE) { throw 'Runtime asset verification or build failed.' }
    & $Godot --headless --path $gameProject --editor --import --quit --quiet
    if ($LASTEXITCODE) { throw 'Godot import failed.' }
    if ($Test) {
        & $Godot --headless --path $gameProject --script res://tests/core_tests.gd
        if ($LASTEXITCODE) { throw 'Core regression tests failed.' }
        return
    }
    $gameArgs = @('--path', $gameProject, '--')
    if ($Gun) { $gameArgs += '--gun' }
    & $Godot @gameArgs
} finally {
    Pop-Location
}
