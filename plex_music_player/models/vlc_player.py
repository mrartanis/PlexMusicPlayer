import vlc
import time
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QUrl, QThread, pyqtSlot
from plex_music_player.lib.logger import Logger

logger = Logger()

class VlcMediaPlayer(QObject):
    """VLC-based media player implementation that matches QMediaPlayer interface."""
    
    # Class variables for instance management
    _instances = []
    _vlc_instance = None  # Shared VLC instance
    
    class PlaybackState:
        """Playback states matching QMediaPlayer.PlaybackState"""
        StoppedState = 0
        PlayingState = 1
        PausedState = 2

    class MediaStatus:
        """Media status matching QMediaPlayer.MediaStatus"""
        UnknownMediaStatus = 0
        NoMedia = 1
        LoadingMedia = 2
        LoadedMedia = 3
        StalledMedia = 4
        BufferingMedia = 5
        BufferedMedia = 6
        EndOfMedia = 7
        InvalidMedia = 8

    class Error:
        """Error types matching QMediaPlayer.Error"""
        NoError = 0
        ResourceError = 1
        FormatError = 2
        NetworkError = 3
        AccessDeniedError = 4
    
    # Signals matching QMediaPlayer interface
    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(int)  # Using int to match QMediaPlayer.PlaybackState
    errorOccurred = pyqtSignal(int, str)  # Using int to match QMediaPlayer.Error
    mediaStatusChanged = pyqtSignal(int)  # Using int to match QMediaPlayer.MediaStatus
    volumeChanged = pyqtSignal(int)  # Signal for volume changes
    
    # Playback states matching QMediaPlayer.PlaybackState
    StoppedState = PlaybackState.StoppedState
    PlayingState = PlaybackState.PlayingState
    PausedState = PlaybackState.PausedState
    
    # Media status matching QMediaPlayer.MediaStatus
    UnknownMediaStatus = MediaStatus.UnknownMediaStatus
    NoMedia = MediaStatus.NoMedia
    LoadingMedia = MediaStatus.LoadingMedia
    LoadedMedia = MediaStatus.LoadedMedia
    StalledMedia = MediaStatus.StalledMedia
    BufferingMedia = MediaStatus.BufferingMedia
    BufferedMedia = MediaStatus.BufferedMedia
    EndOfMedia = MediaStatus.EndOfMedia
    InvalidMedia = MediaStatus.InvalidMedia
    
    # Error types matching QMediaPlayer.Error
    NoError = Error.NoError
    ResourceError = Error.ResourceError
    FormatError = Error.FormatError
    NetworkError = Error.NetworkError
    AccessDeniedError = Error.AccessDeniedError
    
    @classmethod
    def _get_vlc_instance(cls):
        """Get or create shared VLC instance."""
        if cls._vlc_instance is None:
            cls._vlc_instance = vlc.Instance()
        return cls._vlc_instance
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Store parent thread for later use
        self._parent_thread = parent.thread() if parent else QThread.currentThread()
        
        # Move to parent thread if needed
        if self.thread() != self._parent_thread:
            self.moveToThread(self._parent_thread)
            
        # Cleanup old instances in the correct thread
        for old_instance in self._instances:
            try:
                if hasattr(old_instance, '_player'):
                    old_instance._player.stop()
                    old_instance._player.release()
                if hasattr(old_instance, '_media') and old_instance._media:
                    old_instance._media.release()
            except Exception as e:
                logger.error(f"Error cleaning up old instance: {e}")
        self._instances.clear()
            
        # Use shared VLC instance
        self._instance = self._get_vlc_instance()
        
        # Initialize basic attributes
        self._media = None
        self._position = 0
        self._duration = 0
        self._playback_state = self.StoppedState
        self._media_status = self.NoMedia
        self._error = self.NoError
        self._error_string = ""
        self._audio_output = None
        self._volume = 100
        
        # Create player in the correct thread
        if QThread.currentThread() != self._parent_thread:
            from PyQt6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self, "_create_player", Qt.ConnectionType.BlockingQueuedConnection)
        else:
            self._create_player()
            
        # Add this instance to the list
        self._instances.append(self)
        
        # Setup event manager
        self._event_manager = self._player.event_manager()
        self._event_manager.event_attach(vlc.EventType.MediaPlayerTimeChanged, self._on_time_changed)
        self._event_manager.event_attach(vlc.EventType.MediaPlayerLengthChanged, self._on_length_changed)
        self._event_manager.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_playing)
        self._event_manager.event_attach(vlc.EventType.MediaPlayerPaused, self._on_paused)
        self._event_manager.event_attach(vlc.EventType.MediaPlayerStopped, self._on_stopped)
        self._event_manager.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_error)
        
        # Create timer in the correct thread
        self._position_timer = QTimer(self)
        self._position_timer.timeout.connect(self._update_position)
        self._position_timer.start(100)  # Update every 100ms
        
    @pyqtSlot()
    def _create_player(self) -> bool:
        """Create a new VLC player instance in the correct thread."""
        try:
            if not self._vlc_instance:
                self._vlc_instance = self._get_vlc_instance()
            
            # Create media player with caching options
            self._player = self._vlc_instance.media_player_new()
            
            # Set caching options
            self._player.set_rate(1.0)
            self._player.audio_set_volume(100)
            
            # Set network caching options
            self._player.set_network_caching(1000)  # 1 second network cache
            self._player.set_media_caching(1000)    # 1 second media cache
            
            # Set file caching options
            self._player.set_file_caching(1000)     # 1 second file cache
            
            # Set low latency options
            self._player.set_low_latency(True)
            
            # Set early start options
            self._player.set_early_start(True)
            
            # Set buffer size
            self._player.set_buffer_size(1000)      # 1 second buffer
            
            return True
        except Exception as e:
            logger.error(f"Error creating player: {e}")
            return False

    def __del__(self):
        """Cleanup when object is destroyed."""
        try:
            if self in self._instances:
                self._instances.remove(self)
            if hasattr(self, '_player'):
                # Ensure cleanup happens in the correct thread
                if QThread.currentThread() != self._parent_thread:
                    from PyQt6.QtCore import QMetaObject, Qt
                    QMetaObject.invokeMethod(self, "_cleanup_player", Qt.ConnectionType.BlockingQueuedConnection)
                else:
                    self._cleanup_player()
        except Exception as e:
            logger.error(f"Error in VlcMediaPlayer cleanup: {e}")

    @pyqtSlot()
    def _cleanup_player(self):
        """Cleanup player resources in the correct thread."""
        if hasattr(self, '_player'):
            self._player.stop()
            self._player.release()
        if hasattr(self, '_media') and self._media:
            self._media.release()
        
    def setAudioOutput(self, audio_output) -> None:
        """Set audio output device."""
        logger.debug("Setting audio output")
        self._audio_output = audio_output
        # VLC handles audio output internally, so we don't need to do anything else
        
    def setSource(self, url: QUrl) -> None:
        """Set the media source."""
        if not hasattr(self, '_instance') or not self._instance:
            self._error = self.ResourceError
            self._error_string = "VLC instance not initialized"
            self.errorOccurred.emit(self._error, self._error_string)
            return
            
        if url.isEmpty():
            self._media = None
            if hasattr(self, '_player') and self._player:
                self._player.set_media(None)
            self.mediaStatusChanged.emit(self.NoMedia)
            return
            
        self._media = self._instance.media_new(url.toString())
        if hasattr(self, '_player') and self._player:
            self._player.set_media(self._media)
        self.mediaStatusChanged.emit(self.LoadingMedia)
        
    def play(self) -> None:
        """Start playback."""
        if not hasattr(self, '_player') or not self._player:
            self._error = self.ResourceError
            self._error_string = "Player not initialized"
            self.errorOccurred.emit(self._error, self._error_string)
            return
            
        if self._player.play() == -1:
            self._error = self.ResourceError
            self._error_string = "Failed to start playback"
            self.errorOccurred.emit(self._error, self._error_string)
            return
            
        self._playback_state = self.PlayingState
        self.playbackStateChanged.emit(self._playback_state)
        
    def pause(self) -> None:
        """Pause playback."""
        if not hasattr(self, '_player') or not self._player:
            return
        self._player.pause()
        self._playback_state = self.PausedState
        self.playbackStateChanged.emit(self._playback_state)
        
    def stop(self) -> None:
        """Stop playback."""
        if not hasattr(self, '_player') or not self._player:
            return
        self._player.stop()
        self._playback_state = self.StoppedState
        self.playbackStateChanged.emit(self._playback_state)
        
    def setPosition(self, position: int) -> None:
        """Set playback position."""
        if not hasattr(self, '_player') or not self._player or not hasattr(self, '_media') or not self._media:
            return
        self._player.set_time(position)
        self._position = position
        self.positionChanged.emit(position)
        
    def position(self) -> int:
        """Get current playback position."""
        if not hasattr(self, '_player') or not self._player:
            return 0
        return self._player.get_time() or 0
        
    def duration(self) -> int:
        """Get media duration."""
        if not hasattr(self, '_player') or not self._player:
            return 0
        return self._player.get_length() or 0
        
    def playbackState(self) -> int:
        """Get current playback state."""
        return self._playback_state if hasattr(self, '_playback_state') else self.StoppedState
        
    def mediaStatus(self) -> int:
        """Get current media status."""
        return self._media_status if hasattr(self, '_media_status') else self.NoMedia
        
    def error(self) -> int:
        """Get last error."""
        return self.NoError
        
    def errorString(self) -> str:
        """Get last error string."""
        return ""
        
    def source(self) -> QUrl:
        """Get current media source."""
        if not hasattr(self, '_media') or not self._media:
            return QUrl()
        return QUrl(self._media.get_mrl())
        
    def volume(self) -> int:
        """Return the current volume level."""
        if not hasattr(self, '_player') or not self._player:
            return 0
        return self._player.audio_get_volume() or 0

    def setVolume(self, volume: int) -> None:
        """Set the volume level."""
        if not hasattr(self, '_player') or not self._player:
            return
        volume = max(0, min(100, volume))
        self._player.audio_set_volume(volume)
        self.volumeChanged.emit(volume)
        
    def _on_time_changed(self, event):
        """Handle time change events."""
        self._position = event.u.new_time
        self.positionChanged.emit(self._position)
        
    def _on_length_changed(self, event):
        """Handle length change events."""
        self._duration = event.u.new_length
        self.durationChanged.emit(self._duration)
        
    def _on_playing(self, event):
        """Handle playing events."""
        logger.debug("Playback started")
        self._playback_state = self.PlayingState
        self.playbackStateChanged.emit(self._playback_state)
        self._media_status = self.BufferedMedia
        self.mediaStatusChanged.emit(self._media_status)
        
    def _on_paused(self, event):
        """Handle pause events."""
        logger.debug("Playback paused")
        self._playback_state = self.PausedState
        self.playbackStateChanged.emit(self._playback_state)
        
    def _on_stopped(self, event):
        """Handle stop events."""
        logger.debug("Playback stopped")
        self._playback_state = self.StoppedState
        self.playbackStateChanged.emit(self._playback_state)
        
    def _on_error(self, event):
        """Handle error events."""
        logger.error("VLC playback error occurred")
        self._error = self.ResourceError
        self._error_string = "VLC playback error"
        self.errorOccurred.emit(self._error, self._error_string)
        
    def _update_position(self):
        """Update position periodically."""
        if self._playback_state == self.PlayingState:
            pos = self._player.get_time()
            if pos != self._position:
                self._position = pos
                self.positionChanged.emit(pos)

    @pyqtSlot()
    def _recreate_player(self) -> bool:
        """Recreate the VLC player instance."""
        try:
            if hasattr(self, '_player'):
                self._player.stop()
                self._player.release()
            self._create_player()
            return True
        except Exception as e:
            logger.error(f"Error recreating player: {e}")
            return False 