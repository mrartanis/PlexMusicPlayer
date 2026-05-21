from __future__ import annotations

from app.domain import Track


def build_demo_tracks() -> tuple[Track, ...]:
    return (
        Track(
            id="demo-1",
            title="Starter Signal",
            artists=("Plex Music Player",),
            album_title="Bootstrap Sessions",
            duration_ms=185_000,
            stream_ref="demo://starter-signal",
        ),
        Track(
            id="demo-2",
            title="Queue Runner",
            artists=("Plex Music Player", "Prototype"),
            album_title="Bootstrap Sessions",
            duration_ms=204_000,
            stream_ref="demo://queue-runner",
        ),
        Track(
            id="demo-3",
            title="Offline Groove",
            artists=("Local Backend",),
            album_title="Bootstrap Sessions",
            duration_ms=231_000,
            stream_ref="demo://offline-groove",
        ),
    )
