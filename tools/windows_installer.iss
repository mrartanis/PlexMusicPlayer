#define MyAppName "Plex Music Player"
#define MyAppPublisher "PlexMusicPlayer"
#define MyAppId "PlexMusicPlayer.PlexMusicPlayer"

#ifndef MyAppVersion
  #error MyAppVersion is required
#endif
#ifndef MyReleaseTag
  #error MyReleaseTag is required
#endif
#ifndef MySourceDir
  #error MySourceDir is required
#endif
#ifndef MyOutputDir
  #error MyOutputDir is required
#endif
#ifndef MySetupIconFile
  #error MySetupIconFile is required
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/mrartanis/plex_music_player
AppSupportURL=https://github.com/mrartanis/plex_music_player/issues
AppUpdatesURL=https://github.com/mrartanis/plex_music_player/releases
DefaultDirName={localappdata}\Programs\Plex Music Player
DefaultGroupName=Plex Music Player
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\PlexMusicPlayer.exe
SetupIconFile={#MySetupIconFile}
OutputDir={#MyOutputDir}
OutputBaseFilename=PlexMusicPlayer-{#MyReleaseTag}-windows-x86_64-setup

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Plex Music Player"; Filename: "{app}\PlexMusicPlayer.exe"; WorkingDir: "{app}"; IconFilename: "{app}\PlexMusicPlayer.exe"
Name: "{autodesktop}\Plex Music Player"; Filename: "{app}\PlexMusicPlayer.exe"; WorkingDir: "{app}"; IconFilename: "{app}\PlexMusicPlayer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PlexMusicPlayer.exe"; Description: "Launch Plex Music Player"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\PlexMusicPlayer\PlexMusicPlayer"
