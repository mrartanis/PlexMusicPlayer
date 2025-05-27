import sys
import os
import requests
import tempfile
from typing import Optional, Tuple, Dict
from plexapi.server import PlexServer
from plexapi.audio import Track
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtCore import Qt
from .logger import Logger
from .cover_cache import cover_cache
from pathlib import Path
import re

logger = Logger()


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
            
        # Try to get album or track cover
        thumb = None
        if hasattr(track, 'parentThumb'):
            thumb = track.parentThumb
        elif hasattr(track, 'thumb'):
            thumb = track.thumb
            
        if not thumb:
            return None
            
        thumb_url = plex.url(thumb, includeToken=True)
        
        # Use cache to get image
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


def resource_path(relative_path):
    # PyInstaller
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    # py2app
    elif getattr(sys, 'frozen', False):
        bundle_dir = os.path.dirname(sys.executable)
        resources_dir = os.path.abspath(os.path.join(bundle_dir, '..', 'Resources'))
        return os.path.join(resources_dir, relative_path)
    # Usual runtime
    base_dir = Path(__file__).parent.parent.resolve()
    return os.path.join(base_dir, relative_path)

def read_resource_file(relative_path):
    """Reads the content of a resource file, compatible with PyInstaller."""    
    path = resource_path(relative_path)
    try:
        # Try direct file reading
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        # For PyInstaller - try to get content from package resources
        elif hasattr(sys, '_MEIPASS'):
            # Try alternative method for PyInstaller
            try:
                import pkg_resources
                from importlib.resources import files, as_file
                try:
                    # Try to get resource from bundle
                    package_path = os.path.dirname(relative_path)
                    file_name = os.path.basename(relative_path)
                    package = 'plex_music_player'
                    if package_path:
                        package = f"{package}.{package_path.replace('/', '.')}"
                    with as_file(files(package) / file_name) as f:
                        with open(f, "r", encoding="utf-8") as f_read:
                            return f_read.read()
                except Exception:
                    # If it didn't work, use pkg_resources
                    resource_package = 'plex_music_player'
                    return pkg_resources.resource_string(resource_package, relative_path).decode('utf-8')
            except Exception as e:
                logger.error(f"Error reading PyInstaller resource {path}: {e}")
                return None
        else:
            logger.error(f"Resource file not found: {path}")
            return None
    except Exception as e:
        logger.error(f"Error reading resource file {path}: {e}")
        return None

def create_icon(relative_path, color):
    """Creates a QIcon safely, compatible with PyInstaller, py2app и обычным запуском."""
    path = resource_path(relative_path)
    logger.info(f"Creating icon from SVG: {path}")
    if ".svg" in path.lower():
        svg_data = read_resource_file(relative_path)
        if svg_data and color:
            svg_data = re.sub(r'fill="(?!none)([^\"]*)"', f'fill="{color}"', svg_data)
            svg_data = re.sub(r"fill='(?!none)([^']*)'", f"fill='{color}'", svg_data)
            svg_data = re.sub(r'(<path\b(?![^>]*\bfill=)[^>]*)>', r'\1 fill="' + color + '">', svg_data)
            return QIcon(QIcon.fromTheme("", QIcon(QPixmap.fromImage(QImage.fromData(bytes(svg_data, "utf-8"))))))
        elif svg_data:
            return QIcon(QIcon.fromTheme("", QIcon(QPixmap.fromImage(QImage.fromData(bytes(svg_data, "utf-8"))))))
        else:
            logger.error(f"Failed to read SVG data for {relative_path}")
    return QIcon(path)
