from setuptools import setup
import os

APP = ['plex_music_player/__main__.py']
DATA_FILES = [
    ("plex_music_player/icons_svg", [
        "plex_music_player/icons_svg/play.svg",
        "plex_music_player/icons_svg/pause.svg",
        "plex_music_player/icons_svg/add_to_playlist.svg",
        "plex_music_player/icons_svg/remove_track.svg",
        "plex_music_player/icons_svg/shuffle_playlist.svg",
        "plex_music_player/icons_svg/clear_playlist.svg",
        "plex_music_player/icons_svg/next.svg",
        "plex_music_player/icons_svg/previous.svg",
        "plex_music_player/icons_svg/locate_track.svg",
        "plex_music_player/icons_svg/window-minimize.svg",
        "plex_music_player/icons_svg/window-maximize.svg",
        "plex_music_player/icons_svg/window-close.svg",
    ])
]
VLC_LIB_PATH = '/Applications/VLC.app/Contents/MacOS/lib'
PY2APP_OPTIONS = {
    'packages': [
        'PyQt6', 'plexapi', 'requests', 'plex_music_player', 'plex_music_player.ui', 'plex_music_player.models', 'plex_music_player.lib',
        'vlc'
    ],
    'includes': [
        'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'vlc'
    ],
    'iconfile': 'MusicApp.icns',
    'plist': {
        'CFBundleName': 'Plex Music Player',
        'CFBundleDisplayName': 'Plex Music Player',
        'CFBundleIdentifier': 'com.plexmusicplayer.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHumanReadableCopyright': '© 2024'
    },
    'resources': [
        'plex_music_player/icons_svg',
        os.path.join(VLC_LIB_PATH, 'libvlc.dylib'),
        os.path.join(VLC_LIB_PATH, 'libvlccore.dylib'),
    ],
}

setup(
    name="Plex Music Player",
    version="1.0.0",
    packages=['plex_music_player', 'plex_music_player.ui', 'plex_music_player.models', 'plex_music_player.lib'],
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': PY2APP_OPTIONS},
)
