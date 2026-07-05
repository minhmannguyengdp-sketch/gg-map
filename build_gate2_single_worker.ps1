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

$gate1PatchScript = Join-Path $projectRoot "tools\apply_gate1_chrome_diagnose.py"
$gate2PatchScript = Join-Path $projectRoot "tools\apply_gate2_single_worker.py"
$patchedDir = Join-Path $projectRoot ".build_gate2"
$gate1Source = Join-Path $patchedDir "ui_cao_map_gate1.py"
$gate2Source = Join-Path $patchedDir "ui_cao_map.py"

foreach ($scriptPath in @($gate1PatchScript, $gate2PatchScript)) {
    if (-not (Test-Path $scriptPath)) {
        throw "Missing patch script: $scriptPath"
    }
}

if (Test-Path $patchedDir) {
    Remove-Item -LiteralPath $patchedDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $patchedDir | Out-Null

& $pythonExe $gate1PatchScript (Join-Path $projectRoot "ui_cao_map.py") $gate1Source
& $pythonExe $gate2PatchScript $gate1Source $gate2Source

if (-not (Test-Path $gate2Source)) {
    throw "Gate 2 patched source was not generated: $gate2Source"
}

$oldEntry = $env:GG_MAP_ENTRY_SCRIPT
try {
    $env:GG_MAP_ENTRY_SCRIPT = $gate2Source
    & (Join-Path $projectRoot "build_gg_map_exe.ps1")
} finally {
    $env:GG_MAP_ENTRY_SCRIPT = $oldEntry
}
