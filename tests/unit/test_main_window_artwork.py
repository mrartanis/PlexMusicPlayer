from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QLabel, QWidget

from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache
from app.presentation.qt.main_window_artwork import MainWindowArtworkMixin


class _ArtworkHarness(MainWindowArtworkMixin, QWidget):
    def __init__(self, *, cache_dir: Path) -> None:
        super().__init__()
        self._container = SimpleNamespace(
            services=SimpleNamespace(artwork_cache=FileArtworkCache(cache_dir=cache_dir)),
            logger=logging.getLogger("test-artwork"),
        )
        self._accent_color = "#526ee8"
        self._artwork_label = QLabel()
        self._pending_artwork_track_id = None

    def _apply_theme(self) -> None:
        return


def _write_image(path: Path, fill: str, *, center_fill: str | None = None) -> None:
    image = QImage(180, 180, QImage.Format.Format_ARGB32)
    image.fill(QColor(fill))
    if center_fill is not None:
        for y in range(45, 135):
            for x in range(45, 135):
                image.setPixelColor(x, y, QColor(center_fill))
    assert image.save(str(path))


def test_artwork_prefers_pixel_accent_over_api_color(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "pixel-first.png"
    _write_image(image_path, "#202020", center_fill="#db2f2f")

    window._set_artwork_pixmap(image_path, preferred_accent="#22aaee")

    assert window._accent_color != "#22aaee"
    assert window._accent_color != "#526ee8"
    cached = window._container.services.artwork_cache.load_accent_color(image_path)
    assert cached == window._accent_color


def test_artwork_falls_back_to_api_accent_when_pixels_are_unusable(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "api-fallback.png"
    _write_image(image_path, "#ffffff")

    window._set_artwork_pixmap(image_path, preferred_accent="#22aaee")

    assert window._accent_color == "#22aaee"
    assert window._container.services.artwork_cache.load_accent_color(image_path) == "#22aaee"


def test_artwork_falls_back_to_default_when_pixels_and_api_are_unusable(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "default-fallback.png"
    _write_image(image_path, "#ffffff")

    window._set_artwork_pixmap(image_path, preferred_accent="#111111")

    assert window._accent_color == "#526ee8"
    assert window._container.services.artwork_cache.load_accent_color(image_path) == "#526ee8"


def test_artwork_cache_has_priority_over_pixels_and_api(qtbot, tmp_path) -> None:
    window = _ArtworkHarness(cache_dir=tmp_path)
    qtbot.addWidget(window)
    image_path = tmp_path / "cache-priority.png"
    _write_image(image_path, "#202020", center_fill="#db2f2f")
    window._container.services.artwork_cache.save_accent_color(image_path, "#556677")

    window._set_artwork_pixmap(image_path, preferred_accent="#22aaee")

    assert window._accent_color == "#556677"
