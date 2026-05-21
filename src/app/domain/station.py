from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.track import Track


@dataclass(frozen=True, slots=True)
class Station:
    id: str
    title: str
    description: str | None = None
    icon_ref: str | None = None


@dataclass(frozen=True, slots=True)
class StationTrackBatch:
    station_id: str
    batch_id: str | None
    tracks: tuple[Track, ...]


class RadioFeedbackType(str, Enum):
    RADIO_STARTED = "radioStarted"
    TRACK_STARTED = "trackStarted"
    TRACK_FINISHED = "trackFinished"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class RadioSession:
    station_id: str
    session_id: str
    batch_id: str | None
    feedback_from: str
    queue_anchor_track_id: str | None
    tracks: tuple[Track, ...]
