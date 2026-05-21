from __future__ import annotations

import logging
import sqlite3

from app.bootstrap.config import AppConfig
from app.bootstrap.container import build_container


def test_container_quarantines_invalid_state_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLEX_MUSIC_PLAYER_PLAYBACK_BACKEND", "fake")
    config = AppConfig(
        app_name="PlexMusicPlayer",
        app_author="yaymp",
        environment="test",
        log_level="INFO",
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        log_dir=tmp_path / "logs",
    )
    config.ensure_directories()
    config.settings_file.write_text("[]", encoding="utf-8")
    config.auth_session_file.write_text('{"broken": true}', encoding="utf-8")
    config.library_cache_db_file.write_text("not sqlite", encoding="utf-8")
    logger = logging.getLogger("yaymp-test-startup-recovery")

    container = build_container(config, logger)

    assert container.services.auth_service.current_session() is None
    assert list(config.config_dir.glob("settings.json.invalid-*"))
    assert list(config.data_dir.glob("auth_session.json.invalid-*"))
    assert list(config.cache_dir.glob("library_cache.sqlite3.invalid-*"))
    with sqlite3.connect(config.library_cache_db_file) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
    assert {"recent_searches", "tracks", "artwork"} <= table_names
