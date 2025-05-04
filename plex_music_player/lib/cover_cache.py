from typing import Dict, Optional, Tuple
import requests
from PyQt6.QtGui import QImage, QPixmap
import sys
from .logger import Logger

if "darwin" in sys.platform:
    from AppKit import NSImage
else:
    NSImage = None

logger = Logger()

class CoverCache:
    """Singleton class for caching cover images."""
    _instance = None
    _qt_cache: Dict[str, QPixmap] = {}
    _ns_cache: Dict[str, NSImage] = {}
    _raw_data_cache: Dict[str, bytes] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CoverCache, cls).__new__(cls)
        return cls._instance
    
    def _get_base_url(self, url: str) -> str:
        """Remove size parameters from URL to get base URL."""
        # Remove width and height parameters if they exist
        base_url = url.split("&width=")[0]
        return base_url
    
    def _download_image(self, url: str) -> Optional[bytes]:
        """Download image data and cache it."""
        base_url = self._get_base_url(url)
        
        if base_url in self._raw_data_cache:
            logger.debug(f"Raw data cache hit for URL: {base_url}")
            return self._raw_data_cache[base_url]
            
        logger.debug(f"Raw data cache miss for URL: {base_url}")
        try:
            response = requests.get(url)
            if response.status_code == 200:
                self._raw_data_cache[base_url] = response.content
                logger.debug(f"Image data downloaded and cached: {base_url}")
                return response.content
        except Exception as e:
            logger.error(f"Error downloading image data: {e}")
        return None
    
    def get_qt_image(self, url: str) -> Optional[QPixmap]:
        """Get QPixmap from cache or download it."""
        base_url = self._get_base_url(url)
        
        if base_url in self._qt_cache:
            logger.debug(f"Qt cache hit for URL: {base_url}")
            return self._qt_cache[base_url]
            
        logger.debug(f"Qt cache miss for URL: {base_url}")
        image_data = self._download_image(url)
        if image_data:
            try:
                image = QImage()
                image.loadFromData(image_data)
                pixmap = QPixmap.fromImage(image)
                self._qt_cache[base_url] = pixmap
                logger.debug(f"Qt image created and cached: {base_url}")
                return pixmap
            except Exception as e:
                logger.error(f"Error creating Qt image: {e}")
        return None
    
    def get_ns_image(self, url: str) -> Optional[NSImage]:
        """Get NSImage from cache or download it."""
        base_url = self._get_base_url(url)
        
        if base_url in self._ns_cache:
            logger.debug(f"NS cache hit for URL: {base_url}")
            return self._ns_cache[base_url]
            
        logger.debug(f"NS cache miss for URL: {base_url}")
        image_data = self._download_image(url)
        if image_data:
            try:
                image = NSImage.alloc().initWithData_(image_data)
                if image:
                    self._ns_cache[base_url] = image
                    logger.debug(f"NS image created and cached: {base_url}")
                    return image
            except Exception as e:
                logger.error(f"Error creating NS image: {e}")
        return None
    
    def clear(self) -> None:
        """Clear all caches."""
        self._qt_cache.clear()
        self._ns_cache.clear()
        self._raw_data_cache.clear()
        logger.debug("Cover cache cleared")

# Global instance
cover_cache = CoverCache() 
