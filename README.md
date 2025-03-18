# Plex Music Player

A modern music player for Plex Media Server with a beautiful UI and macOS Media Center integration.

## Features

- 🎵 Beautiful and modern UI with dark theme
- 🎨 Album artwork display
- 📱 macOS Media Center integration
  - Now Playing information
  - Media controls (play/pause, next/previous track)
  - Album artwork in Media Center
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
- 🔍 Search functionality
  - Search by title, artist, or album
  - Real-time search results
- 💾 Configuration persistence
  - Server connection details
  - Last played track
  - Playlist state

## Requirements

- Python 3.8+
- macOS 10.15+
- Plex Media Server
- PyQt6
- pygame
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
python -m plex_music_player
```

2. On first run, enter your Plex server details:
   - Server URL (e.g., http://localhost:32400)
   - Username
   - Password

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

The player integrates with macOS Media Center, providing:
- Track information in the Now Playing widget
- Album artwork in the Media Center
- Media controls from:
  - Media Center widget
  - Touch Bar
  - Media keys on keyboard
  - Control Center

## License

MIT License - feel free to use this project as you wish. 