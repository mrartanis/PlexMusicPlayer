from setuptools import setup

APP = ['plex_music_player/__main__.py']
DATA_FILES = []
OPTIONS = {
    'packages': ['PyQt6', 'pygame', 'plexapi', 'requests', 'plex_music_player', 'plex_music_player.ui', 'plex_music_player.models', 'plex_music_player.lib'],
    'includes': ['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets'],
    'iconfile': 'MusicApp.icns',
    'plist': {
        'CFBundleName': 'Plex Music Player',
        'CFBundleDisplayName': 'Plex Music Player',
        'CFBundleIdentifier': 'com.plexmusicplayer.app',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHumanReadableCopyright': '© 2024'
    }
}

setup(
    name="Plex Music Player",
    version="1.0.0",
    packages=['plex_music_player', 'plex_music_player.ui', 'plex_music_player.models', 'plex_music_player.lib'],
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    install_requires=['PyQt6', 'pygame', 'plexapi', 'requests'],
)
