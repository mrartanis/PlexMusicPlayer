env\Scripts\Activate.ps1
pyinstaller -i icon_win.ico  -F --paths=env/Lib/site-packages --add-data="MusicApp.iconset\icon_256x256.png:icon" .\plex_music_player\__main__.py