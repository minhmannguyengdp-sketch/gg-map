$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCandidates = @(
    "C:\Users\PC\.genfarmer\python-3.9.0.amd64\python.exe",
    "C:\Users\PC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
$pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonExe) {
    throw "No supported Python interpreter found."
}

$buildDepsPath = Join-Path $projectRoot ".build_deps"
$workspacePlaywrightCache = Join-Path $projectRoot ".build_ms-playwright"
$workspaceTclCache = Join-Path $projectRoot ".build_tcl"
$specPath = Join-Path $projectRoot "GG_map_7.9_new.spec"
$buildVersionPath = Join-Path $projectRoot "build_version.txt"
$distRoot = Join-Path $projectRoot "dist"
$appDist = Join-Path $distRoot "GG_map_7.9_new"
$playwrightBrowsersJson = ""

function Get-BuildVersionValue {
    param(
        [string]$Path,
        [string]$Fallback = "7.9.1"
    )

    if (Test-Path $Path) {
        $value = (Get-Content -LiteralPath $Path -Raw).Trim()
        if ($value) {
            return $value
        }
    }

    return $Fallback
}

function Get-NextBuildVersionValue {
    param(
        [string]$Value
    )

    if ($Value -match '^(\d+)\.(\d+)\.(\d+)$') {
        return "{0}.{1}.{2}" -f $matches[1], $matches[2], ([int]$matches[3] + 1)
    }

    return "7.9.1"
}

function Get-PlaywrightRequiredRevisions {
    param(
        [string]$BrowsersJsonPath
    )

    $payload = Get-Content -LiteralPath $BrowsersJsonPath -Raw | ConvertFrom-Json
    $required = @()
    foreach ($browser in $payload.browsers) {
        if ($browser.name -in @("chromium", "chromium-headless-shell", "ffmpeg", "winldd")) {
            $required += "{0}-{1}" -f $browser.name, $browser.revision
        }
    }
    return $required
}

function Test-PlaywrightCacheHasRequiredBrowsers {
    param(
        [string]$CachePath,
        [string[]]$RequiredEntries
    )

    if (-not (Test-Path $CachePath)) {
        return $false
    }

    foreach ($entry in $RequiredEntries) {
        if (-not (Test-Path (Join-Path $CachePath $entry))) {
            return $false
        }
    }

    return $true
}

$currentBuildVersion = Get-BuildVersionValue -Path $buildVersionPath
Set-Content -LiteralPath $buildVersionPath -Value $currentBuildVersion -NoNewline -Encoding ascii

if (-not (Test-Path $specPath)) {
    throw "Missing spec file: $specPath"
}

$playwrightBrowsersJson = Join-Path (Split-Path -Parent $pythonExe) "Lib\site-packages\playwright\driver\package\browsers.json"
if (-not (Test-Path $playwrightBrowsersJson)) {
    throw "Missing Playwright browsers.json: $playwrightBrowsersJson"
}

if (Test-Path $buildDepsPath) {
    if ($env:PYTHONPATH) {
        $env:PYTHONPATH = "$buildDepsPath;$env:PYTHONPATH"
    } else {
        $env:PYTHONPATH = $buildDepsPath
    }
}

$sourceTclRoot = Join-Path (Split-Path -Parent $pythonExe) "tcl"
if (-not (Test-Path $sourceTclRoot)) {
    throw "Missing Tcl folder: $sourceTclRoot"
}

if (Test-Path $workspaceTclCache) {
    Remove-Item -LiteralPath $workspaceTclCache -Recurse -Force
}

@"
from pathlib import Path
import shutil

src = Path(r"$sourceTclRoot")
dst = Path(r"$workspaceTclCache")
if dst.exists():
    shutil.rmtree(dst)
shutil.copytree(src, dst)
"@ | & $pythonExe -

$env:TCL_LIBRARY = Join-Path $workspaceTclCache "tcl8.6"
$env:TK_LIBRARY = Join-Path $workspaceTclCache "tk8.6"

$cleanTargets = @(
    (Join-Path $projectRoot "build"),
    (Join-Path $projectRoot "dist")
)
foreach ($target in $cleanTargets) {
    if (Test-Path $target) {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Get-ChildItem -Path $projectRoot -Recurse -Directory -Filter "__pycache__" -Force -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

Get-ChildItem -Path $projectRoot -File -Filter "*.spec" -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -ne "GG_map_7.9_new.spec"
} | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
}

