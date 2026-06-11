Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$nuitkaRoot = Join-Path $projectRoot "build\nuitka"

$processNames = @(
    "python",
    "python3",
    "cl",
    "link",
    "rc",
    "mt",
    "cc1",
    "cc1plus",
    "gcc",
    "g++",
    "ld"
)

foreach ($name in $processNames) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 500

if (Test-Path $nuitkaRoot) {
    Remove-Item -LiteralPath $nuitkaRoot -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Cleaned PlexMusicPlayer Windows build state"
