from typing import Optional, Tuple
from plexapi.server import PlexServer
from plexapi.audio import Track
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt

def format_time(ms: int) -> str:
    """Форматирует время в миллисекундах в строку MM:SS"""
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"

def format_track_info(track: Track) -> str:
    """Форматирует информацию о треке"""
    if not track:
        return "Нет трека"
        
    # Получаем год
    year = f" ({track.year})" if hasattr(track, 'year') and track.year else ""
    
    # Форматируем строку с названием трека, исполнителем и альбомом
    return f"{track.title}{year}\n{track.grandparentTitle}\n{track.parentTitle}"

def load_cover_image(plex: PlexServer, track: Track, size: Tuple[int, int] = (200, 200)) -> Optional[QPixmap]:
    """Загружает обложку альбома"""
    if not track or not plex:
        return None
    
    try:
        # Получаем URL обложки
        cover_url = track.thumb
        if not cover_url:
            return None
            
        # Добавляем базовый URL сервера, если URL относительный
        if cover_url.startswith('/'):
            cover_url = f"{plex._baseurl}{cover_url}"
            
        # Загружаем изображение с токеном
        headers = {'X-Plex-Token': plex._token}
        response = plex._session.get(cover_url, headers=headers)
        if response.status_code != 200:
            return None
            
        # Создаем изображение из данных
        image = QImage()
        image.loadFromData(response.content)
        
        # Конвертируем изображение в RGB32 формат для исправления проблем с цветовым профилем
        image = image.convertToFormat(QImage.Format.Format_RGB32)
        
        # Масштабируем изображение
        scaled_image = image.scaled(size[0], size[1], Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        # Конвертируем в QPixmap
        return QPixmap.fromImage(scaled_image)
    except Exception as e:
        print(f"Ошибка при загрузке обложки: {e}")
        return None 