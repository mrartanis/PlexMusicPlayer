@echo off
setlocal

set "REPO=C:\Users\artanis\PlexMusicPlayer"
cd /d "%REPO%" || exit /b 1

set "MPV_DLL="
for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-ChildItem -Path 'C:\ProgramData\chocolatey\lib','C:\Program Files','C:\Program Files (x86)' -Include 'libmpv-2.dll','mpv-2.dll' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName"') do set "MPV_DLL=%%I"
if not defined MPV_DLL (
  set "MPV_ARCHIVE=%REPO%\build\mpv-dev.7z"
  set "MPV_DIR=%REPO%\build\mpv-dev"
  powershell -NoProfile -Command "$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest'; $asset = $release.assets | Where-Object { $_.name -match '^mpv-dev-x86_64-[^.]+.*\.7z$' } | Select-Object -First 1; if (-not $asset) { throw 'Unable to locate mpv dev asset' }; Invoke-WebRequest -Uri $asset.browser_download_url -OutFile '%MPV_ARCHIVE%'; if (Test-Path '%MPV_DIR%') { Remove-Item -LiteralPath '%MPV_DIR%' -Recurse -Force }; New-Item -ItemType Directory -Force -Path '%MPV_DIR%' | Out-Null"
  7z x "%MPV_ARCHIVE%" "-o%MPV_DIR%" >nul || exit /b 1
  for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-ChildItem -Path '%MPV_DIR%' -Include 'libmpv-2.dll','mpv-2.dll' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName"') do set "MPV_DLL=%%I"
)
if not defined MPV_DLL (
  echo Unable to locate libmpv DLL
  exit /b 1
)
set "PLEX_MUSIC_PLAYER_MPV_LIBRARY=%MPV_DLL%"

set "VSDEVCMD="
for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-ChildItem 'C:\Program Files*\Microsoft Visual Studio\*\*\Common7\Tools\VsDevCmd.bat' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName"') do set "VSDEVCMD=%%I"
if not defined VSDEVCMD (
  echo Unable to locate VsDevCmd.bat
  exit /b 1
)

call "%VSDEVCMD%" -arch=x64 -host_arch=x64 || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%REPO%\scripts\build_nuitka_windows.ps1"
exit /b %ERRORLEVEL%
