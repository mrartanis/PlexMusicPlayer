import os
import json
import time
import traceback
import requests
from typing import Optional, List, Dict, Any
from plexapi.server import PlexServer
from plexapi.audio import Track, Album, Artist
from PyQt6.QtCore import (
    QObject, pyqtSignal, QTimer, QUrl, QThread, 
    pyqtSlot, QMutex, Qt, QModelIndex, QAbstractListModel
)
from PyQt6.QtCore import Qt as QtCore
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import random
import sys
from plex_music_player.lib.media_center import get_media_center
from plex_music_player.lib.logger import Logger

logger = Logger()

# Constants for error handling
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1  # seconds
CONNECTION_CHECK_INTERVAL = 30  # seconds

class ConnectionError(Exception):
    """Custom exception for connection errors."""
    pass

if sys.platform == 'darwin':
    from Foundation import NSObject, NSMutableDictionary
    from AppKit import NSImage
    import objc
    import MediaPlayer

class SavedTrack:
    """Class to store track information without requiring Plex API access."""
    def __init__(self, title: str, artist: str, album: str, year: Optional[int], key: str, rating_key: str):
        self.title = title
        self.grandparentTitle = artist  # To maintain compatibility with Track interface
        self.parentTitle = album  # To maintain compatibility with Track interface
        self.year = year
        self.key = key
        self.ratingKey = rating_key
        self.duration = 0  # Will be set when track is played
        self.media = []  # Will be populated when track is played
        self.thumb = None  # Album cover URL
        self._server = None  # Plex server reference

    def getStreamURL(self, audioFormat: str = 'mp3') -> str:
        """Get stream URL for the track."""
        if not self.media:
            return None
            
        try:
            # Handle both dictionary and object media formats
            if isinstance(self.media[0], dict):
                container = self.media[0].get('container')
                parts = self.media[0].get('parts', [])
            else:
                container = self.media[0].container
                parts = self.media[0].parts
                
            if not parts:
                return None
                
            if container in ['mp3', 'flac']:
                # Handle both dictionary and object part formats
                if isinstance(parts[0], dict):
                    media_key = parts[0].get('key')
                else:
                    media_key = parts[0].key
                    
                if not self._server:
                    return None
                    
                token = self._server._token
                
                # Get the base URL directly from the server
                base_url = self._server.url(media_key)
                logger.debug(f"DEBUG: Base URL: {base_url}")
                
                # Add verify=False to handle SSL certificate issues
                try:
                    # First try with SSL verification
                    url = f"{base_url}?download=1&X-Plex-Token={token}"
                    logger.debug(f"DEBUG: Trying URL with SSL verification: {url}")
                    response = requests.head(url, verify=True, timeout=5)
                    if response.status_code == 200:
                        logger.debug(f"DEBUG: URL with SSL verification successful")
                        return url
                except requests.exceptions.SSLError:
                    logger.debug("SSL verification failed, trying without verification...")
                    # If SSL verification fails, try without it
                    url = f"{base_url}?download=1&X-Plex-Token={token}"
                    logger.debug(f"DEBUG: Trying URL without SSL verification: {url}")
                    response = requests.head(url, verify=False, timeout=5)
                    if response.status_code == 200:
                        logger.debug(f"DEBUG: URL without SSL verification successful")
                        return url
                        
                return None
                
            return None
        except Exception as e:
            logger.error(f"Error in getStreamURL: {e}")
            return None

class TrackLoader(QThread):
    """Thread for loading tracks from Plex asynchronously"""
    tracks_loaded = pyqtSignal(list)  # Signal emitted when tracks are loaded
    first_track_loaded = pyqtSignal(object)  # Signal emitted when first track is loaded
    error_occurred = pyqtSignal(str)  # Signal emitted on error
    finished = pyqtSignal()  # Signal emitted when thread is finished
    progress_updated = pyqtSignal(int, int)  # Signal for progress updates (current, total)

    def __init__(self, load_type, plex_object):
        """
        Initialize track loader
        :param load_type: 'artist' or 'album'
        :param plex_object: Plex artist or album object
        """
        super().__init__()
        self.load_type = load_type
        self.plex_object = plex_object
        self.first_track_emitted = False
        self.should_stop = False
        self.total_tracks = 0
        self.loaded_tracks = 0
        logger.debug(f"TrackLoader initialized for {load_type}: {plex_object.title}")

    def stop(self):
        """Stop the loading process"""
        self.should_stop = True
        logger.debug(f"TrackLoader stopped for {self.plex_object.title}")

    def _update_progress(self, current: int, total: int):
        """Update loading progress"""
        self.loaded_tracks = current
        self.total_tracks = total
        self.progress_updated.emit(current, total)

    def run(self):
        try:
            if self.load_type == 'artist':
                # Load all albums for artist
                try:
                    albums = self.plex_object.albums()
                    total_albums = len(albums)
                    
                    if total_albums == 0:
                        self.error_occurred.emit(f"No albums found for artist {self.plex_object.title}")
                        return
                    
                    for i, album in enumerate(albums, 1):
                        if self.should_stop:
                            break
                            
                        try:
                            # Load tracks for current album
                            album_tracks = album.tracks()
                            track_count = len(album_tracks)
                            
                            if track_count == 0:
                                continue
                            
                            # Emit first track if not done yet
                            if not self.first_track_emitted and album_tracks:
                                self.first_track_loaded.emit(album_tracks[0])
                                self.first_track_emitted = True
                            
                            # Emit tracks for current album
                            if album_tracks:
                                self.tracks_loaded.emit(album_tracks)
                                self._update_progress(i, total_albums)
                            
                            # Small delay to prevent UI freezing
                            self.msleep(50)
                        except Exception as album_error:
                            self.error_occurred.emit(f"Error loading album {album.title}: {str(album_error)}")
                            continue
                except Exception as albums_error:
                    self.error_occurred.emit(f"Error loading albums: {str(albums_error)}")
                    
            elif self.load_type == 'album':
                try:
                    album_tracks = self.plex_object.tracks()
                    track_count = len(album_tracks)
                    
                    if track_count == 0:
                        self.error_occurred.emit(f"No tracks found in album {self.plex_object.title}")
                        return
                    
                    # Emit first track if available
                    if album_tracks:
                        self.first_track_loaded.emit(album_tracks[0])
                        self.tracks_loaded.emit(album_tracks)
                        self._update_progress(1, 1)
                except Exception as album_error:
                    self.error_occurred.emit(f"Error loading tracks: {str(album_error)}")
            
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.finished.emit()

