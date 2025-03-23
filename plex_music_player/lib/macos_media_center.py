import sys
from typing import Any, Optional
from plexapi.audio import Track
from plex_music_player.lib.media_center import MediaCenterInterface
import os
import subprocess
from PySide6.QtCore import QObject, QTimer
from plex_music_player.models.track import Track
from plex_music_player.models.player import Player

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

    class MacOSMediaCenter(MediaCenterInterface):
        def __init__(self):
            self.delegate = None
            self.player = None
            
        def initialize(self) -> None:
            """Initialize the macOS media center integration."""
            self.delegate = MediaCenterDelegate.alloc().init()
            
        def update_now_playing(self, track: Track, is_playing: bool, position: int) -> None:
            """Update the now playing information in macOS media center."""
            if not self.delegate:
                return
                
            try:
                info = NSMutableDictionary.alloc().init()
                info.setObject_forKey_(track.title, MediaPlayer.MPMediaItemPropertyTitle)
                info.setObject_forKey_(track.grandparentTitle, MediaPlayer.MPMediaItemPropertyArtist)
                info.setObject_forKey_(track.parentTitle, MediaPlayer.MPMediaItemPropertyAlbumTitle)
                info.setObject_forKey_(track.duration, MediaPlayer.MPMediaItemPropertyPlaybackDuration)
                info.setObject_forKey_(position / 1000.0, MediaPlayer.MPNowPlayingInfoPropertyElapsedPlaybackTime)
                
                # Set playback rate
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
                
                MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(info)
            except Exception as e:
                print(f"Error updating media center: {e}")
                
        def clear_now_playing(self) -> None:
            """Clear the now playing information from macOS media center."""
            if self.delegate:
                try:
                    MediaPlayer.MPNowPlayingInfoCenter.defaultCenter().setNowPlayingInfo_(None)
                except Exception as e:
                    print(f"Error clearing media center: {e}")
                    
        def set_player(self, player: Any) -> None:
            """Set the player instance that will handle media control commands."""
            self.player = player
            if self.delegate:
                self.delegate.set_player(player)

class MediaCenterDelegate(QObject):
    """Delegate for handling media center updates on macOS."""
    
    def __init__(self, player: Player):
        super().__init__()
        self.player = player
        self._last_position = 0
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_media_center)
        self._update_timer.start(5000)  # Update every 5 seconds
        
    def _update_media_center(self) -> None:
        """Update the media center with current track information."""
        if not self.player or not self.player.current_track:
            return
            
        try:
            track = self.player.current_track
            is_playing = self.player.is_playing()
            position = self.player.position()
            
            # Only update if position changed significantly
            if abs(position - self._last_position) > 1000:  # More than 1 second difference
                self._last_position = position
                
                # Update Now Playing info
                self._update_now_playing(track, is_playing, position)
                
        except Exception:
            # Silently continue after any error
            pass
            
    def _update_now_playing(self, track: Track, is_playing: bool, position: int) -> None:
        """Update the now playing information in macOS media center."""
        try:
            # Get the stream URL from the player
            if hasattr(self.player, '_player') and self.player._player:
                source = self.player._player.source().toString()
                if source:
                    # Update Now Playing info using osascript
                    script = f'''
                    tell application "System Events"
                        tell process "Music"
                            set currentTrack to current track
                            set name of currentTrack to "{track.title}"
                            set artist of currentTrack to "{track.grandparentTitle}"
                            set album of currentTrack to "{track.parentTitle}"
                            set player position to {position/1000.0}
                            if {str(is_playing).lower()} then
                                play
                            else
                                pause
                            end if
                        end tell
                    end tell
                    '''
                    subprocess.run(['osascript', '-e', script], capture_output=True)
                    
        except Exception:
            # Silently continue after any error
            pass
            
    def clear_now_playing(self) -> None:
        """Clear the now playing information in macOS media center."""
        try:
            script = '''
            tell application "System Events"
                tell process "Music"
                    set currentTrack to current track
                    set name of currentTrack to ""
                    set artist of currentTrack to ""
                    set album of currentTrack to ""
                    stop
                end tell
            end tell
            '''
            subprocess.run(['osascript', '-e', script], capture_output=True)
        except Exception:
            # Silently continue after any error
            pass

class MacOSMediaCenter(QObject):
    """Media center integration for macOS."""
    
    def __init__(self):
        super().__init__()
        self.player: Optional[Player] = None
        self.delegate: Optional[MediaCenterDelegate] = None
        
    def set_player(self, player: Player) -> None:
        """Set the player instance."""
        self.player = player
        self.delegate = MediaCenterDelegate(player)
        
    def clear_now_playing(self) -> None:
        """Clear the now playing information."""
        if self.delegate:
            self.delegate.clear_now_playing() 