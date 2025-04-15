import sys
import os
import requests
import tempfile
from typing import Optional, Tuple
from plexapi.server import PlexServer
from plexapi.audio import Track
from PyQt6.QtGui import QImage, QPixmap
from .logger import Logger

logger = Logger()


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


def load_cover_image(plex: PlexServer, track: Track, size: Tuple[int, int] = (200, 200)) -> Optional[QPixmap]:
    if not track or not plex:
        return None
    
    try:
        cover_url = track.thumb
        logger.debug(f"Initial cover URL: {cover_url}")
        if not cover_url:
            return None
        if cover_url.startswith('/'):
            cover_url = f"{plex._baseurl}{cover_url}"
            logger.debug(f"Full cover URL: {cover_url}")
        headers = {'X-Plex-Token': plex._token}
        response = plex._session.get(cover_url, headers=headers)
        logger.debug(f"Response status code: {response.status_code}")
        if response.status_code != 200:
            return None
        image = QImage()
        image.loadFromData(response.content)
        logger.debug(f"Image loaded, size: {image.width()}x{image.height()}")
        
        image = image.convertToFormat(QImage.Format.Format_RGB32)
        return QPixmap.fromImage(image)
    except Exception as e:
        logger.error(f"Error loading cover: {e}")
        logger.debug(f"Exception type: {type(e).__name__}")
        logger.debug(f"Full exception details: {repr(e)}")
        return None


def download_artwork(track: Track) -> bytes | str | os.PathLike:
    """Download artwork for the track and return the local file path."""
    if hasattr(track, 'thumb') and track._server:
        try:
            thumb_url = track._server.url(track.thumb)
            response = requests.get(thumb_url, headers={'X-Plex-Token': track._server._token})
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
