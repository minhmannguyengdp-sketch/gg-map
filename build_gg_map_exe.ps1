$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$coreBuildScript = Join-Path $projectRoot "build_gg_map_exe_core.ps1"
$pythonCandidates = @(
    "C:\Users\PC\.genfarmer\python-3.9.0.amd64\python.exe",
    "C:\Users\PC\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
)
$pythonExe = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $pythonExe) {
    throw "No supported Python interpreter found."
}
if (-not (Test-Path $coreBuildScript)) {
    throw "Missing core build script: $coreBuildScript"
}

$gatePatchScripts = @(
    "tools\apply_gate1_chrome_diagnose.py",
    "tools\apply_gate2_single_worker.py",
    "tools\apply_gate3_async_geocode.py",
    "tools\apply_gate4_coordinate_priority.py",
    "tools\apply_gate5_proxy_layer.py",
    "tools\apply_gate6_maps_buttons.py",
    "tools\apply_gate7_mst_audit.py"
) | ForEach-Object { Join-Path $projectRoot $_ }

$patchedDir = Join-Path $projectRoot ".build_gate_final"
$sources = @(
    (Join-Path $projectRoot "ui_cao_map.py"),
    (Join-Path $patchedDir "ui_cao_map_gate1.py"),
    (Join-Path $patchedDir "ui_cao_map_gate2.py"),
    (Join-Path $patchedDir "ui_cao_map_gate3.py"),
    (Join-Path $patchedDir "ui_cao_map_gate4.py"),
    (Join-Path $patchedDir "ui_cao_map_gate5.py"),
    (Join-Path $patchedDir "ui_cao_map_gate6.py"),
    (Join-Path $patchedDir "ui_cao_map.py")
)

$cleanTargets = @(
    (Join-Path $projectRoot ".build_tcl"),
    (Join-Path $projectRoot "build"),
    (Join-Path $projectRoot "dist")
)
foreach ($target in $cleanTargets) {
    if (Test-Path $target) {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
    }
}
Get-ChildItem -Path $projectRoot -Directory -Filter ".build_gate*" -Force -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $patchedDir | Out-Null

foreach ($scriptPath in $gatePatchScripts) {
    if (-not (Test-Path $scriptPath)) {
        throw "Missing gate patch script: $scriptPath"
    }
}

for ($index = 0; $index -lt $gatePatchScripts.Count; $index++) {
    & $pythonExe $gatePatchScripts[$index] $sources[$index] $sources[$index + 1]
}

$finalSource = $sources[$sources.Count - 1]
if (-not (Test-Path $finalSource)) {
    throw "Final patched source was not generated: $finalSource"
}

$oldEntry = $env:GG_MAP_ENTRY_SCRIPT
try {
    $env:GG_MAP_ENTRY_SCRIPT = $finalSource
    & $coreBuildScript
} finally {
    $env:GG_MAP_ENTRY_SCRIPT = $oldEntry
}
