Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
$verifyRoot = Join-Path $projectRoot "build\verify-windows"
$configDir = Join-Path $verifyRoot "config"
$dataDir = Join-Path $verifyRoot "data"
$cacheDir = Join-Path $verifyRoot "cache"
$logDir = Join-Path $verifyRoot "logs"
$appPath = Join-Path $projectRoot "build\nuitka\PlexMusicPlayer.dist\PlexMusicPlayer.exe"
$appWorkingDir = Split-Path -Parent $appPath

New-Item -ItemType Directory -Force -Path $configDir, $dataDir, $cacheDir, $logDir | Out-Null

$env:QT_QPA_PLATFORM = "offscreen"
$env:PLEX_MUSIC_PLAYER_CONFIG_DIR = $configDir
$env:PLEX_MUSIC_PLAYER_DATA_DIR = $dataDir
$env:PLEX_MUSIC_PLAYER_CACHE_DIR = $cacheDir
$env:PLEX_MUSIC_PLAYER_LOG_DIR = $logDir

$process = Start-Process -FilePath $appPath -WorkingDirectory $appWorkingDir -PassThru
$logPath = Join-Path $logDir "plex_music_player.log"
$deadline = (Get-Date).AddSeconds(20)
$backendPattern = "Using MPV playback backend: .*build\\nuitka\\PlexMusicPlayer\.dist\\lib\\(?:lib)?mpv-2\.dll"
$fallbackPattern = "Falling back to fake playback backend"
$logReady = $false
$backendReady = $false
$fallbackSeen = $false

while ((Get-Date) -lt $deadline) {
    if (Test-Path $logPath) {
        $logReady = $true
        if (Select-String -Path $logPath -Pattern $backendPattern -Quiet) {
            $backendReady = $true
            break
        }
        if (Select-String -Path $logPath -Pattern $fallbackPattern -Quiet) {
            $fallbackSeen = $true
            break
        }
    }

    if ($process.HasExited) {
        break
    }

    Start-Sleep -Milliseconds 500
}

if (-not $process.HasExited) {
    Stop-Process -Id $process.Id -Force
    $process.WaitForExit()
} elseif ($process.ExitCode -ne 0) {
    throw "Packaged app exited with code $($process.ExitCode)"
}

if (-not $logReady -or -not (Test-Path $logPath)) {
    throw "Missing packaged app log at $logPath"
}

Get-Content $logPath

if ($fallbackSeen -or (Select-String -Path $logPath -Pattern $fallbackPattern -Quiet)) {
    throw "Packaged app fell back to fake backend"
}

if (-not $backendReady -and -not (Select-String -Path $logPath -Pattern $backendPattern -Quiet)) {
    throw "Packaged app did not log bundled MPV backend usage"
}

Write-Host "Packaged Windows MPV backend verification passed"
