from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from plexapi.audio import Track
import sys

class MediaCenterInterface(ABC):
    """Abstract base class for media center integration."""
    
    @abstractmethod
    def initialize(self) -> None:
        """Initialize the media center integration."""
        pass
    
    @abstractmethod
    def update_now_playing(self, track: Track, is_playing: bool, position: int) -> None:
        """Update the now playing information in the media center.
        
        Args:
            track: The current track being played
            is_playing: Whether the track is currently playing
            position: Current playback position in milliseconds
        """
        pass
    
    @abstractmethod
    def clear_now_playing(self) -> None:
        """Clear the now playing information from the media center."""
        pass
    
    @abstractmethod
    def set_player(self, player: Any) -> None:
        """Set the player instance that will handle media control commands.
        
        Args:
            player: The player instance that implements media control methods
        """
        pass

def get_media_center() -> Optional[MediaCenterInterface]:
    """Get the appropriate media center implementation for the current platform.
    
    Returns:
        An instance of MediaCenterInterface for the current platform, or None if no implementation is available.
    """
    if sys.platform == 'darwin':
        from .macos_media_center import MacOSMediaCenter
        return MacOSMediaCenter()
    elif sys.platform == 'win32':
        from .windows_media_center import WindowsMediaCenter
        return WindowsMediaCenter()
    return None 