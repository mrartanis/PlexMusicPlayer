Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$nuitkaOutputDir = Join-Path $projectRoot "build\nuitka"
$bundleDir = Join-Path $nuitkaOutputDir "PlexMusicPlayer.dist"
$distDir = Join-Path $projectRoot "dist"
$setupIconPath = Join-Path $nuitkaOutputDir "plex_music_player.ico"
$installerScript = Join-Path $projectRoot "tools\windows_installer.iss"
$releaseTag = $env:RELEASE_TAG
$pyprojectVersion = (& $venvPython -c "import pathlib, tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()

if ($env:OS -ne "Windows_NT") {
    throw "This script builds the Windows installer only."
}

if (-not (Test-Path $venvPython)) {
    throw "Missing virtualenv interpreter: $venvPython"
}

if (-not (Test-Path $bundleDir)) {
    throw "Missing Windows bundle: $bundleDir"
}

if (-not (Test-Path $setupIconPath)) {
    throw "Missing Windows setup icon: $setupIconPath"
}

if (-not (Test-Path $installerScript)) {
    throw "Missing installer script: $installerScript"
}

if ([string]::IsNullOrWhiteSpace($releaseTag)) {
    $releaseTag = $pyprojectVersion
}

$appVersion = $releaseTag -replace '^v', ''
if ([string]::IsNullOrWhiteSpace($appVersion)) {
    $appVersion = $pyprojectVersion
}

$iscc = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
if ($null -eq $iscc) {
    $fallbackIscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $fallbackIscc) {
        $isccPath = $fallbackIscc
    } else {
        throw "Inno Setup compiler was not found. Install Inno Setup 6 and make iscc.exe available."
    }
} else {
    $isccPath = $iscc.Source
}

New-Item -ItemType Directory -Force -Path $distDir | Out-Null

Write-Host "Building Windows installer with Inno Setup"
Write-Host "Bundle source: $bundleDir"
Write-Host "Output directory: $distDir"

& $isccPath `
    "/DMyAppVersion=$appVersion" `
    "/DMyReleaseTag=$releaseTag" `
    "/DMySourceDir=$bundleDir" `
    "/DMyOutputDir=$distDir" `
    "/DMySetupIconFile=$setupIconPath" `
    $installerScript

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
