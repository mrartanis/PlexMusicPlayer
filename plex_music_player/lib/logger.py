import os
import logging
import inspect
from typing import Optional


class Logger:
    """
    Singleton logger class for the Plex Music Player application.
    Provides centralized logging functionality with both console and file output.
    
    Usage:
        from plex_music_player.lib.logger import Logger
        
        logger = Logger()
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")
    """
    _instance: Optional["Logger"] = None
    
    def __new__(cls) -> "Logger":
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._instance._initialize_logger()
        return cls._instance
    
    def _initialize_logger(self) -> None:
        """Initialize the logger with proper formatting and handlers"""
        self.logger = logging.getLogger("PlexMusicPlayer")
        self.logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate log messages
        if self.logger.handlers:
            return
        
        # Create console handler with formatting
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        
        # Create file handler
        log_dir = os.path.join(os.path.expanduser("~"), ".plex_music_player", "logs")
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(
            os.path.join(log_dir, "plex_music_player.log"),
            encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Create formatter
        formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d - [%(caller)s] - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def _get_caller_name(self) -> str:
        """Get the name of the calling function"""
        frame = inspect.currentframe()
        # Skip this method and the logging method
        frame = frame.f_back.f_back
        return frame.f_code.co_name
    
    def debug(self, message: str) -> None:
        """Log a debug message"""
        self.logger.debug(message, extra={"caller": self._get_caller_name()})
    
    def info(self, message: str) -> None:
        """Log an info message"""
        self.logger.info(message, extra={"caller": self._get_caller_name()})
    
    def warning(self, message: str) -> None:
        """Log a warning message"""
        self.logger.warning(message, extra={"caller": self._get_caller_name()})
    
    def error(self, message: str) -> None:
        """Log an error message"""
        self.logger.error(message, extra={"caller": self._get_caller_name()})
    
    def critical(self, message: str) -> None:
        """Log a critical message"""
        self.logger.critical(message, extra={"caller": self._get_caller_name()}) 