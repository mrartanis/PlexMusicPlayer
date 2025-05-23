import sys
from typing import Any, Callable
from plexapi.audio import Track
from plex_music_player.lib.media_center import MediaCenterInterface
from plex_music_player.lib.logger import Logger

logger = Logger()

if sys.platform == 'win32':
    import win32com.client
    import win32gui
    import win32con
    import win32api
    from ctypes import windll, CFUNCTYPE, POINTER, c_int, c_void_p, byref, cast, c_long, c_ulong
    
    # Windows Media Key Virtual Key Codes
    VK_MEDIA_PLAY_PAUSE = 0xB3
    VK_MEDIA_NEXT_TRACK = 0xB0
    VK_MEDIA_PREV_TRACK = 0xB1
    VK_MEDIA_STOP = 0xB2
    
    # Define the callback function type
    HOOKPROC = CFUNCTYPE(c_int, c_int, c_int, POINTER(c_void_p))
    
    class WindowsMediaCenter(MediaCenterInterface):
        def __init__(self):
            self.player = None
            self._hook = None
            self._hook_proc = None  # Keep a reference to prevent garbage collection
            logger.debug("WindowsMediaCenter initialized")
            
        def initialize(self) -> None:
            """Initialize the Windows media center integration."""
            logger.debug("Initializing Windows media center...")
            
            # Create the callback function
            def low_level_keyboard_handler(nCode: int, wParam: int, lParam: POINTER(c_void_p)) -> int:
                """Handle keyboard events for media keys."""
                try:
                    if nCode >= 0 and wParam == win32con.WM_KEYDOWN:
                        kb_struct = cast(lParam, POINTER(c_void_p))
                        vk_code = kb_struct[0]
                        logger.debug(f"Key pressed: {hex(vk_code)}")
                        
                        if vk_code == VK_MEDIA_PLAY_PAUSE:
                            logger.debug("Play/Pause key detected")
                            if self.player:
                                self.player.toggle_play()
                        elif vk_code == VK_MEDIA_NEXT_TRACK:
                            logger.debug("Next Track key detected")
                            if self.player:
                                self.player.play_next_track()
                        elif vk_code == VK_MEDIA_PREV_TRACK:
                            logger.debug("Previous Track key detected")
                            if self.player:
                                self.player.play_previous_track()
                        elif vk_code == VK_MEDIA_STOP:
                            logger.debug("Stop key detected")
                            if self.player:
                                self.player.stop()
                except Exception as e:
                    logger.error(f"Error in keyboard handler: {e}")
                
                # Call the next hook
                return windll.user32.CallNextHookEx(self._hook, nCode, wParam, lParam)
            
            # Store the callback function to prevent garbage collection
            self._hook_proc = HOOKPROC(low_level_keyboard_handler)
            
            # Get the module handle as c_void_p
            module_handle = win32api.GetModuleHandle(None)
            if isinstance(module_handle, int):
                module_handle = c_void_p(module_handle)
            
            # Register the hook
            self._hook = windll.user32.SetWindowsHookExA(
                c_int(win32con.WH_KEYBOARD_LL),
                self._hook_proc,
                module_handle,
                c_ulong(0)
            )
            
            if self._hook:
                logger.debug("Successfully registered keyboard hook")
            else:
                error = win32api.GetLastError()
                logger.error(f"Failed to register keyboard hook. Error: {error}")
            
        def update_now_playing(self, track: Track, is_playing: bool, position: int, update_position_only: bool = False) -> None:
            """Update the now playing information in Windows media center."""
            pass
                
        def clear_now_playing(self) -> None:
            """Clear the now playing information from Windows media center."""
            if not self.player:
                logger.debug("Player not set, skipping clear_now_playing")
                return
                
            try:
                logger.debug("Creating Windows Media Player object...")
                # Create Windows Media Player object
                wmp = win32com.client.Dispatch("WMPlayer.OCX")
                logger.debug("WMP object created successfully")
                
                logger.debug("Stopping playback...")
                wmp.controls.stop()
                logger.debug("Playback stopped")
                
                logger.debug("Clearing current media...")
                wmp.currentMedia = None
                logger.debug("Current media cleared")
                
                logger.debug("Media information cleared successfully")
                
            except Exception as e:
                logger.error(f"Error in clear_now_playing:")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception message: {str(e)}")
                logger.error(f"Full exception details: {repr(e)}")
                # Still silently continue after logging the error
                pass
                
        def set_player(self, player: Any) -> None:
            """Set the player instance that will handle media control commands."""
            self.player = player
            logger.debug("Player set in WindowsMediaCenter")
            
        def __del__(self):
            """Clean up the keyboard hook when the object is destroyed."""
            if self._hook:
                logger.debug("Unregistering keyboard hook...")
                windll.user32.UnhookWindowsHookEx(self._hook) 