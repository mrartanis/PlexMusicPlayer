from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Sequence

from PySide6.QtWidgets import QApplication

from app.bootstrap.config import AppConfig, load_config
from app.bootstrap.container import AppContainer, build_container
from app.presentation.qt.app import create_qt_application
from app.presentation.qt.main_window import MainWindow


@dataclass(slots=True)
class StartupContext:
    config: AppConfig
    logger: logging.Logger
    container: AppContainer
    qt_app: QApplication
    main_window: MainWindow


def initialize_logging(config: AppConfig) -> logging.Logger:
    config.ensure_directories()

    logger = logging.getLogger("plex_music_player")
    logger.setLevel(getattr(logging, config.log_level, logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if not logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        file_handler = logging.FileHandler(config.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.debug("Logging initialized with file %s", config.log_file)
    return logger


def build_startup_context(
    argv: Sequence[str] | None = None,
    *,
    existing_qt_app: QApplication | None = None,
) -> StartupContext:
    config = load_config()
    logger = initialize_logging(config)
    logger.info("Starting application bootstrap")
    logger.info("Resolved config directory: %s", config.config_dir)
    logger.info("Resolved data directory: %s", config.data_dir)
    logger.info("Resolved cache directory: %s", config.cache_dir)
    logger.info("Resolved log file: %s", config.log_file)
    logger.info("Resolved auth session file: %s", config.auth_session_file)
    logger.info("Resolved settings file: %s", config.settings_file)

    container = build_container(config, logger)
    qt_app = existing_qt_app or create_qt_application(argv or sys.argv, config)
    main_window = MainWindow(container=container)
    logger.info("Main window constructed")

    return StartupContext(
        config=config,
        logger=logger,
        container=container,
        qt_app=qt_app,
        main_window=main_window,
    )


def run(argv: Sequence[str] | None = None) -> int:
    context = build_startup_context(argv)
    context.main_window.show()
    context.logger.info("Entering Qt event loop")
    return context.qt_app.exec()
