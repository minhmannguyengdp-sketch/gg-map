$ErrorActionPreference = "Stop"
chcp 65001 > $null
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$coreBuildScript = Join-Path $projectRoot "build_gg_map_exe_core.ps1"
if (-not (Test-Path $coreBuildScript)) {
    throw "Missing core build script: $coreBuildScript"
}

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

Remove-Item Env:\GG_MAP_ENTRY_SCRIPT -ErrorAction SilentlyContinue
& $coreBuildScript
if ($LASTEXITCODE -ne 0) {
    throw "Core build failed: $coreBuildScript"
}
