from __future__ import annotations

from dataclasses import replace

from app.domain import LibraryCacheRepo, Track


def merge_cached_liked_state(
    track: Track,
    cache_repo: LibraryCacheRepo | None,
    *,
    user_id: str | None = None,
) -> Track:
    if cache_repo is None or track.is_liked:
        return track

    if user_id is not None:
        liked_tracks = cache_repo.load_liked_track_ids(user_id)
        if liked_tracks is not None:
            return replace(
                track,
                is_liked=_normalize_track_id(track.id) in liked_tracks.track_ids,
            )

    cached_track = cache_repo.load_track_metadata(track.id)
    if cached_track is None or not cached_track.is_liked:
        return track
    return replace(track, is_liked=True)


def merge_cached_liked_states(
    tracks: tuple[Track, ...],
    cache_repo: LibraryCacheRepo | None,
    *,
    user_id: str | None = None,
) -> tuple[Track, ...]:
    return tuple(
        merge_cached_liked_state(track, cache_repo, user_id=user_id) for track in tracks
    )


def _normalize_track_id(track_id: str) -> str:
    raw_track_id = str(track_id)
    base_id, separator, album_id = raw_track_id.partition(":")
    if separator and base_id.isdigit() and album_id.isdigit():
        return base_id
    return raw_track_id
