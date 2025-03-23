import sys
from typing import Any, Optional
from plexapi.audio import Track
from plex_music_player.lib.media_center import MediaCenterInterface
import os
from PyQt6.QtCore import QObject
from plex_music_player.models.player import Player

if sys.platform == 'darwin':
    from Foundation import NSObject, NSMutableDictionary, NSTimer
    from AppKit import NSImage
    import objc
    import MediaPlayer

    class MediaCenterDelegate(NSObject):
        def init(self):
            self = objc.super(MediaCenterDelegate, self).init()
            if self is None:
                return None
            
            self._last_position = 0
            self.player = None
            
            # Initialize command center
            command_center = MediaPlayer.MPRemoteCommandCenter.sharedCommandCenter()
            
            # Get commands
            play_command = command_center.playCommand()
            pause_command = command_center.pauseCommand()
            toggle_command = command_center.togglePlayPauseCommand()
            next_command = command_center.nextTrackCommand()
            prev_command = command_center.previousTrackCommand()
            change_playback_position_command = command_center.changePlaybackPositionCommand()
            
            # Enable all commands
            play_command.setEnabled_(True)
            pause_command.setEnabled_(True)
            toggle_command.setEnabled_(True)
            next_command.setEnabled_(True)
            prev_command.setEnabled_(True)
            change_playback_position_command.setEnabled_(True)
            
            # Add handlers
            play_command.addTargetWithHandler_(self.handlePlayCommand_)
            pause_command.addTargetWithHandler_(self.handlePauseCommand_)
            toggle_command.addTargetWithHandler_(self.handleTogglePlayPauseCommand_)
            next_command.addTargetWithHandler_(self.handleNextTrackCommand_)
            prev_command.addTargetWithHandler_(self.handlePreviousTrackCommand_)
            change_playback_position_command.addTargetWithHandler_(self.handleSeekCommand_)
            
            # Start update timer
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0,  # interval in seconds
                self,  # target
                objc.selector(self._update_media_center, signature=b'v@:'),  # selector
                None,  # userInfo
                True  # repeats
            )
            
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
            
        def handleSeekCommand_(self, event):
            new_position = event.positionTime()
            if self.player:
                self.player.seek_position(int(new_position * 1000))  # Convert to milliseconds
            return 1  # MPRemoteCommandHandlerStatusSuccess

        def _update_media_center(self) -> None:
            """Update the media center with current track information."""
            if not self.player or not self.player.current_track:
                return
                
            try:
                track = self.player.current_track
                is_playing = self.player.is_playing()
                position = self.player.position()
                
                # Only update if position changed significantly
                if abs(position - self._last_position) > 500:  # More than 0.5 second difference
                    self._last_position = position
                    self.update_now_playing(track, is_playing, position)
                    
            except Exception as e:
                print(f"Error updating media center: {e}")
                
        @objc.python_method
        def update_now_playing(self, track: Track, is_playing: bool, position: int) -> None:
            """Update the now playing information in macOS media center."""
            try:
                info = NSMutableDictionary.alloc().init()
                
                # Set basic track information
                info.setObject_forKey_(track.title, MediaPlayer.MPMediaItemPropertyTitle)
                info.setObject_forKey_(track.grandparentTitle, MediaPlayer.MPMediaItemPropertyArtist)
                info.setObject_forKey_(track.parentTitle, MediaPlayer.MPMediaItemPropertyAlbumTitle)
                info.setObject_forKey_(track.duration / 1000.0, MediaPlayer.MPMediaItemPropertyPlaybackDuration)
                info.setObject_forKey_(position / 1000.0, MediaPlayer.MPNowPlayingInfoPropertyElapsedPlaybackTime)
                
                # Set playback rate (1.0 for playing, 0.0 for paused)
                playback_rate = 1.0 if is_playing else 0.0
                info.setObject_forKey_(playback_rate, MediaPlayer.MPNowPlayingInfoPropertyPlaybackRate)
                
                # Set album artwork if available
                if hasattr(track, 'thumb') and track.thumb:
                    try:
                        response = track._server.url(track.thumb)
                        image_data = track._server._session.get(response).content
                        image = NSImage.alloc().initWithData_(image_data)
                        if image:
                            artwork = MediaPlayer.MPMediaItemArtwork.alloc().initWithImage_(image)
                            info.setObject_forKey_(artwork, MediaPlayer.MPMediaItemPropertyArtwork)
                    except Exception as e:
                        print(f"Error setting album artwork: {e}")
                
                # Update Now Playing info
                MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(info)
                
            except Exception as e:
                print(f"Error updating Now Playing info: {e}")
                
        @objc.python_method
        def clear_now_playing(self) -> None:
            """Clear the now playing information."""
            try:
                MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
            except Exception as e:
                print(f"Error clearing Now Playing info: {e}")

class MacOSMediaCenter(MediaCenterInterface):
    """Media center integration for macOS."""
    
    def __init__(self):
        self.player: Optional[Player] = None
        self.delegate: Optional[MediaCenterDelegate] = None

    def initialize(self) -> None:
        """Initialize the media center integration."""
        if sys.platform == 'darwin':
            self.delegate = MediaCenterDelegate.alloc().init()
    
    def set_player(self, player: Player) -> None:
        """Set the player instance."""
        self.player = player
        if self.delegate:
            self.delegate.set_player(player)
    
    def clear_now_playing(self) -> None:
        """Clear the now playing information."""
        if self.delegate:
            self.delegate.clear_now_playing()

    def update_now_playing(self, track: Track, is_playing: bool, position: int) -> None:
        """Update the now playing information in the media center."""
        if self.delegate:
            self.delegate.update_now_playing(track, is_playing, position) 