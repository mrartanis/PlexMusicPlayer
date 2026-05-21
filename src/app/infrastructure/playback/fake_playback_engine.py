from __future__ import annotations

from app.domain import PlaybackEngine, PlaybackState, PlaybackStatus, Track


class FakePlaybackEngine(PlaybackEngine):
    def __init__(self) -> None:
        self._current_track: Track | None = None
        self._state = PlaybackState()
        self._ready_for_seek_callback = None

    def load(self, track: Track, *, stream_ref: str) -> None:
        del stream_ref
        self._current_track = track
        self._state = PlaybackState(
            status=PlaybackStatus.PAUSED,
            position_ms=0,
            duration_ms=track.duration_ms,
            volume=self._state.volume,
            audio_codec="fake",
            audio_bitrate=None,
        )

    def play(self) -> None:
        self._state = PlaybackState(
            status=PlaybackStatus.PLAYING,
            position_ms=self._state.position_ms,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
            audio_codec=self._state.audio_codec,
            audio_bitrate=self._state.audio_bitrate,
        )

    def pause(self) -> None:
        self._state = PlaybackState(
            status=PlaybackStatus.PAUSED,
            position_ms=self._state.position_ms,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
            audio_codec=self._state.audio_codec,
            audio_bitrate=self._state.audio_bitrate,
        )

    def stop(self) -> None:
        self._state = PlaybackState(
            status=PlaybackStatus.STOPPED,
            position_ms=0,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
            audio_codec=self._state.audio_codec,
            audio_bitrate=self._state.audio_bitrate,
        )

    def seek(self, position_ms: int) -> None:
        max_position = self._state.duration_ms or position_ms
        bounded_position = max(0, min(position_ms, max_position))
        self._state = PlaybackState(
            status=self._state.status,
            position_ms=bounded_position,
            duration_ms=self._state.duration_ms,
            volume=self._state.volume,
            audio_codec=self._state.audio_codec,
            audio_bitrate=self._state.audio_bitrate,
        )

    def set_volume(self, volume: int) -> None:
        self._state = PlaybackState(
            status=self._state.status,
            position_ms=self._state.position_ms,
            duration_ms=self._state.duration_ms,
            volume=max(0, min(100, volume)),
            audio_codec=self._state.audio_codec,
            audio_bitrate=self._state.audio_bitrate,
        )

    def get_state(self) -> PlaybackState:
        return self._state

    def on_ready_for_seek(self, callback) -> None:
        self._ready_for_seek_callback = callback

    def emit_ready_for_seek(self) -> None:
        if self._ready_for_seek_callback is not None:
            self._ready_for_seek_callback()