class ArtistLoader(QThread):
    """Thread for loading artists from Plex asynchronously"""
    artist_loaded = pyqtSignal(object)  # Signal emitted when an artist is loaded
    error_occurred = pyqtSignal(str)  # Signal emitted on error
    finished = pyqtSignal()  # Signal emitted when thread is finished
    progress_updated = pyqtSignal(int, int)  # Signal for progress updates (current, total)

    def __init__(self, plex_server, batch_size=5):
        """
        Initialize artist loader
        :param plex_server: Plex server instance
        :param batch_size: Number of artists to load in parallel
        """
        super().__init__()
        self.plex_server = plex_server
        self.batch_size = batch_size
        self.should_stop = False
        self.total_artists = 0
        self.loaded_artists = 0
        self.artists = []
        logger.debug("ArtistLoader initialized")

    def stop(self):
        """Stop the loading process"""
        self.should_stop = True
        logger.debug("ArtistLoader stopped")

    def _update_progress(self, current: int, total: int):
        """Update loading progress"""
        self.loaded_artists = current
        self.total_artists = total
        self.progress_updated.emit(current, total)

    def run(self):
        try:
            logger.debug("Loading artists from Plex server")
            # Get all artists from the library
            self.artists = self.plex_server.library.search(libtype="artist")
            total_artists = len(self.artists)
            logger.debug(f"Found {total_artists} artists")
            
            if total_artists == 0:
                logger.debug("No artists found")
                self.error_occurred.emit("No artists found in the library")
                return
            
            # Process artists in batches
            for i in range(0, total_artists, self.batch_size):
                if self.should_stop:
                    logger.debug("Loading stopped")
                    break
                
                # Get the current batch of artists
                batch = self.artists[i:i+self.batch_size]
                
                # Process each artist in the batch
                for artist in batch:
                    if self.should_stop:
                        break
                    
                    try:
                        logger.debug(f"Loading artist: {artist.title}")
                        # Emit the artist
                        self.artist_loaded.emit(artist)
                        self._update_progress(i + batch.index(artist) + 1, total_artists)
                    except Exception as artist_error:
                        logger.error(f"Error loading artist {artist.title}: {str(artist_error)}")
                        self.error_occurred.emit(f"Error loading artist {artist.title}: {str(artist_error)}")
                
                # Small delay to prevent UI freezing
                self.msleep(10)
            
        except Exception as e:
            logger.error(f"Error in ArtistLoader: {str(e)}")
            self.error_occurred.emit(str(e))
        finally:
            logger.debug("ArtistLoader finished")
            self.finished.emit()

