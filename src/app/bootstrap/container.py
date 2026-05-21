from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from app.application.auth_service import AuthService
from app.application.demo_library import build_demo_tracks
from app.application.library_service import LibraryService
from app.application.playback_service import PlaybackService
from app.application.search_service import SearchService
from app.application.settings_service import SettingsService
from app.bootstrap.config import AppConfig
from app.domain import (
    AuthSession,
    LibraryCacheRepo,
    MusicService,
    PlaybackStateRepo,
    SettingsRepo,
    Track,
)
from app.domain.errors import AuthError, PlaybackBackendError, StorageError
from app.infrastructure.persistence import (
    FileArtworkCache,
    FileAuthRepo,
    FileLibraryCacheRepo,
    FileSettingsRepo,
    SQLiteLibraryCacheRepo,
    SQLitePlaybackStateRepo,
    quarantine_state_file,
)
from app.infrastructure.playback.fake_playback_engine import FakePlaybackEngine
from app.infrastructure.playback.mpv_playback_engine import MpvPlaybackEngine
from app.infrastructure.playback.stream_proxy_service import StreamProxyService
from app.infrastructure.plex.plex_music_service import PlexMusicService


@dataclass(slots=True)
class AppServices:
    auth_service: AuthService
    settings_repo: SettingsRepo
    settings_service: SettingsService
    artwork_cache: FileArtworkCache
    library_service: LibraryService
    music_service: MusicService
    playback_engine: FakePlaybackEngine | MpvPlaybackEngine
    stream_proxy_service: StreamProxyService
    playback_service: PlaybackService
    search_service: SearchService
    demo_tracks: tuple[Track, ...]


@dataclass(slots=True)
class AppContainer:
    config: AppConfig
    logger: logging.Logger
    services: AppServices


def build_container(config: AppConfig, logger: logging.Logger) -> AppContainer:
    logger.debug("Building application container")
    settings_repo = _build_settings_repo(config, logger)
    settings_service = SettingsService(settings_repo=settings_repo, logger=logger)
    auth_service, restored_session = _build_auth_service(config, logger)
    music_service = PlexMusicService(
        logger=logger,
    )
    if restored_session is not None:
        try:
            logger.info(
                "Restoring Plex session for server=%s library=%s",
                restored_session.server_name,
                restored_session.music_section_title,
            )
            music_service.apply_auth_session(restored_session)
        except AuthError as exc:
            logger.warning("Failed to restore Plex session: %s", exc)
            auth_service.clear_session()
            music_service = PlexMusicService(logger=logger)
    library_cache_repo = _build_library_cache_repo(config, logger)
    playback_state_repo = _build_playback_state_repo(config, logger)
    artwork_cache = FileArtworkCache(cache_dir=config.artwork_cache_dir)
    search_service = SearchService(
        music_service=music_service,
        library_cache_repo=library_cache_repo,
        logger=logger,
    )
    library_service = LibraryService(
        music_service=music_service,
        library_cache_repo=library_cache_repo,
        logger=logger,
    )
    if restored_session is not None:
        logger.info("Skipping eager liked-track index refresh during startup")

    playback_engine = _build_playback_engine(logger)
    stream_proxy_service = StreamProxyService(
        logger=logger,
        library_cache_repo=library_cache_repo,
    )
    playback_service = PlaybackService(
        playback_engine=playback_engine,
        logger=logger,
        music_service=music_service,
        library_cache_repo=library_cache_repo,
        playback_state_repo=playback_state_repo,
        stream_proxy_service=stream_proxy_service,
        waveform_progress_enabled=settings_service.load_waveform_progress_enabled(),
    )
    demo_tracks = build_demo_tracks()
    playback_service.restore_saved_queue()
    playback_service.set_volume(settings_service.load_volume())
    return AppContainer(
        config=config,
        logger=logger,
        services=AppServices(
            auth_service=auth_service,
            settings_repo=settings_repo,
            settings_service=settings_service,
            artwork_cache=artwork_cache,
            library_service=library_service,
            music_service=music_service,
            playback_engine=playback_engine,
            stream_proxy_service=stream_proxy_service,
            playback_service=playback_service,
            search_service=search_service,
            demo_tracks=demo_tracks,
        ),
    )


def _build_settings_repo(config: AppConfig, logger: logging.Logger) -> SettingsRepo:
    settings_repo = FileSettingsRepo(file_path=config.settings_file)
    try:
        settings = settings_repo.load_settings()
    except StorageError as exc:
        logger.warning("Settings are not readable and defaults will be used: %s", exc)
        try:
            quarantine_state_file(config.settings_file, logger=logger, reason=str(exc))
        except StorageError as quarantine_exc:
            logger.warning("Failed to quarantine settings file: %s", quarantine_exc)
        return FileSettingsRepo(file_path=config.settings_file)
    logger.info("Loaded %s settings keys", len(settings))
    return settings_repo


def _build_auth_service(
    config: AppConfig,
    logger: logging.Logger,
) -> tuple[AuthService, AuthSession | None]:
    auth_service = AuthService(
        auth_repo=FileAuthRepo(file_path=config.auth_session_file),
        logger=logger,
    )
    try:
        return auth_service, auth_service.restore_session()
    except StorageError as exc:
        logger.warning("Saved auth session is not readable and will be ignored: %s", exc)
        try:
            quarantine_state_file(config.auth_session_file, logger=logger, reason=str(exc))
        except StorageError as quarantine_exc:
            logger.warning("Failed to quarantine auth session file: %s", quarantine_exc)
        return AuthService(
            auth_repo=FileAuthRepo(file_path=config.auth_session_file),
            logger=logger,
        ), None


def _build_library_cache_repo(config: AppConfig, logger: logging.Logger) -> LibraryCacheRepo:
    try:
        repo = SQLiteLibraryCacheRepo(db_path=config.library_cache_db_file)
    except StorageError as exc:
        logger.warning("SQLite library cache is not usable: %s", exc)
        try:
            quarantine_state_file(config.library_cache_db_file, logger=logger, reason=str(exc))
            repo = SQLiteLibraryCacheRepo(db_path=config.library_cache_db_file)
        except StorageError as recovery_exc:
            logger.warning("Falling back to JSON library cache: %s", recovery_exc)
            return FileLibraryCacheRepo(file_path=config.library_cache_file)
    logger.info("Using SQLite library cache: %s", config.library_cache_db_file)
    return repo


def _build_playback_state_repo(
    config: AppConfig,
    logger: logging.Logger,
) -> PlaybackStateRepo | None:
    try:
        repo = SQLitePlaybackStateRepo(db_path=config.library_cache_db_file)
    except StorageError as exc:
        logger.warning("Playback queue state will not be persisted: %s", exc)
        return None
    return repo


def _build_playback_engine(logger: logging.Logger) -> FakePlaybackEngine | MpvPlaybackEngine:
    backend_name = os.getenv("PLEX_MUSIC_PLAYER_PLAYBACK_BACKEND", "mpv").lower()
    if backend_name != "mpv":
        logger.info("Using fake playback backend")
        return FakePlaybackEngine()

    try:
        engine = MpvPlaybackEngine(logger=logger)
        logger.info("Using MPV playback backend: %s", engine.library_path)
        return engine
    except PlaybackBackendError as exc:
        logger.warning("Falling back to fake playback backend: %s", exc)
        return FakePlaybackEngine()
