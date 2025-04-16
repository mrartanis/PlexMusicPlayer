from PyQt6.QtGui import QImage, QColor
from PyQt6.QtCore import Qt
import numpy as np
from typing import Tuple, Optional, Dict
from sklearn.cluster import KMeans
from .logger import Logger

logger = Logger()

# Кэш для доминантных цветов
_color_cache: Dict[str, QColor] = {}

def get_dominant_color(image: QImage, url: Optional[str] = None, num_colors: int = 3, crop_margin: float = 0.1) -> Optional[QColor]:
    """
    Extract the dominant color from an image.
    
    Args:
        image: QImage to analyze
        url: Optional URL of the image for caching
        num_colors: Number of top colors to consider (default: 3)
        crop_margin: Percentage of image to crop from edges (0.1 = 10%)
        
    Returns:
        QColor representing the dominant color or None if image is invalid
    """
    # Проверяем кэш если есть URL
    if url and url in _color_cache:
        logger.debug(f"Using cached color for URL: {url}")
        return _color_cache[url]
    
    logger.debug(f"Starting color extraction (image size: {image.width()}x{image.height()})")
    
    if image.isNull():
        logger.error("Image is null")
        return None
        
    # Convert image to RGB format if needed
    if image.format() != QImage.Format.Format_RGB32:
        logger.debug("Converting image to RGB32 format")
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    
    # Get image data as numpy array
    width = image.width()
    height = image.height()
    ptr = image.bits()
    ptr.setsize(height * width * 4)  # 4 bytes per pixel (RGBA)
    arr = np.frombuffer(ptr, np.uint8).reshape((height, width, 4))
    
    # Crop margins
    margin_x = int(width * crop_margin)
    margin_y = int(height * crop_margin)
    cropped_arr = arr[margin_y:height-margin_y, margin_x:width-margin_x]
    logger.debug(f"Cropped image size: {cropped_arr.shape[1]}x{cropped_arr.shape[0]} " +
                f"(removed {margin_x}px from left/right, {margin_y}px from top/bottom)")
    
    # Reshape to 2D array of pixels
    pixels = cropped_arr.reshape(-1, 4)
    logger.debug(f"Total pixels in cropped area: {len(pixels)}")
    
    # Remove alpha channel
    pixels = pixels[:, :3]
    
    # Calculate initial saturation for all pixels
    max_vals = np.max(pixels, axis=1)
    min_vals = np.min(pixels, axis=1)
    saturations = (max_vals - min_vals) / (max_vals + 1e-6)  # Avoid division by zero
    
    saturation_threshold = np.percentile(saturations, 1)  # Upper 99% of saturation values
    valid_pixels = pixels[saturations > saturation_threshold]
    logger.debug(f"Pixels after saturation filtering: {len(valid_pixels)} ({(len(valid_pixels)/len(pixels))*100:.1f}%)")
    
    if len(valid_pixels) == 0:
        logger.error("No valid pixels after filtering")
        return None
    
    # Convert RGB pixels to HSV for better color separation
    pixels_rgb = valid_pixels.astype(np.float32) / 255.0
    pixels_hsv = np.zeros_like(pixels_rgb)
    
    # Convert to HSV manually (avoiding OpenCV dependency)
    max_vals = np.max(pixels_rgb, axis=1)
    min_vals = np.min(pixels_rgb, axis=1)
    diff = max_vals - min_vals
    
    # Hue calculation
    hue = np.zeros(len(pixels_rgb))
    # Red is max
    mask = (pixels_rgb[:, 0] == max_vals)
    hue[mask] = 60 * (pixels_rgb[mask, 1] - pixels_rgb[mask, 2]) / diff[mask]
    # Green is max
    mask = (pixels_rgb[:, 1] == max_vals)
    hue[mask] = 60 * (2 + (pixels_rgb[mask, 2] - pixels_rgb[mask, 0]) / diff[mask])
    # Blue is max
    mask = (pixels_rgb[:, 2] == max_vals)
    hue[mask] = 60 * (4 + (pixels_rgb[mask, 0] - pixels_rgb[mask, 1]) / diff[mask])
    
    hue[hue < 0] += 360
    hue[diff == 0] = 0
    
    # Saturation and Value
    saturation = np.zeros(len(pixels_rgb))
    saturation[max_vals != 0] = diff[max_vals != 0] / max_vals[max_vals != 0]
    value = max_vals
    
    # Stack HSV channels
    pixels_hsv[:, 0] = hue / 360  # Normalize hue to [0, 1]
    pixels_hsv[:, 1] = saturation
    pixels_hsv[:, 2] = value
    
    # Log color distribution before clustering
    logger.debug("Color distribution before clustering:")
    
    # Calculate hue distribution
    hue_bins = np.linspace(0, 360, 13)  # 12 bins (30 degrees each)
    hue_hist = np.histogram(hue, bins=hue_bins)[0]
    hue_names = ["Red", "Orange", "Yellow", "Yellow-Green", "Green", "Blue-Green", 
                 "Cyan", "Light-Blue", "Blue", "Purple", "Magenta", "Pink"]
    
    total_pixels = len(hue)
    for i, count in enumerate(hue_hist):
        percentage = (count/total_pixels)*100
        if percentage > 1.0:  # Only show colors with >1% presence
            logger.debug(f"  - {hue_names[i]}: {percentage:.1f}% (hue {hue_bins[i]:.0f}°-{hue_bins[i+1]:.0f}°)")
    
    # Log average RGB values for blue-range pixels
    blue_mask = (hue >= 180) & (hue <= 300)  # Cyan to Purple range
    if np.any(blue_mask):
        blue_pixels = pixels_rgb[blue_mask]
        avg_blue = np.mean(blue_pixels, axis=0)
        logger.debug(f"Average RGB for blue-range pixels: ({avg_blue[0]*255:.0f}, {avg_blue[1]*255:.0f}, {avg_blue[2]*255:.0f})")
    
    # Log pixels by brightness ranges
    dark_mask = value < 0.3
    mid_mask = (value >= 0.3) & (value < 0.7)
    bright_mask = value >= 0.7
    
    logger.debug(f"Brightness distribution:")
    logger.debug(f"  - Dark pixels (0-30%): {np.sum(dark_mask)/total_pixels*100:.1f}%")
    logger.debug(f"  - Mid pixels (30-70%): {np.sum(mid_mask)/total_pixels*100:.1f}%")
    logger.debug(f"  - Bright pixels (70-100%): {np.sum(bright_mask)/total_pixels*100:.1f}%")
    
    # Use k-means clustering in HSV space
    logger.debug("Starting k-means clustering in HSV space")
    kmeans = KMeans(n_clusters=num_colors, 
                    random_state=42, 
                    n_init=10,
                    tol=1.0)
    kmeans.fit(pixels_hsv)
    
    # Convert cluster centers back to RGB
    centers_hsv = kmeans.cluster_centers_
    centers = np.zeros_like(centers_hsv)
    
    for i in range(len(centers_hsv)):
        h, s, v = centers_hsv[i] * [360, 1, 1]  # Un-normalize hue
        
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        
        if h < 60:
            r, g, b = c, x, 0
        elif h < 120:
            r, g, b = x, c, 0
        elif h < 180:
            r, g, b = 0, c, x
        elif h < 240:
            r, g, b = 0, x, c
        elif h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x
            
        centers[i] = [(r + m) * 255, (g + m) * 255, (b + m) * 255]
    
    # Get cluster sizes
    labels = kmeans.labels_
    unique_labels, counts = np.unique(labels, return_counts=True)
    
    # Calculate brightness for each center
    brightness = np.mean(centers, axis=1)
    
    # Log cluster information with percentage and HSV values
    total_pixels = len(valid_pixels)
    for i in range(len(centers)):
        color = QColor(int(centers[i][0]), int(centers[i][1]), int(centers[i][2]))
        percentage = (counts[i]/total_pixels)*100
        logger.debug(f"Cluster {i+1}:")
        logger.debug(f"  - Color: RGB({int(centers[i][0])}, {int(centers[i][1])}, {int(centers[i][2])}) / {color.name()}")
        logger.debug(f"  - HSV: {centers_hsv[i][0]*360:.1f}°, {centers_hsv[i][1]*100:.1f}%, {centers_hsv[i][2]*100:.1f}%")
        logger.debug(f"  - Pixels: {counts[i]} ({percentage:.1f}%)")
        logger.debug(f"  - Brightness: {brightness[i]:.2f}")
    
    # Calculate angles to primary colors correctly
    hue_degrees = centers_hsv[:, 0] * 360
    
    # For blue hues (around 240°)
    angle_to_blue = np.minimum(np.abs(240 - hue_degrees), np.abs(240 - (hue_degrees + 360)))
    blue_bonus = np.exp(-angle_to_blue**2 / 2000)
    
    # For red hues (around 0° or 360°)
    angle_to_red = np.minimum(np.abs(hue_degrees - 0), np.abs(hue_degrees - 360))
    is_red = angle_to_red < 30  # Consider hues within 30° of red
    red_saturation = centers_hsv[:, 1]  # High saturation for vivid reds
    
    logger.debug("Hue analysis:")
    for i in range(len(hue_degrees)):
        logger.debug(f"Cluster {i+1}:")
        logger.debug(f"  - Hue: {hue_degrees[i]:.1f}°")
        logger.debug(f"  - Angle to blue: {angle_to_blue[i]:.1f}°")
        logger.debug(f"  - Angle to red: {angle_to_red[i]:.1f}°")
        logger.debug(f"  - Is red: {is_red[i]}")
        logger.debug(f"  - Red saturation: {red_saturation[i]:.2f}")
        logger.debug(f"  - Blue bonus: {blue_bonus[i]:.2f}")
    
    # New weight formula: no size influence, just color properties
    weights = (1 + brightness * 2.0)
    # Boost red colors that are saturated or give blue bonus
    weights = np.where(is_red, weights * (1 + red_saturation * 2.0), weights * (1 + blue_bonus * 2.0))
    
    logger.debug("Final weights for each cluster:")
    for i in range(len(weights)):
        logger.debug(f"Cluster {i+1} weight components:")
        logger.debug(f"  - Brightness bonus: {1 + brightness[i] * 2.0:.2f}")
        logger.debug(f"  - Color bonus: {'red' if is_red[i] else 'blue'} ({weights[i]/(1 + brightness[i] * 2.0):.2f}x)")
        logger.debug(f"  - Final weight: {weights[i]:.2f}")
    
    dominant_idx = np.argmax(weights)
    dominant_color = centers[dominant_idx]
    
    # Swap red and blue components
    r, g, b = dominant_color
    dominant_color = np.array([b, g, r])
    
    # Create final color
    result = QColor(int(dominant_color[0]), int(dominant_color[1]), int(dominant_color[2]))
    logger.debug(f"Selected dominant color: {result.name()} (RGB: {result.red()}, {result.green()}, {result.blue()})")
    logger.debug(f"Original RGB: ({r:.0f}, {g:.0f}, {b:.0f}), Swapped RGB: ({b:.0f}, {g:.0f}, {r:.0f})")
    
    # Cache if URL exists
    if url:
        logger.debug(f"Caching color for URL: {url}")
        _color_cache[url] = result
    
    return result

