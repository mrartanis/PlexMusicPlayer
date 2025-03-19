import os
import json
from typing import Optional, List, Tuple
from plexapi.server import PlexServer
from plexapi.audio import Track, Album, Artist
from plexapi.exceptions import NotFound
from PyQt6.QtCore import QObject, pyqtSignal, QBuffer, QIODevice, QTimer
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from plex_music_player.lib.utils import load_cover_image
import tempfile
import requests
import random
import sys
from io import BytesIO


if sys.platform == 'darwin':
    from Foundation import NSObject, NSMutableDictionary
    from AppKit import NSImage
    import objc
    import MediaPlayer

    class MediaCenterDelegate(NSObject):
        def init(self):
            self = objc.super(MediaCenterDelegate, self).init()
            if self is None: return None
            
            # Initialize command center
            command_center = MediaPlayer.MPRemoteCommandCenter.sharedCommandCenter()
            
            # Get commands
            play_command = command_center.playCommand()
            pause_command = command_center.pauseCommand()
            toggle_command = command_center.togglePlayPauseCommand()
            next_command = command_center.nextTrackCommand()
            prev_command = command_center.previousTrackCommand()
            
            # Add handlers
            play_command.addTargetWithHandler_(self.handlePlayCommand_)
            pause_command.addTargetWithHandler_(self.handlePauseCommand_)
            toggle_command.addTargetWithHandler_(self.handleTogglePlayPauseCommand_)
            next_command.addTargetWithHandler_(self.handleNextTrackCommand_)
            prev_command.addTargetWithHandler_(self.handlePreviousTrackCommand_)
            
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

