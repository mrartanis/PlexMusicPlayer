from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.domain.track import Track


class PlaybackStatus(str, Enum):
    STOPPED = "stopped"
    PAUSED = "paused"
    PLAYING = "playing"
    BUFFERING = "buffering"


class RepeatMode(str, Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class QueueItem:
    track: Track
    source_type: str | None = None
    source_id: str | None = None
    source_index: int | None = None
    station_batch_id: str | None = None
    radio_session_id: str | None = None
    radio_origin: str | None = None
    radio_queue_anchor_track_id: str | None = None


@dataclass(frozen=True, slots=True)
class PlayEventReport:
    track_id: str
    from_: str
    play_id: str
    timestamp: str
    start_timestamp: str
    add_tracks_to_player_time: str
    track_length_seconds: float
    total_played_seconds: float
    start_position_seconds: float
    end_position_seconds: float
    context: str
    context_item: str
    album_id: str | None = None
    playlist_id: str | None = None
    radio_session_id: str | None = None
    batch_id: str | None = None
    change_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SavedPlaybackQueue:
    queue: tuple[QueueItem, ...] = ()
    active_index: int | None = None
    position_ms: int = 0


@dataclass(frozen=True, slots=True)
class WaveformState:
    buffered_position_ms: int | None = None
    waveform_bins: tuple[float, ...] = ()
    waveform_known_position_ms: int = 0
    waveform_mode: str = "plain"


@dataclass(frozen=True, slots=True)
class PlaybackState:
    status: PlaybackStatus = PlaybackStatus.STOPPED
    active_index: int | None = None
    position_ms: int = 0
    duration_ms: int | None = None
    volume: int = 100
    shuffle_enabled: bool = False
    repeat_mode: RepeatMode = RepeatMode.OFF
    audio_codec: str | None = None
    audio_bitrate: int | None = None
    waveform: WaveformState = field(default_factory=WaveformState)
