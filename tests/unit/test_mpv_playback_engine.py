from __future__ import annotations

import pytest

from app.domain import PlaybackBackendError
from app.infrastructure.playback import mpv_playback_engine
from app.infrastructure.playback.mpv_playback_engine import MpvPlaybackEngine


class MpvModuleStub:
    def __init__(self, player) -> None:
        self._player = player

    def MPV(self):
        return self._player


class PlayerStub:
    def __init__(
        self,
        *,
        fail_time_pos: bool = False,
    ) -> None:
        self.fail_time_pos = fail_time_pos
        self.string_command_calls = []
        self.event_callbacks = {}
        self.property_observers = {}
        self.volume = 100

    def string_command(self, name, *args):
        self.string_command_calls.append((name, *args))
        if name == "set" and self.fail_time_pos:
            raise RuntimeError("time-pos rejected")

    def event_callback(self, *event_types):
        def decorator(callback):
            for event_type in event_types:
                self.event_callbacks[event_type] = callback
            return callback

        return decorator

    def property_observer(self, name):
        def decorator(callback):
            self.property_observers[name] = callback
            return callback

        return decorator


def build_engine(monkeypatch: pytest.MonkeyPatch, player: PlayerStub) -> MpvPlaybackEngine:
    monkeypatch.setattr(
        mpv_playback_engine,
        "ensure_mpv_available",
        lambda: (MpvModuleStub(player), "/tmp/libmpv.dylib"),
    )
    return MpvPlaybackEngine()


def test_mpv_seek_sets_time_pos(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerStub()
    engine = build_engine(monkeypatch, player)

    engine.seek(12_000)

    assert player.string_command_calls[-1] == ("set", "time-pos", "12")


def test_mpv_seek_reports_time_pos_error(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerStub(fail_time_pos=True)
    engine = build_engine(monkeypatch, player)

    with pytest.raises(PlaybackBackendError, match="time-pos rejected"):
        engine.seek(12_000)


def test_mpv_ready_events_notify_seek_callback(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerStub()
    engine = build_engine(monkeypatch, player)
    calls = []
    engine.on_ready_for_seek(lambda: calls.append("ready"))

    player.event_callbacks["file-loaded"]({})
    player.event_callbacks["playback-restart"]({})
    player.property_observers["seekable"]("seekable", False)
    player.property_observers["seekable"]("seekable", True)

    assert calls == ["ready", "ready", "ready"]


def test_mpv_registers_cache_property_observers(monkeypatch: pytest.MonkeyPatch) -> None:
    player = PlayerStub()
    build_engine(monkeypatch, player)

    assert "cache-buffering-state" in player.property_observers
    assert "paused-for-cache" in player.property_observers
