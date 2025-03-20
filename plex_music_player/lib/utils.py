from typing import Optional, Tuple
from plexapi.server import PlexServer
from plexapi.audio import Track
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

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
        if not cover_url:
            return None
        if cover_url.startswith('/'):
            cover_url = f"{plex._baseurl}{cover_url}"
        headers = {'X-Plex-Token': plex._token}
        response = plex._session.get(cover_url, headers=headers)
        if response.status_code != 200:
            return None
        image = QImage()
        image.loadFromData(response.content)
        
        image = image.convertToFormat(QImage.Format.Format_RGB32)
        return QPixmap.fromImage(image)
    except Exception as e:
        print(f"Error loading cover: {e}")
        return None 