from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Track:
    id: str
    title: str
    artists: tuple[str, ...]
    version: str | None = None
    artist_ids: tuple[str, ...] = ()
    album_id: str | None = None
    album_title: str | None = None
    album_year: int | None = None
    duration_ms: int | None = None
    stream_ref: str | None = None
    stream_ref_cached_at: datetime | None = None
    artwork_ref: str | None = None
    accent_color: str | None = None
    waveform_bins: tuple[float, ...] = ()
    available: bool = True
    is_liked: bool = False


@dataclass(frozen=True, slots=True)
class LikedTrackIds:
    user_id: str
    revision: int
    track_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class LikedTrackSnapshot:
    user_id: str
    revision: int
    tracks: tuple[Track, ...]
