from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Playlist:
    id: str
    title: str
    owner_id: str | None = None
    owner_name: str | None = None
    description: str | None = None
    track_count: int | None = None
    artwork_ref: str | None = None
    is_generated: bool = False
    is_liked: bool = False
