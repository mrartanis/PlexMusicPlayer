from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QWidget

from app.application.playback_service import PlaybackSnapshot
from app.domain import PlaybackState, PlaybackStatus, QueueItem, RepeatMode, Track
from app.infrastructure.persistence.file_artwork_cache import FileArtworkCache
from app.presentation.qt.system_media import (
    LinuxMprisIntegration,
    MacOSSystemMediaIntegration,
    WindowsSystemMediaIntegration,
    _repeat_mode_from_windows,
    _timedelta_like_to_milliseconds,
    _windows_playback_status,
    _windows_repeat_mode,
    build_system_media_integration,
)


class StubPlaybackController:
    def play(self) -> None:
        pass

    def pause(self) -> None:
        pass

    def next(self) -> None:
        pass

    def previous(self) -> None:
        pass

    def seek(self, position_ms: int) -> None:
        self.position_ms = position_ms


class StubLogger:
    def debug(self, message: str, *args: object) -> None:
        del message, args

    def info(self, message: str, *args: object) -> None:
        del message, args

    def warning(self, message: str, *args: object) -> None:
        del message, args

    def error(self, message: str, *args: object) -> None:
        del message, args

    def exception(self, message: str, *args: object) -> None:
        del message, args


def test_build_system_media_integration_selects_platform(monkeypatch, qtbot, tmp_path) -> None:
    controller = StubPlaybackController()
    artwork_cache = FileArtworkCache(cache_dir=tmp_path)
    window = QWidget()
    qtbot.addWidget(window)
    logger = StubLogger()

    monkeypatch.setattr("app.presentation.qt.system_media.sys.platform", "darwin")
    assert isinstance(
        build_system_media_integration(
            playback_controller=controller,
            artwork_cache=artwork_cache,
            window=window,
            logger=logger,
        ),
        MacOSSystemMediaIntegration,
    )

    monkeypatch.setattr("app.presentation.qt.system_media.sys.platform", "linux")
    assert isinstance(
        build_system_media_integration(
            playback_controller=controller,
            artwork_cache=artwork_cache,
            window=window,
            logger=logger,
        ),
        LinuxMprisIntegration,
    )

    monkeypatch.setattr("app.presentation.qt.system_media.sys.platform", "win32")
    assert isinstance(
        build_system_media_integration(
            playback_controller=controller,
            artwork_cache=artwork_cache,
            window=window,
            logger=logger,
        ),
        WindowsSystemMediaIntegration,
    )


def test_linux_mpris_integration_builds_metadata_with_cached_art(qtbot, tmp_path) -> None:
    controller = StubPlaybackController()
    artwork_cache = FileArtworkCache(cache_dir=tmp_path)
    window = QWidget()
    qtbot.addWidget(window)
    integration = LinuxMprisIntegration(
        playback_controller=controller,
        artwork_cache=artwork_cache,
        window=window,
        logger=StubLogger(),
    )
    artwork_url = artwork_cache.normalize_url("//example.test/cover/%%") or ""
    cache_path = artwork_cache.cache_path_for_url(artwork_url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"cover")
    track = Track(
        id="track-1",
        title="Signal",
        artists=("Artist",),
        album_title="Album",
        duration_ms=180_000,
        artwork_ref="//example.test/cover/%%",
    )
    snapshot = PlaybackSnapshot(
        queue=(QueueItem(track=track),),
        state=PlaybackState(
            status=PlaybackStatus.PLAYING,
            position_ms=12_000,
            volume=75,
            shuffle_enabled=True,
            repeat_mode=RepeatMode.ALL,
        ),
        current_item=QueueItem(track=track),
    )

    integration.update_snapshot(snapshot)

    metadata = integration._state.metadata or {}
    assert integration._state.playback_status == "Playing"
    assert integration._state.loop_status == "Playlist"
    assert integration._state.position_us == 12_000_000
    assert integration._state.volume == 0.75
    assert metadata["xesam:title"] == "Signal"
    assert metadata["xesam:album"] == "Album"
    assert metadata["xesam:artist"] == ["Artist"]
    assert metadata["mpris:length"] == 180_000_000
    assert metadata["mpris:artUrl"] == Path(cache_path).as_uri()


class StubWindowsPlaybackStatus:
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class StubWindowsRepeatMode:
    TRACK = "track"
    LIST = "list"
    NONE = "none"


class TimedeltaLike:
    def __init__(self, seconds: float) -> None:
        self._seconds = seconds

    def total_seconds(self) -> float:
        return self._seconds


def test_windows_playback_status_mapping() -> None:
    assert _windows_playback_status(PlaybackStatus.PLAYING, StubWindowsPlaybackStatus) == "playing"
    assert _windows_playback_status(PlaybackStatus.PAUSED, StubWindowsPlaybackStatus) == "paused"
    assert _windows_playback_status(PlaybackStatus.STOPPED, StubWindowsPlaybackStatus) == "stopped"


def test_windows_repeat_mode_mapping() -> None:
    assert _windows_repeat_mode(RepeatMode.ONE, StubWindowsRepeatMode) == "track"
    assert _windows_repeat_mode(RepeatMode.ALL, StubWindowsRepeatMode) == "list"
    assert _windows_repeat_mode(RepeatMode.OFF, StubWindowsRepeatMode) == "none"
    assert _repeat_mode_from_windows("track", StubWindowsRepeatMode) == RepeatMode.ONE
    assert _repeat_mode_from_windows("list", StubWindowsRepeatMode) == RepeatMode.ALL
    assert _repeat_mode_from_windows("none", StubWindowsRepeatMode) == RepeatMode.OFF


def test_timedelta_like_to_milliseconds() -> None:
    assert _timedelta_like_to_milliseconds(TimedeltaLike(12.345)) == 12_345
    assert _timedelta_like_to_milliseconds(object()) == 0
