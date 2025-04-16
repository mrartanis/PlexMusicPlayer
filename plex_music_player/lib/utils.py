import sys
import os
import requests
import tempfile
from typing import Optional, Tuple, Dict
from plexapi.server import PlexServer
from plexapi.audio import Track
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt
from .logger import Logger
from .cover_cache import cover_cache

logger = Logger()

# Простой кэш в памяти для обложек
_cover_cache: Dict[str, QPixmap] = {}

def format_time(ms: int) -> str:
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def format_track_info(track: Track) -> str:
    if not track:
        return "No track"
    year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
    return f"{track.title}{year}\n{track.grandparentTitle}\n{track.parentTitle}"


def load_cover_image(plex: PlexServer, track: Track, size: int = 600) -> Optional[QPixmap]:
    """Load cover image for track with caching."""
    try:
        if not track or not plex:
            return None
            
        # Пробуем получить обложку альбома или трека
        thumb = None
        if hasattr(track, 'parentThumb'):
            thumb = track.parentThumb
        elif hasattr(track, 'thumb'):
            thumb = track.thumb
            
        if not thumb:
            return None
            
        thumb_url = plex.url(thumb, includeToken=True)
        
        # Используем кэш для получения изображения
        return cover_cache.get_qt_image(thumb_url)
            
    except Exception as e:
        logger.error(f"Error loading cover: {e}")
        return None


def download_artwork(track: Track) -> bytes | str | os.PathLike:
    """Download artwork for the track and return the local file path."""
    if hasattr(track, 'parentThumb') and track._server:
        try:
            thumb_url = track._server.url(track.parentThumb, includeToken=True)
            response = requests.get(thumb_url)
            if response.status_code == 200:
                temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                temp_file.write(response.content)
                temp_file.close()
                return temp_file.name
        except Exception as e:
            logger.error(f"Error downloading artwork: {e}")
    return None


def pyintaller_resource_path(relative_path) -> str | bytes:
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)
