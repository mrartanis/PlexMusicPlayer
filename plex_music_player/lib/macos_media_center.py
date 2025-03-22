import sys
from typing import Any
from plexapi.audio import Track
from plex_music_player.lib.media_center import MediaCenterInterface

if sys.platform == 'darwin':
    from Foundation import NSObject, NSMutableDictionary
    from AppKit import NSImage
    import objc
    import MediaPlayer

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
            if self.player:
                self.player.play()
            return MediaPlayer.MPRemoteCommandEventStatusSuccess
            
        def handlePauseCommand_(self, event):
            if self.player:
                self.player.pause()
            return MediaPlayer.MPRemoteCommandEventStatusSuccess
            
        def handleTogglePlayPauseCommand_(self, event):
            if self.player:
                self.player.toggle_play()
            return MediaPlayer.MPRemoteCommandEventStatusSuccess
            
        def handleNextTrackCommand_(self, event):
            if self.player:
                self.player.play_next_track()
            return MediaPlayer.MPRemoteCommandEventStatusSuccess
            
        def handlePreviousTrackCommand_(self, event):
            if self.player:
                self.player.play_previous_track()
            return MediaPlayer.MPRemoteCommandEventStatusSuccess
            
        def handleSeekCommand_(self, event):
            if self.player and hasattr(event, 'positionTime'):
                self.player.seek_position(int(event.positionTime() * 1000))
            return MediaPlayer.MPRemoteCommandEventStatusSuccess 