class PlaylistUpdater(QThread):
    """Thread for updating playlist asynchronously"""
    track_added = pyqtSignal(object)  # Signal emitted when a track is added
    finished = pyqtSignal()  # Signal emitted when all tracks are added
    
    def __init__(self, tracks, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        self.should_stop = False
    
    def stop(self):
        """Stop the update process"""
        self.should_stop = True
    
    def run(self):
        """Add tracks to playlist with a delay between each"""
        for track in self.tracks:
            if self.should_stop:
                break
                
            # Emit signal for each track
            self.track_added.emit(track)
            
            # Small delay to prevent UI freezing
            self.msleep(10)
        
        self.finished.emit()

class Player(QObject):
    """Class for managing music playback in a separate thread."""
    
    # Signals for UI updates
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    playback_state_changed = pyqtSignal(bool)
    track_changed = pyqtSignal()  # Signal for track changes
    tracks_batch_loaded = pyqtSignal(list)  # New signal for batch track loading
    connection_error = pyqtSignal(str)  # New signal for connection errors
    connection_restored = pyqtSignal()  # New signal for connection restoration
    player_ready = pyqtSignal()  # Signal emitted when player is ready for playback
    playback_started = pyqtSignal()  # Signal emitted when playback actually starts
    playback_failed = pyqtSignal(str)  # Signal emitted when playback fails
    
    # New signals for thread-safe operations
    play_next_track_signal = pyqtSignal()
    play_previous_track_signal = pyqtSignal()
    toggle_play_signal = pyqtSignal()
    stop_signal = pyqtSignal()
    seek_position_signal = pyqtSignal(int)
    
    def __init__(self):
        super().__init__()
        self._playlist_lock = QMutex()  # Add mutex for thread safety
        # QMediaPlayer and QAudioOutput will be created in initialize_player()
        self._player: Optional[QMediaPlayer] = None
        self._audio_output: Optional[QAudioOutput] = None
        
        # Plex data
        self.plex: Optional[PlexServer] = None
        self.current_track: Optional[Track] = None
        self.current_album: Optional[Album] = None
        self.current_artist: Optional[Artist] = None
        self.artists: List[Artist] = []
        self.albums: List[Album] = []
        self.tracks: List[Track] = []
        self.playlist: List[Track] = []
        self.current_playlist_index: int = -1
        self.auto_play: bool = True  # Auto-play enabled by default

        # Initialize media center integration
        self.media_center = get_media_center()
        if self.media_center:
            self.media_center.initialize()
            self.media_center.set_player(self)

        # Last known position
        self._last_position = 0

        self._active_loaders = []  # Keep track of active loaders

        self._connection_check_timer = None
        self._last_connection_check = 0
        self._is_reconnecting = False
        
        # Playback state tracking
        self._playback_start_timer = QTimer()
        self._playback_start_timer.setSingleShot(True)
        self._playback_start_timer.timeout.connect(self._check_playback_start)
        self._playback_attempts = 0
        self._max_playback_attempts = 3

        # Add media status tracking
        self._media_loaded = False
        self._playback_error = False

        # Connect signals to slots
        self.play_next_track_signal.connect(self._play_next_track_impl, Qt.ConnectionType.QueuedConnection)
        self.play_previous_track_signal.connect(self._play_previous_track_impl, Qt.ConnectionType.QueuedConnection)
        self.toggle_play_signal.connect(self._toggle_play_impl, Qt.ConnectionType.QueuedConnection)
        self.stop_signal.connect(self._stop_impl, Qt.ConnectionType.QueuedConnection)
        self.seek_position_signal.connect(self._seek_position_impl, Qt.ConnectionType.QueuedConnection)
        
        logger.debug("Player initialized in thread: " + str(QThread.currentThread()))

    @pyqtSlot()
    def initialize_player(self) -> None:
        """
        Initialize QMediaPlayer and QAudioOutput in this thread.
        This ensures that all playback objects work within the same thread.
        """
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        # Connect signals
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_error_occurred)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        logger.debug("Player initialized in thread: " + str(QThread.currentThread()))
        self.player_ready.emit()

    @pyqtSlot(str, str)
    def connect_server(self, url: str, token: str) -> bool:
        """Connect to Plex server."""
        try:
            self.plex = PlexServer(url, token)
            # Test connection
            self.plex.library.search("", limit=1)
                
            # Start connection checking after successful connection
            self._start_connection_check()
            logger.debug("Successfully connected to Plex server")
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL verification error: {e}")
            self.connection_error.emit("SSL verification failed. Please check your server's SSL certificate.")
            raise
        except Exception as e:
            logger.error(f"Error connecting to Plex server: {e}")
            self.connection_error.emit(f"Failed to connect to Plex server: {str(e)}")
            raise

    @pyqtSlot(result=dict)
    def load_config(self) -> Optional[dict]:
        """Load configuration from file and attempt to connect."""
        try:
            logger.debug("Starting load_config() method")
            config_path = os.path.expanduser("~/.config/plex_music_player/config.json")
            logger.debug(f"Config path: {config_path}")
            
            # Create default config
            default_config = {
                'plex': {
                    'url': None,
                    'token': None
                },
                'auto_play': True
            }
            
            # Create config directory if it doesn't exist
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            if not os.path.exists(config_path):
                logger.debug("Config file does not exist, creating new one")
                with open(config_path, "w") as f:
                    json.dump(default_config, f)
                return default_config
            
            try:
                with open(config_path, "r") as f:
                    logger.debug("Reading config file")
                    content = f.read()
                    logger.debug(f"Config file content: {content}")
                    config = json.loads(content)
                    logger.debug(f"Parsed config: {config}")
                    
                    if 'plex' in config:
                        logger.debug("Plex config found")
                        plex_config = config['plex']
                        if plex_config['url'] and plex_config['token']:
                            logger.debug(f"Connecting to Plex server: {plex_config['url']}")
                            self.connect_server(plex_config['url'], plex_config['token'])
                            
                            # Load playlist if available
                            if 'playlist' in config and config['playlist']:
                                logger.debug(f"Loading playlist with {len(config['playlist'])} tracks")
                                self.playlist.clear()
                                for track_data in config['playlist']:
                                    if 'title' in track_data and 'rating_key' in track_data:
                                        # Create a SavedTrack with minimal information
                                        track = SavedTrack(
                                            title=track_data['title'],
                                            artist="",  # Will be filled when track is loaded
                                            album="",   # Will be filled when track is loaded
                                            year=None,
                                            key="",     # Will be filled when track is loaded
                                            rating_key=track_data['rating_key']
                                        )
                                        self.playlist.append(track)
                                
                                # Safely restore playlist index
                                if 'playlist_index' in config:
                                    saved_index = config['playlist_index']
                                    saved_track_key = config.get('playlist_index_track_key')
                                    
                                    # Validate saved index
                                    if (isinstance(saved_index, int) and 
                                        0 <= saved_index < len(self.playlist)):
                                        # If we have a track key, verify it matches
                                        if saved_track_key:
                                            track = self.playlist[saved_index]
                                            if (hasattr(track, 'ratingKey') and 
                                                track.ratingKey == saved_track_key):
                                                self.current_playlist_index = saved_index
                                                self.current_track = track
                                        else:
                                            # No track key to verify, just set the index
                                            self.current_playlist_index = saved_index
                                            self.current_track = self.playlist[saved_index]
                                    else:
                                        # Invalid index, reset to beginning
                                        self.current_playlist_index = 0 if self.playlist else -1
                                        self.current_track = self.playlist[0] if self.playlist else None
                            
                            # Set auto-play state
                            if 'auto_play' in config:
                                self.auto_play = config['auto_play']
                            
                            return config
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}")
                logger.error(f"Error position: line {e.lineno}, column {e.colno}, char {e.pos}")
                # Try to read the file again to see the problematic content
                with open(config_path, "r") as f:
                    content = f.read()
                    logger.error(f"Problematic content around error: {content[max(0, e.pos-20):min(len(content), e.pos+20)]}")
                # Create a new config file with default values
                logger.debug("Creating new config file with default values")
                with open(config_path, "w") as f:
                    json.dump(default_config, f)
                logger.debug("New config file created")
                return default_config
                
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            logger.error(f"Exception type: {type(e)}")
            logger.error(f"Exception details: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        return None

    @pyqtSlot(result=list)
    def load_artists(self) -> List[str]:
        """Load the list of artists."""
        if not self.plex:
            return []
        try:
            self.artists = self.plex.library.search(libtype="artist")
            return [artist.title for artist in self.artists]
        except Exception:
            return []

    @pyqtSlot(int, result=list)
    def load_albums(self, artist_index: int) -> List[str]:
        """Load the list of albums for the artist, sorted by year."""
        if not self.plex or artist_index < 0 or artist_index >= len(self.artists):
            return []
        try:
            self.current_artist = self.artists[artist_index]
            self.albums = self.current_artist.albums()
            # Sort albums by year
            self.albums.sort(key=lambda album: album.year if hasattr(album, 'year') else 0)
            return [f"{album.title} ({album.year})" if hasattr(album, 'year') and album.year else album.title 
                   for album in self.albums]
        except Exception:
            return []

    @pyqtSlot(int, result=list)
    def load_tracks(self, album_index: int) -> List[str]:
        """Load the list of tracks for the album."""
        if not self.plex or album_index < 0 or album_index >= len(self.albums):
            return []
        try:
            self.current_album = self.albums[album_index]
            self.tracks = self.current_album.tracks()
            return [f"{track.index}. {track.title} ({track.year})" 
                   if hasattr(track, 'year') and track.year else f"{track.index}. {track.title}"
                   for track in self.tracks]
        except Exception:
            return []

    @pyqtSlot(result=str)
    def get_stream_url(self) -> str:
        """Get stream URL with retry mechanism."""
        if not self.current_track:
            return None
            
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                logger.debug(f"Attempting to get stream URL (attempt {attempt + 1})")
                url = self.current_track.getStreamURL()
                if url:
                    logger.debug(f"Stream URL obtained: {url}")
                    return url
                raise ConnectionError("Failed to get stream URL")
            except Exception as e:
                logger.error(f"Error getting stream URL (attempt {attempt + 1}): {e}")
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY)
                    if not self._check_connection():
                        self._retry_connection()
                else:
                    self.connection_error.emit(f"Failed to get stream URL: {str(e)}")
                    return None

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """Handle playback state changes safely."""
        logger.debug(f"State changed to: {state}")
        logger.debug(f"Current position: {self._player.position() if self._player else 'No player'}")
        
        if state == QMediaPlayer.PlaybackState.StoppedState:
            current_pos = self.get_current_position()
            logger.debug(f"Current position on stop: {current_pos}")
            # Save position before stopping
            self._last_position = current_pos
            logger.debug(f"Saved last position: {self._last_position}")
            
            # Check if this was an error stop
            error = self._player.error()
            if error != QMediaPlayer.Error.NoError:
                error_string = self._player.errorString()
                logger.error(f"Playback stopped due to error: {error_string}")
                
                # Check if this is an SSL error
                if "TLS/SSL" in error_string or "SSL" in error_string:
                    logger.debug("SSL error detected, will retry playback")
                    # Don't move to next track, let the retry mechanism handle it
                    return
                
                # For other errors, try to refresh track info and retry
                if self.plex and self.current_track:
                    try:
                        logger.debug("Error occurred, refreshing track information...")
                        refreshed_track = self.plex.fetchItem(self.current_track.ratingKey)
                        if refreshed_track:
                            if isinstance(self.current_track, SavedTrack):
                                self.current_track.media = refreshed_track.media
                                self.current_track._server = self.plex
                            else:
                                self.current_track = refreshed_track
                            # Try playing again with refreshed information
                            self._play_track_impl()
                            return
                    except Exception as refresh_error:
                        logger.error(f"Recovery attempt failed: {refresh_error}")
            
            # Only auto-play next track if this wasn't an error stop
            if self.auto_play:
                if not self.play_next_track():
                    logger.debug("No more tracks to play.")
                else:
                    logger.debug("Next track started.")
            else:
                logger.debug("No current track available.")
                
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        logger.debug(f"Player state: {'Playing' if is_playing else 'Paused/Stopped'}")
        self.playback_state_changed.emit(is_playing)
        QTimer.singleShot(100, self._update_media_center)

    def _on_position_changed(self, position: int) -> None:
        """Handle position changes."""
        if abs(position - self._last_position) > 1000:  # Update if change is more than 1 second
            self.position_changed.emit(position)
            self._last_position = position
            if position % 1000 == 0:
                QTimer.singleShot(0, self._update_media_center)

    def _on_duration_changed(self, duration: int) -> None:
        """Handle duration changes."""
        self.duration_changed.emit(duration)

    def _on_error_occurred(self, error: QMediaPlayer.Error, error_string: str) -> None:
        """Handle media player errors."""
        logger.error(f"Media player error: {error}, {error_string}")
        if error != QMediaPlayer.Error.NoError:
            if error == QMediaPlayer.Error.NetworkError:
                logger.debug("Network error occurred, attempting to recover...")
                if self._retry_connection():
                    # If connection is restored, try to refresh track info and retry
                    if isinstance(self.current_track, SavedTrack):
                        try:
                            logger.debug("Refreshing track information after network error...")
                            refreshed_track = self.plex.fetchItem(self.current_track.ratingKey)
                            if refreshed_track:
                                self.current_track.media = refreshed_track.media
                                self.current_track._server = self.plex
                        except Exception as e:
                            logger.error(f"Error refreshing track info after network error: {e}")
                    # Retry playing the current track
                    self._play_track_impl()
                else:
                    # If reconnection failed, try next track
                    self.play_next_track()
            elif error == QMediaPlayer.Error.FormatError:
                logger.debug("Format error occurred, skipping track...")
                self.play_next_track()
            elif "TLS/SSL" in error_string or "SSL" in error_string:
                logger.debug("SSL error occurred, will retry playback")
                # Don't move to next track, let the retry mechanism handle it
                # Try to refresh track info and retry
                if self.plex and self.current_track:
                    try:
                        logger.debug("Refreshing track information after SSL error...")
                        refreshed_track = self.plex.fetchItem(self.current_track.ratingKey)
                        if refreshed_track:
                            if isinstance(self.current_track, SavedTrack):
                                self.current_track.media = refreshed_track.media
                                self.current_track._server = self.plex
                            else:
                                self.current_track = refreshed_track
                            # Try playing again with refreshed information
                            self._play_track_impl()
                    except Exception as e:
                        logger.error(f"Error refreshing track info after SSL error: {e}")
            else:
                logger.error(f"An error occurred during playback: {error_string}")
                self.connection_error.emit(f"Playback error: {error_string}")

    @pyqtSlot(result=bool)
    def play_next_track(self) -> bool:
        """Thread-safe method to play next track."""
        self.play_next_track_signal.emit()
        return True

    @pyqtSlot(result=bool)
    def play_previous_track(self) -> bool:
        """Thread-safe method to play previous track."""
        self.play_previous_track_signal.emit()
        return True

    @pyqtSlot(result=bool)
    def toggle_play(self) -> bool:
        """Thread-safe method to toggle play/pause."""
        self.toggle_play_signal.emit()
        return True

    @pyqtSlot()
    def stop(self) -> None:
        """Thread-safe method to stop playback."""
        self.stop_signal.emit()

    @pyqtSlot(int)
    def seek_position(self, position: int) -> None:
        """Thread-safe method to seek to position."""
        self.seek_position_signal.emit(position)

    @pyqtSlot()
    def _play_next_track_impl(self) -> None:
        """Internal implementation of play next track."""
        if not self.playlist:
            return
        
        if self.current_playlist_index >= 0 and self.current_playlist_index < len(self.playlist) - 1:
            # Store current track info
            current_track = self.current_track
            current_index = self.current_playlist_index
            
            # Recreate player to ensure clean state
            if not self._recreate_player():
                logger.error("Failed to recreate player")
                return
            
            # Update track index and current track
            self.current_playlist_index += 1
            self.current_track = self.playlist[self.current_playlist_index]
            
            # Reset playback attempts counter
            self._playback_attempts = 0
            
            # Start playback of new track
            success = self._play_track_impl()
            if success:
                self.track_changed.emit()
                QTimer.singleShot(120, self._update_media_center)

    @pyqtSlot()
    def _play_previous_track_impl(self) -> None:
        """Internal implementation of play previous track."""
        if self.current_playlist_index > 0:
            # Store current track info
            current_track = self.current_track
            current_index = self.current_playlist_index
            
            # Recreate player to ensure clean state
            if not self._recreate_player():
                logger.error("Failed to recreate player")
                return
            
            self.current_playlist_index -= 1
            self.current_track = self.playlist[self.current_playlist_index]
            success = self._play_track_impl()
            if success:
                self.track_changed.emit()
                QTimer.singleShot(120, self._update_media_center)

    @pyqtSlot()
    def _toggle_play_impl(self) -> None:
        """Internal implementation of toggle play/pause."""
        if self._player is None:
            logger.error("Player not initialized!")
            return
        
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.playback_state_changed.emit(False)
        else:
            if self._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState:
                self._player.setPosition(self._last_position or 0)
            self._player.play()
            self.playback_state_changed.emit(True)
        QTimer.singleShot(100, self._update_media_center)

    @pyqtSlot()
    def _stop_impl(self) -> None:
        """Internal implementation of stop."""
        if self._player:
            self._player.stop()
        self.current_track = None
        self.current_playlist_index = -1
        self.playback_state_changed.emit(False)
        self.track_changed.emit()

    @pyqtSlot(int)
    def _seek_position_impl(self, position: int) -> None:
        """Internal implementation of seek to position."""
        if self._player is None:
            logger.error("Player not initialized!")
            return
        self._player.setPosition(position)
        self._update_media_center()

    @pyqtSlot()
    def _play_track_impl(self) -> bool:
        """Internal implementation of track playback."""
        logger.debug("\n === Starting _play_track_impl ===")
        if self._player is None:
            logger.error("ERROR: Player not initialized!")
            return False
            
        try:
            logger.debug(f"Current player state before stop: {self._player.playbackState()}")
            # Stop any current playback
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                logger.debug("Stopping current playback")
                self._player.stop()
                logger.debug(f"Current player state after stop: {self._player.playbackState()}")
            
            # Ensure we have a valid current track
            if not self.current_track:
                logger.error("ERROR: No current track selected")
                return False
                
            logger.debug(f"Attempting to play track: {self.current_track.title}")
            logger.debug(f"Track index: {self.current_playlist_index}")
            
            # Get stream URL with retry mechanism
            stream_url = self.get_stream_url()
            if not stream_url:
                logger.error("ERROR: Failed to get stream URL")
                return False
                
            logger.debug(f"Got stream URL: {stream_url}")
            
            # Create QUrl and set source
            qurl = QUrl(stream_url)
            logger.debug(f"Created QUrl: {qurl.toString()}")
            
            # Clear any existing source first
            self._player.setSource(QUrl())
            
            # Reset media status tracking
            self._media_loaded = False
            self._playback_error = False
            
            # Set new source
            self._player.setSource(qurl)
            logger.debug("Source set")
            
            # Start playback
            logger.debug("Starting playback...")
            self._player.play()
            logger.debug(f"Current player state after play: {self._player.playbackState()}")
            
            return True
            
        except Exception as e:
            logger.error(f"ERROR in _play_track_impl: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return False

    @pyqtSlot(result=dict)
    def config(self) -> dict:
        """Return the player configuration."""
        logger.debug("Starting config() method")
        
        # Save only essential configuration data
        config_data = {
            'plex': {
                'url': self.plex._baseurl if self.plex else None,
                'token': self.plex._token if self.plex else None
            },
            'auto_play': self.auto_play
        }
        logger.debug(f"Basic config data: {config_data}")
        
        # Safely save playlist index
        if self.playlist and self.current_playlist_index >= 0:
            if self.current_playlist_index < len(self.playlist):
                config_data['playlist_index'] = self.current_playlist_index
                # Save the rating key of the track at this index for validation during load
                track = self.playlist[self.current_playlist_index]
                if hasattr(track, 'ratingKey'):
                    config_data['playlist_index_track_key'] = track.ratingKey
        
        # Save current track info if available
        if self.current_track:
            logger.debug(f"Current track type: {type(self.current_track)}")
            logger.debug(f"Current track attributes: {dir(self.current_track)}")
            config_data['current_track'] = {
                'title': self.current_track.title if hasattr(self.current_track, 'title') else None,
                'rating_key': self.current_track.ratingKey if hasattr(self.current_track, 'ratingKey') else None
            }
            logger.debug(f"Current track data: {config_data['current_track']}")
            
        # Save current album info if available
        if self.current_album:
            logger.debug(f"Current album type: {type(self.current_album)}")
            logger.debug(f"Current album attributes: {dir(self.current_album)}")
            config_data['current_album'] = {
                'title': self.current_album.title if hasattr(self.current_album, 'title') else None,
                'rating_key': self.current_album.ratingKey if hasattr(self.current_album, 'ratingKey') else None
            }
            logger.debug(f"Current album data: {config_data['current_album']}")
            
        # Save current artist info if available
        if self.current_artist:
            logger.debug(f"Current artist type: {type(self.current_artist)}")
            logger.debug(f"Current artist attributes: {dir(self.current_artist)}")
            config_data['current_artist'] = {
                'title': self.current_artist.title if hasattr(self.current_artist, 'title') else None,
                'rating_key': self.current_artist.ratingKey if hasattr(self.current_artist, 'ratingKey') else None
            }
            logger.debug(f"Current artist data: {config_data['current_artist']}")
            
        logger.debug(f"Final config data: {config_data}")
        return config_data

    @pyqtSlot()
    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            logger.debug("Starting save_config() method")
            config_dir = os.path.expanduser("~/.config/plex_music_player")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "config.json")
            logger.debug(f"Config path: {config_path}")
            
            logger.debug("Getting config data")
            config_data = self.config()
            
            logger.debug("Attempting to serialize config data")
            try:
                json_str = json.dumps(config_data)
                logger.debug("Successfully serialized config data")
                logger.debug(f"JSON string: {json_str}")
            except TypeError as e:
                logger.error(f"JSON serialization error: {e}")
                logger.error(f"Error details: {str(e)}")
                # Try to identify the problematic key
                for key, value in config_data.items():
                    try:
                        json.dumps({key: value})
                    except TypeError:
                        logger.error(f"Problem with key '{key}'")
                        if isinstance(value, dict):
                            for subkey, subvalue in value.items():
                                try:
                                    json.dumps({subkey: subvalue})
                                except TypeError:
                                    logger.error(f"Problem with subkey '{key}.{subkey}'")
                                    logger.error(f"Value type: {type(subvalue)}")
                                    logger.error(f"Value: {subvalue}")
            
            logger.debug("Writing config to file")
            with open(config_path, "w") as f:
                json.dump(config_data, f)
            logger.debug("Config saved successfully")
            
            # Verify the saved file
            logger.debug("Verifying saved config file")
            with open(config_path, "r") as f:
                content = f.read()
                logger.debug(f"Saved file content: {content}")
                try:
                    json.loads(content)
                    logger.debug("Saved file is valid JSON")
                except json.JSONDecodeError as e:
                    logger.error(f"Saved file is not valid JSON: {e}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            logger.error(f"Exception type: {type(e)}")
            logger.error(f"Exception details: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")

    @pyqtSlot()
    def save_playlist(self) -> None:
        """Save the playlist to file."""
        try:
            config_dir = os.path.expanduser("~/.config/plex_music_player")
            os.makedirs(config_dir, exist_ok=True)
            playlist_path = os.path.join(config_dir, "playlist.json")
            
            playlist_data = []
            for track in self.playlist:
                if isinstance(track, SavedTrack):
                    # Handle media data safely
                    media_data = []
                    if track.media:
                        for m in track.media:
                            # Handle both dictionary and object media formats
                            if isinstance(m, dict):
                                container = m.get('container')
                                parts = m.get('parts', [])
                            else:
                                container = m.container
                                parts = m.parts
                                
                            # Handle parts safely
                            parts_data = []
                            for p in parts:
                                if isinstance(p, dict):
                                    key = p.get('key')
                                else:
                                    key = p.key
                                parts_data.append({'key': key})
                                
                            media_data.append({
                                'container': container,
                                'parts': parts_data
                            })
                            
                    track_data = {
                        'title': track.title,
                        'artist': track.grandparentTitle,
                        'album': track.parentTitle,
                        'year': track.year,
                        'key': track.key,
                        'ratingKey': track.ratingKey,
                        'duration': track.duration,
                        'media': media_data,
                        'thumb': track.thumb
                    }
                else:
                    # Handle media data safely for regular tracks
                    media_data = []
                    if track.media:
                        for m in track.media:
                            # Handle both dictionary and object media formats
                            if isinstance(m, dict):
                                container = m.get('container')
                                parts = m.get('parts', [])
                            else:
                                container = m.container
                                parts = m.parts
                                
                                
                            # Handle parts safely
                            parts_data = []
                            for p in parts:
                                if isinstance(p, dict):
                                    key = p.get('key')
                                else:
                                    key = p.key
                                parts_data.append({'key': key})
                                
                            media_data.append({
                                'container': container,
                                'parts': parts_data
                            })
                            
                    track_data = {
                        'title': track.title,
                        'artist': track.grandparentTitle,
                        'album': track.parentTitle,
                        'year': track.year if hasattr(track, 'year') else None,
                        'key': track.key,
                        'ratingKey': track.ratingKey,
                        'duration': track.duration,
                        'media': media_data,
                        'thumb': track.thumb if hasattr(track, 'thumb') else None
                    }
                playlist_data.append(track_data)
            
            with open(playlist_path, "w") as f:
                json.dump({
                    'playlist': playlist_data,
                    'current_index': self.current_playlist_index
                }, f)
        except Exception as e:
            logger.error(f"Error saving playlist: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")

    @pyqtSlot()
    def load_playlist(self) -> None:
        """Load the playlist from file."""
        playlist_path = os.path.expanduser("~/.config/plex_music_player/playlist.json")
        
        # If file doesn't exist, just return
        if not os.path.exists(playlist_path):
            return
            
        try:
            # Load data from file
            with open(playlist_path, "r") as f:
                data = json.load(f)
                
            # Check basic data structure
            if not isinstance(data, dict) or 'playlist' not in data:
                logger.error("Invalid playlist format: missing 'playlist' field or invalid structure")
                os.remove(playlist_path)
                return
                
            # Clear current playlist
            self.playlist.clear()
            
            # Check if playlist is a list
            if not isinstance(data['playlist'], list):
                logger.error("Invalid playlist format: 'playlist' is not a list")
                os.remove(playlist_path)
                return
                
            # Check each track in the playlist
            for track_data in data['playlist']:
                # Check if track_data is a dictionary
                if not isinstance(track_data, dict):
                    logger.error("Invalid track format: track data is not a dictionary")
                    os.remove(playlist_path)
                    return
                    
                # Check for required fields
                required_fields = ['title', 'artist', 'album', 'key', 'ratingKey']
                if not all(field in track_data for field in required_fields):
                    logger.error("Invalid track format: missing required fields")
                    os.remove(playlist_path)
                    return
                    
                # Convert fields to strings if needed
                try:
                    track = SavedTrack(
                        title=str(track_data['title']),
                        artist=str(track_data['artist']),
                        album=str(track_data['album']),
                        year=int(track_data['year']) if track_data.get('year') is not None else None,
                        key=str(track_data['key']),
                        rating_key=str(track_data['ratingKey'])
                    )
                    
                    # Add optional fields
                    if 'duration' in track_data:
                        track.duration = int(track_data['duration'])
                    if 'media' in track_data and track_data['media']:
                        track.media = track_data['media']
                    if 'thumb' in track_data:
                        track.thumb = track_data['thumb']
                        
                    # Set the server reference
                    track._server = self.plex
                        
                    self.playlist.append(track)
                except (ValueError, TypeError) as e:
                    logger.error(f"Error converting track data: {e}")
                    os.remove(playlist_path)
                    return
            
            # Set current index
            self.current_playlist_index = data.get('current_index', -1)
            
            # Check if index is within valid range
            if self.current_playlist_index >= len(self.playlist):
                self.current_playlist_index = -1
                
            # Set current track
            if 0 <= self.current_playlist_index < len(self.playlist):
                self.current_track = self.playlist[self.current_playlist_index]
                
            # Emit playback state changed signal
            self.playback_state_changed.emit(True)
            
        except json.JSONDecodeError:
            logger.error("Invalid playlist file: not a valid JSON")
            os.remove(playlist_path)
        except Exception as e:
            logger.error(f"Error loading playlist: {e}")
            # In case of error, clear playlist and remove file
            self.playlist.clear()
            self.current_playlist_index = -1
            self.current_track = None
            if os.path.exists(playlist_path):
                os.remove(playlist_path)

    @pyqtSlot(list)
    def add_tracks_batch_async(self, tracks: List[Track]) -> None:
        """Add multiple tracks to the playlist asynchronously"""
        if not tracks:
            return
            
        self._playlist_lock.lock()
        try:
            # Filter out tracks that already exist in the playlist
            existing_rating_keys = {track.ratingKey for track in self.playlist}
            new_tracks = [
                track for track in tracks 
                if track.ratingKey not in existing_rating_keys
            ]
            
            if new_tracks:
                # Add only new tracks to playlist
                self.playlist.extend(new_tracks)
                
                # Emit signal for UI update
                self.tracks_batch_loaded.emit(new_tracks)
                
                # If this is the first track being added, update UI
                if len(self.playlist) == len(new_tracks):
                    self.current_playlist_index = 0
                    self.current_track = self.playlist[0]
                    self.track_changed.emit()
                    QTimer.singleShot(120, self._update_media_center)
                
                # Save playlist after adding tracks
                self.save_playlist()
        finally:
            self._playlist_lock.unlock()

    def data(self, index: QModelIndex, role: int = QtCore.ItemDataRole.DisplayRole) -> Any:
        """Return data for the given role"""
        if not index.isValid():
            return None
            
        track_item = self.playlist[index.row()]
        
        # Lock the mutex before accessing the track data
        self._playlist_lock.lock()
        try:
            if role == QtCore.ItemDataRole.DisplayRole:
                return track_item.title
            elif role == QtCore.ItemDataRole.ToolTipRole:
                return f"{track_item.title}\n{track_item.artist}\n{track_item.album}"
            elif role == QtCore.ItemDataRole.UserRole:
                return track_item
            elif role == QtCore.ItemDataRole.ForegroundRole:
                return track_item.color
        finally:
            self._playlist_lock.unlock()
            
        return None

    @pyqtSlot(bool)
    def set_auto_play(self, enabled: bool) -> None:
        """Set the auto-play state."""
        self.auto_play = enabled

    @pyqtSlot(result=bool)
    def is_auto_play_enabled(self) -> bool:
        """Return whether auto-play is enabled."""
        return self.auto_play

    @pyqtSlot()
    def update_progress(self) -> None:
        """Update playback progress."""
        if self.is_playing() and self.current_track:
            current_pos = self.get_current_position()
            logger.debug(f"Current position: {current_pos}")
            logger.debug(f"Player state: {self._player.playbackState() if self._player else 'Not initialized'}")
            if current_pos >= self.current_track.duration:
                logger.debug("Track ended, playing next track...")
                self.play_next_track()
        else:
            pass

    @pyqtSlot(result=int)
    def get_current_track_size(self) -> Optional[int]:
        """Return the size of the current track in bytes."""
        if not self.current_track or not self.current_track.media or not self.current_track.media[0].parts:
            return None
        
        try:
            media_key = self.current_track.media[0].parts[0].key
            token = self.current_track._server._token
            base_url = self.current_track._server.url(media_key)
            stream_url = f"{base_url}?download=1&X-Plex-Token={token}"
            response = requests.head(stream_url)
            if response.status_code == 200:
                return int(response.headers.get('Content-Length', 0))
            else:
                logger.error(f"Error getting track size: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error getting track size: {e}")
            return None

    def start_artist_tracks_loading(self, artist, stop_previous=True) -> TrackLoader:
        """Start asynchronous loading of all tracks for an artist"""
        # Stop any active loaders if requested
        if stop_previous:
            for loader in self._active_loaders:
                loader.stop()
                loader.wait()
            self._active_loaders.clear()

        # Create new loader
        loader = TrackLoader('artist', artist)
        loader.tracks_loaded.connect(self.add_tracks_batch_async)
        loader.error_occurred.connect(self._handle_loader_error)
        loader.first_track_loaded.connect(self._handle_first_track)
        loader.finished.connect(lambda: self._cleanup_loader(loader))
        self._active_loaders.append(loader)
        loader.start()
        
        return loader

    def start_album_tracks_loading(self, album) -> TrackLoader:
        """Start asynchronous loading of all tracks for an album"""
        # Stop any active loaders
        for loader in self._active_loaders:
            loader.stop()
            loader.wait()
        self._active_loaders.clear()

        # Create new loader
        loader = TrackLoader('album', album)
        loader.tracks_loaded.connect(self.add_tracks_batch_async)
        loader.error_occurred.connect(self._handle_loader_error)
        loader.first_track_loaded.connect(self._handle_first_track)
        loader.finished.connect(lambda: self._cleanup_loader(loader))
        self._active_loaders.append(loader)
        loader.start()
        
        return loader

    def _cleanup_loader(self, loader):
        """Clean up the loader after it's finished"""
        if loader in self._active_loaders:
            self._active_loaders.remove(loader)
            loader.deleteLater()

    @pyqtSlot(str)
    def _handle_loader_error(self, error_msg: str) -> None:
        """Handle errors from track loader"""
        logger.error(f"Error loading tracks: {error_msg}")

    @pyqtSlot(object)
    def _handle_first_track(self, track: object) -> None:
        """Handle first track loaded when playlist is empty"""
        if not self.playlist:
            self.add_to_playlist(track)  # This will emit tracks_batch_loaded
            self.current_playlist_index = 0
            self.current_track = track
            # Emit track_changed signal before starting playback to update UI
            self.track_changed.emit()
            # Update media center info
            QTimer.singleShot(120, self._update_media_center)
            # Start playback
            if self._play_track_impl():
                QTimer.singleShot(120, self._update_media_center)

    def _check_connection(self) -> bool:
        """Check Plex server connection."""
        if not self.plex:
            return False
            
        try:
            # Simple request to check connection
            self.plex.library.search("", limit=1)
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False

    def _retry_connection(self) -> bool:
        """Retry connection to Plex server."""
        if self._is_reconnecting:
            return False
            
        self._is_reconnecting = True
        self.connection_error.emit("Attempting to reconnect to Plex server...")
        
        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                if self.plex:
                    # Try to reconnect using existing credentials
                    self.plex = PlexServer(self.plex._baseurl, self.plex._token)
                    if self._check_connection():
                        self._is_reconnecting = False
                        self.connection_restored.emit()
                        return True
                time.sleep(RETRY_DELAY)
            except Exception as e:
                logger.error(f"Retry attempt {attempt + 1} failed: {e}")
                if attempt < MAX_RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY)
                    
        self._is_reconnecting = False
        self.connection_error.emit("Failed to reconnect to Plex server")
        return False

    def _start_connection_check(self) -> None:
        """Start periodic connection checking."""
        if self._connection_check_timer is None:
            self._connection_check_timer = QTimer()
            self._connection_check_timer.timeout.connect(self._check_connection_periodically)
            self._connection_check_timer.start(CONNECTION_CHECK_INTERVAL * 1000)  # Convert to milliseconds

    def _check_connection_periodically(self) -> None:
        """Periodically check connection and attempt to restore if needed."""
        current_time = time.time()
        if current_time - self._last_connection_check >= CONNECTION_CHECK_INTERVAL:
            self._last_connection_check = current_time
            if not self._check_connection():
                self._retry_connection()

    def _stop_connection_check(self) -> None:
        """Stop periodic connection checking."""
        if self._connection_check_timer:
            self._connection_check_timer.stop()
            self._connection_check_timer = None

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Handle media status changes."""
        logger.debug(f"Media status changed to: {status}")
        
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            logger.debug("Media loaded successfully")
            self._media_loaded = True
            self._playback_attempts = 0
            # Emit signal that playback is ready
            self.playback_started.emit()
            
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            logger.error("Invalid media")
            self._playback_error = True
            self.playback_failed.emit("Invalid media format")
            # Try next track
            self.play_next_track()
            
        elif status == QMediaPlayer.MediaStatus.LoadingMedia:
            logger.debug("Media is loading...")
            
        elif status == QMediaPlayer.MediaStatus.NoMedia:
            logger.debug("No media loaded")
            
        elif status == QMediaPlayer.MediaStatus.StalledMedia:
            logger.debug("Media playback stalled")
            # This can happen during buffering, no need to take action yet
            
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            logger.debug("Media is buffered")
            if not self._media_loaded:
                # If we haven't marked the media as loaded yet, do it now
                self._media_loaded = True
                self.playback_started.emit()

    def _start_playback_start_check(self) -> None:
        """Start checking if playback has actually started."""
        self._playback_start_timer.start(3000)  # Check after 3 seconds

    def _check_playback_start(self) -> None:
        """Check if playback has started and handle accordingly."""
        if not self._player:
            return

        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            logger.debug("Playback confirmed started")
            self.playback_started.emit()
            return

        logger.debug("Playback not started yet")
        self._playback_attempts += 1
        
        if self._playback_attempts < self._max_playback_attempts:
            logger.debug(f"Retrying playback (attempt {self._playback_attempts + 1})")
            # Store current track info before recreating player
            current_track = self.current_track
            current_index = self.current_playlist_index
            
            self._recreate_player()
            
            # Restore track info after player recreation
            self.current_track = current_track
            self.current_playlist_index = current_index
            
            # Try playing the same track again
            self._play_track_impl()
            # Give more time for the next attempt
            self._playback_start_timer.start(3000 + (self._playback_attempts * 1000))  # Increase wait time with each attempt
        else:
            logger.error("Max playback attempts reached")
            self.playback_failed.emit("Failed to start playback after multiple attempts")

    @pyqtSlot(result=int)
    def get_current_position(self) -> int:
        """Return the current playback position."""
        if self._player is None:
            return 0
        return self._player.position()

    @pyqtSlot(result=bool)
    def is_playing(self) -> bool:
        """Check if playback is active."""
        if self._player is None:
            return False
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    @pyqtSlot(object)
    def add_to_playlist(self, track: Track) -> None:
        """Add a track to the playlist"""
        self._playlist_lock.lock()
        try:
            # Check if track already exists
            track_exists = any(
                existing_track.ratingKey == track.ratingKey 
                for existing_track in self.playlist
            )
            
            if not track_exists:
                self.playlist.append(track)
                # Emit signal for UI update with a list containing the single track
                self.tracks_batch_loaded.emit([track])
                self.save_playlist()
        finally:
            self._playlist_lock.unlock()

    @pyqtSlot()
    def clear_playlist(self) -> None:
        """Clear the playlist."""
        if self._player:
            self._player.stop()  # Stop playback before clearing the playlist
        self.playlist.clear()
        self.current_playlist_index = -1
        if self.current_track and self._player:
            self._player.stop()
            self.current_track = None
            # Clear media center info
            if self.media_center:
                try:
                    self.media_center.clear_now_playing()
                except Exception as e:
                    logger.error(f"Error clearing media center: {e}")

    @pyqtSlot(list)
    def remove_from_playlist(self, indices: List[int]) -> None:
        """Remove tracks from the playlist."""
        indices = sorted(indices, reverse=True)
        for index in indices:
            self.playlist.pop(index)
        if self.current_playlist_index in indices:
            if self._player:
                self._player.stop()
            self.current_track = None
            self.current_playlist_index = -1
            if self.media_center:
                try:
                    self.media_center.clear_now_playing()
                except Exception as e:
                    logger.error(f"Error clearing media center: {e}")
        elif self.current_playlist_index > 0:
            self.current_playlist_index -= len([i for i in indices if i < self.current_playlist_index])

    @pyqtSlot()
    def shuffle_playlist(self) -> None:
        """Shuffle the playlist."""
        if not self.playlist:
            return
        
        # Save current track if any
        current_track = self.current_track
        current_index = self.current_playlist_index
        
        # Stop playback to ensure clean state
        if self._player:
            self._player.stop()
        
        # Shuffle the playlist
        random.shuffle(self.playlist)
        
        # Update current track and index
        if current_track and current_track in self.playlist:
            self.current_playlist_index = self.playlist.index(current_track)
            self.current_track = current_track
        elif self.playlist:
            # If current track is not in playlist anymore or no current track,
            # set to first track and ensure it's ready for playback
            self.current_playlist_index = 0
            self.current_track = self.playlist[0]
            # Ensure track has media information
            if isinstance(self.current_track, SavedTrack) and not self.current_track.media:
                try:
                    if self.plex:
                        refreshed_track = self.plex.fetchItem(self.current_track.ratingKey)
                        if refreshed_track:
                            self.current_track.media = refreshed_track.media
                            self.current_track._server = self.plex
                except Exception as e:
                    logger.error(f"Error refreshing track info after shuffle: {e}")
                    # If we can't refresh the track, move to the next one
                    if len(self.playlist) > 1:
                        self.playlist.pop(0)
                        self.current_track = self.playlist[0]
                        self.current_playlist_index = 0
        else:
            self.current_playlist_index = -1
            self.current_track = None
        
        # Reset player state
        if self._player:
            self._player.setSource(QUrl())
            self._player.setPosition(0)
        
        # Emit track changed signal to update UI
        self.track_changed.emit()
        
        # Update media center
        QTimer.singleShot(120, self._update_media_center)

    @pyqtSlot()
    def close(self) -> None:
        """Clean up resources."""
        try:
            # Stop connection checking
            self._stop_connection_check()
            
            # Stop playback
            if self._player:
                self._player.stop()
            
            # Clear playlist
            self.clear_playlist()
            
            # Save configuration
            self.save_config()
            
            logger.debug("Player closed successfully")
        except Exception as e:
            logger.error(f"Error during player cleanup: {e}")

    def _update_media_center(self) -> None:
        """Update media center information."""
        if not self.current_track or not self.media_center:
            return
        try:
            current_pos = self._player.position() if self._player else 0
            
            # If track is a SavedTrack, set the _server attribute
            if isinstance(self.current_track, SavedTrack) and not self.current_track._server:
                self.current_track._server = self.plex
            
            self.media_center.update_now_playing(
                self.current_track,
                self.is_playing(),
                current_pos
            )
        except Exception as e:
            # Log the error but continue silently
            logger.error(f"Error updating media center: {e}")

    def _recreate_player(self) -> bool:
        """Recreate the player and audio output."""
        logger.debug("Recreating player")
        try:
            # First, disconnect all signals
            if self._player:
                try:
                    self._player.positionChanged.disconnect()
                    self._player.durationChanged.disconnect()
                    self._player.playbackStateChanged.disconnect()
                    self._player.errorOccurred.disconnect()
                except Exception as e:
                    logger.error(f"DEBUG: Error disconnecting signals: {e}")
            
            if self._audio_output:
                try:
                    self._audio_output.deleteLater()
                except Exception as e:
                    logger.error(f"DEBUG: Error deleting old audio output: {e}")
            
            # Wait for objects to be deleted
            QThread.msleep(100)
            
            # Create new player and audio output
            self._player = QMediaPlayer(self)
            self._audio_output = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_output)
            
            # Connect signals
            self._player.positionChanged.connect(self._on_position_changed)
            self._player.durationChanged.connect(self._on_duration_changed)
            self._player.playbackStateChanged.connect(self._on_playback_state_changed)
            self._player.errorOccurred.connect(self._on_error_occurred)
            
            logger.debug("Player recreated successfully")
            return True
        except Exception as e:
            logger.error(f"ERROR in _recreate_player: {e}")
            logger.error(f"Stack trace: {traceback.format_exc()}")
            return False

class PlayerThread(QThread):
    player_ready = pyqtSignal(object)  # Signal to notify that the player is ready

    def __init__(self, parent=None):
        super().__init__(parent)
        self.player = None

    def run(self):
        # Create the Player object in this thread (so its children are created in the correct thread)
        self.player = Player()
        self.player.initialize_player()  # This initializes QMediaPlayer, etc.
        self.player_ready.emit(self.player)  # Notify main thread that player is ready
        self.exec()
