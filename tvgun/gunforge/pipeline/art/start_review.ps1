# Restore the read-only review services after their processes exit or Windows restarts.
$ErrorActionPreference = 'Stop'
$artRoot = $PSScriptRoot
$reviewPython = Join-Path $artRoot '.venv/Scripts/python.exe'
$reviewServer = Join-Path $artRoot 'serve_t02_gallery.py'
if (-not (Test-Path -LiteralPath $reviewPython)) { throw "Missing Python environment: $reviewPython" }
$reviewLogs = Join-Path $artRoot '.review-logs'
New-Item -ItemType Directory -Path $reviewLogs -Force | Out-Null
$reviewSites = @(@{Port=8765;Task='T02'},@{Port=8766;Task='T03'},@{Port=8767;Task='T07'})
if (Test-Path -LiteralPath (Join-Path $artRoot '../../games/g01/reports/art/T08/gallery/index.html')) {
    $reviewSites += @{Port=8768;Task='T08'}
}
foreach ($reviewSite in $reviewSites) {
    $reviewListener = Get-NetTCPConnection -LocalPort $reviewSite.Port -State Listen -ErrorAction SilentlyContinue
    if (-not $reviewListener) {
        $reviewArguments = @('"' + $reviewServer + '"', '--port', [string]$reviewSite.Port, '--task', $reviewSite.Task)
        Start-Process -FilePath $reviewPython -ArgumentList $reviewArguments -WorkingDirectory $artRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $reviewLogs ($reviewSite.Task+'.out.log')) -RedirectStandardError (Join-Path $reviewLogs ($reviewSite.Task+'.err.log')) | Out-Null
    }
}
$reviewViewer = Join-Path $artRoot '../../../art2d/demos/viewer/serve.mjs'
if (-not (Get-NetTCPConnection -LocalPort 4173 -State Listen -ErrorAction SilentlyContinue)) {
    $reviewNode = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($reviewNode) {
        $reviewViewerPath = (Resolve-Path -LiteralPath $reviewViewer).Path
        Start-Process -FilePath $reviewNode.Source -ArgumentList ('"' + $reviewViewerPath + '"') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $reviewLogs 'art2d.out.log') -RedirectStandardError (Join-Path $reviewLogs 'art2d.err.log') | Out-Null
    } else {
        Write-Warning 'Node is required for the character previews on port 4173.'
    }
}
if ($reviewSites.Task -contains 'T08') {
    Write-Output 'Current T08 review: http://127.0.0.1:8768/gallery/'
}
Write-Output 'T07 character review: http://127.0.0.1:8767/gallery/'
Write-Output 'Earlier T02 references: http://127.0.0.1:8765/gallery/'