def get_contrasting_text_color(background_color: QColor) -> QColor:
    """
    Determine if black or white text should be used on a given background color.
    
    Args:
        background_color: QColor of the background
        
    Returns:
        QColor (black or white) for the text
    """
    # Calculate relative luminance using the formula from WCAG 2.0
    r = background_color.red() / 255.0
    g = background_color.green() / 255.0
    b = background_color.blue() / 255.0
    
    # Apply gamma correction
    r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
    g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
    b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
    
    # Calculate relative luminance
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    # Return black for light backgrounds, white for dark backgrounds
    return QColor(0, 0, 0) if luminance > 0.5 else QColor(255, 255, 255)

def adjust_color_brightness(color: QColor, factor: float) -> QColor:
    """
    Adjust the brightness of a color by a factor.
    
    Args:
        color: QColor to adjust
        factor: Brightness adjustment factor (0.0 to 1.0 for darker, >1.0 for lighter)
        
    Returns:
        Adjusted QColor
    """
    h, s, v, a = color.getHsv()
    v = min(255, int(v * factor))
    return QColor.fromHsv(h, s, v, a)

def get_color_palette(color: QColor, num_colors: int = 5) -> list[QColor]:
    """
    Generate a harmonious color palette based on a main color.
    
    Args:
        color: Base color to generate palette from
        num_colors: Number of colors in palette
        
    Returns:
        List of QColors forming a palette
    """
    h, s, v, _ = color.getHsv()
    palette = []
    
    # Add analogous colors
    for i in range(num_colors):
        new_hue = (h + (360 // num_colors) * i) % 360
        palette.append(QColor.fromHsv(new_hue, s, v))
    
    return palette 