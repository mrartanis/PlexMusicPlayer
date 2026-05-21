from __future__ import annotations

from app.domain import Track


def display_track_title(track: Track) -> str:
    if not track.version:
        return track.title
    return f"{track.title} · {track.version}"
