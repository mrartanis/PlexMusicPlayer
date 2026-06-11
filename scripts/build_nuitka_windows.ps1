Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$outputDir = Join-Path $projectRoot "build\nuitka"
$appName = "PlexMusicPlayer"
$displayName = "Plex Music Player"
$nuitkaStem = "nuitka_entry"
$builtDistDir = Join-Path $outputDir "$nuitkaStem.dist"
$distDir = Join-Path $outputDir "$appName.dist"
$iconSourcePath = Join-Path $projectRoot "assets\plex_music_player_256.png"
$iconBuildScript = Join-Path $projectRoot "tools\build_windows_icon.py"
$setupIconPath = Join-Path $outputDir "plex_music_player.ico"
$bundledPrimaryDllName = ""
$mpvLibraryDir = ""
$appVersion = ""
$windowsVersion = ""
$nuitkaArgs = @()
$nuitkaVerbose = $env:PLEX_MUSIC_PLAYER_NUITKA_VERBOSE -eq "1"

Set-Location $projectRoot

if ($env:OS -ne "Windows_NT") {
    throw "This script builds the Windows Nuitka standalone bundle only."
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Missing virtualenv interpreter: $venvPython"
    Write-Host "Create it first:"
    Write-Host "  py -3.12 -m venv .venv"
    Write-Host "  .venv\Scripts\python -m pip install -e '.[dev,packaging]'"
    exit 1
}

if (-not (Test-Path $iconSourcePath)) {
    throw "Missing app icon source: $iconSourcePath"
}

if (-not (Test-Path $iconBuildScript)) {
    throw "Missing Windows icon builder: $iconBuildScript"
}

$appVersion = (& $venvPython -c "import pathlib, tomllib; print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))['project']['version'])").Trim()
$versionParts = $appVersion.Split(".")
if ($versionParts.Count -eq 3) {
    $windowsVersion = "$appVersion.0"
} else {
    $windowsVersion = $appVersion
}

$mpvLibrary = $env:PLEX_MUSIC_PLAYER_MPV_LIBRARY
if ([string]::IsNullOrWhiteSpace($mpvLibrary)) {
    $searchRoots = @(
        "C:\ProgramData\chocolatey\lib\mpv.install\tools\mpv",
        "C:\ProgramData\chocolatey\lib\mpvio.install\tools\mpv",
        "C:\ProgramData\chocolatey\lib",
        "C:\Program Files",
        "C:\Program Files (x86)"
    )
    $candidate = $null
    foreach ($root in $searchRoots) {
        if (-not (Test-Path $root)) {
            continue
        }
        $candidate = Get-ChildItem -Path $root -Include "libmpv-2.dll", "mpv-2.dll" -File -Recurse -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty FullName
        if ($candidate) {
            break
        }
    }
    $mpvLibrary = $candidate
}

if ([string]::IsNullOrWhiteSpace($mpvLibrary) -or -not (Test-Path $mpvLibrary)) {
    Write-Host "Missing libmpv DLL. Install mpv and set PLEX_MUSIC_PLAYER_MPV_LIBRARY to mpv-2.dll."
    exit 1
}

$bundledPrimaryDllName = [System.IO.Path]::GetFileName($mpvLibrary)
$mpvLibrary = (Resolve-Path $mpvLibrary).Path
$mpvLibraryDir = Split-Path -Parent $mpvLibrary

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

& $venvPython $iconBuildScript --source $iconSourcePath --destination $setupIconPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
    (Join-Path $outputDir "$nuitkaStem.build"), `
    $builtDistDir, `
    $distDir, `
    (Join-Path $outputDir "$nuitkaStem.onefile-build")

$nuitkaArgs = @(
    "--standalone",
    "--assume-yes-for-downloads",
    "--windows-console-mode=disable",
    "--plugin-enable=pyside6",
    "--include-module=_cffi_backend",
    "--include-package=certifi",
    "--include-package-data=certifi",
    "--include-package=cffi",
    "--include-package=miniaudio",
    "--include-package=app",
    "--include-package-data=app.presentation.qt",
    "--include-data-files=$mpvLibrary=lib/$bundledPrimaryDllName",
    "--include-data-files=$mpvLibraryDir\*.dll=lib/",
    "--windows-icon-from-ico=$setupIconPath",
    "--windows-company-name=Plex Music Player",
    "--windows-product-name=$displayName",
    "--windows-file-description=$displayName",
    "--windows-file-version=$windowsVersion",
    "--windows-product-version=$windowsVersion",
    "--output-dir=$outputDir",
    "--output-filename=$appName",
    "tools/nuitka_entry.py"
)

if ($nuitkaVerbose) {
    $nuitkaArgs = @("--show-progress", "--show-scons", "--verbose") + $nuitkaArgs
}

if (Get-Command "cl.exe" -ErrorAction SilentlyContinue) {
    $nuitkaArgs = @("--msvc=latest") + $nuitkaArgs
}

Write-Host "Building Windows bundle with Nuitka"
Write-Host "Using MPV library: $mpvLibrary"
Write-Host "Output directory: $distDir"

& $venvPython -u -m nuitka @nuitkaArgs
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Move-Item -Force $builtDistDir $distDir

Write-Host "Built: $distDir"