$originalHome = $env:HOME
$originalUserProfile = $env:USERPROFILE
try {
    $env:HOME = $projectRoot
    $env:USERPROFILE = $projectRoot
    & $pythonExe -m PyInstaller --noconfirm --clean $specPath
} finally {
    $env:HOME = $originalHome
    $env:USERPROFILE = $originalUserProfile
}

$exePath = Join-Path $appDist "GG_map_7.9_new.exe"
if (-not (Test-Path $exePath)) {
    throw "PyInstaller did not create exe: $exePath"
}

$requiredPlaywrightEntries = Get-PlaywrightRequiredRevisions -BrowsersJsonPath $playwrightBrowsersJson
$localPlaywrightCache = Join-Path $env:LOCALAPPDATA "ms-playwright"

if (Test-PlaywrightCacheHasRequiredBrowsers -CachePath $workspacePlaywrightCache -RequiredEntries $requiredPlaywrightEntries) {
    $playwrightCache = $workspacePlaywrightCache
} elseif (Test-PlaywrightCacheHasRequiredBrowsers -CachePath $localPlaywrightCache -RequiredEntries $requiredPlaywrightEntries) {
    $playwrightCache = $localPlaywrightCache
} elseif (Test-Path $workspacePlaywrightCache) {
    $playwrightCache = $workspacePlaywrightCache
} else {
    $playwrightCache = $localPlaywrightCache
}

if (-not (Test-Path $playwrightCache)) {
    throw "Playwright cache not found: $playwrightCache"
}

$playwrightTarget = Join-Path $appDist "ms-playwright"
New-Item -ItemType Directory -Force -Path $playwrightTarget | Out-Null

$browserPatterns = @(
    "chromium-*",
    "chromium_headless_shell-*",
    "ffmpeg-*",
    "winldd-*"
)

foreach ($pattern in $browserPatterns) {
    Get-ChildItem -Path $playwrightCache -Directory -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item -Path $_.FullName -Destination (Join-Path $playwrightTarget $_.Name) -Recurse -Force
    }
}

Copy-Item -Path (Join-Path $projectRoot "LICENSE_APPS_SCRIPT_SETUP.md") -Destination (Join-Path $appDist "LICENSE_APPS_SCRIPT_SETUP.md") -Force
Copy-Item -Path (Join-Path $projectRoot "license_apps_script_webapp.gs") -Destination (Join-Path $appDist "license_apps_script_webapp.gs") -Force
Copy-Item -Path $buildVersionPath -Destination (Join-Path $appDist "build_version.txt") -Force
Copy-Item -Path $exePath -Destination (Join-Path $appDist ("GG_map_7.9_new_v{0}.exe" -f $currentBuildVersion)) -Force

$saveDataTarget = Join-Path $appDist "Save_data"
New-Item -ItemType Directory -Force -Path $saveDataTarget | Out-Null
$saveDataSource = Join-Path $projectRoot "Save_data"
New-Item -ItemType Directory -Force -Path $saveDataSource | Out-Null

$licenseJsonPath = Join-Path $saveDataSource "ui_cao_map_license.json"
if (-not (Test-Path $licenseJsonPath)) {
    Set-Content -LiteralPath $licenseJsonPath -Value "{}" -NoNewline -Encoding utf8
}

$licenseServerJsonPath = Join-Path $saveDataSource "ui_cao_map_license_server.json"
if (-not (Test-Path $licenseServerJsonPath)) {
    Set-Content -LiteralPath $licenseServerJsonPath -Value '{"license_api_url":""}' -NoNewline -Encoding utf8
}

Get-ChildItem -LiteralPath $saveDataSource -File -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $saveDataTarget $_.Name) -Force
}

$nextBuildVersion = Get-NextBuildVersionValue -Value $currentBuildVersion
Set-Content -LiteralPath $buildVersionPath -Value $nextBuildVersion -NoNewline -Encoding ascii

Write-Host ""
Write-Host "Build complete:"
Write-Host "Build version: $currentBuildVersion"
Write-Host "EXE: $exePath"
Write-Host "Versioned EXE: $(Join-Path $appDist ("GG_map_7.9_new_v{0}.exe" -f $currentBuildVersion))"
Write-Host "Release folder: $appDist"
