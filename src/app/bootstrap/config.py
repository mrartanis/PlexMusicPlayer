from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_name: str
    app_author: str
    environment: str
    log_level: str
    config_dir: Path
    data_dir: Path
    cache_dir: Path
    log_dir: Path

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.json"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "plex_music_player.log"

    @property
    def auth_session_file(self) -> Path:
        return self.data_dir / "auth_session.json"

    @property
    def recent_searches_file(self) -> Path:
        return self.library_cache_file

    @property
    def library_cache_file(self) -> Path:
        return self.cache_dir / "library_cache.json"

    @property
    def library_cache_db_file(self) -> Path:
        return self.cache_dir / "library_cache.sqlite3"

    @property
    def artwork_cache_dir(self) -> Path:
        return self.cache_dir / "artwork"

    def ensure_directories(self) -> None:
        for path in (self.config_dir, self.data_dir, self.cache_dir, self.log_dir):
            path.mkdir(parents=True, exist_ok=True)


def _resolve_path_override(value: str | None, fallback: Path) -> Path:
    if value:
        return Path(value).expanduser()
    return fallback


def load_config() -> AppConfig:
    app_name = os.getenv("PLEX_MUSIC_PLAYER_APP_NAME", "PlexMusicPlayer")
    app_author = os.getenv("PLEX_MUSIC_PLAYER_APP_AUTHOR", "PlexMusicPlayer")
    environment = os.getenv("PLEX_MUSIC_PLAYER_ENV", "development")
    log_level = os.getenv("PLEX_MUSIC_PLAYER_LOG_LEVEL", "INFO").upper()

    dirs = PlatformDirs(appname=app_name, appauthor=app_author, roaming=False, ensure_exists=False)
    return AppConfig(
        app_name=app_name,
        app_author=app_author,
        environment=environment,
        log_level=log_level,
        config_dir=_resolve_path_override(
            os.getenv("PLEX_MUSIC_PLAYER_CONFIG_DIR"),
            Path(dirs.user_config_dir),
        ),
        data_dir=_resolve_path_override(
            os.getenv("PLEX_MUSIC_PLAYER_DATA_DIR"),
            Path(dirs.user_data_dir),
        ),
        cache_dir=_resolve_path_override(
            os.getenv("PLEX_MUSIC_PLAYER_CACHE_DIR"),
            Path(dirs.user_cache_dir),
        ),
        log_dir=_resolve_path_override(
            os.getenv("PLEX_MUSIC_PLAYER_LOG_DIR"),
            Path(dirs.user_log_dir),
        ),
    )
