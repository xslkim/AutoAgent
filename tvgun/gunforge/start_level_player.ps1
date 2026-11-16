param([ValidateSet('paper.alley','paper.assault','paper.station','paper.stall','paper.video_shop','paper.footbridge','paper.footbridge_cyclist','paper.plaza','paper.night_market','paper.cinema','paper.waiting_room','paper.waiting_room_contrast','paper.platform','paper.platform_contrast','paper.platform_passerby','paper.green_car','paper.green_car_contrast','paper.lantern_base','paper.lantern_pullback','paper.train_station','paper.train_station_hardened','paper.train_station_readability','paper.train_station_boss','paper.lantern_city','paper.lantern_city_campaign','paper.lantern_city_ui','paper.lantern_city_epilogue','paper.lantern_city_tadpole','paper.lantern_city_rescue','paper.lantern_city_cast','paper.tadpole_encounter','gallery.intro','orbital.convoy','orbital.siege')][string]$Package='paper.alley',[string]$Build,[string]$Godot=$env:GODOT_BIN,[double]$QuitAfter=0,[switch]$Candidate,[string]$Proposal,[switch]$SkipOpening)
$ErrorActionPreference='Stop'
$levelRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$levelPython=Join-Path $levelRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $levelPython)) {
    $levelPython=(Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
}
if (-not $Godot) { $Godot=Join-Path $levelRoot '../gunforge_cache/tools/godot-4.6.3/Godot_v4.6.3-stable_win64_console.exe' }
if ($Proposal) {
    if ($Build -or $Candidate) { throw '-Proposal selects an exact candidate. Omit -Build and -Candidate.' }
    $proposalPath = (Resolve-Path -LiteralPath $Proposal).Path
    $revisionTool = Join-Path $PSScriptRoot 'pipeline/level_design/review_revision.py'
    $Package = & $levelPython $revisionTool package $proposalPath
    if ($LASTEXITCODE) { throw 'Cannot identify the proposal package' }
}
if (-not $Build -and $Package -in @('paper.alley','paper.assault','paper.station','paper.stall','paper.night_market','paper.lantern_city','paper.lantern_city_campaign','paper.lantern_city_ui','paper.lantern_city_epilogue','paper.lantern_city_tadpole','paper.lantern_city_rescue','paper.lantern_city_cast')) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'framework/runtime/station/station.json'))) {
        & $levelPython (Join-Path $PSScriptRoot 'pipeline/build_0b.py')
        if ($LASTEXITCODE) { throw 'Initial runtime asset build failed' }
    }
    & $levelPython (Join-Path $PSScriptRoot 'pipeline/build_0b.py')
    if ($LASTEXITCODE) { throw 'Native asset preparation failed' }
}
if ($Proposal) {
    $comparison = & $levelPython $revisionTool preview $proposalPath
    if ($LASTEXITCODE) { throw 'Proposal could not be built' }
    $Build = ($comparison | ConvertFrom-Json).candidate
} elseif (-not $Build) {
    $levelNames=@{'paper.alley'='paper';'paper.assault'='assault';'paper.station'='station';'paper.stall'='stall';'paper.video_shop'='video_shop';'paper.footbridge'='footbridge';'paper.footbridge_cyclist'='footbridge_cyclist';'paper.plaza'='plaza';'paper.night_market'='night_market';'paper.cinema'='cinema';'paper.waiting_room'='waiting_room';'paper.waiting_room_contrast'='waiting_room_contrast';'paper.platform'='platform';'paper.platform_contrast'='platform_contrast';'paper.platform_passerby'='platform_passerby';'paper.green_car'='green_car';'paper.green_car_contrast'='green_car_contrast';'paper.lantern_base'='lantern_base';'paper.lantern_pullback'='lantern_pullback';'paper.train_station'='train_station';'paper.train_station_hardened'='train_station_hardened';'paper.train_station_readability'='train_station_readability';'paper.train_station_boss'='train_station_boss';'paper.lantern_city'='lantern_city';'paper.lantern_city_campaign'='lantern_city_campaign';'paper.lantern_city_ui'='lantern_city_ui';'paper.lantern_city_epilogue'='lantern_city_epilogue';'paper.lantern_city_tadpole'='lantern_city_tadpole';'paper.lantern_city_rescue'='lantern_city_rescue';'paper.lantern_city_cast'='lantern_city_cast';'paper.tadpole_encounter'='tadpole_encounter';'gallery.intro'='gallery';'orbital.convoy'='protection';'orbital.siege'='siege'}
    $levelName=$levelNames[$Package]
    & $levelPython (Join-Path $PSScriptRoot "pipeline/level_design/build_$levelName.py")
    if ($LASTEXITCODE) { throw 'Level compilation failed' }
    $Build=(Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot "level_design/reviews/${levelName}_build.json") | ConvertFrom-Json).compiled
    if (-not $Candidate) {
        $levelSelected=& $levelPython (Join-Path $PSScriptRoot 'pipeline/level_design/resolve_launch.py') $Package
        if ($LASTEXITCODE) { throw 'Adopted level resolution failed' }
        if ($levelSelected) { $Build=$levelSelected }
    }
}
if ($Package -in @('paper.alley','paper.assault','paper.station','paper.stall','paper.night_market','paper.lantern_city','paper.lantern_city_campaign','paper.lantern_city_ui','paper.lantern_city_epilogue','paper.lantern_city_tadpole','paper.lantern_city_rescue','paper.lantern_city_cast')) {
    & $Godot --headless --editor --import --quit --path (Join-Path $PSScriptRoot 'framework')
    if ($LASTEXITCODE) { throw 'Godot resource import failed' }
}
$playerArgs = @("--build=$Build", "--assets=$levelRoot", "--quit-after=$QuitAfter")
if ($Package -in @('paper.station','paper.night_market','paper.lantern_city','paper.lantern_city_campaign','paper.lantern_city_ui','paper.lantern_city_epilogue','paper.lantern_city_tadpole','paper.lantern_city_rescue','paper.lantern_city_cast') -and -not $SkipOpening) {
    $openingDir = Join-Path $PSScriptRoot 'games/g01/cinematics/opening_original'
    $playerArgs += "--opening-dir=$openingDir"
}
if ($Package -in @('paper.lantern_city_cast','paper.lantern_city_campaign','paper.lantern_city_ui','paper.lantern_city_epilogue','paper.lantern_city_tadpole','paper.lantern_city_rescue')) {
    $playerArgs += "--transitions-dir=$(Join-Path $PSScriptRoot 'games/g01/cinematics/transitions_original')"
}
& $Godot --path (Join-Path $PSScriptRoot 'framework') --script res://tools/level_player.gd -- @playerArgs
exit $LASTEXITCODE
