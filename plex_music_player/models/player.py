import os
import json
from typing import Optional, List
from plexapi.server import PlexServer
from plexapi.audio import Track, Album, Artist
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QUrl, QThread, pyqtSlot
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
import tempfile
import requests
import random
import sys

if sys.platform == 'darwin':
    from Foundation import NSObject, NSMutableDictionary
    from AppKit import NSImage
    import objc
    import MediaPlayer

    class MediaCenterDelegate(NSObject):
        def init(self):
            self = objc.super(MediaCenterDelegate, self).init()
            if self is None:
                return None
            
            # Initialize command center
            command_center = MediaPlayer.MPRemoteCommandCenter.sharedCommandCenter()
            
            # Get commands
            play_command = command_center.playCommand()
            pause_command = command_center.pauseCommand()
            toggle_command = command_center.togglePlayPauseCommand()
            next_command = command_center.nextTrackCommand()
            prev_command = command_center.previousTrackCommand()
            change_playback_position_command = command_center.changePlaybackPositionCommand()
            
            # Add handlers
            play_command.addTargetWithHandler_(self.handlePlayCommand_)
            pause_command.addTargetWithHandler_(self.handlePauseCommand_)
            toggle_command.addTargetWithHandler_(self.handleTogglePlayPauseCommand_)
            next_command.addTargetWithHandler_(self.handleNextTrackCommand_)
            prev_command.addTargetWithHandler_(self.handlePreviousTrackCommand_)
            change_playback_position_command.addTargetWithHandler_(self.handleSeekCommand_)
            
            return self
            
        @objc.python_method
        def set_player(self, player):
            self.player = player
            
        def handlePlayCommand_(self, event):
            if not self.player.is_playing():
                self.player.toggle_play()
            return 1  # MPRemoteCommandHandlerStatusSuccess
            
        def handlePauseCommand_(self, event):
            if self.player.is_playing():
                self.player.toggle_play()
            return 1  # MPRemoteCommandHandlerStatusSuccess
            
        def handleTogglePlayPauseCommand_(self, event):
            self.player.toggle_play()
            return 1  # MPRemoteCommandHandlerStatusSuccess
            
        def handleNextTrackCommand_(self, event):
            self.player.play_next_track()
            return 1  # MPRemoteCommandHandlerStatusSuccess
            
        def handlePreviousTrackCommand_(self, event):
            self.player.play_previous_track()
            return 1  # MPRemoteCommandHandlerStatusSuccess

        @objc.python_method
        def update_now_playing(self, info_dict):
            try:
                MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(info_dict)
            except Exception as e:
                print(f"Error updating Now Playing: {e}")

        def handleSeekCommand_(self, event):
            new_position = event.positionTime()
            if self.player:
                self.player.seek_position(int(new_position * 1000))  # Convert to milliseconds
            return 1  # MPRemoteCommandHandlerStatusSuccess

