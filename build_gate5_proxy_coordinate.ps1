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

$gatePatchScripts = @(
    "tools\apply_gate1_chrome_diagnose.py",
    "tools\apply_gate2_single_worker.py",
    "tools\apply_gate3_async_geocode.py",
    "tools\apply_gate4_coordinate_priority.py",
    "tools\apply_gate5_proxy_layer.py"
) | ForEach-Object { Join-Path $projectRoot $_ }

$patchedDir = Join-Path $projectRoot ".build_gate5"
$source0 = Join-Path $projectRoot "ui_cao_map.py"
$source1 = Join-Path $patchedDir "ui_cao_map_gate1.py"
$source2 = Join-Path $patchedDir "ui_cao_map_gate2.py"
$source3 = Join-Path $patchedDir "ui_cao_map_gate3.py"
$source4 = Join-Path $patchedDir "ui_cao_map_gate4.py"
$source5 = Join-Path $patchedDir "ui_cao_map.py"

foreach ($scriptPath in $gatePatchScripts) {
    if (-not (Test-Path $scriptPath)) {
        throw "Missing patch script: $scriptPath"
    }
}

if (Test-Path $patchedDir) {
    Remove-Item -LiteralPath $patchedDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $patchedDir | Out-Null

& $pythonExe $gatePatchScripts[0] $source0 $source1
& $pythonExe $gatePatchScripts[1] $source1 $source2
& $pythonExe $gatePatchScripts[2] $source2 $source3
& $pythonExe $gatePatchScripts[3] $source3 $source4
& $pythonExe $gatePatchScripts[4] $source4 $source5

if (-not (Test-Path $source5)) {
    throw "Gate 5 patched source was not generated: $source5"
}

$oldEntry = $env:GG_MAP_ENTRY_SCRIPT
try {
    $env:GG_MAP_ENTRY_SCRIPT = $source5
    & (Join-Path $projectRoot "build_gg_map_exe.ps1")
} finally {
    $env:GG_MAP_ENTRY_SCRIPT = $oldEntry
}
