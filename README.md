# Plex Music Player

A modern music player for Plex Media Server, integrated with Mac Os media center and media keys on windows.

![Screenshot](screenshot.png)

CAUTON! AI-generated

Should work on OSX, windows and linux.
Tested only on osx 15 with arm processor and windows 11

## Features

- 🎵 QT6 dark theme ui.
- 🎨 Album artwork display
- 📱 macOS Media Center integration
  - Now Playing information
  - Media controls (play/pause, next/previous track)
  - Album artwork in Media Center
- ⊞ Windows media keys integration
- 🎯 Automatic connection to Plex server at startup
- 🔄 Playlist management
  - Add/remove tracks
  - Shuffle playlist
  - Clear playlist
- 🎚️ Playback controls
  - Play/Pause
  - Next/Previous track
  - Progress bar with seeking
  - Volume control
- 📋 Track information display
  - Title
  - Artist
  - Album
  - Year
  - Duration
- 💾 Configuration persistence
  - Server connection details
  - Playlist state

## Requirements

- Python 3.11 (tested on)
- Access to Plex Media Server via network
- PyQt6
- plexapi
- requests

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/plex_music_player.git
cd plex_music_player
```

2. Create and activate a virtual environment:
```bash
python -m venv env
source env/bin/activate  # On macOS/Linux
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the application:
```bash
python -m plex_music_player.main
```

2. On first run, enter your Plex server details:
   - Server URL (e.g., http://localhost:32400)
   - Username
   - Token

3. The application will connect to your Plex server and display your music library.

## Controls

- **Play/Pause**: Space or Play/Pause button
- **Next Track**: Right arrow or Next button
- **Previous Track**: Left arrow or Previous button
- **Volume**: Up/Down arrows or Volume slider
- **Seek**: Click on progress bar
- **Search**: Type in the search box
- **Add to Playlist**: Double-click on a track
- **Remove from Playlist**: Select track and press Delete
- **Shuffle Playlist**: Click the shuffle button
- **Clear Playlist**: Click the clear button

## Media Center Integration

The player integrates with macOS Media Center and Windows Media Keys, providing:
- Track information in the Now Playing widget (macOS)
- Album artwork in the Media Center (macOS)
- Media controls from:
  - Media Center widget (macOS)
  - Touch Bar (macOS)
  - Media keys on keyboard (macOS and Windows)
  - Control Center (macOS)

## Known Issues

- **Timer Warning**: After pausing a track, you might see a "QObject::killTimer: Timers cannot be stopped from another thread" warning in the console. This is a known Qt issue and doesn't affect playback functionality.
- **Media Keys**: On Windows, media keys might take a few seconds to start working after application launch.

## License

feel free to use this project as you wish. 
