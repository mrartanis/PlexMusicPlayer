import os
import json
from typing import Optional, List, Tuple
from plexapi.server import PlexServer
from plexapi.audio import Track, Album, Artist
from plexapi.exceptions import NotFound
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QMediaFormat
from plex_music_player.lib.utils import load_cover_image
import pygame
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
        pygame.mixer.init()

        # Initialize macOS Media Center integration
        if sys.platform == 'darwin':
            self.media_center_delegate = MediaCenterDelegate.alloc().init()
            self.media_center_delegate.set_player(self)

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

    def download_track(self, track: Track) -> str:
        """Downloads the track completely before playing"""
        url = track.getStreamURL()
        response = requests.get(url, stream=True)
        response.raise_for_status()

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        with open(temp_file.name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        return temp_file.name

    def play_track(self, track_index: int) -> bool:
        """Plays the track at the given index"""
        if 0 <= track_index < len(self.playlist):
            self.current_playlist_index = track_index
            self.current_track = self.playlist[track_index]
            
            # Download track before playing
            track_path = self.download_track(self.current_track)
            self._player.setSource(QMediaFormat.fromLocalFile(track_path))
            self._player.play()
            self._update_media_center()
            return True
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
            current_pos = pygame.mixer.music.get_pos()
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
            stream_url = self.current_track.getStreamURL()
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                response = requests.get(stream_url, stream=True)
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                temp_file_path = temp_file.name

            pygame.mixer.music.stop()
            pygame.mixer.music.load(temp_file_path)
            pygame.mixer.music.play()
            
            # Update Media Center with a small delay to ensure playback has started
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self._update_media_center)
            
            # Emit track changed signal
            self.track_changed.emit()
            
            return True
        except Exception as e:
            print(f"Error playing track: {e}")
            return False

    def toggle_play(self) -> None:
        """Toggles play/pause state"""
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
        else:
            pygame.mixer.music.unpause()
        # Update Media Center with a small delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._update_media_center)

    def seek_position(self, position: int) -> None:
        """Seeks to specified position"""
        pygame.mixer.music.set_pos(position / 1000)
        self._update_media_center()

    def get_current_position(self) -> int:
        """Returns current playback position"""
        return pygame.mixer.music.get_pos()

    def is_playing(self) -> bool:
        """Checks if playback is active"""
        return pygame.mixer.music.get_busy()

    def add_to_playlist(self, track: Track) -> None:
        """Adds a track to the playlist"""
        self.playlist.append(track)

    def clear_playlist(self) -> None:
        """Clears the playlist"""
        self.playlist.clear()
        self.current_playlist_index = -1
        if self.current_track:
            pygame.mixer.music.stop()
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
            pygame.mixer.music.stop()
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
            return self._play_track_impl()
        elif self.current_album and self.tracks:
            current_index = self.tracks.index(self.current_track)
            if current_index < len(self.tracks) - 1:
                self.current_track = self.tracks[current_index + 1]
                return self._play_track_impl()
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
        pygame.mixer.quit()

    def _on_position_changed(self, position: int) -> None:
        """Handler for position change"""
        self.position_changed.emit(position)

    def _on_duration_changed(self, duration: int) -> None:
        """Handler for duration change"""
        self.duration_changed.emit(duration)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """Handler for playback state change"""
        is_playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.playback_state_changed.emit(is_playing)

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