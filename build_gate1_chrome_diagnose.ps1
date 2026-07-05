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

$patchScript = Join-Path $projectRoot "tools\apply_gate1_chrome_diagnose.py"
$patchedDir = Join-Path $projectRoot ".build_gate1"
$patchedSource = Join-Path $patchedDir "ui_cao_map.py"

if (-not (Test-Path $patchScript)) {
    throw "Missing Gate 1 patch script: $patchScript"
}

if (Test-Path $patchedDir) {
    Remove-Item -LiteralPath $patchedDir -Recurse -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force -Path $patchedDir | Out-Null

& $pythonExe $patchScript (Join-Path $projectRoot "ui_cao_map.py") $patchedSource
if (-not (Test-Path $patchedSource)) {
    throw "Gate 1 patched source was not generated: $patchedSource"
}

$oldEntry = $env:GG_MAP_ENTRY_SCRIPT
try {
    $env:GG_MAP_ENTRY_SCRIPT = $patchedSource
    & (Join-Path $projectRoot "build_gg_map_exe.ps1")
} finally {
    $env:GG_MAP_ENTRY_SCRIPT = $oldEntry
}