class Player(QObject):
    """Class for managing music playback in a separate thread."""
    
    # Signals for UI updates
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    playback_state_changed = pyqtSignal(bool)
    track_changed = pyqtSignal()  # Signal for track changes
    
    def __init__(self):
        super().__init__()
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

        # Initialize macOS Media Center integration if on macOS
        if sys.platform == 'darwin':
            self.media_center_delegate = MediaCenterDelegate.alloc().init()
            self.media_center_delegate.set_player(self)

        # Last known position
        self._last_position = 0

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
        print("Player initialized in thread:", QThread.currentThread())

    @pyqtSlot(str, str)
    def connect_server(self, url: str, token: str) -> None:
        """Connect to the Plex server."""
        try:
            self.plex = PlexServer(url, token)
            # Save credentials to config on successful connection
            config_dir = os.path.expanduser("~/.config/plex_music_player")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "config.json")
            
            config = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r") as f:
                        config = json.load(f)
                except:
                    pass
                
            config['plex'] = {
                'url': url,
                'token': token
            }
            
            with open(config_path, "w") as f:
                json.dump(config, f)
            
        except Exception as e:
            self.plex = None
            raise e

    @pyqtSlot(result=dict)
    def load_config(self) -> Optional[dict]:
        """Load configuration from file and attempt to connect."""
        try:
            config_path = os.path.expanduser("~/.config/plex_music_player/config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                    if 'plex' in config:
                        plex_config = config['plex']
                        self.connect_server(plex_config['url'], plex_config['token'])
                        return config
        except Exception as e:
            print(f"Error loading configuration: {e}")
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
        """Form the URL for the track stream."""
        if self.current_track.media[0].container == 'mp3':
            print("Track is already in MP3 format, downloading without conversion.")
            media_key = self.current_track.media[0].parts[0].key
            token = self.current_track._server._token
            base_url = self.current_track._server.url(media_key)
            return f"{base_url}?download=1&X-Plex-Token={token}"
        else:
            print("Track is not in MP3 format, converting to MP3.")
            return self.current_track.getStreamURL(audioFormat='mp3')

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """Handle playback state changes safely."""
        print(f"Playback state changed: {state}")
        if state == QMediaPlayer.PlaybackState.StoppedState:
            current_pos = self.get_current_position()
            # Check if current_track exists before accessing its duration
            if self.current_track:
                track_duration = self.current_track.duration / 1000.0  # Duration in seconds
                if current_pos >= track_duration - 1:
                    print("Track is nearing its end, playing next track...")
                    if self.auto_play:
                        if not self.play_next_track():
                            print("No more tracks to play.")
                        else:
                            print("Next track started.")
            else:
                print("No current track available.")
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        print(f"Player state: {'Playing' if is_playing else 'Paused/Stopped'}")
        self.playback_state_changed.emit(is_playing)
        QTimer.singleShot(100, self._update_media_center)

    def _on_position_changed(self, position: int) -> None:
        """Handle position changes."""
        if abs(position - self._last_position) > 1000:  # Update if change is more than 1 second
            self.position_changed.emit(position)
            self._last_position = position
            QTimer.singleShot(0, self._update_media_center)

    def _on_duration_changed(self, duration: int) -> None:
        """Handle duration changes."""
        self.duration_changed.emit(duration)

    def _on_error_occurred(self, error: QMediaPlayer.Error, error_string: str) -> None:
        """Handle media player errors."""
        print(f"Media player error: {error}, {error_string}")
        if error != QMediaPlayer.Error.NoError:
            print("An error occurred during playback.")

    @pyqtSlot()
    def toggle_play(self) -> None:
        """Toggle play/pause state."""
        if self._player is None:
            print("Player not initialized!")
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.playback_state_changed.emit(False)
        else:
            self._player.play()
            self.playback_state_changed.emit(True)
        QTimer.singleShot(100, self._update_media_center)

    @pyqtSlot(int)
    def seek_position(self, position: int) -> None:
        """Seek to the specified position."""
        if self._player is None:
            print("Player not initialized!")
            return
        self._player.setPosition(position)
        self._update_media_center()

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
        """Add a track to the playlist."""
        self.playlist.append(track)

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
            # Clear Media Center info on macOS
            if sys.platform == 'darwin':
                try:
                    MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
                except Exception as e:
                    print(f"Error clearing Media Center: {e}")

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
            if sys.platform == 'darwin':
                try:
                    MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
                except Exception as e:
                    print(f"Error clearing Media Center: {e}")
        elif self.current_playlist_index > 0:
            self.current_playlist_index -= len([i for i in indices if i < self.current_playlist_index])

    @pyqtSlot()
    def shuffle_playlist(self) -> None:
        """Shuffle the playlist."""
        random.shuffle(self.playlist)

    @pyqtSlot(result=bool)
    def play_next_track(self) -> bool:
        """Play the next track."""
        if self.current_playlist_index >= 0 and self.current_playlist_index < len(self.playlist) - 1:
            self.current_playlist_index += 1
            self.current_track = self.playlist[self.current_playlist_index]
            if self._player:
                self._player.stop()
            success = self._play_track_impl()
            if success:
                self.track_changed.emit()
                QTimer.singleShot(120, self._update_media_center)
            return success
        elif self.current_album and self.tracks:
            current_index = self.tracks.index(self.current_track)
            if current_index < len(self.tracks) - 1:
                self.current_track = self.tracks[current_index + 1]
                if self._player:
                    self._player.stop()
                success = self._play_track_impl()
                if success:
                    self.track_changed.emit()
                    QTimer.singleShot(120, self._update_media_center)
                return success
        return False

    @pyqtSlot(result=bool)
    def play_previous_track(self) -> bool:
        """Play the previous track."""
        if self.current_playlist_index > 0:
            self.current_playlist_index -= 1
            self.current_track = self.playlist[self.current_playlist_index]
            success = self._play_track_impl()
            if success:
                self._update_media_center()
                return success
        elif self.current_album and self.tracks:
            current_index = self.tracks.index(self.current_track)
            if current_index > 0:
                self.current_track = self.tracks[current_index - 1]
                success = self._play_track_impl()
                if success:
                    QTimer.singleShot(120, self._update_media_center)
                    return success
        return False

    @pyqtSlot()
    def close(self) -> None:
        """Close the player."""
        if self._player:
            self._player.stop()

    def _update_media_center(self) -> None:
        """Update macOS Media Center information."""
        if not sys.platform == 'darwin' or not self.current_track:
            return
        try:
            info = NSMutableDictionary.alloc().init()
            
            # Set track information
            info[MediaPlayer.MPMediaItemPropertyTitle] = self.current_track.title
            info[MediaPlayer.MPMediaItemPropertyArtist] = self.current_track.grandparentTitle
            info[MediaPlayer.MPMediaItemPropertyAlbumTitle] = self.current_track.parentTitle
            info[MediaPlayer.MPMediaItemPropertyPlaybackDuration] = float(self.current_track.duration) / 1000.0
            current_pos = self._player.position() if self._player else 0
            if current_pos > 0:
                info[MediaPlayer.MPNowPlayingInfoPropertyElapsedPlaybackTime] = float(current_pos) / 1000.0
            info[MediaPlayer.MPNowPlayingInfoPropertyPlaybackRate] = 1.0 if self.is_playing() else 0.0
            
            # Try to add artwork
            if hasattr(self.current_track, 'thumb') and self.plex:
                try:
                    thumb_url = self.plex.url(self.current_track.thumb)
                    response = requests.get(thumb_url, headers={'X-Plex-Token': self.plex._token})
                    if response.status_code == 200:
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                            temp_file.write(response.content)
                            image = NSImage.alloc().initWithContentsOfFile_(temp_file.name)
                            if image:
                                artwork = MediaPlayer.MPMediaItemArtwork.alloc().initWithImage_(image)
                                info[MediaPlayer.MPMediaItemPropertyArtwork] = artwork
                            os.unlink(temp_file.name)
                except Exception as e:
                    print(f"Error setting artwork: {e}")
            self.media_center_delegate.update_now_playing(info)
        except Exception as e:
            print(f"Error updating Media Center: {e}")

    def _play_track_impl(self) -> bool:
        """Internal implementation of track playback."""
        if self._player is None:
            print("Player not initialized!")
            return False
        try:
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._player.stop()
            stream_url = self.get_stream_url()
            print(f"Track URL: {stream_url}")
            self._player.setSource(QUrl(stream_url))
            print("Starting playback...")
            self._player.play()
            QTimer.singleShot(120, self._update_media_center)
            return True
        except Exception as e:
            print(f"Error playing track: {e}")
            return False

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Handle media status changes."""
        print(f"Media status changed: {status}")
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.auto_play:
                print("Playing next track...")
                if not self.play_next_track():
                    print("No more tracks to play.")
                else:
                    print("Next track started.")

    @pyqtSlot()
    def save_config(self) -> None:
        """Save configuration to file."""
        try:
            config_dir = os.path.expanduser("~/.config/plex_music_player")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump(self.config(), f)
        except Exception as e:
            print(f"Error saving configuration: {e}")

    @pyqtSlot()
    def save_playlist(self) -> None:
        """Save the playlist to file."""
        try:
            config_dir = os.path.expanduser("~/.config/plex_music_player")
            os.makedirs(config_dir, exist_ok=True)
            playlist_path = os.path.join(config_dir, "playlist.json")
            
            playlist_data = []
            for track in self.playlist:
                track_data = {
                    'title': track.title,
                    'artist': track.grandparentTitle,
                    'album': track.parentTitle,
                    'year': track.year if hasattr(track, 'year') else None,
                    'key': track.key,
                    'ratingKey': track.ratingKey
                }
                playlist_data.append(track_data)
            
            with open(playlist_path, "w") as f:
                json.dump({
                    'playlist': playlist_data,
                    'current_index': self.current_playlist_index
                }, f)
        except Exception as e:
            print(f"Error saving playlist: {e}")

    @pyqtSlot()
    def load_playlist(self) -> None:
        """Load the playlist from file."""
        try:
            playlist_path = os.path.expanduser("~/.config/plex_music_player/playlist.json")
            if not os.path.exists(playlist_path):
                return
                
            with open(playlist_path, "r") as f:
                data = json.load(f)
                
            if not self.plex:
                return
                
            self.playlist.clear()
            for track_data in data['playlist']:
                try:
                    results = self.plex.library.search(track_data['title'], libtype="track")
                    for track in results:
                        if (track.grandparentTitle == track_data['artist'] and 
                            track.parentTitle == track_data['album'] and
                            track.key == track_data['key']):
                            self.playlist.append(track)
                            break
                except Exception as e:
                    print(f"Error loading track {track_data['title']}: {e}")
                    continue
            
            self.current_playlist_index = data.get('current_index', -1)
            if 0 <= self.current_playlist_index < len(self.playlist):
                self.current_track = self.playlist[self.current_playlist_index]
            self.playback_state_changed.emit(True)
        except Exception as e:
            print(f"Error loading playlist: {e}")

    @pyqtSlot(object)
    def add_tracks_batch(self, tracks) -> None:
        """Batch-add tracks to the playlist."""
        self.playlist.extend(tracks)

    @pyqtSlot(bool)
    def set_auto_play(self, enabled: bool) -> None:
        """Set the auto-play state."""
        self.auto_play = enabled

    @pyqtSlot(result=bool)
    def is_auto_play_enabled(self) -> bool:
        """Return whether auto-play is enabled."""
        return self.auto_play

    @pyqtSlot(result=dict)
    def config(self) -> dict:
        """Return the player configuration."""
        return {
            'plex': {
                'url': self.plex.url if self.plex else None,
                'token': self.plex.token if self.plex else None
            },
            'current_track': self.current_track.title if self.current_track else None,
            'current_album': self.current_album.title if self.current_album else None,
            'current_artist': self.current_artist.title if self.current_artist else None,
            'artists': [artist.title for artist in self.artists],
            'albums': [album.title for album in self.albums],
            'tracks': [track.title for track in self.tracks],
            'playlist': [track.title for track in self.playlist],
            'current_playlist_index': self.current_playlist_index,
            'is_playing': self.is_playing(),
            'auto_play': self.auto_play
        }

    @pyqtSlot()
    def update_progress(self) -> None:
        """Update playback progress."""
        if self.is_playing() and self.current_track:
            current_pos = self.get_current_position()
            print(f"Current position: {current_pos}")
            print(f"Player state: {self._player.playbackState() if self._player else 'Not initialized'}")
            # Here, it is assumed that UI elements (e.g., progress_slider, update_time_label)
            # are defined elsewhere in the UI code – existing logic is preserved.
            if current_pos >= self.current_track.duration:
                print("Track ended, playing next track...")
                self.play_next_track()
        else:
            # Placeholder for additional UI update logic if needed
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
                print(f"Error getting track size: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error getting track size: {e}")
            return None

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