class Player(QObject):
    """Class for managing music playback"""
    
    # Signals for UI updates
    position_changed = pyqtSignal(int)
    duration_changed = pyqtSignal(int)
    playback_state_changed = pyqtSignal(bool)
    track_changed = pyqtSignal()  # New signal for track changes
    
    def __init__(self):
        super().__init__()
        
        # Initialize player
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._player.setAudioOutput(self._audio_output)
        
        # Connect signals
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.errorOccurred.connect(self._on_error_occurred)  # Connect errorOccurred signal
        
        # Initialize buffer
        self.buffer = QBuffer()
        
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
        self.auto_play: bool = True  # Enable auto-play by default

        # Initialize macOS Media Center integration
        if sys.platform == 'darwin':
            self.media_center_delegate = MediaCenterDelegate.alloc().init()
            self.media_center_delegate.set_player(self)

        # Last known position
        self._last_position = 0

    def connect(self, url: str, token: str) -> None:
        """Connects to Plex server"""
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

    def load_config(self) -> Optional[dict]:
        """Loads configuration from file and attempts to connect"""
        try:
            config_path = os.path.expanduser("~/.config/plex_music_player/config.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                    if 'plex' in config:
                        plex_config = config['plex']
                        self.connect(plex_config['url'], plex_config['token'])
                        return config
        except Exception as e:
            print(f"Error loading configuration: {e}")
        return None

    def load_artists(self) -> List[str]:
        """Loads list of artists"""
        if not self.plex:
            return []
        try:
            self.artists = self.plex.library.search(libtype="artist")
            return [artist.title for artist in self.artists]
        except Exception:
            return []

    def load_albums(self, artist_index: int) -> List[str]:
        """Loads list of albums for the artist"""
        if not self.plex or artist_index < 0 or artist_index >= len(self.artists):
            return []
        try:
            self.current_artist = self.artists[artist_index]
            self.albums = self.current_artist.albums()
            return [f"{album.title} ({album.year})" if hasattr(album, 'year') and album.year else album.title 
                   for album in self.albums]
        except Exception:
            return []

    def load_tracks(self, album_index: int) -> List[str]:
        """Loads list of tracks for the album"""
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

    def play_track(self, track_index: int) -> bool:
        """Plays a track"""
        if not self.plex or not self.current_album or track_index < 0 or track_index >= len(self.tracks):
            return False
        try:
            self.current_track = self.tracks[track_index]
            success = self._play_track_impl()
            if success:
                self._update_media_center()  # Update media center status when track is played
            return success
        except Exception:
            return False

    def _update_media_center(self) -> None:
        """Updates macOS Media Center info"""
        if not sys.platform == 'darwin' or not self.current_track:
            return

        try:
            info = NSMutableDictionary.alloc().init()
            
            # Set track info
            info[MediaPlayer.MPMediaItemPropertyTitle] = self.current_track.title
            info[MediaPlayer.MPMediaItemPropertyArtist] = self.current_track.grandparentTitle
            info[MediaPlayer.MPMediaItemPropertyAlbumTitle] = self.current_track.parentTitle
            
            # Set duration and position
            info[MediaPlayer.MPMediaItemPropertyPlaybackDuration] = float(self.current_track.duration) / 1000.0
            current_pos = self._player.position()
            if current_pos > 0:  # Only set if we have a valid position
                info[MediaPlayer.MPNowPlayingInfoPropertyElapsedPlaybackTime] = float(current_pos) / 1000.0
            
            # Set playback rate
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

            # Update Media Center
            self.media_center_delegate.update_now_playing(info)
        except Exception as e:
            print(f"Error updating Media Center: {e}")

    def _play_track_impl(self) -> bool:
        """Internal implementation of track playback"""
        try:
            # Stop playback before clearing the buffer
            if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self._player.stop()  # Stop playback if it's currently playing
            
            # Clear buffer before playing new track
            if self.buffer.isOpen():
                self.buffer.close()  # Close buffer if it's open
            self.buffer = QBuffer()  # Create a new buffer instance
            self.buffer.open(QIODevice.OpenModeFlag.ReadWrite)  # Open buffer for writing

            if self.current_track.media[0].container == 'mp3':
                print("Track is already in MP3 format, downloading without conversion.")
                media_key = self.current_track.media[0].parts[0].key
                token = self.current_track._server._token
                base_url = self.current_track._server.url(media_key)
                stream_url = f"{base_url}?download=1&X-Plex-Token={token}"
            else:
                print("Track is not in MP3 format, converting to MP3.")
                stream_url = self.current_track.getStreamURL(audioFormat='mp3')
            
            # Debug: Print detailed track information
            print(f"Track title: {self.current_track.title}")
            print(f"Track URL: {stream_url}")
            print(f"Track duration: {self.current_track.duration / 1000.0} seconds")  # Длительность в секундах
            
            # Загрузка трека в память с использованием потоковой загрузки
            response = requests.get(stream_url, stream=True)
            response.raise_for_status()
            
            # Чтение данных и запись в буфер "на ходу"
            for chunk in response.iter_content(chunk_size=1024):  # Чтение по 1 КБ
                if chunk:  # Если есть данные
                    self.buffer.write(chunk)
            
            if self.get_current_track_size() != self.buffer.size():
                print(f"Track size mismatch. Buffer size: {self.buffer.size()}, Track size: {self.get_current_track_size()}")
                print(f"Track URL: {stream_url}")
            
            self.buffer.seek(0)
            self._player.setSourceDevice(self.buffer)
            
            print("Starting playback...")
            self._player.play()
            return True
        except Exception as e:
            print(f"Error playing track: {e}")
            return False

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Handles media status changes"""
        print(f"Media status changed: {status}")  # Debug: Print media status
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Auto-play next track if enabled
            if self.auto_play:
                print("Playing next track...")
                if not self.play_next_track():
                    print("No more tracks to play.")  # Debug: No more tracks
                else:
                    print("Next track started.")  # Debug: Next track started

    def toggle_play(self) -> None:
        """Toggles play/pause state"""
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.playback_state_changed.emit(False)
        else:
            self._player.play()
            self.playback_state_changed.emit(True)
        # Update Media Center with a small delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._update_media_center)

    def seek_position(self, position: int) -> None:
        """Seeks to specified position"""
        self._player.setPosition(position)
        self._update_media_center()

    def get_current_position(self) -> int:
        """Returns current playback position"""
        return self._player.position()

    def is_playing(self) -> bool:
        """Checks if playback is active"""
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def add_to_playlist(self, track: Track) -> None:
        """Adds a track to the playlist"""
        self.playlist.append(track)

    def clear_playlist(self) -> None:
        """Clears the playlist"""
        self._player.stop()  # Stop playback before clearing the playlist
        self.playlist.clear()
        self.current_playlist_index = -1
        if self.current_track:
            self._player.stop()
            self.current_track = None
            # Clear Media Center
            if sys.platform == 'darwin':
                try:
                    MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
                except Exception as e:
                    print(f"Error clearing Media Center: {e}")

    def remove_from_playlist(self, indices: List[int]) -> None:
        """Removes tracks from playlist"""
        # Sort indices in descending order to remove from end
        indices = sorted(indices, reverse=True)
        
        # Remove elements from list
        for index in indices:
            self.playlist.pop(index)

        # If current track was removed, stop playback
        if self.current_playlist_index in indices:
            self._player.stop()
            self.current_track = None
            self.current_playlist_index = -1
            # Clear Media Center
            if sys.platform == 'darwin':
                try:
                    MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
                except Exception as e:
                    print(f"Error clearing Media Center: {e}")
        # If tracks before current were removed, adjust index
        elif self.current_playlist_index > 0:
            self.current_playlist_index -= len([i for i in indices if i < self.current_playlist_index])

    def shuffle_playlist(self) -> None:
        """Shuffles the playlist"""
        random.shuffle(self.playlist)

    def play_next_track(self) -> bool:
        """Plays next track"""
        if self.current_playlist_index >= 0 and self.current_playlist_index < len(self.playlist) - 1:
            self.current_playlist_index += 1
            self.current_track = self.playlist[self.current_playlist_index]
            self._player.stop()  # Stop playback before playing the next track
            success = self._play_track_impl()
            if success:
                # Notify the main window to update the playlist selection
                self.track_changed.emit()  # Emit signal to update UI
            return success
        elif self.current_album and self.tracks:
            current_index = self.tracks.index(self.current_track)
            if current_index < len(self.tracks) - 1:
                self.current_track = self.tracks[current_index + 1]
                self._player.stop()  # Stop playback before playing the next track
                success = self._play_track_impl()
                if success:
                    # Notify the main window to update the playlist selection
                    self.track_changed.emit()  # Emit signal to update UI
                return success
        return False

    def play_previous_track(self) -> bool:
        """Plays previous track"""
        if self.current_playlist_index > 0:
            self.current_playlist_index -= 1
            self.current_track = self.playlist[self.current_playlist_index]
            return self._play_track_impl()
        elif self.current_album and self.tracks:
            current_index = self.tracks.index(self.current_track)
            if current_index > 0:
                self.current_track = self.tracks[current_index - 1]
                return self._play_track_impl()
        return False

    def close(self) -> None:
        """Closes the player"""
        self._player.stop()

    def _on_position_changed(self, position: int) -> None:
        """Handler for position change"""
        # Update position only if it has changed significantly
        if abs(position - self._last_position) > 1000:  # Update if change is more than 1 second
            self.position_changed.emit(position)
            self._last_position = position

    def _on_duration_changed(self, duration: int) -> None:
        """Handler for duration change"""
        self.duration_changed.emit(duration)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """Handler for playback state change"""
        print(f"Playback state changed: {state}")  # Debug: Print playback state change
        if state == QMediaPlayer.PlaybackState.StoppedState:
            current_pos = self.get_current_position()
            track_duration = self.current_track.duration / 1000.0  # Duration in seconds
            
            # If current position is close to the track duration (e.g., 1 second)
            if current_pos >= track_duration - 1:  # 1 second before the end
                print("Track is nearing its end, playing next track...")
                if self.auto_play:
                    if not self.play_next_track():
                        print("No more tracks to play.")  # Debug: No more tracks
                    else:
                        print("Next track started.")  # Debug: Next track started
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        print(f"Player state: {'Playing' if is_playing else 'Paused/Stopped'}")  # Состояние плеера
        self.playback_state_changed.emit(is_playing)

    def _on_error_occurred(self, error: QMediaPlayer.Error, error_string: str) -> None:
        """Handles media player errors"""
        print(f"Media player error: {error}, {error_string}")  # Debug: Print error information
        if error != QMediaPlayer.Error.NoError:
            print("An error occurred during playback.")  # Debug: Error occurred

    def save_config(self) -> None:
        """Saves configuration to file"""
        try:
            config_dir = os.path.expanduser("~/.config/plex_music_player")
            os.makedirs(config_dir, exist_ok=True)
            config_path = os.path.join(config_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump(self.config, f)
        except Exception as e:
            print(f"Error saving configuration: {e}")

    def save_playlist(self) -> None:
        """Saves playlist to file"""
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

    def load_playlist(self) -> None:
        """Loads playlist from file"""
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
                    # Поиск трека в библиотеке Plex
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
                
        except Exception as e:
            print(f"Error loading playlist: {e}")

    def add_tracks_batch(self, tracks):
        """Batch adds tracks to playlist"""
        self.playlist.extend(tracks)

    def set_auto_play(self, enabled: bool) -> None:
        """Sets auto-play state"""
        self.auto_play = enabled

    def is_auto_play_enabled(self) -> bool:
        """Returns auto-play state"""
        return self.auto_play

    def config(self) -> dict:
        """Returns player configuration"""
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

    def update_progress(self) -> None:
        """Updates playback progress"""
        if self.player.is_playing() and self.player.current_track:
            current_pos = self.player.get_current_position()
            print(f"Current position: {current_pos}")  # Debug: Print current position
            print(f"Player state: {self._player.playbackState()}")  # Debug: Print player state
            print(f"Buffer size: {self.buffer.size()} bytes")  # Debug: Print buffer size
            self.progress_slider.setValue(current_pos)
            self.update_time_label(current_pos, self.player.current_track.duration)
            
            # Check if track has ended
            if current_pos >= self.player.current_track.duration:
                print("Track ended, playing next track...")  # Debug: Track ended
                self.play_next_track()
        else:
            if self.player.current_track and self.progress_slider.value() >= self.player.current_track.duration:
                print("Track ended, playing next track...")  # Debug: Track ended
                self.play_next_track() 

    def get_current_track_size(self) -> Optional[int]:
        """Возвращает размер текущего трека в байтах."""
        if not self.current_track or not self.current_track.media or not self.current_track.media[0].parts:
            return None
        
        try:
            # Получаем URL потока
            media_key = self.current_track.media[0].parts[0].key
            token = self.current_track._server._token
            base_url = self.current_track._server.url(media_key)
            stream_url = f"{base_url}?download=1&X-Plex-Token={token}"
            
            # Выполняем HEAD-запрос для получения заголовков
            response = requests.head(stream_url)
            if response.status_code == 200:
                # Получаем размер из заголовка Content-Length
                return int(response.headers.get('Content-Length', 0))
            else:
                print(f"Ошибка при получении размера трека: {response.status_code}")
                return None
        except Exception as e:
            print(f"Ошибка при получении размера трека: {e}")
            return None 