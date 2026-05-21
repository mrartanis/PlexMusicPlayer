from __future__ import annotations

from dataclasses import dataclass

from app.domain.playlist import Playlist
from app.domain.track import Track


@dataclass(frozen=True, slots=True)
class Album:
    id: str
    title: str
    artists: tuple[str, ...] = ()
    artist_ids: tuple[str, ...] = ()
    is_liked: bool = False
    release_type: str | None = None
    year: int | None = None
    track_count: int | None = None
    artwork_ref: str | None = None


@dataclass(frozen=True, slots=True)
class Artist:
    id: str
    name: str
    artwork_ref: str | None = None
    is_liked: bool = False


@dataclass(frozen=True, slots=True)
class CatalogSearchResults:
    tracks: tuple[Track, ...] = ()
    albums: tuple[Album, ...] = ()
    singles: tuple[Album, ...] = ()
    compilations: tuple[Album, ...] = ()
    artists: tuple[Artist, ...] = ()
    playlists: tuple[Playlist, ...] = ()
