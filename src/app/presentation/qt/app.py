from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.bootstrap.config import AppConfig


def create_qt_application(argv: Sequence[str], config: AppConfig) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing

    qt_app = QApplication(list(argv))
    qt_app.setApplicationName(config.app_name)
    qt_app.setOrganizationName(config.app_author)
    qt_app.setApplicationDisplayName("Plex Music Player")
    icon_path = Path(__file__).resolve().parents[4] / "assets" / "plex_music_player_256.png"
    qt_app.setWindowIcon(QIcon(str(icon_path)) if icon_path.exists() else QIcon())
    return qt_app
