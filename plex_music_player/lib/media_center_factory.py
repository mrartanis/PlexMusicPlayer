import sys
from plex_music_player.lib.media_center import MediaCenterInterface

def get_media_center() -> MediaCenterInterface:
    """Get the appropriate media center implementation for the current platform."""
    if sys.platform == 'darwin':
        from plex_music_player.lib.macos_media_center import MacOSMediaCenter
        return MacOSMediaCenter()
    elif sys.platform == 'win32':
        from plex_music_player.lib.windows_media_center import WindowsMediaCenter
        return WindowsMediaCenter()
    else:
        # Return a dummy implementation for unsupported platforms
        class DummyMediaCenter(MediaCenterInterface):
            def initialize(self) -> None:
                pass
                
            def update_now_playing(self, track, is_playing, position) -> None:
                pass
                
            def clear_now_playing(self) -> None:
                pass
                
            def set_player(self, player) -> None:
                pass
                
        return DummyMediaCenter() 